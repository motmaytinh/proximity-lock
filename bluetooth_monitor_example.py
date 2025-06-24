import asyncio
from bluetooth_monitor import BluetoothMonitor

async def main():
    monitor = BluetoothMonitor(["XX:XX:XX:XX:XX:XXC"])
    results = await monitor.monitor_once()
    for device in results:
        print(device)

if __name__ == "__main__":
    asyncio.run(main())
