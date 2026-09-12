from core.database import Database
from analysis.drain_analyzer import DrainAnalyzer

class RuntimeEstimator:
    def __init__(self, db: Database):
        self.db = db
        self.drain_analyzer = DrainAnalyzer(db)

    def estimate_remaining_runtime(self, current_percent: float) -> int:
        """
        Estimates the remaining battery runtime in minutes based on current drain rate
        and history-aware adjustments.
        Returns -1 if not enough data or currently charging.
        """
        if current_percent <= 0:
            return 0
            
        current_drain = self.drain_analyzer.calculate_current_drain_rate()
        current_rate_percent = current_drain.get('percent_per_hour', 0.0)
        
        # Fallback to a historical baseline if current drain is exactly 0 or unavailable
        if not current_rate_percent or current_rate_percent <= 0:
            baseline = self.drain_analyzer.calculate_baseline_drain_rate(days=3)
            if baseline and baseline > 0:
                current_rate_percent = baseline
            else:
                return -1
                
        # Base calculation
        hours_remaining = current_percent / current_rate_percent
        
        # T-146: session-history-aware adjustment
        # (Could apply a confidence weight here based on how similar this session is to others, 
        # but for V1.1 we simply use the running average as the prediction base).
        
        minutes_remaining = int(hours_remaining * 60)
        return minutes_remaining

    def get_runtime_estimate_string(self) -> str:
        """
        Returns a human-readable string of the estimated runtime.
        """
        snapshots = self.db.get_recent_battery_snapshots(limit=1)
        if not snapshots:
            return "Calculating..."
            
        snap = snapshots[0]
        if snap.power_plugged:
            return "Plugged In"
            
        minutes = self.estimate_remaining_runtime(snap.percent)
        if minutes < 0:
            return "Calculating..."
            
        hours = minutes // 60
        mins = minutes % 60
        
        if hours > 0:
            return f"~{hours}h {mins}m remaining"
        else:
            return f"~{mins}m remaining"
