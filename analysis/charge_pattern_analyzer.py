from core.database import Database

class ChargePatternAnalyzer:
    def __init__(self, db: Database):
        self.db = db

    def get_charging_habits(self) -> dict:
        """
        Analyzes historical charging sessions to determine patterns.
        """
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM charge_sessions ORDER BY start_timestamp DESC LIMIT 30")
            sessions = [dict(row) for row in cursor.fetchall()]
            
        # Filter incomplete sessions
        sessions = [s for s in sessions if s['start_percent'] is not None and s['end_percent'] is not None]
            
        if not sessions:
            return {}
            
        total_sessions = len(sessions)
        avg_start = sum(s['start_percent'] for s in sessions) / total_sessions
        avg_end = sum(s['end_percent'] for s in sessions) / total_sessions
        
        full_cycles = sum(1 for s in sessions if s['start_percent'] <= 20 and s['end_percent'] >= 95)
        top_ups = sum(1 for s in sessions if (s['end_percent'] - s['start_percent']) <= 30)
        
        pattern = "Mixed"
        if top_ups > (total_sessions * 0.6):
            pattern = "Frequent Top-ups"
        elif full_cycles > (total_sessions * 0.6):
            pattern = "Deep Cycles"
            
        return {
            'average_start_percent': avg_start,
            'average_end_percent': avg_end,
            'pattern_type': pattern,
            'total_analyzed': total_sessions
        }

    def get_habit_advice(self) -> str:
        """
        Returns evidence-based advice based on charging habits.
        """
        habits = self.get_charging_habits()
        if not habits:
            return "Not enough charging data to analyze habits."
            
        advice = []
        if habits['average_start_percent'] < 15:
            advice.append("You frequently drain your battery very low (below 15%). This can accelerate chemical wear.")
        if habits['average_end_percent'] > 95 and habits['pattern_type'] == "Frequent Top-ups":
            advice.append("You frequently keep the battery at near 100%. Consider limiting charge to 80% if plugged in constantly.")
            
        if not advice:
            return "Your charging habits look healthy. Keep it up!"
            
        return " ".join(advice)
