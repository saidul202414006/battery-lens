import pytest
import os
from typing import List
from core.database import Database
from core.models import BatterySnapshot, SleepEvent
from services.sleep_detector import SleepDetector
from platform_adapters.base import BatteryAdapter

class MockAdapter(BatteryAdapter):
    def get_battery_snapshot(self):
        pass
    def get_top_processes_by_cpu(self, limit=5):
        return []
    def get_sleep_events_since(self, timestamp: int) -> List[SleepEvent]:
        # Return empty list to test the fallback logic
        return []

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_sleep_detector.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_sleep_detected_on_time_jump(test_db):
    adapter = MockAdapter()
    sd = SleepDetector(test_db, adapter, poll_interval=30)
    
    # First snapshot
    sd.process_snapshot(BatterySnapshot(timestamp=1000, percent=100.0, power_plugged=False))
    
    # Normal next snapshot (30s later)
    sd.process_snapshot(BatterySnapshot(timestamp=1030, percent=99.9, power_plugged=False))
    
    # Verify no sleep event recorded yet
    with test_db._get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM sleep_events")
        assert cursor.fetchone()[0] == 0

    # Time jump! System slept for 2 hours (7200 seconds)
    # 1030 + 7200 = 8230
    sd.process_snapshot(BatterySnapshot(timestamp=8230, percent=90.0, power_plugged=False))
    
    # Verify sleep event recorded
    with test_db._get_connection() as conn:
        cursor = conn.execute("SELECT * FROM sleep_events")
        rows = cursor.fetchall()
        assert len(rows) == 1
        event = rows[0]
        
        assert event['sleep_timestamp'] == 1030
        assert event['wake_timestamp'] == 8230
        assert event['percent_before'] == 99.9
        assert event['percent_after'] == 90.0
        assert abs(event['drain_during_sleep'] - 9.9) < 0.01
        assert event['duration_minutes'] == 7200 / 60.0
        # rate = 9.9 / 120 = 0.0825 * 60 = 4.95
        assert abs(event['drain_rate_per_hour'] - 4.95) < 0.01

def test_no_negative_drain_rate(test_db):
    adapter = MockAdapter()
    sd = SleepDetector(test_db, adapter, poll_interval=30)
    
    # First snapshot
    sd.process_snapshot(BatterySnapshot(timestamp=1000, percent=50.0, power_plugged=False))
    
    # Jump, but plugged in during sleep, so percent went UP
    sd.process_snapshot(BatterySnapshot(timestamp=5000, percent=80.0, power_plugged=True))
    
    with test_db._get_connection() as conn:
        cursor = conn.execute("SELECT * FROM sleep_events")
        rows = cursor.fetchall()
        event = rows[0]
        
        assert event['drain_during_sleep'] == 0.0
        assert event['drain_rate_per_hour'] == 0.0
