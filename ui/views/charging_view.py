import customtkinter as ctk
from datetime import datetime
from core.database import Database
from analysis.charge_analyzer import ChargeAnalyzer


class ChargingView(ctk.CTkFrame):
    def __init__(self, master, db: Database, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db
        self.analyzer = ChargeAnalyzer(db)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_frame = ctk.CTkFrame(self)
        self.header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.lbl_avg_speed = ctk.CTkLabel(self.header_frame, text="Avg Charge Speed: --",
                                          font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_avg_speed.pack(pady=10)

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        for i in range(4):
            self.list_frame.grid_columnconfigure(i, weight=1)

        headers = ["Date", "Start → End", "Duration", "Avg Speed"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.list_frame, text=h,
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, pady=(5, 10), padx=5, sticky="w")

    def refresh(self):
        avg = self.analyzer.get_average_charge_speed()
        watts = avg / 1000.0 if avg else 0.0
        if watts > 0:
            self.lbl_avg_speed.configure(text=f"Historical Average Charge Speed: {watts:.1f} W")
        else:
            self.lbl_avg_speed.configure(text="Historical Average Charge Speed: -- (need more data)")

        for widget in self.list_frame.winfo_children():
            try:
                if int(widget.grid_info()["row"]) > 0:
                    widget.destroy()
            except Exception:
                pass

        history = self.analyzer.get_charging_history()

        if not history:
            ctk.CTkLabel(
                self.list_frame,
                text="No charge sessions recorded yet.\nData will appear after you plug in and charge the battery.",
                text_color="gray",
                justify="center",
            ).grid(row=1, column=0, columnspan=4, pady=40)
            return

        for idx, row in enumerate(history[:50], start=1):
            dt = datetime.fromtimestamp(row["start_timestamp"]).strftime("%b %d, %H:%M")
            start_p = row["start_percent"] or 0.0
            end_p   = row["end_percent"]   or 0.0
            dur     = row["duration_seconds"] or 0

            hours = dur // 3600
            mins  = (dur % 3600) // 60
            dur_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

            speed   = row["charge_speed_avg_mw"] or 0.0
            speed_w = speed / 1000.0

            ctk.CTkLabel(self.list_frame, text=dt).grid(row=idx, column=0, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=f"{start_p:.0f}% → {end_p:.0f}%").grid(row=idx, column=1, pady=5, padx=5, sticky="w")
            ctk.CTkLabel(self.list_frame, text=dur_str).grid(row=idx, column=2, pady=5, padx=5, sticky="w")
            speed_txt = f"{speed_w:.1f} W" if speed_w > 0 else "--"
            ctk.CTkLabel(self.list_frame, text=speed_txt).grid(row=idx, column=3, pady=5, padx=5, sticky="w")
