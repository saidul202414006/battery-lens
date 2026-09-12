import customtkinter as ctk
import time
from contextlib import closing
from typing import Optional
from core.database import Database
from analysis.drain_analyzer import DrainAnalyzer
from analysis.runtime_estimator import RuntimeEstimator


class DashboardView(ctk.CTkFrame):
    def __init__(self, master, db: Database, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db
        self.drain_analyzer = DrainAnalyzer(db)
        self.runtime_estimator = RuntimeEstimator(db)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Status ──────────────────────────────────────────
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.status_frame, text="Battery Status",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        self.lbl_percent = ctk.CTkLabel(self.status_frame, text="--%",
                                        font=ctk.CTkFont(size=36, weight="bold"))
        self.lbl_percent.pack(pady=5)
        self.lbl_charging = ctk.CTkLabel(self.status_frame, text="--")
        self.lbl_charging.pack()
        self.lbl_health = ctk.CTkLabel(self.status_frame, text="Health: --")
        self.lbl_health.pack(pady=(5, 5))
        self.lbl_runtime = ctk.CTkLabel(self.status_frame, text="~Calculating...",
                                        font=ctk.CTkFont(slant="italic"))
        self.lbl_runtime.pack(pady=(0, 10))

        # ── Drain ────────────────────────────────────────────
        self.drain_frame = ctk.CTkFrame(self)
        self.drain_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.drain_frame, text="Current Drain",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        self.lbl_drain_rate = ctk.CTkLabel(self.drain_frame, text="-- W\n-- %/hr",
                                           font=ctk.CTkFont(size=20))
        self.lbl_drain_rate.pack(pady=10)
        self.lbl_drain_comparison = ctk.CTkLabel(self.drain_frame, text="--")
        self.lbl_drain_comparison.pack(pady=(0, 10))

        # ── Session ──────────────────────────────────────────
        self.session_frame = ctk.CTkFrame(self)
        self.session_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.session_frame, text="Current Session",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        self.lbl_session_duration = ctk.CTkLabel(self.session_frame, text="Duration: --")
        self.lbl_session_duration.pack(pady=2)
        self.lbl_session_start = ctk.CTkLabel(self.session_frame, text="Started at: --%")
        self.lbl_session_start.pack(pady=2)
        self.lbl_session_none = ctk.CTkLabel(self.session_frame, text="Not discharging", text_color="gray")
        self.lbl_session_none.pack(pady=(0, 10))

        # ── Alerts ───────────────────────────────────────────
        self.alerts_frame = ctk.CTkFrame(self)
        self.alerts_frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.alerts_frame, text="Active Alerts",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        self.lbl_alerts = ctk.CTkLabel(self.alerts_frame, text="No active alerts.", text_color="green")
        self.lbl_alerts.pack(pady=10, padx=10)

    def refresh(self):
        """Refreshes all dashboard sections with the latest data."""
        self._refresh_status()
        self._refresh_drain()
        self._refresh_session()
        self._refresh_alerts()

    # ─────────────────────────────────────────────────────────
    # Status section
    # ─────────────────────────────────────────────────────────

    def _refresh_status(self):
        snapshots = self.db.get_recent_battery_snapshots(limit=1)
        if not snapshots:
            self.lbl_percent.configure(text="--")
            self.lbl_charging.configure(text="No data yet — waiting for first poll...")
            self.lbl_health.configure(text="Health: --")
            self.lbl_runtime.configure(text="~Calculating...")
            return

        snap = snapshots[0]
        percent = snap.percent

        # C2: Detect "no battery" mode (desktop / AC-only)
        is_desktop_mode = (snap.full_charge_capacity_mwh is None and
                           snap.design_capacity_mwh is None and
                           snap.power_plugged and percent >= 100.0)

        if is_desktop_mode:
            self.lbl_percent.configure(text="AC")
            self.lbl_charging.configure(text="No battery detected — running on AC power")
            self.lbl_health.configure(text="Health: N/A")
            self.lbl_runtime.configure(text="Plugged In")
            return

        self.lbl_percent.configure(text=f"{percent:.1f}%")
        state = "Plugged In (Charging)" if snap.power_plugged else "Discharging"
        if snap.power_plugged and percent >= 100.0:
            state = "Fully Charged"
        self.lbl_charging.configure(text=state)

        # Health — use public method
        records = self.db.get_health_records(limit=1)
        if records:
            hp = records[-1]["health_percent"]
            color = "green" if hp > 80 else ("orange" if hp > 60 else "red")
            self.lbl_health.configure(text=f"Health: {hp:.1f}%", text_color=color)
        else:
            self.lbl_health.configure(text="Health: -- (collecting data...)", text_color="gray")

        # Runtime
        runtime_str = self.runtime_estimator.get_runtime_estimate_string()
        self.lbl_runtime.configure(text=runtime_str)

    # ─────────────────────────────────────────────────────────
    # Drain section
    # ─────────────────────────────────────────────────────────

    def _refresh_drain(self):
        try:
            drain_data = self.drain_analyzer.calculate_current_drain_rate()
            drain_comp = self.drain_analyzer.compare_to_baseline()

            mw = drain_data.get("mw") or 0.0
            pct_hr = drain_data.get("percent_per_hour") or drain_comp.get("current_rate", 0.0)
            watts = mw / 1000.0 if mw else 0.0

            if watts > 0:
                rate_text = f"{watts:.1f} W\n{pct_hr:.1f} %/hr"
            else:
                rate_text = f"{pct_hr:.1f} %/hr"

            self.lbl_drain_rate.configure(text=rate_text)

            status = drain_comp.get("status", "Normal")
            if status == "Normal":
                self.lbl_drain_comparison.configure(text="Normal drain rate", text_color="green")
            else:
                ratio = drain_comp.get("ratio", 1.0)
                diff = (ratio - 1.0) * 100
                comp_text = f"+{diff:.0f}% above baseline"
                color = "orange" if status == "Elevated" else "red"
                self.lbl_drain_comparison.configure(text=comp_text, text_color=color)
        except Exception:
            self.lbl_drain_rate.configure(text="-- W\n-- %/hr")
            self.lbl_drain_comparison.configure(text="--")

    # ─────────────────────────────────────────────────────────
    # Session section
    # ─────────────────────────────────────────────────────────

    def _refresh_session(self):
        session = self.db.get_unfinished_session()
        if session:
            now = int(time.time())
            duration = max(0, now - session.start_timestamp)
            hours   = duration // 3600
            minutes = (duration % 3600) // 60
            self.lbl_session_duration.configure(text=f"Duration: {hours}h {minutes}m")
            self.lbl_session_start.configure(text=f"Started at: {session.start_percent:.1f}%")
            self.lbl_session_duration.grid()
            self.lbl_session_start.grid()
            self.lbl_session_none.pack_forget()
        else:
            self.lbl_session_duration.configure(text="Duration: --")
            self.lbl_session_start.configure(text="Started at: --%")
            self.lbl_session_none.pack(pady=(0, 10))

    # ─────────────────────────────────────────────────────────
    # Alerts section
    # ─────────────────────────────────────────────────────────

    def _refresh_alerts(self):
        try:
            with closing(self.db._get_connection()) as conn:
                cursor = conn.execute(
                    "SELECT description, severity FROM anomaly_events "
                    "WHERE acknowledged = 0 ORDER BY timestamp DESC LIMIT 3"
                )
                alerts = cursor.fetchall()

            if alerts:
                alert_text = "\n\n".join([f"• {a['description']}" for a in alerts])
                self.lbl_alerts.configure(text=alert_text, text_color="red")
            else:
                self.lbl_alerts.configure(text="No active alerts.", text_color="green")
        except Exception:
            self.lbl_alerts.configure(text="--", text_color="gray")
