import customtkinter as ctk
from datetime import datetime
from core.database import Database
from analysis.health_analyzer import HealthAnalyzer
from analysis.health_predictor import HealthPredictor


class HealthView(ctk.CTkFrame):
    def __init__(self, master, db: Database, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db
        self.analyzer = HealthAnalyzer(db)
        self.predictor = HealthPredictor(db)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Summary card
        self.summary_frame = ctk.CTkFrame(self)
        self.summary_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.summary_frame.grid_columnconfigure(0, weight=1)
        self.summary_frame.grid_columnconfigure(1, weight=1)

        self.lbl_health = ctk.CTkLabel(
            self.summary_frame, text="Current Health: --",
            font=ctk.CTkFont(size=24, weight="bold"))
        self.lbl_health.grid(row=0, column=0, columnspan=2, pady=(15, 5))

        self.lbl_degradation = ctk.CTkLabel(self.summary_frame, text="Degradation Rate: --")
        self.lbl_degradation.grid(row=1, column=0, pady=(0, 5))

        self.lbl_prediction = ctk.CTkLabel(self.summary_frame, text="Prediction: --",
                                           font=ctk.CTkFont(slant="italic"))
        self.lbl_prediction.grid(row=1, column=1, pady=(0, 5))

        # Capacity details
        self.details_frame = ctk.CTkFrame(self)
        self.details_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.lbl_design_cap = ctk.CTkLabel(self.details_frame, text="Design Capacity: -- mWh")
        self.lbl_design_cap.pack(side="left", pady=8, padx=20)
        self.lbl_full_cap = ctk.CTkLabel(self.details_frame, text="Full Charge Capacity: -- mWh")
        self.lbl_full_cap.pack(side="left", pady=8, padx=20)

        # History trend list
        ctk.CTkLabel(self, text="Health History Trend",
                     font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, pady=(10, 0), sticky="n")

        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.grid(row=3, column=0, padx=20, pady=(5, 20), sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

    def refresh(self):
        # Use the new public DB method instead of raw _get_connection()
        records = self.db.get_health_records(limit=365)
        rate = self.analyzer.get_degradation_rate()

        if records:
            latest = records[-1]
            hp = latest["health_percent"]
            color = "green" if hp > 80 else ("orange" if hp > 60 else "red")
            self.lbl_health.configure(
                text=f"Current Health: {hp:.1f}%", text_color=color)
            self.lbl_design_cap.configure(
                text=f"Design Capacity: {latest['design_capacity_mwh']:.0f} mWh")
            self.lbl_full_cap.configure(
                text=f"Full Charge Capacity: {latest['full_charge_capacity_mwh']:.0f} mWh")

            if rate > 0:
                self.lbl_degradation.configure(
                    text=f"Degradation: {rate:.2f}%/month")
            else:
                self.lbl_degradation.configure(
                    text="Degradation: Insufficient data")

            # Prediction
            pred_str = self.predictor.get_prediction_string()
            self.lbl_prediction.configure(text=pred_str)
        else:
            self.lbl_health.configure(
                text="Current Health: -- (collecting data...)", text_color="gray")
            self.lbl_degradation.configure(text="Degradation Rate: --")
            self.lbl_prediction.configure(
                text="Connect and discharge a few times to build health history.")

        # Update trend list
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not records:
            ctk.CTkLabel(
                self.list_frame,
                text="No health records yet.\nHealth data is recorded once per day when battery capacity data is available.",
                text_color="gray",
                justify="center",
            ).grid(row=0, column=0, pady=30)
            return

        for i, record in enumerate(reversed(records)):
            dt = datetime.fromtimestamp(record["timestamp"]).strftime("%Y-%m-%d")
            hp = record["health_percent"]
            fcc = record["full_charge_capacity_mwh"]
            color = "green" if hp > 80 else ("orange" if hp > 60 else "red")
            text = f"{dt}   {hp:.1f}%   ({fcc:.0f} mWh)"
            ctk.CTkLabel(self.list_frame, text=text,
                         text_color=color).grid(row=i, column=0, pady=2, padx=10, sticky="w")
