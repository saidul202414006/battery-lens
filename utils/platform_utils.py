"""
Cross-platform path and adapter utilities for Battery Lens.

Data directory locations (per OS conventions):
  Windows  → %APPDATA%\\BatteryLens\\
  macOS    → ~/Library/Application Support/BatteryLens/
  Linux    → $XDG_DATA_HOME/battery-lens/
               (default: ~/.local/share/battery-lens/)

Note: Earlier versions of Battery Lens stored the Linux database in
~/.config/battery-lens/ (XDG_CONFIG_HOME). On first run with this
version, the database and log file are migrated automatically to the
correct XDG_DATA_HOME location. The migration is logged and silent.
"""
import os
import sys
import shutil
import logging
import pathlib

logger = logging.getLogger(__name__)


def get_current_platform() -> str:
    """Returns 'windows', 'macos', 'linux', or 'unknown'."""
    import platform
    s = platform.system().lower()
    if s == "windows":
        return "windows"
    elif s == "darwin":
        return "macos"
    elif s == "linux":
        return "linux"
    return "unknown"


def _linux_old_config_dir() -> pathlib.Path:
    """
    Returns the OLD (incorrect) Linux config dir used by earlier versions.
    Only used for migration detection.
    """
    base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    return pathlib.Path(base) / "battery-lens"


def _linux_data_dir() -> pathlib.Path:
    """
    Returns the correct XDG data directory for Linux.
    Per XDG Base Directory Specification:
      $XDG_DATA_HOME (default ~/.local/share) holds user-specific data files.
    """
    base = os.environ.get(
        "XDG_DATA_HOME",
        os.path.join(os.path.expanduser("~"), ".local", "share"),
    )
    return pathlib.Path(base) / "battery-lens"


def _migrate_linux_data_if_needed(new_dir: pathlib.Path) -> None:
    """
    Migrates database and logs from the old ~/.config/battery-lens/ to
    the new XDG data location if the old directory exists and the new DB
    does not yet exist.  The migration is atomic per-file (move, not copy).
    """
    old_dir = _linux_old_config_dir()
    if not old_dir.exists():
        return  # Nothing to migrate

    new_db = new_dir / "battery_lens.db"
    if new_db.exists():
        return  # New location already populated — migration already done

    logger.info(
        f"Migrating Battery Lens data from {old_dir} → {new_dir} "
        "(XDG data dir correction)"
    )
    new_dir.mkdir(parents=True, exist_ok=True)

    migrated, failed = [], []
    for item in old_dir.iterdir():
        try:
            shutil.move(str(item), str(new_dir / item.name))
            migrated.append(item.name)
        except Exception as e:
            failed.append(f"{item.name}: {e}")

    if migrated:
        logger.info(f"Migrated files: {', '.join(migrated)}")
    if failed:
        logger.warning(f"Could not migrate: {'; '.join(failed)}")

    # Remove old directory if now empty
    try:
        if not any(old_dir.iterdir()):
            old_dir.rmdir()
            logger.info(f"Removed empty old directory: {old_dir}")
    except Exception:
        pass


def get_app_data_dir() -> pathlib.Path:
    """
    Returns the OS-specific application data directory, creating it if needed.

    Windows  : %APPDATA%\\BatteryLens\\
    macOS    : ~/Library/Application Support/BatteryLens/
    Linux    : $XDG_DATA_HOME/battery-lens/  (default ~/.local/share/battery-lens/)
    """
    platform = get_current_platform()

    if platform == "windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        app_dir = pathlib.Path(base) / "BatteryLens"

    elif platform == "macos":
        app_dir = (
            pathlib.Path(os.path.expanduser("~"))
            / "Library"
            / "Application Support"
            / "BatteryLens"
        )

    else:  # Linux and unknown
        app_dir = _linux_data_dir()
        # Automatically migrate from old config-dir location on first use
        _migrate_linux_data_if_needed(app_dir)

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_log_dir() -> pathlib.Path:
    """
    Returns the OS-specific directory for Battery Lens log files.
    Matches get_app_data_dir() for simplicity (one directory to find).
    """
    return get_app_data_dir()


def get_adapter():
    """
    Factory: returns the correct platform adapter instance, or None if
    the platform is unsupported or the adapter fails to initialize.
    """
    platform = get_current_platform()

    if platform == "windows":
        from platform_adapters.windows_adapter import WindowsAdapter
        return WindowsAdapter()
    elif platform == "linux":
        from platform_adapters.linux_adapter import LinuxAdapter
        return LinuxAdapter()
    elif platform == "macos":
        from platform_adapters.macos_adapter import macOSAdapter
        return macOSAdapter()

    logger.warning(f"No battery adapter available for platform: {sys.platform}")
    return None
