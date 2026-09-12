from typing import Dict, Any, List
from core.database import Database

class HealthAnalyzer:
    def __init__(self, db: Database):
        self.db = db

    def calculate_health_percent(self, full_charge_capacity_mwh: float, design_capacity_mwh: float) -> float:
        if not design_capacity_mwh or design_capacity_mwh <= 0:
            return 100.0
        health = (full_charge_capacity_mwh / design_capacity_mwh) * 100.0
        return min(health, 100.0) # Cap at 100% just in case

    def get_health_trend(self) -> List[Dict[str, Any]]:
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM health_records ORDER BY timestamp ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_degradation_rate(self) -> float:
        """
        Returns the estimated % health lost per 30 days (month).
        If not enough data (e.g. less than 2 points or span < 1 day), returns 0.0.
        """
        trend = self.get_health_trend()
        if len(trend) < 2:
            return 0.0
            
        first = trend[0]
        last = trend[-1]
        
        time_diff_days = (last['timestamp'] - first['timestamp']) / (24 * 3600.0)
        if time_diff_days < 1.0:
            return 0.0
            
        health_lost = first['health_percent'] - last['health_percent']
        
        rate_per_day = health_lost / time_diff_days
        rate_per_month = rate_per_day * 30.0
        
        return max(rate_per_month, 0.0)
