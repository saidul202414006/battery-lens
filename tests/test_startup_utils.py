"""
P9a: Tests for startup_utils — cross-platform startup registration.

Windows-specific registry tests run only on win32.
Linux .desktop tests are run on all platforms (filesystem-only, no OS execution).
macOS plist tests are run on all platforms (filesystem-only, no launchctl).
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────
# Helper — isolate all file I/O to tmp_path
# ─────────────────────────────────────────────────────────────

def _patch_home(tmp_path):
    """Returns a context manager that patches Path.home() to tmp_path."""
    return patch("pathlib.Path.home", return_value=tmp_path)


# ─────────────────────────────────────────────────────────────
# _get_executable_args
# ─────────────────────────────────────────────────────────────

def test_get_executable_args_from_source():
    """When not frozen, should return (python_path, main_py_path)."""
    from utils.startup_utils import _get_executable_args
    exe, script = _get_executable_args()
    assert exe  # Not empty
    assert script is not None
    assert script.endswith("main.py")
    assert Path(script).name == "main.py"


def test_get_executable_args_when_frozen(tmp_path):
    """When frozen (PyInstaller), script should be None."""
    fake_exe = str(tmp_path / "BatteryLens.exe")
    with patch.object(sys, "frozen", True, create=True):
        with patch.object(sys, "executable", fake_exe):
            from utils.startup_utils import _get_executable_args
            exe, script = _get_executable_args()
            assert exe == fake_exe
            assert script is None


# ─────────────────────────────────────────────────────────────
# Linux XDG Autostart
# ─────────────────────────────────────────────────────────────

def test_linux_desktop_created(tmp_path):
    """_linux_enable() creates a valid .desktop file in autostart dir."""
    from utils import startup_utils

    with patch.object(startup_utils, "_linux_desktop_path",
                      return_value=tmp_path / "battery-lens.desktop"):
        result = startup_utils._linux_enable()

    assert result is True
    desktop = tmp_path / "battery-lens.desktop"
    assert desktop.exists()

    content = desktop.read_text()
    assert "[Desktop Entry]" in content
    assert "Type=Application" in content
    assert "BatteryLens" in content
    assert "Hidden=true" not in content
    assert "X-GNOME-Autostart-enabled=true" in content


def test_linux_is_enabled_true(tmp_path):
    """_linux_is_enabled() returns True when .desktop file exists without Hidden=true."""
    from utils import startup_utils

    desktop = tmp_path / "battery-lens.desktop"
    desktop.write_text("[Desktop Entry]\nHidden=false\n")

    with patch.object(startup_utils, "_linux_desktop_path", return_value=desktop):
        assert startup_utils._linux_is_enabled() is True


def test_linux_is_enabled_false_when_missing(tmp_path):
    """_linux_is_enabled() returns False when .desktop file doesn't exist."""
    from utils import startup_utils

    with patch.object(startup_utils, "_linux_desktop_path",
                      return_value=tmp_path / "nonexistent.desktop"):
        assert startup_utils._linux_is_enabled() is False


def test_linux_is_enabled_false_when_hidden(tmp_path):
    """_linux_is_enabled() returns False when Hidden=true is in the file."""
    from utils import startup_utils

    desktop = tmp_path / "battery-lens.desktop"
    desktop.write_text("[Desktop Entry]\nHidden=true\n")

    with patch.object(startup_utils, "_linux_desktop_path", return_value=desktop):
        assert startup_utils._linux_is_enabled() is False


def test_linux_disable_removes_file(tmp_path):
    """_linux_disable() removes the .desktop file."""
    from utils import startup_utils

    desktop = tmp_path / "battery-lens.desktop"
    desktop.write_text("[Desktop Entry]\n")

    with patch.object(startup_utils, "_linux_desktop_path", return_value=desktop):
        result = startup_utils._linux_disable()

    assert result is True
    assert not desktop.exists()


def test_linux_disable_when_already_absent(tmp_path):
    """_linux_disable() returns True even if .desktop file doesn't exist."""
    from utils import startup_utils

    with patch.object(startup_utils, "_linux_desktop_path",
                      return_value=tmp_path / "nonexistent.desktop"):
        assert startup_utils._linux_disable() is True


