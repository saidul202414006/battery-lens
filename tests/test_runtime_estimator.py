import pytest
import os
import time
from core.database import Database
from core.models import BatterySnapshot
from analysis.runtime_estimator import RuntimeEstimator

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_runtime_estimator.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_estimate_remaining_runtime(test_db):
    estimator = RuntimeEstimator(test_db)
    
    # Insert some recent snapshots to give a drain rate of 10% per hour
    now = int(time.time())
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now - 3600, percent=60.0, power_plugged=False))
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now, percent=50.0, power_plugged=False))
    
    # Current drain is 10%/hr. We are at 50%.
    # 50 / 10 = 5 hours = 300 minutes.
    minutes = estimator.estimate_remaining_runtime(50.0)
    assert abs(minutes - 300) < 5
    
    # Test string formatting
    s = estimator.get_runtime_estimate_string()
    assert "5h 0m" in s
    
    # Test plugged in
    test_db.insert_battery_snapshot(BatterySnapshot(timestamp=now+10, percent=50.1, power_plugged=True))
    s2 = estimator.get_runtime_estimate_string()
    assert s2 == "Plugged In"
