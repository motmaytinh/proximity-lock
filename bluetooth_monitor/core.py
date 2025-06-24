import asyncio
import time
import subprocess
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

try:
    from bleak import BleakScanner, BleakClient
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    print("Bleak library not found. Bluetooth functionalities will be limited.")

# Set up logging for the module
logger = logging.getLogger(__name__)

# Define standard BLE UUIDs
DEVICE_INFO_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_NAME_CHARACTERISTIC_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_CHARACTERISTIC_UUID = "00002a24-0000-1000-8000-00805f9b34fb"

class BluetoothDetector:
    """
    A class to detect and manage Bluetooth Low Energy (BLE) devices using Bleak.
    It provides functionalities for scanning, retrieving device information,
    estimating distance, and classifying proximity.
    """

    def __init__(self, target_devices: Optional[List[str]] = None,
                 scan_duration: int = 10,
                 log_level: str = "INFO"):
        """
        Initializes the BluetoothDetector.

        Args:
            target_devices (Optional[List[str]]): A list of MAC addresses or names
                                                  of target devices to look for.
            scan_duration (int): The duration (in seconds) for BLE scans.
            log_level (str): The logging level (e.g., "INFO", "DEBUG", "WARNING").
        """
        self.target_devices = [td.upper() for td in target_devices] if target_devices else []
        self.scan_duration = scan_duration
        self.discovered_devices: Dict[str, BLEDevice] = {}
        self._setup_logging(log_level)

    def _setup_logging(self, level: str):
        """
        Configures the logging for the detector.
        """
        level = level.upper()
        if level in ["OFF", "DISABLED"]:
            logger.disabled = True
            return

        log_levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        logger.setLevel(log_levels.get(level, logging.INFO))

        # Add a stream handler if not already present
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

    def set_log_level(self, level: str):
        """
        Dynamically changes the logging level.
        """
        self._setup_logging(level)
        logger.info(f"Logging level set to {level.upper()}")

    def is_target_device(self, mac_address: str, name: str) -> bool:
        """
        Checks if a device is one of the specified target devices.

        Args:
            mac_address (str): The MAC address of the device.
            name (str): The name of the device.

        Returns:
            bool: True if the device is a target device, False otherwise.
        """
        return any(target in mac_address.upper() or target.lower() in name.lower()
                   for target in self.target_devices)

    async def scan_ble_devices(self, target_only: bool = False) -> List[Tuple[str, str, int, Dict]]:
        """
        Scans for Bluetooth Low Energy (BLE) devices.

        Args:
            target_only (bool): If True, the scan stops early once all target devices
                                (or at least one if target_devices is empty) are found.

        Returns:
            List[Tuple[str, str, int, Dict]]: A list of tuples, each containing:
                (mac_address, device_name, rssi, advertisement_data).
        """
        if not BLEAK_AVAILABLE:
            logger.warning("Bleak library not available. Falling back to subprocess methods (if implemented).")
            # Consider implementing a fallback or raising an error if no subprocess method exists
            raise NotImplementedError("Bleak is not available and subprocess scan is not implemented.")

        logger.info(f"Starting BLE scan for {self.scan_duration} seconds...")
        devices_found: List[Tuple[str, str, int, Dict]] = []
        found_target_macs = set()
        stop_scan_event = asyncio.Event()

        def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
            mac = device.address
            name = device.name or advertisement_data.local_name or "Unknown"
            rssi = advertisement_data.rssi

            self.discovered_devices[mac] = device  # Store the Bleak device object

            ad_data = {
                'manufacturer_data': advertisement_data.manufacturer_data,
                'service_data': advertisement_data.service_data,
                'service_uuids': advertisement_data.service_uuids,
                'tx_power': advertisement_data.tx_power
            }

            devices_found.append((mac, name, rssi, ad_data))
            logger.debug(f"Discovered: {name} ({mac}) - RSSI: {rssi} dBm")

            if target_only and self.target_devices:
                if self.is_target_device(mac, name):
                    found_target_macs.add(mac)
                    logger.info(f"Target device found: {name} ({mac})")
                    if len(found_target_macs) == len(self.target_devices) or not self.target_devices:
                        # If all targets found or if there are no specific targets and one is found
                        stop_scan_event.set()
            elif target_only and not self.target_devices: # If target_only is true but no specific targets, stop on first
                stop_scan_event.set()


        scanner = BleakScanner(detection_callback=detection_callback)

        try:
            await scanner.start()
            if target_only:
                # Wait until all targets are found or scan duration expires
                try:
                    await asyncio.wait_for(stop_scan_event.wait(), timeout=self.scan_duration)
                except asyncio.TimeoutError:
                    logger.info(f"Scan timed out after {self.scan_duration} seconds without finding all targets.")
            else:
                await asyncio.sleep(self.scan_duration)
            await scanner.stop()
        except Exception as e:
            logger.error(f"Error during BLE scan: {e}")
            await scanner.stop() # Ensure scanner is stopped even on error
            return []

        if target_only and self.target_devices:
            # Return only target devices if target_only was True and targets were specified
            return [d for d in devices_found if self.is_target_device(d[0], d[1])]
        return devices_found

    async def get_device_info(self, mac_address: str) -> Optional[Dict[str, Any]]:
        """
        Connects to a BLE device and retrieves its services and Device Information profile data.

        Args:
            mac_address (str): The MAC address of the device to connect to.

        Returns:
            Optional[Dict]: A dictionary containing device information, or None if connection fails.
        """
        if not BLEAK_AVAILABLE:
            logger.warning("Bleak library not available. Cannot get device info.")
            return None

        device = self.discovered_devices.get(mac_address)
        if not device:
            logger.warning(f"Device {mac_address} not found in discovered devices. Please scan first.")
            return None

        info: Dict[str, Any] = {'connected': False}
        try:
            async with BleakClient(device) as client:
                if client.is_connected:
                    info['connected'] = True
                    services = client.services
                    info['services'] = [str(s.uuid) for s in services]
                    info['service_count'] = len(services)

                    # Attempt to read Device Information service characteristics
                    if DEVICE_INFO_SERVICE_UUID in info['services']:
                        try:
                            mfg = await client.read_gatt_char(MANUFACTURER_NAME_CHARACTERISTIC_UUID)
                            info['manufacturer'] = mfg.decode('utf-8')
                        except Exception as e:
                            logger.debug(f"Failed to read manufacturer for {mac_address}: {e}")

                        try:
                            model = await client.read_gatt_char(MODEL_NUMBER_CHARACTERISTIC_UUID)
                            info['model'] = model.decode('utf-8')
                        except Exception as e:
                            logger.debug(f"Failed to read model for {mac_address}: {e}")
                else:
                    logger.warning(f"Could not establish connection to {mac_address}.")
        except Exception as e:
            logger.error(f"Error connecting to or reading info from {mac_address}: {e}")
            return None
        return info

    def estimate_distance(self, rssi: int, tx_power: Optional[int] = None) -> Optional[float]:
        """
        Estimates the distance to a BLE device based on its RSSI and Tx Power.

        Args:
            rssi (int): The Received Signal Strength Indicator (in dBm).
            tx_power (Optional[int]): The calibrated Tx Power at 1 meter (in dBm).
                                      Defaults to -59 dBm.

        Returns:
            Optional[float]: The estimated distance in meters, or None if RSSI is invalid.
        """
        if rssi is None or rssi == 0:
            return None
        # N is the environmental factor, typically between 2.0 and 4.0
        # 2.0 for free space, 3.0-4.0 for indoor environments
        n = 2.0
        tx_power = tx_power or -59
        distance = pow(10, (tx_power - rssi) / (10 * n))
        return round(distance, 2)

    def classify_proximity(self, distance: Optional[float]) -> str:
        """
        Classifies the proximity of a device based on its estimated distance.

        Args:
            distance (Optional[float]): The estimated distance to the device in meters.

        Returns:
            str: A string indicating the proximity (e.g., "Immediate", "Near", "Far", "Very Far", "Unknown").
        """
        if distance is None:
            return "Unknown"
        elif distance < 0.5:
            return "Immediate"
        elif distance < 2:
            return "Near"
        elif distance < 10:
            return "Far"
        else:
            return "Very Far"

    # Deprecated/Not Implemented Methods (Consider removing or fully implementing)
    def scan_devices_subprocess(self, target_only: bool = False) -> List[Tuple[str, str, int, Dict]]:
        """
        Placeholder for a subprocess-based BLE scan. Not implemented.
        """
        logger.error("Subprocess scan method is not implemented.")
        raise NotImplementedError("Subprocess scan is not implemented yet.")

    def get_rssi_subprocess(self, mac_address: str) -> Optional[int]:
        """
        Attempts to get RSSI using hcitool subprocess. (May require root/permissions)
        This method is less reliable and system-dependent compared to Bleak.
        """
        try:
            # This command is deprecated and might not work on all systems (e.g., newer Linux kernels)
            result = subprocess.run(f"hcitool rssi {mac_address}", shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                match = re.search(r'RSSI return value: (-?\d+)', result.stdout)
                if match:
                    rssi_value = int(match.group(1))
                    logger.debug(f"hcitool RSSI for {mac_address}: {rssi_value}")
                    return rssi_value
            logger.warning(f"Could not get RSSI for {mac_address} via hcitool. Output: {result.stderr.strip()}")
            return None
        except FileNotFoundError:
            logger.error("hcitool command not found. Please ensure BlueZ is installed and hcitool is in your PATH.")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"hcitool command timed out for {mac_address}.")
            return None
        except Exception as e:
            logger.error(f"Error getting RSSI for {mac_address} via hcitool: {e}")
            return None
