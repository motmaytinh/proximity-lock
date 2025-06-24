# proximity-lock

**proximity-lock** is a background service that automatically locks your Ubuntu screen when your Bluetooth device (like a phone or smartwatch) is no longer nearby. It uses Bluetooth signal proximity to determine if the device is **Far** or **Very Far**, and locks the screen for security.

---

## 🛠️ Setup Instructions

### 1. Create a Config File for Your Device's MAC Address

Replace `XX:XX:XX:XX:XX:XX` with your target Bluetooth device’s MAC address:

```bash
echo "XX:XX:XX:XX:XX:XX" > ~/.bluetooth_proximity_config
```

This file is read by the service to determine which device to track.

### 2. Make the Script Executable

Ensure the main script (proximity_lock_service.py) is executable:

```bash
chmod +x /path/to/proximity_lock_service.py
```

### 3. Create a systemd User Service Link
Assuming your service file is stored at `~/.services/proximity-lock.service`, create a symlink:

```bash
mkdir -p ~/.config/systemd/user
ln -s ~/.services/proximity-lock.service ~/.config/systemd/user/proximity-lock.service
```

### 4. Enable and Start the Service

Use `systemctl --user` to manage the user-level systemd service:

```bash
systemctl --user daemon-reexec
systemctl --user daemon-reload
systemctl --user enable --now proximity-lock.service
```

### 5. Check Service Logs
To monitor logs in real-time:

```bash
journalctl --user -u proximity-lock.service -f
```

### 🧩 Optional Commands
Stop the service manually:
```bash
systemctl --user stop proximity-lock.service
```
