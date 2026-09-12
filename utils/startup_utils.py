"""
Cross-platform startup (login item) registration for Battery Lens.

Each OS uses its own native mechanism:
  - Windows  → HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
  - Linux    → ~/.config/autostart/battery-lens.desktop   (XDG Autostart spec)
  - macOS    → ~/Library/LaunchAgents/com.batterylens.app.plist  (launchd)

Public API (platform-transparent):
  enable_startup()   -> bool
  disable_startup()  -> bool
  is_startup_enabled() -> bool
  get_startup_label()  -> str   (UI text for the settings checkbox)
"""
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_APP_NAME    = "BatteryLens"
_MACOS_LABEL = "com.batterylens.app"


# ─────────────────────────────────────────────────────────────
# Helper — resolve (executable, optional_script) for the
# current environment (frozen exe vs. running from source).
# ─────────────────────────────────────────────────────────────

def _get_executable_args() -> Tuple[str, Optional[str]]:
    """
    Returns (executable, script_or_None):
      - Frozen (PyInstaller): (path/to/BatteryLens.exe, None)
      - Running from source:  (path/to/pythonw.exe, path/to/main.py)
                              Falls back to python.exe if pythonw.exe absent.
    """
    if getattr(sys, "frozen", False):
        return (sys.executable, None)

    exe = Path(sys.executable)

    # On Windows prefer pythonw.exe (no console window on startup)
    if sys.platform == "win32":
        pythonw = exe.parent / "pythonw.exe"
        if pythonw.exists():
            exe = pythonw

    # main.py lives two levels up from this file  (utils/ → project root)
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return (str(exe), str(main_py))


# ─────────────────────────────────────────────────────────────
# WINDOWS — HKCU Run registry key
# ─────────────────────────────────────────────────────────────

def _windows_enable() -> bool:
    try:
        import winreg
        exe, script = _get_executable_args()
        value = f'"{exe}" "{script}"' if script else f'"{exe}"'
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.SetValueEx(k, _APP_NAME, 0, winreg.REG_SZ, value)
        logger.info(f"Windows startup registered: {value}")
        return True
    except Exception as e:
        logger.error(f"Windows startup registration failed: {e}")
        return False


def _windows_disable() -> bool:
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as k:
            try:
                winreg.DeleteValue(k, _APP_NAME)
                logger.info("Windows startup registration removed.")
            except FileNotFoundError:
                pass  # Was not registered — nothing to do
        return True
    except Exception as e:
        logger.error(f"Windows startup deregistration failed: {e}")
        return False


