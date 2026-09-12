# Battery Lens

Battery Lens is a cross-platform desktop application that monitors your laptop's battery behavior, detects anomalies, tracks long-term health trends, and provides evidence-based diagnostics — all locally, with no internet connection required.

## Features

- **Real-Time Monitoring** — Battery percentage, charge speed, and discharge rate.
- **Anomaly Detection** — Alerts when the battery drains significantly faster than your personal baseline.
- **Sleep Drain Analysis** — Detects and alerts if your laptop consumes too much power while suspended.
- **Health Tracking** — Records full-charge capacity over time and predicts when your battery will reach 80%.
- **Charging Analysis** — Tracks charge speed and detects slower-than-normal charging sessions.
- **Process Correlator** — When a high-drain event occurs, captures the top CPU-consuming processes.
- **Habit Recommendations** — Evidence-based advice based on your charging and drain patterns.

## Supported Platforms

| Platform | Tray Icon | Notifications | Battery Health | Startup on Login |
|----------|-----------|---------------|----------------|-----------------|
| Windows 10/11 | ✅ | ✅ | ✅ WMI | ✅ Registry |
| Linux (GNOME/KDE) | ✅ AppIndicator3 | ✅ libnotify | ✅ /sys/class | ✅ XDG Autostart |
| macOS 12+ | ✅ AppKit | ✅ | ✅ ioreg | ✅ LaunchAgent |

---

## Installation

### Windows

**Requirements:** Python 3.10+ (from [python.org](https://www.python.org/downloads/windows/) — check "Add Python to PATH")

**Quick install (recommended):**
```bat
install.bat
```
Then double-click `battery-lens.bat` to launch.

**Manual:**
```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-windows.txt
.venv\Scripts\pythonw.exe main.py
```

The app appears in the **system tray** (bottom-right, near the clock). No window opens immediately.

---

### Linux

**Requirements:**

1. Python 3.10+ (`python3` from your package manager)
2. System packages for tray icon and notifications:

```bash
# Ubuntu / Debian / Linux Mint
sudo apt install python3-tk gir1.2-appindicator3-0.1 libnotify-bin

# Fedora / RHEL / CentOS Stream
sudo dnf install python3-tkinter libappindicator-gtk3 libnotify

# Arch Linux / Manjaro
sudo pacman -S tk libappindicator-gtk3 libnotify
```

> **GNOME 42+ note:** GNOME removed system tray support by default. Install the AppIndicator extension:
> ```bash
> sudo apt install gnome-shell-extension-appindicator
> gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
> ```

**Quick install (recommended):**
```bash
bash install.sh
./battery-lens
```

**Manual:**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

The app appears in the **system tray**. If running GNOME, check the top-right status area.

---

### macOS

**Requirements:** Python 3.10+ (from [python.org](https://www.python.org/downloads/macos/) or `brew install python`)

> **tkinter on macOS:** If using Homebrew Python, also run: `brew install python-tk`

**Quick install (recommended):**
```bash
bash install.sh
./battery-lens
```

**Manual:**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-macos.txt
.venv/bin/python main.py
```

The app appears in the **menu bar** (top-right).

---

## Usage

Battery Lens runs quietly in the background:

| Action | Result |
|--------|--------|
| **Right-click** tray/menu-bar icon | Open Dashboard, Settings, or Exit |
| **Double-click** icon (Windows/Linux) | Open Dashboard |
| Anomaly detected | System notification appears |
| Close the Dashboard window | App stays running in tray |
| Exit via tray menu | App fully shuts down |

### First Launch
A welcome dialog explains the basics. The app needs **a few charge/discharge cycles** before anomaly detection becomes active.

### Run on Login / Startup
Open the app → **Settings** → check **"Run Battery Lens on Login"** → **Save Settings**.

Each platform uses its native mechanism:
- **Windows:** `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry key
- **Linux:** `~/.config/autostart/battery-lens.desktop` (XDG Autostart)
- **macOS:** `~/Library/LaunchAgents/com.batterylens.app.plist` (launchd)

---

## Data & Privacy

All data is stored **locally**. Nothing is sent to the internet. No accounts, no cloud.

| Platform | Database | Logs |
|----------|----------|------|
| Windows | `%APPDATA%\BatteryLens\battery_lens.db` | same directory |
| Linux | `~/.local/share/battery-lens/battery_lens.db` | same directory |
| macOS | `~/Library/Application Support/BatteryLens/battery_lens.db` | same directory |

### Uninstall

1. Open the app → Settings → uncheck "Run Battery Lens on Login" → Save
2. Exit the app (tray menu → Exit)
3. Delete the application folder
4. Delete the data directory (paths above)

---

## Building a Standalone Executable (PyInstaller)

```bash
pip install pyinstaller
pyinstaller battery_lens.spec
# Output: dist/BatteryLens/BatteryLens.exe  (Windows)
#         dist/BatteryLens/BatteryLens       (Linux/macOS)
```

---

## Development

```bash
# Run tests
.venv/bin/python -m pytest tests/ -v

# Run with coverage
.venv/bin/python -m pytest tests/ --cov=. --cov-report=term-missing
```

Python 3.10+ required. See `requirements.txt` for pip dependencies and `requirements-linux.txt` / `requirements-macos.txt` for platform-specific additions.
