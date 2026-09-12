import pytest
import os
from core.database import Database
from core.models import BatterySnapshot
from services.session_manager import SessionManager

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_session_mgr.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_session_starts_when_unplugged(test_db):
    sm = SessionManager(test_db)
    assert sm.active_session_id is None
    
    # Plugged in, no session should start
    sm.process_snapshot(BatterySnapshot(timestamp=1000, percent=100.0, power_plugged=True))
    assert sm.active_session_id is None
    
    # Unplugged but at 100%, some laptops keep it at 100% for a bit. Our logic: < 100% to start
    sm.process_snapshot(BatterySnapshot(timestamp=2000, percent=100.0, power_plugged=False))
    assert sm.active_session_id is None
    
    # Unplugged and drops below 100%, session should start
    sm.process_snapshot(BatterySnapshot(timestamp=3000, percent=99.0, power_plugged=False))
    assert sm.active_session_id is not None
    assert sm.active_session_start_timestamp == 3000

def test_session_ends_when_plugged_in(test_db):
    sm = SessionManager(test_db)
    
    # Start session
    sm.process_snapshot(BatterySnapshot(timestamp=1000, percent=95.0, power_plugged=False))
    session_id = sm.active_session_id
    assert session_id is not None
    
    # Continuing session
    sm.process_snapshot(BatterySnapshot(timestamp=2000, percent=90.0, power_plugged=False))
    assert sm.active_session_id == session_id
    
    # Plugged in, session should end
    sm.process_snapshot(BatterySnapshot(timestamp=3000, percent=88.0, power_plugged=True))
    assert sm.active_session_id is None
    
    # Verify in DB
    session = test_db.get_session_by_id(session_id)
    assert session is not None
    assert session.end_timestamp == 3000
    assert session.end_percent == 88.0
    assert session.duration_seconds == 2000

def test_resume_unfinished_session(test_db):
    sm1 = SessionManager(test_db)
    sm1.process_snapshot(BatterySnapshot(timestamp=1000, percent=80.0, power_plugged=False))
    session_id = sm1.active_session_id
    
    # Simulate app restart by creating a new SessionManager instance
    sm2 = SessionManager(test_db)
    assert sm2.active_session_id == session_id
    assert sm2.active_session_start_timestamp == 1000
    
    # End it
    sm2.process_snapshot(BatterySnapshot(timestamp=2000, percent=70.0, power_plugged=True))
    assert sm2.active_session_id is None
