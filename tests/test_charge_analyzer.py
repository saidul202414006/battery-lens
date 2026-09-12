import pytest
import os
import time
from core.database import Database
from core.models import ChargeSession, BatterySnapshot
from analysis.charge_analyzer import ChargeAnalyzer

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_charge_analyzer.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_charge_analyzer(test_db):
    analyzer = ChargeAnalyzer(test_db)
    
    # Empty history
    assert analyzer.get_average_charge_speed() == 0.0
    
    # Insert history
    for i in range(1, 4):
        test_db.insert_charge_session(ChargeSession(start_timestamp=0, start_percent=0, id=None))
        test_db.update_charge_session(i, ChargeSession(
            id=i,
            start_timestamp=0,
            start_percent=0,
            end_timestamp=1,
            end_percent=1,
            duration_seconds=1,
            charge_speed_avg_mw=i * 1000.0, # 1000, 2000, 3000
            full_charge_reached=True
        ))
        
    assert analyzer.get_average_charge_speed() == 2000.0
    assert len(analyzer.get_charging_history()) == 3
    
    # Test current charge speed comparison
    now = int(time.time())
    
    # Active session
    test_db.insert_charge_session(ChargeSession(
        start_timestamp=now - 400, # More than 300s duration
        start_percent=50.0,
        id=None
    ))
    
    # Battery snapshots simulating charging at 500 mW (very slow compared to 2000 average)
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now - 60, percent=50.0, power_plugged=True, discharge_rate_mw=500.0))
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now, percent=50.5, power_plugged=True, discharge_rate_mw=500.0))
    
    comparison = analyzer.compare_current_charge_speed()
    assert comparison is not None
    assert comparison['current_speed'] == 500.0
    assert comparison['historical_average'] == 2000.0
    assert comparison['status'] == 'Slow'
