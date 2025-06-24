import asyncio
import time
from datetime import datetime
from bluetooth_monitor import BluetoothMonitor
from ubuntu_screenlock import UbuntuScreenLock, StatusCheckError, LockFailedError
from pathlib import Path

CONFIG_FILE = Path.home() / ".bluetooth_proximity_config"
FAR_PROXIMITIES = {"Far", "Very Far"}
CHECK_INTERVAL = 30  # seconds

def load_target_mac():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file {CONFIG_FILE} not found.")
    return CONFIG_FILE.read_text().strip()

async def scan_proximity(target_mac):
    monitor = BluetoothMonitor([target_mac])
    results = await monitor.monitor_once()
    for device in results:
        if device.get("mac") == target_mac:
            print(f"[{datetime.now()}] Found {device['name']} - Proximity: {device['proximity']}")
            return device.get("proximity")
    print(f"[{datetime.now()}] Target device not found.")
    return "Very Far"  # Assume far if not found

def run_service():
    locker = UbuntuScreenLock()
    target_mac = load_target_mac()

    while True:
        try:
            if not locker.is_locked():
                proximity = asyncio.run(scan_proximity(target_mac))
                if proximity in FAR_PROXIMITIES:
                    print("Locking screen due to distance...")
                    locker.lock()
                else:
                    print("Device nearby. No action.")
            else:
                print("Screen already locked.")
        except (StatusCheckError, LockFailedError, FileNotFoundError) as e:
            print(f"Error: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_service()
