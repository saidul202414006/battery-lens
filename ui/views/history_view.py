import customtkinter as ctk
from datetime import datetime
from core.database import Database
from analysis.drain_analyzer import DrainAnalyzer


class HistoryView(ctk.CTkFrame):
    def __init__(self, master, db: Database, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db
        self.drain_analyzer = DrainAnalyzer(db)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Discharge Session History",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, pady=(20, 10))

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        for i in range(5):
            self.list_frame.grid_columnconfigure(i, weight=1)

        headers = ["Date", "Start → End", "Duration", "Drain Rate", "Vs Baseline"]
        for i, header in enumerate(headers):
            ctk.CTkLabel(self.list_frame, text=header,
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, pady=(5, 10), padx=5, sticky="w")

    def refresh(self):
        for widget in self.list_frame.winfo_children():
            try:
                if int(widget.grid_info()["row"]) > 0:
                    widget.destroy()
            except Exception:
                pass

        baseline = self.drain_analyzer.calculate_baseline_drain_rate(days=7)

        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute("""
                SELECT start_timestamp, start_percent, end_percent, duration_seconds
                FROM sessions
                WHERE end_timestamp IS NOT NULL
                ORDER BY start_timestamp DESC LIMIT 20
            """)
            rows = cursor.fetchall()

        if not rows:
            ctk.CTkLabel(
                self.list_frame,
                text="No discharge sessions recorded yet.\nData will appear after you unplug and use the laptop on battery.",
                text_color="gray",
                justify="center",
            ).grid(row=1, column=0, columnspan=5, pady=40)
            return

        for row_idx, row in enumerate(rows, start=1):
            dt = datetime.fromtimestamp(row["start_timestamp"]).strftime("%b %d, %H:%M")

            start_p  = row["start_percent"]  or 0.0
            end_p    = row["end_percent"]    or 0.0
            dur_sec  = row["duration_seconds"] or 0

            dur_hours = dur_sec // 3600
            dur_mins  = (dur_sec % 3600) // 60
            dur_str   = f"{dur_hours}h {dur_mins}m" if dur_hours > 0 else f"{dur_mins}m"

            drain_rate = 0.0
            if dur_sec > 0:
                drain_rate = (start_p - end_p) / (dur_sec / 3600.0)

            vs_baseline = "--"
            color = "white"
            if baseline > 0:
                ratio = drain_rate / baseline
                diff  = (ratio - 1.0) * 100
                if diff > 15:
                    vs_baseline = f"+{diff:.0f}%"
                    color = "orange" if diff < 30 else "red"
                elif diff < -15:
                    vs_baseline = f"{diff:.0f}%"
                    color = "green"
                else:
                    vs_baseline = "Normal"

            ctk.CTkLabel(self.list_frame, text=dt).grid(row=row_idx, column=0, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=f"{start_p:.0f}% → {end_p:.0f}%").grid(row=row_idx, column=1, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=dur_str).grid(row=row_idx, column=2, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=f"{drain_rate:.1f} %/hr").grid(row=row_idx, column=3, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=vs_baseline, text_color=color).grid(row=row_idx, column=4, pady=5, padx=5, sticky="w")
