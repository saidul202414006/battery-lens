import time
from typing import Dict, Any, Optional
from core.database import Database

class ChargeAnalyzer:
    def __init__(self, db: Database):
        self.db = db

    def get_charging_history(self) -> list:
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute('''
                SELECT * FROM charge_sessions 
                WHERE end_timestamp IS NOT NULL 
                ORDER BY start_timestamp DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def compare_current_charge_speed(self) -> Optional[Dict[str, Any]]:
        """
        Compares the currently active charge session to historical average.
        """
        session = self.db.get_unfinished_charge_session()
        if not session:
            return None
            
        now = int(time.time())
        duration = now - session.start_timestamp
        if duration < 300: # Wait at least 5 mins before judging speed
            return None
            
        # Try to get current speed in mW from the latest battery snapshot
        # Since snapshot.discharge_rate_mw could be positive when charging
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute("SELECT discharge_rate_mw FROM battery_snapshots ORDER BY timestamp DESC LIMIT 5")
            rows = cursor.fetchall()
            
        rates = [r['discharge_rate_mw'] for r in rows if r['discharge_rate_mw'] is not None and r['discharge_rate_mw'] > 0]
        if not rates:
            return None
            
        current_speed = sum(rates) / len(rates)
        
        # Calculate historical average
        history = self.get_charging_history()
        past_speeds = [h['charge_speed_avg_mw'] for h in history if h.get('charge_speed_avg_mw')]
        if not past_speeds:
            return None
            
        historical_average = sum(past_speeds) / len(past_speeds)
        
        if historical_average <= 0:
            return None
            
        ratio = current_speed / historical_average
        
        status = 'Normal'
        if ratio < 0.5: # Charging at less than half the normal speed
            status = 'Slow'
            
        return {
            'current_speed': current_speed,
            'historical_average': historical_average,
            'ratio': ratio,
            'status': status
        }

    def get_average_charge_speed(self) -> float:
        """
        Returns the historical average charge speed across all completed charge sessions.
        """
        history = self.get_charging_history()
        past_speeds = [h['charge_speed_avg_mw'] for h in history if h.get('charge_speed_avg_mw')]
        if not past_speeds:
            return 0.0
            
        return sum(past_speeds) / len(past_speeds)
