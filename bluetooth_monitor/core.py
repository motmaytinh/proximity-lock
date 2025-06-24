import asyncio
import time
import subprocess
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    from bleak import BleakScanner, BleakClient
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

logger = logging.getLogger(__name__)

class BleakBluetoothDetector:
    def __init__(self, target_devices: Optional[List[str]] = None, scan_duration: int = 10, log_level: str = "INFO"):
        self.target_devices = target_devices or []
        self.scan_duration = scan_duration
        self.device_history: Dict = {}
        self.discovered_devices: Dict[str, BLEDevice] = {}

        # Set up logging with custom level
        self.set_log_level(log_level)

    def set_log_level(self, level: str):
        """
        Set the logging level for the detector.
        DEBUG < INFO < WARNING < ERROR < CRITICAL

        Args:
            level: Logging level as string. Options:
                - "DEBUG": Show all messages (debug, info, warning, error, critical)
                - "INFO": Show info, warning, error, critical
                - "WARNING": Show warning, error, critical
                - "ERROR": Show error, critical only
                - "CRITICAL": Show critical only
                - "OFF" or "DISABLED": Disable all logging
        """
        level = level.upper()

        if level in ["OFF", "DISABLED"]:
            logger.setLevel(logging.CRITICAL + 1)  # Higher than CRITICAL to disable all
        else:
            log_levels = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL
            }

            if level in log_levels:
                logging.basicConfig(level=log_levels[level])
                logger.setLevel(log_levels[level])
            else:
                # Default to INFO if invalid level provided
                logging.basicConfig(level=logging.INFO)
                logger.setLevel(logging.INFO)
                logger.warning(f"Invalid log level '{level}', defaulting to INFO")

    def _log_debug(self, message: str):
        """Log debug message"""
        logger.debug(message)

    def _log_info(self, message: str):
        """Log info message"""
        logger.info(message)

    def _log_warning(self, message: str):
        """Log warning message"""
        logger.warning(message)

    def _log_error(self, message: str):
        """Log error message"""
        logger.error(message)

    def _log_critical(self, message: str):
        """Log critical message"""
        logger.critical(message)

    async def scan_ble_devices(self, target_only: bool = False) -> List[Tuple[str, str, int, Dict]]:
        if not BLEAK_AVAILABLE:
            self._log_warning("Bleak not available, falling back to subprocess methods")
            return self.scan_devices_subprocess(target_only)

        try:
            self._log_info("Scanning for BLE devices...")
            devices = []
            found_targets = set()
            scanner = None

            def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
                nonlocal devices, found_targets, scanner
                mac = device.address
                name = device.name or advertisement_data.local_name or "Unknown"
                rssi = advertisement_data.rssi
                self.discovered_devices[mac] = device

                ad_data = {
                    'manufacturer_data': advertisement_data.manufacturer_data,
                    'service_data': advertisement_data.service_data,
                    'service_uuids': advertisement_data.service_uuids,
                    'tx_power': advertisement_data.tx_power
                }

                devices.append((mac, name, rssi, ad_data))
                self._log_info(f"Found BLE: {name} ({mac}) - RSSI: {rssi} dBm")

                if target_only and self.target_devices:
                    for target in self.target_devices:
                        if (target.upper() in mac.upper() or target.lower() in name.lower()):
                            found_targets.add(target)
                            self._log_info(f"Target device found: {name} ({mac})")
                            if len(found_targets) >= len(self.target_devices) or len(found_targets) == 1:
                                self._log_info("Target device(s) found, stopping scan early")
                                asyncio.create_task(self._stop_scanner_delayed(scanner))
                                return

            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()

            if target_only and self.target_devices:
                for _ in range(self.scan_duration * 2):
                    await asyncio.sleep(0.5)
                    if found_targets:
                        break
            else:
                await asyncio.sleep(self.scan_duration)

            await scanner.stop()

            # In target_only mode, filter and return only matched targets
            if target_only and self.target_devices:
                filtered_devices = []
                for target in self.target_devices:
                    for mac, name, rssi, ad_data in devices:
                        if (target.upper() in mac.upper() or target.lower() in name.lower()):
                            filtered_devices.append((mac, name, rssi, ad_data))
                            break  # Only first match for this target
                return filtered_devices

            return devices

        except Exception as e:
            self._log_error(f"Error during BLE scan: {e}")
            return []

    async def _stop_scanner_delayed(self, scanner):
        await asyncio.sleep(0.1)
        if scanner:
            try:
                await scanner.stop()
            except Exception as e:
                self._log_warning(f"Failed to stop scanner: {e}")

    def scan_devices_subprocess(self, target_only: bool = False) -> List[Tuple[str, str, int, Dict]]:
        # Same subprocess fallback logic as original, omitted here for brevity
        return []

    def get_rssi_subprocess(self, mac_address: str) -> Optional[int]:
        try:
            result = subprocess.run(f"hcitool rssi {mac_address}", shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                match = re.search(r'RSSI return value: (-?\d+)', result.stdout)
                if match:
                    return int(match.group(1))
            return None
        except Exception:
            return None

    async def get_device_info(self, mac_address: str) -> Optional[Dict]:
        if not BLEAK_AVAILABLE or mac_address not in self.discovered_devices:
            return None

        try:
            device = self.discovered_devices[mac_address]
            async with BleakClient(device) as client:
                if client.is_connected:
                    services = client.services
                    info = {
                        'connected': True,
                        'services': [str(s.uuid) for s in services],
                        'service_count': len(services)
                    }

                    DEVICE_INFO_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
                    if DEVICE_INFO_UUID in info['services']:
                        try:
                            mfg = await client.read_gatt_char("00002a29-0000-1000-8000-00805f9b34fb")
                            info['manufacturer'] = mfg.decode('utf-8')
                        except: pass

                        try:
                            model = await client.read_gatt_char("00002a24-0000-1000-8000-00805f9b34fb")
                            info['model'] = model.decode('utf-8')
                        except: pass

                    return info
        except Exception as e:
            self._log_warning(f"Failed to connect to {mac_address}: {e}")
            return None

    def estimate_distance(self, rssi: int, tx_power: Optional[int] = None) -> Optional[float]:
        if rssi is None or rssi == 0:
            return None
        tx_power = tx_power or -59
        n = 2.0
        return round(pow(10, (tx_power - rssi) / (10 * n)), 2)

    def classify_proximity(self, distance: Optional[float]) -> str:
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

    def set_logging(self, enable: bool):
        """Enable or disable logging at runtime"""
        self.enable_logging = enable
        if enable:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.CRITICAL)
