import pystray
import logging
from PIL import Image, ImageDraw
import threading
from plyer import notification
from typing import Callable, Optional
from core.database import Database
from core.models import BatterySnapshot

logger = logging.getLogger(__name__)

class TrayIcon:
    def __init__(self, db: Database, on_show_dashboard: Callable, on_exit: Callable):
        self.db = db
        self.on_show_dashboard = on_show_dashboard
        self.on_exit = on_exit
        self.icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self.last_snapshot: Optional[BatterySnapshot] = None

    def _create_image(self, percent: float, is_charging: bool) -> Image.Image:
        """
        Dynamically generates a tray icon based on battery percentage.
        """
        width = 64
        height = 64
        
        # Create transparent background
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw battery outline
        outline_color = "white"
        fill_color = "white"
        
        if percent <= 20 and not is_charging:
            fill_color = "red"
        elif is_charging:
            fill_color = "green"
            
        draw.rectangle([10, 20, 54, 44], outline=outline_color, width=2)
        draw.rectangle([54, 26, 58, 38], fill=outline_color) # Battery tip
        
        # Draw battery level
        fill_width = int((percent / 100.0) * 40)
        if fill_width > 0:
            draw.rectangle([12, 22, 12 + fill_width, 42], fill=fill_color)
            
        # Draw text inside or below? We'll just rely on the shape for now
        # because small text in 16x16 icon is hard to read on Windows.
        return image

    def _create_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Open Dashboard", self._on_open_dashboard, default=True),
            pystray.MenuItem("Settings", self._on_open_settings),
            pystray.MenuItem("Exit", self._on_exit_clicked)
        )

    def _on_open_dashboard(self, icon, item):
        self.on_show_dashboard("dashboard")

    def _on_open_settings(self, icon, item):
        self.on_show_dashboard("settings")

    def _on_exit_clicked(self, icon, item):
        if self.icon:
            self.icon.stop()
        self.on_exit()

    def update(self, snapshot: BatterySnapshot):
        """
        Updates the tray icon image and tooltip.
        """
        self.last_snapshot = snapshot
        if not self.icon:
            return
            
        img = self._create_image(snapshot.percent, snapshot.power_plugged)
        self.icon.icon = img
        
        status = "Charging" if snapshot.power_plugged else "Discharging"
        if snapshot.power_plugged and snapshot.percent >= 100:
            status = "Fully Charged"
            
        tooltip = f"Battery Lens\n{snapshot.percent:.1f}% - {status}"
        if not snapshot.power_plugged and snapshot.discharge_rate_mw:
            tooltip += f"\nDrain: {snapshot.discharge_rate_mw / 1000.0:.1f} W"
            
        self.icon.title = tooltip

    def run(self):
        """
        Runs the tray icon in the current thread (blocking).
        Usually called in a background thread or main thread.
        """
        # Initial image
        img = self._create_image(100.0, False)
        self.icon = pystray.Icon("BatteryLens", img, "Battery Lens - Loading...", self._create_menu())
        self.icon.run()

    def stop(self):
        if self.icon:
            self.icon.stop()

    def show_notification(self, title: str, message: str):
        """
        Shows a system notification using plyer.
        Falls back gracefully on platforms where plyer has no backend.
        """
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Battery Lens",
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
