import asyncio
import socket
import sys
try:
    from bleak import BleakScanner
except ImportError:
    BleakScanner = None

SERVICE_UUID = '7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93e'

async def advertise():
    """Advertise the DropLink service UUID on Windows BLE."""
    if sys.platform != 'win32':
        print('BLE advertising is currently supported on Windows only.')
        return
    try:
        from winrt.windows.devices.bluetooth.advertisement import (
            BluetoothLEAdvertisement, BluetoothLEAdvertisementPublisher,
        )
        from uuid import UUID
    except ImportError:
        print('Install Windows BLE support with: pip install -r requirements.txt')
        return

    advertisement = BluetoothLEAdvertisement()
    # Keep the name short so it fits beside the 128-bit service UUID in the
    # legacy BLE advertisement payload.
    advertisement.local_name = socket.gethostname()[:5]
    advertisement.service_uuids.append(UUID(SERVICE_UUID))
    publisher = BluetoothLEAdvertisementPublisher(advertisement)
    publisher.start()
    print(f'Advertising {socket.gethostname()} with DropLink BLE service {SERVICE_UUID}. Press Ctrl+C to stop.')
    try:
        await asyncio.Event().wait()
    finally:
        publisher.stop()

async def scan(seconds=5):
    if BleakScanner is None:
        print('Install Bluetooth support with: pip install bleak')
        return
    devices = await BleakScanner.discover(timeout=seconds)
    for d in devices:
        print(f'{d.name or "Unknown"} | {d.address} | RSSI={d.rssi}')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--advertise', action='store_true', help='Advertise the DropLink BLE service')
    args = parser.parse_args()
    asyncio.run(advertise() if args.advertise else scan())
