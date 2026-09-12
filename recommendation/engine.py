from typing import Dict, Any, List, Optional
from core.database import Database
from core.models import AnomalyEvent
from analysis.process_correlator import ProcessCorrelator

class RecommendationEngine:
    def __init__(self, db: Database):
        self.db = db
        self.process_correlator = ProcessCorrelator(db)

    def generate_for_anomaly(self, anomaly: AnomalyEvent) -> Dict[str, Any]:
        """
        Generates a structured recommendation based on the anomaly type and its evidence.
        """
        # Default structure
        recommendation = {
            'observation': anomaly.description,
            'evidence': anomaly.evidence,
            'likely_cause': 'Unknown',
            'action': 'Monitor the situation.',
            'confidence': 'unlikely'
        }

        if anomaly.anomaly_type == 'high_drain':
            self._handle_high_drain(anomaly, recommendation)
        elif anomaly.anomaly_type == 'sleep_drain':
            self._handle_sleep_drain(anomaly, recommendation)
        elif anomaly.anomaly_type == 'slow_charge':
            self._handle_slow_charge(anomaly, recommendation)
        elif anomaly.anomaly_type == 'health_decline':
            self._handle_health_decline(anomaly, recommendation)

        return recommendation

    def _handle_high_drain(self, anomaly: AnomalyEvent, rec: Dict[str, Any]):
        # Check if we have an active session to correlate with processes
        session = self.db.get_unfinished_session()
        if session:
            high_impact = self.process_correlator.get_high_impact_processes(session.id, cpu_threshold=5.0)
            if high_impact:
                # We have concrete evidence of a specific process
                top_process = high_impact[0]['process_name']
                avg_cpu = high_impact[0]['avg_cpu']
                rec['likely_cause'] = f"The process '{top_process}' is using {avg_cpu:.1f}% CPU on average."
                rec['action'] = f"Consider closing or restarting '{top_process}' if you are not actively using it."
                rec['confidence'] = 'certain'
                return

        rec['likely_cause'] = "General high system activity or background tasks."
        rec['action'] = "Lower screen brightness or turn on battery saver mode."
        rec['confidence'] = 'possible'

    def _handle_sleep_drain(self, anomaly: AnomalyEvent, rec: Dict[str, Any]):
        drain_rate = anomaly.evidence.get('drain_rate_per_hour', 0.0)
        rec['observation'] = f"Battery drained {drain_rate:.1f}% per hour while sleeping."
        
        # If it's extremely high (> 10%/hr), it's likely preventing true sleep (Modern Standby issues)
        if drain_rate > 10.0:
            rec['likely_cause'] = "System failed to enter deep sleep (Modern Standby / S0ix issue)."
            rec['action'] = "Check power settings and background apps that might wake the system (e.g., Windows Update, network activity)."
            rec['confidence'] = 'possible'
        else:
            rec['likely_cause'] = "Background background activity or connected USB devices drawing power."
            rec['action'] = "Unplug external devices before putting the system to sleep."
            rec['confidence'] = 'possible'

    def _handle_slow_charge(self, anomaly: AnomalyEvent, rec: Dict[str, Any]):
        current_speed = anomaly.evidence.get('current_speed', 0.0)
        avg_speed = anomaly.evidence.get('historical_average', 0.0)
        
        if avg_speed > 0:
            rec['observation'] = f"Charging at {current_speed:.0f} mW (normal is ~{avg_speed:.0f} mW)."
            
        if current_speed < 10000.0:  # Less than 10W
            rec['likely_cause'] = "The charger is providing very low wattage, or the cable is faulty."
            rec['action'] = "Ensure you are using the original power adapter and not charging from a low-power USB port."
            rec['confidence'] = 'certain'
        else:
            rec['likely_cause'] = "The system might be thermal throttling charging to protect battery health."
            rec['action'] = "Make sure the laptop is well-ventilated and not overheating."
            rec['confidence'] = 'possible'

    def _handle_health_decline(self, anomaly: AnomalyEvent, rec: Dict[str, Any]):
        rate = anomaly.evidence.get('degradation_rate_per_month', 0.0)
        rec['observation'] = f"Battery health is degrading at {rate:.1f}% per month."
        
        if rate > 5.0:
            rec['likely_cause'] = "Battery might be defective, old, or frequently exposed to extreme heat."
            rec['action'] = "Avoid keeping the laptop plugged in at 100% all the time and avoid hot environments."
            rec['confidence'] = 'possible'
        else:
            rec['likely_cause'] = "Natural aging of lithium-ion cells, potentially accelerated by heavy usage."
            rec['action'] = "Consider using charge limit features (e.g., cap at 80%) if your laptop supports it."
            rec['confidence'] = 'possible'
