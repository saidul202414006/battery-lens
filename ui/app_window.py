import customtkinter as ctk
import logging
from typing import Callable, Optional
from core.database import Database

from ui.views.dashboard_view import DashboardView
from ui.views.history_view import HistoryView
from ui.views.health_view import HealthView
from ui.views.charging_view import ChargingView
from ui.views.alerts_view import AlertsView
from ui.views.settings_view import SettingsView
from ui.views.sleep_view import SleepView

logger = logging.getLogger(__name__)

# Map of lowercase/alias tab names to canonical tab names (for tray menu calls)
_TAB_ALIASES = {
    "dashboard": "Dashboard",
    "history":   "History",
    "sleep":     "Sleep",
    "health":    "Health",
    "charging":  "Charging",
    "alerts":    "Alerts",
    "settings":  "Settings",
}


class AppWindow(ctk.CTkToplevel):
    """
    Main application window.

    Architecture note:
    - main.py creates a hidden ctk.CTk() root (the real Tk root for customtkinter).
    - This window is a CTkToplevel child of that root.
    - Two CTk() instances would conflict; CTkToplevel is the correct class for child windows.
    """

    def __init__(self, master, db: Database, on_close: Callable, monitor=None, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db
        self.on_close_callback = on_close
        self.monitor = monitor  # Used to reload settings after save

        # Window configuration
        self.title("Battery Lens")
        self.geometry("960x660")
        self.minsize(820, 580)

        # Handle close button — minimize to tray rather than destroy
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Create tabview
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=20, pady=20, fill="both", expand=True)

        # Add tabs
        self.tabs = ["Dashboard", "History", "Sleep", "Health", "Charging", "Alerts", "Settings"]
        for tab in self.tabs:
            self.tabview.add(tab)

        # Setup all view components
        self._setup_dashboard_tab()
        self._setup_history_tab()
        self._setup_sleep_tab()
        self._setup_health_tab()
        self._setup_charging_tab()
        self._setup_alerts_tab()
        self._setup_settings_tab()

        # Auto-refresh mechanism — refresh only the ACTIVE tab every 30s
        self.after(30000, self._auto_refresh)

    # ──────────────────────────────────────────────────────────
    # Tab setup
    # ──────────────────────────────────────────────────────────

    def _setup_dashboard_tab(self):
        tab = self.tabview.tab("Dashboard")
        self.dashboard_view = DashboardView(tab, self.db)
        self.dashboard_view.pack(fill="both", expand=True)

    def _setup_history_tab(self):
        tab = self.tabview.tab("History")
        self.history_view = HistoryView(tab, self.db)
        self.history_view.pack(fill="both", expand=True)

    def _setup_sleep_tab(self):
        tab = self.tabview.tab("Sleep")
        self.sleep_view = SleepView(tab, self.db)
        self.sleep_view.pack(fill="both", expand=True)

    def _setup_health_tab(self):
        tab = self.tabview.tab("Health")
        self.health_view = HealthView(tab, self.db)
        self.health_view.pack(fill="both", expand=True)

    def _setup_charging_tab(self):
        tab = self.tabview.tab("Charging")
        self.charging_view = ChargingView(tab, self.db)
        self.charging_view.pack(fill="both", expand=True)

    def _setup_alerts_tab(self):
        tab = self.tabview.tab("Alerts")
        self.alerts_view = AlertsView(tab, self.db)
        self.alerts_view.pack(fill="both", expand=True)

    def _setup_settings_tab(self):
        tab = self.tabview.tab("Settings")
        self.settings_view = SettingsView(tab, self.db, on_save=self._on_settings_saved)
        self.settings_view.pack(fill="both", expand=True)

    # ──────────────────────────────────────────────────────────
    # Callbacks
    # ──────────────────────────────────────────────────────────

    def _on_settings_saved(self):
        """Called after settings are saved — reloads monitor settings."""
        if self.monitor:
            self.monitor.reload_settings()
        logger.info("Settings saved and monitor settings reloaded.")

    def _on_close(self):
        """
        Called when user clicks the X button.
        Withdraws (hides) the window instead of destroying it.
        """
        self.withdraw()
        self.on_close_callback()

    # ──────────────────────────────────────────────────────────
    # Show / hide
    # ──────────────────────────────────────────────────────────

    def show_window(self, active_tab: str = "Dashboard"):
        """
        Shows the window and brings it to front.
        Accepts both canonical names ("Dashboard") and aliases ("dashboard").
        """
        canonical = _TAB_ALIASES.get(active_tab.lower(), active_tab)

        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))

        if canonical in self.tabs:
            self.tabview.set(canonical)

        # Trigger an immediate refresh when shown
        self._refresh_active_tab(canonical)

    # ──────────────────────────────────────────────────────────
    # Refresh
    # ──────────────────────────────────────────────────────────

    def _auto_refresh(self):
        """Periodically refreshes only the active tab if the window is visible."""
        try:
            if self.winfo_exists() and self.winfo_viewable():
                active_tab = self.tabview.get()
                self._refresh_active_tab(active_tab)
        except Exception as e:
            logger.debug(f"Auto-refresh error: {e}")

        # Schedule next refresh
        self.after(30000, self._auto_refresh)

    def _refresh_active_tab(self, tab_name: str):
        """Refreshes only the specified tab's view."""
        view_map = {
            "Dashboard": "dashboard_view",
            "History":   "history_view",
            "Sleep":     "sleep_view",
            "Health":    "health_view",
            "Charging":  "charging_view",
            "Alerts":    "alerts_view",
            "Settings":  "settings_view",
        }
        attr = view_map.get(tab_name)
        if attr and hasattr(self, attr):
            try:
                getattr(self, attr).refresh()
            except Exception as e:
                logger.error(f"Error refreshing {tab_name} view: {e}", exc_info=True)

    def refresh_views(self):
        """Refreshes all views (use sparingly — prefer _refresh_active_tab)."""
        for view_attr in ["dashboard_view", "history_view", "sleep_view",
                          "health_view", "charging_view", "alerts_view", "settings_view"]:
            if hasattr(self, view_attr):
                try:
                    getattr(self, view_attr).refresh()
                except Exception as e:
                    logger.error(f"Error refreshing {view_attr}: {e}", exc_info=True)
