import pytest
import os
import time
from core.database import Database
from core.models import BatterySnapshot, SessionRecord
from analysis.drain_analyzer import DrainAnalyzer

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_drain_analyzer.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_calculate_current_drain_rate(test_db):
    analyzer = DrainAnalyzer(test_db)
    
    # Needs at least 2 snapshots
    assert analyzer.calculate_current_drain_rate()['percent_per_hour'] == 0.0
    
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=1000, percent=100.0, power_plugged=False))
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=1000 + 3600, percent=90.0, power_plugged=False, discharge_rate_mw=5000.0))
    
    rate = analyzer.calculate_current_drain_rate()
    assert abs(rate['percent_per_hour'] - 10.0) < 0.01
    assert abs(rate['mw'] - 5000.0) < 0.01

def test_calculate_baseline_drain_rate(test_db):
    analyzer = DrainAnalyzer(test_db)
    assert analyzer.calculate_baseline_drain_rate() == 0.0
    
    now = int(time.time())
    
    # Insert a session from 1 day ago
    # Duration: 2 hours. Dropped 20%. Rate = 10% / hr
    test_db.insert_session(SessionRecord(
        start_timestamp=now - 86400,
        start_percent=100.0,
        id=None
    ))
    # Update it
    test_db.update_session(SessionRecord(
        id=1,
        start_timestamp=now - 86400,
        start_percent=100.0,
        end_timestamp=now - 86400 + 7200,
        end_percent=80.0,
        duration_seconds=7200
    ))
    
    # Insert a session from 2 days ago
    # Duration: 1 hour. Dropped 15%. Rate = 15% / hr
    test_db.insert_session(SessionRecord(
        start_timestamp=now - (2 * 86400),
        start_percent=80.0,
        id=None
    ))
    test_db.update_session(SessionRecord(
        id=2,
        start_timestamp=now - (2 * 86400),
        start_percent=80.0,
        end_timestamp=now - (2 * 86400) + 3600,
        end_percent=65.0,
        duration_seconds=3600
    ))
    
    # Baseline should be total percent dropped (20 + 15 = 35) / total hours (2 + 1 = 3)
    # 35 / 3 = 11.666...
    baseline = analyzer.calculate_baseline_drain_rate()
    assert abs(baseline - 11.666) < 0.01

def test_compare_to_baseline(test_db):
    analyzer = DrainAnalyzer(test_db)
    
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
    
    # Current rate setup: 15% per hour (timestamp diff is 1 hour, percent drop is 15%)
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now - 3600, percent=80.0, power_plugged=False))
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now, percent=65.0, power_plugged=False))
    
    # Compare
    comparison = analyzer.compare_to_baseline()
    assert comparison['baseline_rate'] == 10.0
    assert comparison['current_rate'] == 15.0
    assert comparison['ratio'] == 1.5
    # threshold is 30% above baseline by default, 1.5 is 50% above, so High
    assert comparison['status'] == 'High'
