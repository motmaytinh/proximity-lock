import asyncio
import time
from datetime import datetime
from bluetooth_monitor import BluetoothMonitor
from ubuntu_screenlock import UbuntuScreenLock, StatusCheckError, LockFailedError
from pathlib import Path

CONFIG_FILE = Path.home() / ".bluetooth_proximity_config"
FAR_PROXIMITIES = {"Far", "Very Far"}
CHECK_INTERVAL = 30  # seconds
RETRY_COUNT = 3  # Number of retries when device not found
RETRY_DELAY = 5  # seconds between retries

def load_target_mac():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file {CONFIG_FILE} not found.")
    return CONFIG_FILE.read_text().strip()

async def scan_proximity(target_mac):
    monitor = BluetoothMonitor([target_mac], log_level="WARNING")
    results = await monitor.monitor_once()
    for device in results:
        if device.get("mac") == target_mac:
            print(f"[{datetime.now()}] Found {device['name']} - Proximity: {device['proximity']}")
            return device.get("proximity")
    return None  # Device not found

async def scan_proximity_with_retry(target_mac):
    for attempt in range(RETRY_COUNT):
        print(f"[{datetime.now()}] Scanning attempt {attempt + 1}/{RETRY_COUNT}")
        proximity = await scan_proximity(target_mac)

        if proximity is not None and proximity not in FAR_PROXIMITIES:
            # Device found and is close enough
            return proximity

        if attempt < RETRY_COUNT - 1:  # Don't wait after the last attempt
            if proximity is None:
                print(f"[{datetime.now()}] Target device not found. Retrying in {RETRY_DELAY} seconds...")
            else:
                print(f"[{datetime.now()}] Device is {proximity}. Retrying in {RETRY_DELAY} seconds...")
            await asyncio.sleep(RETRY_DELAY)

    if proximity is None:
        print(f"[{datetime.now()}] Target device not found after {RETRY_COUNT} attempts.")
    else:
        print(f"[{datetime.now()}] Device remains {proximity} after {RETRY_COUNT} attempts.")

    return "Very Far"  # Assume far if not found or still far after all retries

def run_service():
    locker = UbuntuScreenLock()
    target_mac = load_target_mac()

    while True:
        try:
            if not locker.is_locked():
                proximity = asyncio.run(scan_proximity_with_retry(target_mac))
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
