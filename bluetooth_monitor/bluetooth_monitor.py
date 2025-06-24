import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, AsyncGenerator

# Import BluetoothDetector from the same package
from .core import BluetoothDetector

# Set up logging for the bluetooth_monitor module
logger = logging.getLogger(__name__)

# Define what symbols are exported when 'from bluetooth_monitor import *' is used
__all__ = [
    "BluetoothMonitor",
    # Note: estimate_distance and classify_proximity are now methods of BluetoothDetector
    # and generally accessed via a BluetoothMonitor instance.
    # If they are intended to be standalone utilities, they should be in a separate utility module,
    # or kept here but explicitly documented as independent functions.
    # For now, let's keep them and assume they might be used directly in some cases,
    # but the primary usage is via the detector.
    "estimate_distance", # Keeping for backward compatibility or direct utility use
    "classify_proximity" # Keeping for backward compatibility or direct utility use
]

class BluetoothMonitor:
    """
    Monitors Bluetooth Low Energy (BLE) devices using the BluetoothDetector.
    Provides functionalities for one-time scans, continuous monitoring, and
    retrieving detailed device information.
    """

    def __init__(self, targets: Optional[List[str]] = None, scan_duration: int = 10, log_level: str = "INFO"):
        """
        Initializes the BluetoothMonitor.

        Args:
            targets (Optional[List[str]]): A list of MAC addresses or names
                                           of target devices to look for.
            scan_duration (int): The duration (in seconds) for each BLE scan.
            log_level (str): The logging level (e.g., "INFO", "DEBUG", "WARNING").
        """
        # BluetoothDetector handles its own logging setup based on the passed log_level
        self.detector = BluetoothDetector(
            target_devices=targets,
            scan_duration=scan_duration,
            log_level=log_level # Pass the log level to the detector
        )
        # Set logging for this module as well
        self._set_module_log_level(log_level)
        logger.info("BluetoothMonitor initialized.")

    def _set_module_log_level(self, level: str):
        """
        Helper to set the logging level for this specific module.
        """
        level = level.upper()
        if level in ["OFF", "DISABLED"]:
            logger.setLevel(logging.CRITICAL + 1) # Effectively disables logging for this logger
            return

        log_levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        # Ensure the logger has a handler if it doesn't already
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        logger.setLevel(log_levels.get(level, logging.INFO))


    def set_log_level(self, level: str):
        """
        Set the logging level for the monitor and its underlying detector.

        Args:
            level (str): Logging level as a string (e.g., "DEBUG", "INFO", "OFF").
        """
        self._set_module_log_level(level) # Set log level for bluetooth_monitor.py
        self.detector.set_log_level(level) # Delegate to BluetoothDetector's logging
        logger.info(f"Monitor and detector logging level set to {level.upper()}")

    async def monitor_once(self) -> List[Dict[str, Any]]:
        """
        Performs a single scan for target BLE devices and processes the results.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each representing a
                                  discovered target device with its details.
        """
        logger.debug("Performing a single monitoring scan.")
        results: List[Dict[str, Any]] = []
        # Use target_only=True to optimize scan if targets are defined
        devices = await self.detector.scan_ble_devices(target_only=True)

        for mac, name, rssi, ad_data in devices:
            tx_power = ad_data.get("tx_power") # Safely get tx_power, it can be None

            # The detector's estimate_distance method handles None for tx_power
            distance = self.detector.estimate_distance(rssi, tx_power)
            proximity = self.detector.classify_proximity(distance)

            results.append({
                "name": name,
                "mac": mac,
                "rssi": rssi,
                "tx_power": tx_power, # Store original tx_power from ad_data
                "distance": distance,
                "proximity": proximity,
                "timestamp": datetime.now().isoformat(), # Use ISO format for better serialization
                "advertisement": ad_data,
            })
            logger.debug(f"Processed device: {name} ({mac}), Proximity: {proximity}, Distance: {distance:.2f}m")

        logger.info(f"Single monitoring scan complete. Found {len(results)} target device(s).")
        return results

    async def monitor_loop(self, interval_seconds: int = 30) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """
        Continuously monitors for BLE devices in a loop.

        Args:
            interval_seconds (int): The pause duration between scan attempts.

        Yields:
            AsyncGenerator[List[Dict[str, Any]], None]: A list of discovered
                                                         target device details.
        """
        if interval_seconds <= 0:
            logger.warning("Interval must be positive. Defaulting to 30 seconds.")
            interval_seconds = 30

        logger.info(f"Starting continuous monitoring loop with {interval_seconds}s interval.")
        while True:
            try:
                results = await self.monitor_once()
                yield results
            except Exception as e:
                logger.error(f"Error during continuous monitoring loop: {e}")
                # Decide if you want to break the loop or continue after an error
            await asyncio.sleep(interval_seconds)

    async def get_device_info(self, mac: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves detailed information about a specific BLE device by its MAC address.

        Args:
            mac (str): The MAC address of the device.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing device information, or None if not found/connected.
        """
        logger.debug(f"Attempting to get detailed info for MAC: {mac}")
        info = await self.detector.get_device_info(mac)
        if info:
            logger.info(f"Successfully retrieved info for {mac}.")
        else:
            logger.warning(f"Could not retrieve info for {mac}.")
        return info

# Standalone utility functions (kept for backward compatibility or direct use)
# It's generally better to use the methods on a BluetoothMonitor or BluetoothDetector instance
# if they are part of the class's core functionality.
def estimate_distance(rssi: int, tx_power: Optional[int] = None) -> Optional[float]:
    """
    Estimates the distance to a BLE device based on its RSSI and Tx Power.
    This is a standalone utility function, also available via BluetoothDetector.

    Args:
        rssi (int): The Received Signal Strength Indicator (in dBm).
        tx_power (Optional[int]): The calibrated Tx Power at 1 meter (in dBm).
                                  Defaults to -59 dBm.

    Returns:
        Optional[float]: The estimated distance in meters, or None if RSSI is invalid.
    """
    if rssi is None or rssi == 0:
        logger.debug(f"Cannot estimate distance: invalid RSSI ({rssi}).")
        return None
    # N is the environmental factor, typically between 2.0 and 4.0
    # 2.0 for free space, 3.0-4.0 for indoor environments
    n = 2.0
    tx_power = tx_power or -59
    distance = pow(10, (tx_power - rssi) / (10 * n))
    return round(distance, 2)

def classify_proximity(distance: Optional[float]) -> str:
    """
    Classifies the proximity of a device based on its estimated distance.
    This is a standalone utility function, also available via BluetoothDetector.

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
