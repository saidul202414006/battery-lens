import pytest
import os
import time
from core.database import Database
from core.models import BatterySnapshot
from platform_adapters.base import BatteryAdapter
from services.monitor_service import MonitorService

class MockAdapter(BatteryAdapter):
    def __init__(self):
        self.call_count = 0
        
    def get_battery_snapshot(self) -> BatterySnapshot:
        self.call_count += 1
        return BatterySnapshot(
            timestamp=int(time.time()),
            percent=100.0,
            power_plugged=True,
            platform="mock"
        )
        
    def get_sleep_events_since(self, timestamp: int):
        return []
        
    def get_top_processes_by_cpu(self, limit=5):
        return []

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_monitor_service.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_monitor_service_lifecycle(test_db):
    adapter = MockAdapter()
    monitor = MonitorService(test_db, adapter)
    
    # Fast poll for test
    monitor.poll_interval = 1
    
    monitor.start()
    time.sleep(1.5)  # Wait enough for at least one or two polls
    monitor.stop()
    
    # Verify adapter was called
    assert adapter.call_count >= 1
    
    # Verify battery snapshot was inserted in db
    with test_db._get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM battery_snapshots")
        count = cursor.fetchone()[0]
        assert count >= 1
