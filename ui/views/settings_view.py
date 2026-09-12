import logging
import customtkinter as ctk
from typing import Callable, Optional
from core.database import Database
from utils.startup_utils import (
    enable_startup,
    disable_startup,
    is_startup_enabled,
    get_startup_label,
)

logger = logging.getLogger(__name__)


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, db: Database, on_save: Optional[Callable] = None, **kwargs):
        # Intercept on_save before passing to CTkFrame — CTkFrame does not accept it
        super().__init__(master, **kwargs)
        self.db = db
        self.on_save = on_save
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(self, text="Settings",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=row, column=0, columnspan=2, pady=(20, 15))

        row += 1
        ctk.CTkLabel(self, text="Poll Interval (seconds)\n[min: 10, max: 3600]",
                     justify="left").grid(row=row, column=0, padx=20, pady=8, sticky="w")
        self.entry_poll = ctk.CTkEntry(self, placeholder_text="e.g. 30")
        self.entry_poll.grid(row=row, column=1, padx=20, pady=8, sticky="ew")

        row += 1
        ctk.CTkLabel(self, text="Sleep Drain Threshold (%/hr)\n[min: 0.5, max: 50.0]",
                     justify="left").grid(row=row, column=0, padx=20, pady=8, sticky="w")
        self.entry_sleep_drain = ctk.CTkEntry(self, placeholder_text="e.g. 3.0")
        self.entry_sleep_drain.grid(row=row, column=1, padx=20, pady=8, sticky="ew")

        row += 1
        ctk.CTkLabel(self, text="Anomaly Drain Threshold (% above baseline)\n[min: 5, max: 200]",
                     justify="left").grid(row=row, column=0, padx=20, pady=8, sticky="w")
        self.entry_anomaly_drain = ctk.CTkEntry(self, placeholder_text="e.g. 30.0")
        self.entry_anomaly_drain.grid(row=row, column=1, padx=20, pady=8, sticky="ew")

        row += 1
        ctk.CTkLabel(self, text="History Retention (days)\n[min: 7, max: 3650]",
                     justify="left").grid(row=row, column=0, padx=20, pady=8, sticky="w")
        self.entry_history = ctk.CTkEntry(self, placeholder_text="e.g. 90")
        self.entry_history.grid(row=row, column=1, padx=20, pady=8, sticky="ew")

        row += 1
        # P1: Platform-aware startup label (Windows/Linux/macOS)
        ctk.CTkLabel(self, text=get_startup_label()).grid(
            row=row, column=0, padx=20, pady=8, sticky="w")
        self.chk_startup_var = ctk.StringVar(value="off")
        self.chk_startup = ctk.CTkCheckBox(self, text="", variable=self.chk_startup_var,
                                           onvalue="on", offvalue="off")
        self.chk_startup.grid(row=row, column=1, padx=20, pady=8, sticky="w")

        row += 1
        ctk.CTkButton(self, text="Save Settings", command=self._save_settings).grid(
            row=row, column=0, columnspan=2, pady=20)

        row += 1
        self.lbl_status = ctk.CTkLabel(self, text="")
        self.lbl_status.grid(row=row, column=0, columnspan=2, pady=(0, 20))

    def refresh(self):
        settings = self.db.get_settings()
        self.entry_poll.delete(0, "end")
        self.entry_poll.insert(0, str(settings.poll_interval_seconds))

        self.entry_sleep_drain.delete(0, "end")
        self.entry_sleep_drain.insert(0, str(settings.sleep_drain_threshold_percent_per_hour))

        self.entry_anomaly_drain.delete(0, "end")
        self.entry_anomaly_drain.insert(0, str(settings.anomaly_drain_threshold_percent_above_baseline))

        self.entry_history.delete(0, "end")
        self.entry_history.insert(0, str(settings.history_retention_days))

        # Read the ACTUAL current registration state, not just the DB value.
        # This keeps the UI in sync if startup was enabled/disabled outside the app.
        self.chk_startup_var.set("on" if is_startup_enabled() else "off")
        self.lbl_status.configure(text="")

    def _validate_inputs(self):
        """
        Validates all inputs. Returns (errors: list[str], values: dict).
        errors is empty if all valid.
        """
        errors = []
        values = {}

        # Poll interval
        try:
            v = int(self.entry_poll.get().strip())
            if not (10 <= v <= 3600):
                raise ValueError("out of range")
            values["poll_interval_seconds"] = str(v)
        except (ValueError, TypeError):
            errors.append("Poll interval must be an integer between 10 and 3600.")

        # Sleep drain threshold
        try:
            v = float(self.entry_sleep_drain.get().strip())
            if not (0.5 <= v <= 50.0):
                raise ValueError("out of range")
            values["sleep_drain_threshold_percent_per_hour"] = str(v)
        except (ValueError, TypeError):
            errors.append("Sleep drain threshold must be a number between 0.5 and 50.0.")

        # Anomaly drain threshold
        try:
            v = float(self.entry_anomaly_drain.get().strip())
            if not (5.0 <= v <= 200.0):
                raise ValueError("out of range")
            values["anomaly_drain_threshold_percent_above_baseline"] = str(v)
        except (ValueError, TypeError):
            errors.append("Anomaly threshold must be a number between 5 and 200.")

        # History retention
        try:
            v = int(self.entry_history.get().strip())
            if not (7 <= v <= 3650):
                raise ValueError("out of range")
            values["history_retention_days"] = str(v)
        except (ValueError, TypeError):
            errors.append("History retention must be an integer between 7 and 3650.")

        return errors, values

    def _save_settings(self):
        errors, values = self._validate_inputs()
        if errors:
            self.lbl_status.configure(
                text="⚠ " + "\n".join(errors), text_color="red"
            )
            return

        try:
            for key, val in values.items():
                self.db.update_setting(key, val)

            run_on_startup = self.chk_startup_var.get() == "on"
            self.db.update_setting("run_on_startup", "1" if run_on_startup else "0")

            # P1/P2: Use startup_utils for the correct platform mechanism
            if run_on_startup:
                ok = enable_startup()
            else:
                ok = disable_startup()

            if not ok:
                self.lbl_status.configure(
                    text="⚠ Settings saved, but could not update startup registration.",
                    text_color="orange"
                )
            else:
                self.lbl_status.configure(text="✓ Settings saved successfully!", text_color="green")

            # Notify monitor to reload settings (poll interval etc.)
            if self.on_save:
                self.on_save()

        except Exception as e:
            logger.error(f"Error saving settings: {e}", exc_info=True)
            self.lbl_status.configure(text=f"⚠ Error: {e}", text_color="red")

    # _apply_startup_registration() removed — now handled by startup_utils
