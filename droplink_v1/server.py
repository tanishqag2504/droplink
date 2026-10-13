import os, socket, threading, json, time, asyncio, subprocess, ipaddress, re
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet, InvalidToken

try:
    from bleak import BleakScanner
except ImportError:
    BleakScanner = None

APP_NAME = 'DropLink'
PORT = int(os.environ.get('DROPLINK_PORT', '8765'))
DISCOVERY_PORT = int(os.environ.get('DROPLINK_DISCOVERY_PORT', '37020'))
DEVICE_NAME = os.environ.get('DROPLINK_NAME', socket.gethostname())
BLE_SERVICE_UUID = '7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93e'
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'received')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
KEY_PATH = os.path.join(os.path.dirname(__file__), '.droplink.key')
if not os.path.exists(KEY_PATH):
    with open(KEY_PATH, 'wb') as key_file:
        key_file.write(Fernet.generate_key())
with open(KEY_PATH, 'rb') as key_file:
    FILE_CIPHER = Fernet(key_file.read())

app = Flask(__name__, static_folder='web', static_url_path='')

@app.get('/')
def index():
    return send_from_directory('web', 'index.html')

@app.get('/phone')
def phone_upload_page():
    return send_from_directory('web', 'phone.html')

@app.get('/api/info')
def info():
    return jsonify({
        'name': DEVICE_NAME, 'type': 'Windows PC', 'port': PORT,
        'protocol': 'HTTP', 'ip': local_ip(),
        'phone_url': f'http://{local_ip()}:{PORT}/phone'
    })

@app.get('/api/discover')
def discover():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.7)
    msg = json.dumps({'type': 'DROPLINK_DISCOVER', 'from': DEVICE_NAME}).encode()
    try:
        sock.sendto(msg, ('255.255.255.255', DISCOVERY_PORT))
        found = {}
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                x = json.loads(data.decode())
                if x.get('type') == 'DROPLINK_HERE' and x.get('name') != DEVICE_NAME:
                    x['ip'] = addr[0]
                    found[x['ip'] + ':' + str(x.get('port'))] = x
            except socket.timeout:
                break
        ble_found = discover_ble_devices()
        for device in ble_found:
            # Keep BLE-only entries visible. The sender UI disables transfer
            # until a Wi-Fi endpoint is available from LAN discovery.
            key = 'ble:' + device['address']
            found[key] = device
        return jsonify(list(found.values()))
    finally:
        sock.close()

def discover_ble_devices():
    """Return nearby devices advertising the DropLink BLE service UUID."""
    if BleakScanner is None:
        return []
    try:
        advertisements = asyncio.run(BleakScanner.discover(timeout=1.2, return_adv=True))
    except Exception:
        # Bluetooth may be unavailable, disabled, or denied by the OS. LAN
        # discovery should continue to work in those cases.
        return []

    devices = []
    for address, (ble_device, advertisement) in advertisements.items():
        service_uuids = {value.lower() for value in (advertisement.service_uuids or [])}
        if BLE_SERVICE_UUID not in service_uuids:
            continue
        devices.append({
            'name': advertisement.local_name or ble_device.name or 'DropLink device',
            'type': 'Windows PC',
            'ip': None,
            'port': None,
            'transport': 'Bluetooth',
            'address': address,
            'rssi': advertisement.rssi,
        })
    return devices

@app.post('/api/upload')
def upload():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    name = secure_filename(f.filename) or 'received_file'
    path = os.path.join(DOWNLOAD_DIR, name)
    base, ext = os.path.splitext(name)
    i = 1
    while os.path.exists(path):
        path = os.path.join(DOWNLOAD_DIR, f'{base}_{i}{ext}')
        i += 1
    encrypted = FILE_CIPHER.encrypt(f.read())
    with open(path, 'wb') as output:
        output.write(encrypted)
    return jsonify({'ok': True, 'filename': os.path.basename(path), 'size': len(encrypted), 'encrypted_at_rest': True})

@app.get('/api/files/<path:name>')
def download(name):
    safe_name = secure_filename(name)
    path = os.path.join(DOWNLOAD_DIR, safe_name)
    if not safe_name or not os.path.isfile(path):
        return jsonify({'error': 'File not found'}), 404
    try:
        with open(path, 'rb') as encrypted_file:
            data = FILE_CIPHER.decrypt(encrypted_file.read())
    except InvalidToken:
        return jsonify({'error': 'File cannot be decrypted with this installation key'}), 500
    response = app.response_class(data, mimetype='application/octet-stream')
    response.headers['Content-Disposition'] = f'attachment; filename="{safe_name}"'
    return response

def local_ip():
    configured_ip = os.environ.get('DROPLINK_HOST_IP')
    if configured_ip:
        try:
            return str(ipaddress.IPv4Address(configured_ip))
        except ipaddress.AddressValueError:
            pass
    if os.name == 'nt':
        # Prefer Wi-Fi/Ethernet addresses over VPN and virtual adapter routes.
        try:
            result = subprocess.run(
                ['ipconfig'],
                capture_output=True, text=True, timeout=3, check=False,
            )
            adapters = []
            for block in re.split(r'\r?\n\s*\r?\n', result.stdout):
                ipv4_match = re.search(r'IPv4[^:\r\n]*:\s*([\d.]+)', block, re.IGNORECASE)
                if not ipv4_match:
                    continue
                address = ipv4_match.group(1)
                try:
                    parsed = ipaddress.IPv4Address(address)
                    if not parsed.is_loopback and not parsed.is_link_local:
                        adapters.append((block.lower(), str(parsed)))
                except ipaddress.AddressValueError:
                    continue
            preferred = next((ip for block, ip in adapters if 'wi-fi' in block or 'wireless' in block), None)
            if not preferred:
                preferred = next((ip for block, ip in adapters
                                  if ('ethernet' in block and 'vethernet' not in block
                                      and 'warp' not in block and 'virtual' not in block)), None)
            if preferred:
                return preferred
        except (OSError, subprocess.TimeoutExpired):
            pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()

def discovery_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(('', DISCOVERY_PORT))
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            msg = json.loads(data.decode())
            if msg.get('type') == 'DROPLINK_DISCOVER':
                response = {
                    'type': 'DROPLINK_HERE', 'name': DEVICE_NAME,
                    'ip': local_ip(), 'port': PORT, 'device_type': 'Windows PC',
                    'timestamp': time.time()
                }
                sock.sendto(json.dumps(response).encode(), addr)
        except Exception:
            pass

def discovery_broadcaster():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            msg = json.dumps({'type': 'DROPLINK_DISCOVER', 'from': DEVICE_NAME}).encode()
            sock.sendto(msg, ('255.255.255.255', DISCOVERY_PORT))
        except OSError:
            pass
        time.sleep(3)

if __name__ == '__main__':
    threading.Thread(target=discovery_listener, daemon=True).start()
    threading.Thread(target=discovery_broadcaster, daemon=True).start()
    print(f'{APP_NAME} running as {DEVICE_NAME} at http://{local_ip()}:{PORT}')
    app.run(host='0.0.0.0', port=PORT, threaded=True)
