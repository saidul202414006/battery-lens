import pytest
import os
import time
from core.database import Database
from core.models import BatterySnapshot, SessionRecord, ChargeSession, AppSettings
from analysis.anomaly_detector import AnomalyDetector

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_anomaly_detector.db")
    db = Database(db_path)
    
    # We need to set up the default setting threshold for anomaly to a known value
    db.update_setting("anomaly_drain_threshold_percent_above_baseline", "30.0")
    
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_high_drain_anomaly_detected(test_db):
    detector = AnomalyDetector(test_db)
    now = int(time.time())
    
    # Baseline setup: 10% per hour
    test_db.insert_session(SessionRecord(
        start_timestamp=now - 86400,
        start_percent=100.0,
        id=None
    ))
    test_db.update_session(SessionRecord(
        id=1,
        start_timestamp=now - 86400,
        start_percent=100.0,
        end_timestamp=now - 86400 + 3600,
        end_percent=90.0,
        duration_seconds=3600
    ))
    
    # Current setup: 15% per hour. Ratio = 1.5, which is > 1.30 (30% above baseline)
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now - 3600, percent=80.0, power_plugged=False))
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now, percent=65.0, power_plugged=False))
    
    assert detector.check_high_drain_anomaly() is True
    
    # Verify anomaly created in DB
    with test_db._get_connection() as conn:
        conn.row_factory = None
        cursor = conn.execute("SELECT COUNT(*) FROM anomaly_events")
        assert cursor.fetchone()[0] == 1
        
    # Running it again should NOT trigger another anomaly because of the 1-hour cooldown
    assert detector.check_high_drain_anomaly() is False

def test_slow_charge_anomaly_detected(test_db):
    detector = AnomalyDetector(test_db)
    now = int(time.time())
    
    # Setup history: Average charge speed = 10000 mW
    for i in range(2):
        test_db.insert_charge_session(ChargeSession(start_timestamp=0, start_percent=0, id=None))
        test_db.update_charge_session(i+1, ChargeSession(
            id=i+1,
            start_timestamp=0,
            start_percent=0,
            end_timestamp=1,
            end_percent=1,
            duration_seconds=1,
            charge_speed_avg_mw=10000.0,
            full_charge_reached=True
        ))
        
    # Setup active session: duration > 300s
    test_db.insert_charge_session(ChargeSession(start_timestamp=now - 400, start_percent=50.0, id=None))
    
    # Current battery snapshots showing slow charge (e.g. 4000 mW, which is < 0.5 * 10000)
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now-20, percent=50.0, power_plugged=True, discharge_rate_mw=4000.0))
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now, percent=50.1, power_plugged=True, discharge_rate_mw=4000.0))
    
    assert detector.check_slow_charge_anomaly() is True
    
    # Running it again should trigger cooldown
    assert detector.check_slow_charge_anomaly() is False
