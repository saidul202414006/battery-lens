import customtkinter as ctk
import json
from datetime import datetime
from core.database import Database
from core.models import AnomalyEvent
from recommendation.engine import RecommendationEngine


class AlertsView(ctk.CTkFrame):
    def __init__(self, master, db: Database, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db
        self.engine = RecommendationEngine(db)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Battery Alerts & Recommendations",
                     font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, pady=(20, 10))

        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    def refresh(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM anomaly_events ORDER BY timestamp DESC LIMIT 20"
            )
            events = [dict(row) for row in cursor.fetchall()]

        if not events:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No alerts found.\nBattery behavior is normal.",
                text_color="green",
                justify="center",
            ).grid(row=0, column=0, pady=40)
            return

        for i, event in enumerate(events):
            self._create_alert_card(self.scroll_frame, event, i)

    def _create_alert_card(self, parent, event, row_idx):
        card = ctk.CTkFrame(parent, fg_color=("gray85", "gray20"))
        card.grid(row=row_idx, column=0, pady=5, padx=5, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        color = "red" if event["severity"] == "critical" else "orange"
        dt = datetime.fromtimestamp(event["timestamp"]).strftime("%b %d, %H:%M")
        header_text = f"[{event['severity'].upper()}] {dt} — {event['description']}"

        ctk.CTkLabel(card, text=header_text, text_color=color,
                     font=ctk.CTkFont(weight="bold"),
                     wraplength=500, justify="left").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        # Build AnomalyEvent for recommendation engine
        ev_obj = AnomalyEvent(
            timestamp=event["timestamp"],
            anomaly_type=event["anomaly_type"],
            severity=event["severity"],
            description=event["description"],
            evidence=json.loads(event["evidence"]) if event.get("evidence") else {},
            id=event["id"],
            acknowledged=bool(event["acknowledged"]),
        )

        rec = self.engine.generate_for_anomaly(ev_obj)
        body_text = (
            f"Likely Cause: {rec['likely_cause']}\n"
            f"Action: {rec['action']}\n"
            f"Confidence: {rec['confidence'].capitalize()}"
        )
        ctk.CTkLabel(card, text=body_text, justify="left",
                     wraplength=500).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        if not event["acknowledged"]:
            btn = ctk.CTkButton(
                card, text="Acknowledge", width=120,
                command=lambda e_id=event["id"]: self._acknowledge_alert(e_id)
            )
            btn.grid(row=0, column=1, rowspan=2, padx=10, pady=10)
        else:
            ctk.CTkLabel(card, text="✓ Acknowledged",
                         text_color="gray").grid(row=0, column=1, rowspan=2, padx=10, pady=10)

    def _acknowledge_alert(self, event_id: int):
        # A5: Use proper DB method with correct transaction handling
        self.db.acknowledge_anomaly(event_id)
        self.refresh()
