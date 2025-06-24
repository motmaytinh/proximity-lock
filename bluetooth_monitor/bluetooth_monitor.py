import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict

from .core import BleakBluetoothDetector

logger = logging.getLogger(__name__)

__all__ = [
    "BluetoothMonitor",
    "estimate_distance",
    "classify_proximity"
]

class BluetoothMonitor:
    def __init__(self, targets: Optional[List[str]] = None, scan_duration: int = 10, log_level: str = "INFO"):
        """
        Initialize BluetoothMonitor with custom logging control.

        Args:
            targets: List of target device MAC addresses or names
            scan_duration: Duration in seconds for each scan
            log_level: Logging level. Options:
                - "DEBUG": Show all messages
                - "INFO": Show info, warning, error, critical (default)
                - "WARNING": Show warning, error, critical
                - "ERROR": Show error, critical only
                - "CRITICAL": Show critical only
                - "OFF" or "DISABLED": Disable all logging
        """
        self.detector = BleakBluetoothDetector(
            target_devices=targets,
            scan_duration=scan_duration,
            log_level=log_level
        )

    def set_log_level(self, level: str):
        """
        Set the logging level for the monitor and its detector.

        Args:
            level: Logging level as string. Options:
                - "DEBUG": Show all messages
                - "INFO": Show info, warning, error, critical
                - "WARNING": Show warning, error, critical
                - "ERROR": Show error, critical only
                - "CRITICAL": Show critical only
                - "OFF" or "DISABLED": Disable all logging
        """
        self.detector.set_log_level(level)

        # Also set the module-level logger
        level = level.upper()
        if level in ["OFF", "DISABLED"]:
            logger.setLevel(logging.CRITICAL + 1)
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
                logging.basicConfig(level=logging.INFO)
                logger.setLevel(logging.INFO)

    async def monitor_once(self) -> List[Dict]:
        results = []
        devices = await self.detector.scan_ble_devices(target_only=True)

        for mac, name, rssi, ad_data in devices:
            tx_power = ad_data.get("tx_power")
            distance = self.detector.estimate_distance(rssi, tx_power)
            proximity = self.detector.classify_proximity(distance)

            results.append({
                "name": name,
                "mac": mac,
                "rssi": rssi,
                "tx_power": tx_power,
                "distance": distance,
                "proximity": proximity,
                "timestamp": datetime.now(),
                "advertisement": ad_data,
            })

        return results

    async def monitor_loop(self, interval_seconds: int = 30):
        while True:
            results = await self.monitor_once()
            yield results
            await asyncio.sleep(interval_seconds)

    async def get_device_info(self, mac: str) -> Optional[Dict]:
        return await self.detector.get_device_info(mac)

def estimate_distance(rssi: int, tx_power: Optional[int] = None) -> Optional[float]:
    tx_power = tx_power or -59
    n = 2.0
    return round(pow(10, (tx_power - rssi) / (10 * n)), 2)

def classify_proximity(distance: Optional[float]) -> str:
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
