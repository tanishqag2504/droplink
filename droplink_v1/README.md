# DropLink v1 — Bluetooth + Wi-Fi integrated MVP

This version uses:
- **Wi-Fi UDP discovery** to automatically find other DropLink PCs on the same LAN.
- **Wi-Fi HTTP upload** for direct file transfer with progress.
- **Bluetooth LE service advertising** (`bluetooth_scanner.py --advertise`) on Windows, in addition to scanning.
- **Encrypted received-file storage** using Fernet; files are decrypted when downloaded through the app.

## Run on Windows

1. Install Python 3.11+.
2. Open PowerShell in this folder.
3. Run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py server.py
```

4. Open `http://127.0.0.1:8765` in the browser.
5. Run the same project on the second PC. Put both PCs on the same Wi-Fi/LAN.
6. Allow Python/DropLink through Windows Firewall on **Private networks** when Windows asks.
7. The other PC should appear automatically. Select it, choose a file, and press **Send file**.

## Send files from a phone

Keep DropLink running on the PC and connect the phone to the same Wi-Fi network. Open the phone upload address shown on the DropLink home page (or use `http://<PC-LAN-IP>:8765/phone`). Select one or more files and tap **Send files**. The files are encrypted and saved in the PC's `received/` folder.

## Bluetooth discovery

The web app scans for BLE advertisements automatically while it performs LAN discovery. To make a PC visible over Bluetooth, run the advertiser in a second terminal with Bluetooth enabled:

```powershell
py bluetooth_scanner.py --advertise
```

To scan nearby BLE devices and RSSI from the command line instead:

```powershell
py bluetooth_scanner.py
```

The BLE service UUID is `7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93e`. Devices found only over Bluetooth appear in the web app, but sending remains disabled until their Wi-Fi endpoint is discovered. BLE advertising needs Windows Bluetooth support and permissions.

Uploaded files are encrypted on disk in `received/`. The `.droplink.key` file is generated on first launch and must be kept with the installation; deleting it makes existing received files unreadable. Download a received file through `/api/files/<filename>` to get the original bytes.

## Security note

This is a local-network development MVP. File encryption is at rest only; uploads and downloads still use plain HTTP on the LAN. Do not expose port 8765 to the public internet. A production version should add pairing/authentication, TLS, transfer tokens, file-size limits, and an explicit receiver approval dialog.
