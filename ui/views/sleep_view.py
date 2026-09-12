import customtkinter as ctk
from datetime import datetime
from core.database import Database


class SleepView(ctk.CTkFrame):
    def __init__(self, master, db: Database, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Sleep Drain History",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, pady=(20, 10))

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        for i in range(5):
            self.list_frame.grid_columnconfigure(i, weight=1)

        headers = ["Date", "Start → End", "Duration", "Drain Rate", "Status"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.list_frame, text=h,
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, pady=(5, 10), padx=5, sticky="w")

    def refresh(self):
        # Clear existing rows (keep header row 0)
        for widget in self.list_frame.winfo_children():
            try:
                if int(widget.grid_info()["row"]) > 0:
                    widget.destroy()
            except Exception:
                pass

        settings = self.db.get_settings()
        threshold = settings.sleep_drain_threshold_percent_per_hour

        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            # Only show COMPLETED sleep events (wake_timestamp IS NOT NULL)
            cursor = conn.execute(
                "SELECT * FROM sleep_events WHERE wake_timestamp IS NOT NULL "
                "ORDER BY sleep_timestamp DESC LIMIT 50"
            )
            events = [dict(row) for row in cursor.fetchall()]

        if not events:
            ctk.CTkLabel(
                self.list_frame,
                text="No sleep events recorded yet.\nData will appear after the computer sleeps and wakes.",
                text_color="gray",
                justify="center",
            ).grid(row=1, column=0, columnspan=5, pady=40)
            return

        for i, row in enumerate(events, start=1):
            dt = datetime.fromtimestamp(row["sleep_timestamp"]).strftime("%b %d, %H:%M")

            start_p = row["percent_before"] or 0.0
            end_p   = row["percent_after"]  or 0.0
            dur_mins = row["duration_minutes"] or 0.0
            rate     = row["drain_rate_per_hour"] or 0.0

            hours = int(dur_mins // 60)
            mins  = int(dur_mins % 60)
            dur_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

            status = "Normal"
            color  = "green"
            if rate > threshold:
                status = "⚠ Anomalous"
                color  = "red"

            ctk.CTkLabel(self.list_frame, text=dt).grid(row=i, column=0, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=f"{start_p:.0f}% → {end_p:.0f}%").grid(row=i, column=1, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=dur_str).grid(row=i, column=2, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=f"{rate:.1f} %/hr").grid(row=i, column=3, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=status, text_color=color).grid(row=i, column=4, pady=5, padx=5, sticky="w")
