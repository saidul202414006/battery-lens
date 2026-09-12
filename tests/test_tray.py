import pytest
from unittest.mock import MagicMock
from core.models import BatterySnapshot
from ui.tray import TrayIcon

def test_tray_icon_image_generation():
    tray = TrayIcon(db=MagicMock(), on_show_dashboard=MagicMock(), on_exit=MagicMock())
    
    img_full = tray._create_image(100.0, False)
    assert img_full.size == (64, 64)
    
    img_charging = tray._create_image(50.0, True)
    assert img_charging.size == (64, 64)
    
    img_low = tray._create_image(15.0, False)
    assert img_low.size == (64, 64)

def test_tray_icon_tooltip_generation():
    tray = TrayIcon(db=MagicMock(), on_show_dashboard=MagicMock(), on_exit=MagicMock())
    tray.icon = MagicMock()
    
    snapshot = BatterySnapshot(
        timestamp=1000,
        percent=85.5,
        power_plugged=False,
        discharge_rate_mw=15000.0,
        platform="mock"
    )
    
    tray.update(snapshot)
    
    # Verify title updated correctly
    title = tray.icon.title
    assert "85.5%" in title
    assert "Discharging" in title
    assert "15.0 W" in title
