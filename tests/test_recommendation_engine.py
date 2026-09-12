import pytest
import os
import time
from core.database import Database
from core.models import AnomalyEvent, SessionRecord, ProcessSnapshot
from recommendation.engine import RecommendationEngine

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_recommendation.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_generate_for_high_drain_with_processes(test_db):
    engine = RecommendationEngine(test_db)
    now = int(time.time())
    
    # Active session setup
    session = SessionRecord(start_timestamp=now, start_percent=100.0, id=None)
    session_id = test_db.insert_session(session)
    
    # Process setup
    test_db.insert_process_snapshots([
        ProcessSnapshot(timestamp=now, session_id=session_id, process_name="heavy.exe", cpu_percent=25.0, memory_mb=100)
    ])
    
    anomaly = AnomalyEvent(
        timestamp=now,
        anomaly_type='high_drain',
        severity='warning',
        description="High drain detected",
        evidence={'current_rate': 20.0, 'baseline_rate': 10.0}
    )
    
    rec = engine.generate_for_anomaly(anomaly)
    
    assert rec['confidence'] == 'certain'
    assert 'heavy.exe' in rec['likely_cause']
    assert 'heavy.exe' in rec['action']

def test_generate_for_high_drain_no_processes(test_db):
    engine = RecommendationEngine(test_db)
    anomaly = AnomalyEvent(
        timestamp=int(time.time()),
        anomaly_type='high_drain',
        severity='warning',
        description="High drain detected",
        evidence={'current_rate': 20.0, 'baseline_rate': 10.0}
    )
    
    rec = engine.generate_for_anomaly(anomaly)
    
    assert rec['confidence'] == 'possible'
    assert 'General' in rec['likely_cause']
    assert 'brightness' in rec['action']

def test_generate_for_sleep_drain(test_db):
    engine = RecommendationEngine(test_db)
    
    # Extreme sleep drain
    anomaly_extreme = AnomalyEvent(
        timestamp=int(time.time()),
        anomaly_type='sleep_drain',
        severity='warning',
        description="Sleep drain",
        evidence={'drain_rate_per_hour': 15.0}
    )
    rec = engine.generate_for_anomaly(anomaly_extreme)
    assert 'Modern Standby' in rec['likely_cause']
    
    # Moderate sleep drain
    anomaly_mod = AnomalyEvent(
        timestamp=int(time.time()),
        anomaly_type='sleep_drain',
        severity='warning',
        description="Sleep drain",
        evidence={'drain_rate_per_hour': 6.0}
    )
    rec2 = engine.generate_for_anomaly(anomaly_mod)
    assert 'USB devices' in rec2['likely_cause']

def test_generate_for_slow_charge(test_db):
    engine = RecommendationEngine(test_db)
    
    # Slow charge (e.g., 5W)
    anomaly_slow = AnomalyEvent(
        timestamp=int(time.time()),
        anomaly_type='slow_charge',
        severity='warning',
        description="Slow charge",
        evidence={'current_speed': 5000.0, 'historical_average': 25000.0}
    )
    rec = engine.generate_for_anomaly(anomaly_slow)
    assert rec['confidence'] == 'certain'
    assert 'charger' in rec['likely_cause'].lower()
    
    # Slow charge (e.g. 15W, but still less than 40W baseline)
    anomaly_throttle = AnomalyEvent(
        timestamp=int(time.time()),
        anomaly_type='slow_charge',
        severity='warning',
        description="Slow charge",
        evidence={'current_speed': 15000.0, 'historical_average': 40000.0}
    )
    rec2 = engine.generate_for_anomaly(anomaly_throttle)
    assert rec2['confidence'] == 'possible'
    assert 'thermal throttling' in rec2['likely_cause'].lower()
