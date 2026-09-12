from typing import Dict, Any, List
from core.database import Database

class SleepAnalyzer:
    def __init__(self, db: Database):
        self.db = db

    def get_sleep_drain_history(self) -> List[Dict[str, Any]]:
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM sleep_events ORDER BY sleep_timestamp DESC")
            return [dict(row) for row in cursor.fetchall()]

    def analyze_sleep_drain(self, event_id: int) -> Dict[str, Any]:
        """
        Analyzes a specific sleep event and compares its drain rate to the threshold.
        """
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM sleep_events WHERE id = ?", (event_id,))
            row = cursor.fetchone()
            
        if not row:
            return {}
            
        rate = row['drain_rate_per_hour']
        settings = self.db.get_settings()
        threshold = settings.sleep_drain_threshold_percent_per_hour
        
        is_anomalous = self.is_sleep_drain_anomalous(rate, threshold)
        
        return {
            'event_id': event_id,
            'drain_rate': rate,
            'threshold': threshold,
            'is_anomalous': is_anomalous
        }

    def is_sleep_drain_anomalous(self, drain_rate: float, threshold: float = 3.0) -> bool:
        """
        Returns True if drain > threshold (e.g. default 3.0 %/hour)
        """
        if drain_rate is None:
            return False
        return drain_rate > threshold
