import pytest
import os
import time
from core.database import Database
from analysis.health_predictor import HealthPredictor
from analysis.charge_pattern_analyzer import ChargePatternAnalyzer

from core.models import ChargeSession, HealthRecord

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_phase10.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_charge_pattern_analyzer(test_db):
    analyzer = ChargePatternAnalyzer(test_db)
    
    # Insert some deep cycles
    now = int(time.time())
    for i in range(10):
        session = ChargeSession(
            id=None,
            start_timestamp=now - (i * 86400),
            end_timestamp=now - (i * 86400) + 3600,
            start_percent=10.0,
            end_percent=100.0,
            duration_seconds=3600,
            charge_speed_avg_mw=20000.0
        )
        session_id = test_db.insert_charge_session(session)
        test_db.update_charge_session(session_id, session)
        
    habits = analyzer.get_charging_habits()
    assert habits['pattern_type'] == "Deep Cycles"
    
    advice = analyzer.get_habit_advice()
    assert "frequently drain your battery very low" in advice

def test_health_predictor(test_db):
    predictor = HealthPredictor(test_db)
    
    # Insert declining health records over 100 days
    now = int(time.time())
    
    for i in range(10):
        test_db.insert_health_record(HealthRecord(
            timestamp=now - ((10-i) * 864000),
            health_percent=100.0 - (i * 1.0),
            full_charge_capacity_mwh=50000.0,
            design_capacity_mwh=50000.0,
            cycle_count=10
        ))
        
    pred = predictor.predict_months_until(80.0)
    assert pred is not None
    assert pred['months'] > 0
    
    s = predictor.get_prediction_string()
    assert "Estimated" in s
