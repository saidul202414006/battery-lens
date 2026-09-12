from core.database import Database
from analysis.health_analyzer import HealthAnalyzer
import math

class HealthPredictor:
    def __init__(self, db: Database):
        self.db = db
        self.analyzer = HealthAnalyzer(db)

    def predict_months_until(self, target_health_percent: float = 80.0) -> dict:
        """
        Uses simple linear regression on historical health records to predict
        when the battery health will drop to target_health_percent.
        Returns a dict with estimate and confidence interval.
        """
        trend = self.analyzer.get_health_trend()
        if len(trend) < 5:
            return None # Need more data for a meaningful prediction

        # x: timestamp (in days), y: health_percent
        first_ts = trend[0]['timestamp']
        
        n = len(trend)
        sum_x = 0
        sum_y = 0
        sum_xy = 0
        sum_xx = 0
        
        for record in trend:
            x = (record['timestamp'] - first_ts) / 86400.0 # days
            y = record['health_percent']
            
            sum_x += x
            sum_y += y
            sum_xy += (x * y)
            sum_xx += (x * x)
            
        denominator = (n * sum_xx) - (sum_x * sum_x)
        if denominator == 0:
            return None
            
        slope = ((n * sum_xy) - (sum_x * sum_y)) / denominator
        
        # If health is increasing or flat, we can't predict degradation
        if slope >= -0.001: 
            return None
            
        intercept = (sum_y - (slope * sum_x)) / n
        
        # We want to find x when y = target_health_percent
        # target = slope * x + intercept
        # x = (target - intercept) / slope
        target_x_days = (target_health_percent - intercept) / slope
        
        # How many days from the LAST record?
        last_x_days = (trend[-1]['timestamp'] - first_ts) / 86400.0
        days_remaining = target_x_days - last_x_days
        
        if days_remaining <= 0:
            return {'months': 0, 'range': (0, 0)}
            
        months_remaining = days_remaining / 30.44
        
        # Simple confidence interval heuristic: fewer data points = wider range
        # Also higher slope variance (not fully calculated here) = wider range
        margin = max(1.0, months_remaining * (0.2 + (10 / n)))
        
        return {
            'months': months_remaining,
            'range': (max(0, months_remaining - margin), months_remaining + margin)
        }

    def get_prediction_string(self) -> str:
        pred = self.predict_months_until(80.0)
        if not pred:
            return "Insufficient degradation data to predict lifespan."
            
        months = int(round(pred['months']))
        low = int(round(pred['range'][0]))
        high = int(round(pred['range'][1]))
        
        return f"Estimated {low}-{high} months until 80% capacity based on current trend."