def _windows_is_enabled() -> bool:
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ
        ) as k:
            winreg.QueryValueEx(k, _APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# LINUX — XDG Autostart .desktop file
# https://specifications.freedesktop.org/autostart-spec/autostart-spec-latest.html
# ─────────────────────────────────────────────────────────────

def _linux_desktop_path() -> Path:
    """Returns the path to the XDG autostart .desktop file."""
    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    return autostart_dir / "battery-lens.desktop"


def _linux_enable() -> bool:
    try:
        exe, script = _get_executable_args()
        exec_line = f"{exe} {script}" if script else exe

        content = "\n".join([
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            f"Name={_APP_NAME}",
            "GenericName=Battery Monitor",
            "Comment=Battery monitoring in the system tray",
            f"Exec={exec_line}",
            "StartupNotify=false",
            "Hidden=false",
            "X-GNOME-Autostart-enabled=true",
            "",
        ])
        path = _linux_desktop_path()
        path.write_text(content, encoding="utf-8")
        logger.info(f"Linux XDG autostart .desktop created: {path}")
        return True
    except Exception as e:
        logger.error(f"Linux autostart registration failed: {e}")
        return False


def _linux_disable() -> bool:
    try:
        path = _linux_desktop_path()
        if path.exists():
            path.unlink()
            logger.info(f"Linux XDG autostart .desktop removed: {path}")
        return True
    except Exception as e:
        logger.error(f"Linux autostart deregistration failed: {e}")
        return False


def _linux_is_enabled() -> bool:
    path = _linux_desktop_path()
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
        # Disabled if Hidden=true is present
        return "Hidden=true" not in text
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# macOS — launchd LaunchAgent plist
# https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
# ─────────────────────────────────────────────────────────────

def _macos_plist_path() -> Path:
    """Returns the path to the LaunchAgent plist file."""
    la_dir = Path.home() / "Library" / "LaunchAgents"
    la_dir.mkdir(parents=True, exist_ok=True)
    return la_dir / f"{_MACOS_LABEL}.plist"


def _macos_enable() -> bool:
    import subprocess
    try:
        exe, script = _get_executable_args()

        if script:
            prog_args = (
                f"        <string>{exe}</string>\n"
                f"        <string>{script}</string>"
            )
        else:
            prog_args = f"        <string>{exe}</string>"

        log_path = Path.home() / "Library" / "Logs" / "BatteryLens.log"

        plist = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
            ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "    <key>Label</key>\n"
            f"    <string>{_MACOS_LABEL}</string>\n"
            "    <key>ProgramArguments</key>\n"
            "    <array>\n"
            f"{prog_args}\n"
            "    </array>\n"
            "    <key>RunAtLoad</key>\n"
            "    <true/>\n"
            "    <key>KeepAlive</key>\n"
            "    <false/>\n"
            "    <key>StandardOutPath</key>\n"
            f"    <string>{log_path}</string>\n"
            "    <key>StandardErrorPath</key>\n"
            f"    <string>{log_path}</string>\n"
            "</dict>\n"
            "</plist>\n"
        )

        path = _macos_plist_path()
        path.write_text(plist, encoding="utf-8")

        # Load the agent immediately (no logout required)
        result = subprocess.run(
            ["launchctl", "load", str(path)],
            capture_output=True, timeout=5
        )
        if result.returncode != 0:
            logger.warning(
                f"launchctl load returned {result.returncode}: "
                f"{result.stderr.decode(errors='replace').strip()}"
            )

        logger.info(f"macOS LaunchAgent created and loaded: {path}")
        return True
    except Exception as e:
        logger.error(f"macOS LaunchAgent registration failed: {e}")
        return False


def _macos_disable() -> bool:
    import subprocess
    try:
        path = _macos_plist_path()
        if path.exists():
            subprocess.run(
                ["launchctl", "unload", str(path)],
                capture_output=True, timeout=5
            )
            path.unlink()
            logger.info(f"macOS LaunchAgent removed: {path}")
        return True
    except Exception as e:
        logger.error(f"macOS LaunchAgent deregistration failed: {e}")
        return False


def _macos_is_enabled() -> bool:
    return _macos_plist_path().exists()


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def enable_startup() -> bool:
    """
    Registers Battery Lens to launch on user login using the
    correct native mechanism for the current OS.
    Returns True on success, False on failure.
    """
    if sys.platform == "win32":
        return _windows_enable()
    elif sys.platform == "darwin":
        return _macos_enable()
    else:
        return _linux_enable()


def disable_startup() -> bool:
    """
    Removes Battery Lens from launch-on-login.
    Returns True on success, False on failure.
    """
    if sys.platform == "win32":
        return _windows_disable()
    elif sys.platform == "darwin":
        return _macos_disable()
    else:
        return _linux_disable()


def is_startup_enabled() -> bool:
    """
    Returns True if Battery Lens is currently registered to
    launch on user login on this OS.
    """
    if sys.platform == "win32":
        return _windows_is_enabled()
    elif sys.platform == "darwin":
        return _macos_is_enabled()
    else:
        return _linux_is_enabled()


def get_startup_label() -> str:
    """
    Returns the platform-appropriate UI label for the
    'run on startup' checkbox in the Settings view.
    """
    if sys.platform == "win32":
        return "Run Battery Lens on Windows Startup"
    elif sys.platform == "darwin":
        return "Run Battery Lens on Login  (macOS Launch Agent)"
    else:
        return "Run Battery Lens on Login  (XDG Autostart)"