# ─────────────────────────────────────────────────────────────
# macOS LaunchAgent plist
# ─────────────────────────────────────────────────────────────

def test_macos_plist_created(tmp_path):
    """_macos_enable() creates a valid plist file."""
    from utils import startup_utils

    plist_path = tmp_path / "com.batterylens.app.plist"

    with patch.object(startup_utils, "_macos_plist_path", return_value=plist_path):
        # Mock launchctl so we don't actually load anything
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = startup_utils._macos_enable()

    assert result is True
    assert plist_path.exists()

    content = plist_path.read_text()
    assert "<?xml" in content
    assert "com.batterylens.app" in content
    assert "<key>RunAtLoad</key>" in content
    assert "<true/>" in content
    assert "main.py" in content


def test_macos_is_enabled_true(tmp_path):
    """_macos_is_enabled() returns True when plist file exists."""
    from utils import startup_utils

    plist = tmp_path / "com.batterylens.app.plist"
    plist.write_text("<plist/>")

    with patch.object(startup_utils, "_macos_plist_path", return_value=plist):
        assert startup_utils._macos_is_enabled() is True


def test_macos_is_enabled_false(tmp_path):
    """_macos_is_enabled() returns False when plist file is absent."""
    from utils import startup_utils

    with patch.object(startup_utils, "_macos_plist_path",
                      return_value=tmp_path / "nonexistent.plist"):
        assert startup_utils._macos_is_enabled() is False


def test_macos_disable_removes_plist(tmp_path):
    """_macos_disable() removes the plist and calls launchctl unload."""
    from utils import startup_utils

    plist = tmp_path / "com.batterylens.app.plist"
    plist.write_text("<plist/>")

    with patch.object(startup_utils, "_macos_plist_path", return_value=plist):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = startup_utils._macos_disable()

    assert result is True
    assert not plist.exists()
    mock_run.assert_called_once()
    assert "launchctl" in mock_run.call_args[0][0]


# ─────────────────────────────────────────────────────────────
# Public API routing
# ─────────────────────────────────────────────────────────────

def test_get_startup_label_is_platform_specific():
    """get_startup_label() returns a non-empty string for the current platform."""
    from utils.startup_utils import get_startup_label
    label = get_startup_label()
    assert isinstance(label, str)
    assert len(label) > 5
    # Must not be hardcoded to Windows on non-Windows
    if sys.platform != "win32":
        assert "Windows" not in label


def test_public_api_routes_correctly():
    """
    enable_startup / disable_startup / is_startup_enabled route to the
    correct platform implementation without raising.
    """
    from utils import startup_utils

    # Patch all platform implementations to no-ops
    with patch.object(startup_utils, "_windows_enable", return_value=True) as we, \
         patch.object(startup_utils, "_linux_enable", return_value=True) as le, \
         patch.object(startup_utils, "_macos_enable", return_value=True) as me:

        startup_utils.enable_startup()

        if sys.platform == "win32":
            we.assert_called_once()
            le.assert_not_called()
            me.assert_not_called()
        elif sys.platform == "darwin":
            me.assert_called_once()
            we.assert_not_called()
            le.assert_not_called()
        else:
            le.assert_called_once()
            we.assert_not_called()
            me.assert_not_called()


# ─────────────────────────────────────────────────────────────
# Windows registry (Windows-only)
# ─────────────────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only registry test")
def test_windows_enable_writes_registry():
    """_windows_enable() writes a registry value on Windows."""
    import winreg
    from utils.startup_utils import _windows_enable, _windows_is_enabled, _windows_disable

    # Enable
    ok = _windows_enable()
    assert ok is True
    assert _windows_is_enabled() is True

    # Disable and verify removal
    ok = _windows_disable()
    assert ok is True
    assert _windows_is_enabled() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_windows_disable_is_idempotent():
    """_windows_disable() does not raise when the key doesn't exist."""
    from utils.startup_utils import _windows_disable
    # Call twice — second call should succeed silently
    _windows_disable()
    result = _windows_disable()
    assert result is True
