import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict

from .core import BleakBluetoothDetector

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

__all__ = [
    "BluetoothMonitor",
    "estimate_distance",
    "classify_proximity"
]

class BluetoothMonitor:
    def __init__(self, targets: Optional[List[str]] = None, scan_duration: int = 10):
        self.detector = BleakBluetoothDetector(target_devices=targets, scan_duration=scan_duration, log_level="WARNING")

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
