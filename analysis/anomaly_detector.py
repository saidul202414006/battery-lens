import time
import logging
from contextlib import closing
from core.database import Database
from core.models import AnomalyEvent
from analysis.drain_analyzer import DrainAnalyzer
from analysis.charge_analyzer import ChargeAnalyzer

logger = logging.getLogger(__name__)

class AnomalyDetector:
    def __init__(self, db: Database):
        self.db = db
        self.drain_analyzer = DrainAnalyzer(db)
        self.charge_analyzer = ChargeAnalyzer(db)

    def _was_recently_alerted(self, anomaly_type: str, cooldown_seconds: int = 3600) -> bool:
        """Returns True if the same anomaly type was alerted within the cooldown period."""
        now = int(time.time())
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT timestamp FROM anomaly_events WHERE anomaly_type = ? AND acknowledged = 0 ORDER BY timestamp DESC LIMIT 1",
                (anomaly_type,)
            )
            row = cursor.fetchone()
        if row and (now - row['timestamp'] < cooldown_seconds):
            return True
        return False

    def check_high_drain_anomaly(self) -> bool:
        """
        Checks if current drain is significantly higher than baseline.
        Creates an AnomalyEvent if so. Returns True if an anomaly was created.
        """
        comparison = self.drain_analyzer.compare_to_baseline()
        
        if comparison['status'] != 'High':
            return False
            
        if self._was_recently_alerted('high_drain'):
            return False
                    
        evidence = {
            'current_rate': comparison['current_rate'],
            'baseline_rate': comparison['baseline_rate']
        }
        
        # Integrate ProcessCorrelator: identify which processes are causing the drain
        try:
            from analysis.process_correlator import ProcessCorrelator
            correlator = ProcessCorrelator(self.db)
            session = self.db.get_unfinished_session()
            if session:
                high_impact = correlator.get_high_impact_processes(session.id, cpu_threshold=5.0)
                if high_impact:
                    evidence['top_processes'] = [
                        {'name': p['process_name'], 'cpu': p['avg_cpu']} 
                        for p in high_impact[:3]
                    ]
        except Exception as e:
            logger.warning(f"Process correlation failed during anomaly check: {e}")

        now = int(time.time())
        anomaly = AnomalyEvent(
            timestamp=now,
            anomaly_type='high_drain',
            severity='warning',
            description=f"Battery is draining {comparison['ratio']:.1f}x faster than your normal average.",
            evidence=evidence,
            recommendation="Check the top processes to see what is consuming power."
        )
        self.db.insert_anomaly_event(anomaly)
        logger.info(f"High drain anomaly created: {comparison['ratio']:.1f}x baseline")
        return True

    def check_slow_charge_anomaly(self) -> bool:
        """
        Checks if the current charging session is significantly slower than average.
        """
        comparison = self.charge_analyzer.compare_current_charge_speed()
        if not comparison:
            return False
            
        if comparison['status'] != 'Slow':
            return False
            
        if self._was_recently_alerted('slow_charge'):
            return False
                    
        now = int(time.time())
        anomaly = AnomalyEvent(
            timestamp=now,
            anomaly_type='slow_charge',
            severity='warning',
            description="Your battery is charging much slower than usual.",
            evidence={
                'current_speed': comparison['current_speed'],
                'historical_average': comparison['historical_average']
            },
            recommendation="Ensure your charger is properly plugged in and providing sufficient wattage."
        )
        self.db.insert_anomaly_event(anomaly)
        logger.info("Slow charge anomaly created.")
        return True

    def check_sleep_drain_anomaly(self) -> bool:
        """
        Checks if the most recent sleep event had an abnormally high drain rate.
        Uses the sleep_drain_threshold from settings.
        """
        settings = self.db.get_settings()
        threshold = settings.sleep_drain_threshold_percent_per_hour
        
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM sleep_events WHERE wake_timestamp IS NOT NULL ORDER BY wake_timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()
            
        if not row:
            return False
            
        if row['drain_rate_per_hour'] is None:
            return False
            
        drain_rate = float(row['drain_rate_per_hour'])
        if drain_rate <= threshold:
            return False
            
        # Only alert once per sleep event (use wake_timestamp as a unique identifier)
        wake_ts = row['wake_timestamp']
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT id FROM anomaly_events WHERE anomaly_type = 'sleep_drain' AND timestamp >= ? ORDER BY timestamp DESC LIMIT 1",
                (wake_ts - 60,)  # small buffer for timestamp imprecision
            )
            existing = cursor.fetchone()
            
        if existing:
            return False  # Already alerted for this sleep event
        
        now = int(time.time())
        anomaly = AnomalyEvent(
            timestamp=now,
            anomaly_type='sleep_drain',
            severity='warning' if drain_rate < 10.0 else 'critical',
            description=f"Battery drained {row['drain_during_sleep']:.1f}% during sleep ({drain_rate:.1f}%/hr — threshold is {threshold:.1f}%/hr).",
            evidence={
                'drain_rate_per_hour': drain_rate,
                'drain_during_sleep': float(row['drain_during_sleep']),
                'duration_minutes': float(row['duration_minutes'])
            },
            recommendation="Check for apps that prevent the system from sleeping deeply."
        )
        self.db.insert_anomaly_event(anomaly)
        logger.info(f"Sleep drain anomaly created: {drain_rate:.1f}%/hr")
        return True
