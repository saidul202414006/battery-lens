from typing import Tuple, Dict, Any
import time
from core.database import Database

class DrainAnalyzer:
    def __init__(self, db: Database):
        self.db = db

    def calculate_current_drain_rate(self) -> Dict[str, Any]:
        """
        Calculates the current drain rate using the last 5 battery snapshots.
        Returns a dictionary with %/hour and mW (if available).
        """
        snapshots = self.db.get_recent_battery_snapshots(limit=5)
        
        if len(snapshots) < 2:
            return {'percent_per_hour': 0.0, 'mw': 0.0}

        first = snapshots[0]
        last = snapshots[-1]
        
        time_diff_hours = (last.timestamp - first.timestamp) / 3600.0
        if time_diff_hours <= 0:
            return {'percent_per_hour': 0.0, 'mw': 0.0}
            
        percent_diff = first.percent - last.percent
        if percent_diff < 0:
            percent_diff = 0.0  # Charging or error
            
        percent_per_hour = percent_diff / time_diff_hours
        
        # Calculate mW if discharge_rate_mw is available
        avg_mw = 0.0
        mw_values = [s.discharge_rate_mw for s in snapshots if s.discharge_rate_mw is not None]
        if mw_values:
            avg_mw = sum(mw_values) / len(mw_values)
            
        return {
            'percent_per_hour': percent_per_hour,
            'mw': avg_mw
        }

    def calculate_baseline_drain_rate(self, days: int = 7) -> float:
        """
        Calculates the average drain rate (%/hour) from sessions over the last N days.
        """
        cutoff = int(time.time()) - (days * 24 * 3600)
        
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            # We want sessions that have finished and have duration > 0
            cursor = conn.execute('''
                SELECT start_percent, end_percent, duration_seconds 
                FROM sessions 
                WHERE end_timestamp IS NOT NULL 
                AND duration_seconds > 60 
                AND start_timestamp >= ?
            ''', (cutoff,))
            
            rows = cursor.fetchall()
            
        if not rows:
            return 0.0
            
        total_drain_percent = 0.0
        total_duration_hours = 0.0
        
        for row in rows:
            drain = row['start_percent'] - row['end_percent']
            hours = row['duration_seconds'] / 3600.0
            if drain > 0 and hours > 0:
                total_drain_percent += drain
                total_duration_hours += hours
                
        if total_duration_hours <= 0:
            return 0.0
            
        return total_drain_percent / total_duration_hours

    def compare_to_baseline(self) -> Dict[str, Any]:
        """
        Compares current drain rate to the baseline.
        Returns the ratio and a status (Normal, Elevated, High).
        """
        current = self.calculate_current_drain_rate()['percent_per_hour']
        baseline = self.calculate_baseline_drain_rate(days=7)
        
        if baseline <= 0:
            return {
                'current_rate': current,
                'baseline_rate': baseline,
                'ratio': 1.0,
                'status': 'Normal'
            }
            
        ratio = current / baseline
        
        settings = self.db.get_settings()
        anomaly_threshold = 1.0 + (settings.anomaly_drain_threshold_percent_above_baseline / 100.0)
        
        if ratio >= anomaly_threshold:
            status = 'High'
        elif ratio >= 1.15: # 15% above normal
            status = 'Elevated'
        else:
            status = 'Normal'
            
        return {
            'current_rate': current,
            'baseline_rate': baseline,
            'ratio': ratio,
            'status': status
        }
