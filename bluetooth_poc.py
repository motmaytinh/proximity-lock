#!/usr/bin/env python3
"""
Bluetooth Low Energy Device Detection and Distance Estimation using Bleak
For Raspberry Pi Zero 2 W - Modern BLE approach
"""

import asyncio
import time
import subprocess
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Try to import bleak, fall back to subprocess methods if not available
try:
    from bleak import BleakScanner, BleakClient
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    print("Warning: Bleak not available, using subprocess methods only")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BleakBluetoothDetector:
    def __init__(self, target_devices: Optional[List[str]] = None, scan_duration: int = 10):
        """
        Initialize Bluetooth detector using Bleak for BLE devices

        Args:
            target_devices: List of target MAC addresses or device names to monitor
            scan_duration: Duration for each scan in seconds
        """
        self.target_devices = target_devices or []
        self.scan_duration = scan_duration
        self.device_history: Dict = {}
        self.discovered_devices: Dict[str, BLEDevice] = {}

    async def scan_ble_devices(self, target_only: bool = False) -> List[Tuple[str, str, int, Dict]]:
        """
        Scan for BLE devices using Bleak

        Args:
            target_only: If True, return early when target devices are found

        Returns:
            List of tuples: (mac_address, device_name, rssi, advertisement_data)
        """
        if not BLEAK_AVAILABLE:
            logger.warning("Bleak not available, falling back to subprocess methods")
            return self.scan_devices_subprocess(target_only)

        try:
            logger.info("Scanning for BLE devices...")
            devices = []
            found_targets = set()
            scanner = None

            # Create scanner with callback
            def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
                nonlocal devices, found_targets, scanner

                mac = device.address
                name = device.name or advertisement_data.local_name or "Unknown"
                rssi = advertisement_data.rssi

                # Store device for later use
                self.discovered_devices[mac] = device

                # Extract additional info from advertisement
                ad_data = {
                    'manufacturer_data': advertisement_data.manufacturer_data,
                    'service_data': advertisement_data.service_data,
                    'service_uuids': advertisement_data.service_uuids,
                    'tx_power': advertisement_data.tx_power
                }

                devices.append((mac, name, rssi, ad_data))
                logger.info(f"Found BLE: {name} ({mac}) - RSSI: {rssi} dBm")

                # Check if this is a target device and we should return early
                if target_only and self.target_devices:
                    for target in self.target_devices:
                        if (target.upper() in mac.upper() or
                            target.lower() in name.lower()):
                            found_targets.add(target)
                            logger.info(f"Target device found: {name} ({mac})")

                            # If we found all targets or this is the first target, stop scanning
                            if len(found_targets) >= len(self.target_devices) or len(found_targets) == 1:
                                logger.info("Target device(s) found, stopping scan early")
                                # Schedule scanner stop
                                asyncio.create_task(self._stop_scanner_delayed(scanner))
                                return

            # Start scanning
            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()

            # Wait for scan duration or until targets found
            if target_only and self.target_devices:
                # Check every 0.5 seconds if we found targets
                for i in range(self.scan_duration * 2):
                    await asyncio.sleep(0.5)
                    if found_targets:
                        logger.info(f"Found {len(found_targets)} target device(s), ending scan early")
                        break
            else:
                await asyncio.sleep(self.scan_duration)

            await scanner.stop()
            return devices

        except Exception as e:
            logger.error(f"Error during BLE scan: {e}")
            return []

    async def _stop_scanner_delayed(self, scanner):
        """Helper method to stop scanner with small delay"""
        await asyncio.sleep(0.1)  # Small delay to ensure callback completes
        if scanner:
            try:
                await scanner.stop()
            except Exception as e:
                logger.warning(f"Failed to stop scanner: {e}")

    def scan_devices_subprocess(self, target_only: bool = False) -> List[Tuple[str, str, int, Dict]]:
        """
        Fallback method using subprocess tools

        Args:
            target_only: If True, return early when target devices are found
        """
        try:
            logger.info("Using hcitool for device discovery...")
            devices = []
            found_targets = set()

            # Helper function to check if device is target
            def is_target_device(mac: str, name: str) -> bool:
                if not self.target_devices:
                    return False
                for target in self.target_devices:
                    if (target.upper() in mac.upper() or
                        target.lower() in name.lower()):
                        return True
                return False

            # Use hcitool lescan for BLE devices
            if target_only:
                logger.info("Scanning for target devices only...")

                # Start lescan in background
                lescan_process = subprocess.Popen(
                    ["hcitool", "lescan"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                start_time = time.time()
                max_scan_time = self.scan_duration

                try:
                    # Read output line by line with timeout
                    while time.time() - start_time < max_scan_time:
                        line = lescan_process.stdout.readline()
                        if line:
                            line = line.strip()
                            if line and not line.startswith('LE Scan'):
                                parts = line.split(' ', 1)
                                if len(parts) >= 2:
                                    mac = parts[0].strip()
                                    name = parts[1].strip() if len(parts) > 1 else "Unknown"

                                    if is_target_device(mac, name):
                                        rssi = self.get_rssi_subprocess(mac)
                                        devices.append((mac, name, rssi, {}))
                                        found_targets.add(mac)
                                        logger.info(f"Found target: {name} ({mac}) - RSSI: {rssi} dBm")

                                        # Return early if we found target(s)
                                        lescan_process.terminate()
                                        return devices

                        time.sleep(0.1)  # Small delay to prevent busy waiting

                finally:
                    lescan_process.terminate()
                    lescan_process.wait()

            # If target_only didn't find anything or not target_only, do full scan
            if not devices or not target_only:
                cmd = f"timeout {self.scan_duration + 5} hcitool lescan"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if line.strip() and not line.startswith('LE Scan'):
                            parts = line.strip().split(' ', 1)
                            if len(parts) >= 2:
                                mac = parts[0].strip()
                                name = parts[1].strip() if len(parts) > 1 else "Unknown"

                                # Skip if already found
                                if any(d[0] == mac for d in devices):
                                    continue

                                rssi = self.get_rssi_subprocess(mac)
                                devices.append((mac, name, rssi, {}))
                                logger.info(f"Found: {name} ({mac}) - RSSI: {rssi} dBm")

                                # Early return for target devices
                                if target_only and is_target_device(mac, name):
                                    logger.info("Target device found, returning early")
                                    return devices

                # Also try regular scan for classic Bluetooth
                cmd = f"timeout {self.scan_duration + 5} hcitool scan"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[1:]  # Skip header
                    for line in lines:
                        if line.strip():
                            parts = line.strip().split('\t', 1)
                            if len(parts) >= 2:
                                mac = parts[0].strip()
                                name = parts[1].strip()

                                # Skip if already found
                                if any(d[0] == mac for d in devices):
                                    continue

                                rssi = self.get_rssi_subprocess(mac)
                                devices.append((mac, name, rssi, {}))
                                logger.info(f"Found Classic: {name} ({mac}) - RSSI: {rssi} dBm")

                                # Early return for target devices
                                if target_only and is_target_device(mac, name):
                                    logger.info("Target device found, returning early")
                                    return devices

            return devices

        except Exception as e:
            logger.error(f"Subprocess scan failed: {e}")
            return []

    def get_rssi_subprocess(self, mac_address: str) -> Optional[int]:
        """
        Get RSSI using subprocess methods
        """
        try:
            # Try hcitool rssi
            cmd = f"hcitool rssi {mac_address}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                match = re.search(r'RSSI return value: (-?\d+)', result.stdout)
                if match:
                    return int(match.group(1))

            return None

        except Exception:
            return None

    async def get_device_info(self, mac_address: str) -> Optional[Dict]:
        """
        Get detailed device information using BLE connection
        """
        if not BLEAK_AVAILABLE:
            return None

        try:
            if mac_address not in self.discovered_devices:
                logger.warning(f"Device {mac_address} not in discovered devices")
                return None

            device = self.discovered_devices[mac_address]

            async with BleakClient(device) as client:
                if client.is_connected:
                    services = client.services

                    device_info = {
                        'connected': True,
                        'services': [str(service.uuid) for service in services],
                        'service_count': len(services)
                    }

                    # Try to read device information service if available
                    DEVICE_INFO_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
                    if DEVICE_INFO_UUID in [str(s.uuid) for s in services]:
                        # Read manufacturer name, model number, etc.
                        try:
                            manufacturer_char = "00002a29-0000-1000-8000-00805f9b34fb"
                            manufacturer = await client.read_gatt_char(manufacturer_char)
                            device_info['manufacturer'] = manufacturer.decode('utf-8')
                        except:
                            pass

                        try:
                            model_char = "00002a24-0000-1000-8000-00805f9b34fb"
                            model = await client.read_gatt_char(model_char)
                            device_info['model'] = model.decode('utf-8')
                        except:
                            pass

                    return device_info

        except Exception as e:
            logger.warning(f"Could not connect to {mac_address}: {e}")
            return None

    def estimate_distance(self, rssi: int, tx_power: Optional[int] = None) -> Optional[float]:
        """
        Estimate distance based on RSSI value

        Args:
            rssi: Received Signal Strength Indicator in dBm
            tx_power: Transmit power at 1 meter (from advertisement data or default -59 dBm)

        Returns:
            Estimated distance in meters
        """
        if rssi is None or rssi == 0:
            return None

        # Use tx_power from advertisement data if available, otherwise default
        tx_power = tx_power or -59

        if rssi > tx_power:
            return 0.1  # Very close

        # Calculate distance using the standard formula
        # Distance = 10^((Tx Power - RSSI) / (10 * N))
        # Where N is the path loss exponent (2 for free space, 2-4 for indoor)
        n = 2.0  # Path loss exponent
        ratio = (tx_power - rssi) / (10.0 * n)
        distance = pow(10, ratio)

        return round(distance, 2)

    def classify_proximity(self, distance: Optional[float]) -> str:
        """
        Classify proximity based on estimated distance
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

    async def monitor_target_devices(self):
        """
        Monitor specific target devices continuously
        """
        if not self.target_devices:
            logger.warning("No target devices specified")
            return

        logger.info(f"Monitoring target devices: {self.target_devices}")

        try:
            while True:
                # Scan for all devices
                devices = await self.scan_ble_devices(True)

                # Check each target device
                for target in self.target_devices:
                    found = False

                    for mac, name, rssi, ad_data in devices:
                        if (target.upper() in mac.upper() or
                            target.lower() in name.lower()):

                            found = True
                            tx_power = ad_data.get('tx_power')
                            distance = self.estimate_distance(rssi, tx_power)
                            proximity = self.classify_proximity(distance)

                            # Get additional device info
                            # device_info = await self.get_device_info(mac)

                            # Update device history
                            self.device_history[mac] = {
                                'name': name,
                                'last_seen': datetime.now(),
                                'rssi': rssi,
                                'distance': distance,
                                'proximity': proximity,
                                'tx_power': tx_power,
                                # 'device_info': device_info,
                                'advertisement_data': ad_data
                            }

                            logger.info(f"Target {name} ({mac}): Present - "
                                      f"RSSI: {rssi} dBm, "
                                      f"Distance: {distance}m, "
                                      f"Proximity: {proximity}")
                            break

                    if not found:
                        logger.info(f"Target device '{target}': Not found")

                await asyncio.sleep(30)  # Wait 30 seconds between scans

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Error in monitoring: {e}")

    async def scan_and_display(self):
        """
        Perform a single scan and display results
        """
        devices = await self.scan_ble_devices()

        if not devices:
            print("No Bluetooth devices found")
            return

        print("\n" + "="*70)
        print("BLUETOOTH DEVICES DETECTED")
        print("="*70)

        for mac, name, rssi, ad_data in devices:
            tx_power = ad_data.get('tx_power')
            distance = self.estimate_distance(rssi, tx_power)
            proximity = self.classify_proximity(distance)

            print(f"Device: {name}")
            print(f"MAC Address: {mac}")
            print(f"RSSI: {rssi} dBm" if rssi else "RSSI: Unknown")
            if tx_power:
                print(f"TX Power: {tx_power} dBm")
            print(f"Estimated Distance: {distance}m" if distance else "Distance: Unknown")
            print(f"Proximity: {proximity}")

            # Show additional advertisement data
            if ad_data.get('manufacturer_data'):
                print(f"Manufacturer Data: {ad_data['manufacturer_data']}")
            if ad_data.get('service_uuids'):
                print(f"Services: {ad_data['service_uuids']}")

            print("-" * 50)

    async def connect_to_device(self, mac_address: str):
        """
        Connect to a specific device and explore its services
        """
        if not BLEAK_AVAILABLE:
            print("Bleak not available for device connection")
            return

        try:
            if mac_address not in self.discovered_devices:
                print(f"Device {mac_address} not found. Please scan first.")
                return

            device = self.discovered_devices[mac_address]
            print(f"Connecting to {device.name} ({mac_address})...")

            async with BleakClient(device) as client:
                if client.is_connected:
                    print(f"Connected to {device.name}")

                    # Get services
                    services = await client.get_services()
                    print(f"\nAvailable Services ({len(services)}):")

                    for service in services:
                        print(f"  Service: {service.uuid}")
                        for char in service.characteristics:
                            print(f"    Characteristic: {char.uuid}")
                            print(f"      Properties: {char.properties}")
                else:
                    print("Failed to connect")

        except Exception as e:
            print(f"Connection error: {e}")

async def main():
    """
    Main function with example usage
    """
    print("Raspberry Pi Bluetooth Detection with Bleak (BLE)")
    print("="*50)

    # Example target devices (replace with actual MAC addresses or device names)
    target_devices = [
        "XX:XX:XX:XX:XX:XX",  # Replace with actual MAC address
        # "iPhone",             # Or search by device name
        # "Galaxy",             # Partial names work too
    ]

    detector = BleakBluetoothDetector(target_devices=target_devices)

    try:
        while True:
            print("\nChoose an option:")
            print("1. Scan for all BLE devices")
            print("2. Monitor target devices")
            print("3. Connect to a specific device")
            print("4. Exit")

            choice = input("Enter choice (1-4): ").strip()

            if choice == "1":
                await detector.scan_and_display()
            elif choice == "2":
                if target_devices:
                    await detector.monitor_target_devices()
                else:
                    print("No target devices configured. Please edit the script to add MAC addresses or device names.")
            elif choice == "3":
                mac = input("Enter MAC address to connect to: ").strip()
                await detector.connect_to_device(mac)
            elif choice == "4":
                break
            else:
                print("Invalid choice. Please try again.")

    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    asyncio.run(main())
