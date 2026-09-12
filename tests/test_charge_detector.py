import pytest
import os
from core.database import Database
from core.models import BatterySnapshot
from services.charge_detector import ChargeDetector

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_charge_detector.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_charge_starts_when_plugged_and_not_full(test_db):
    cd = ChargeDetector(test_db)
    assert cd.active_session_id is None
    
    # Unplugged, no charge session
    cd.process_snapshot(BatterySnapshot(timestamp=1000, percent=50.0, power_plugged=False))
    assert cd.active_session_id is None
    
    # Plugged in but 100%, no active charge session (just maintaining)
    cd.process_snapshot(BatterySnapshot(timestamp=2000, percent=100.0, power_plugged=True))
    assert cd.active_session_id is None
    
    # Plugged in and below 100%, starts charge session
    cd.process_snapshot(BatterySnapshot(timestamp=3000, percent=99.0, power_plugged=True))
    assert cd.active_session_id is not None
    assert cd.active_session_start_timestamp == 3000

def test_charge_ends_when_unplugged(test_db):
    cd = ChargeDetector(test_db)
    
    cd.process_snapshot(BatterySnapshot(timestamp=1000, percent=50.0, power_plugged=True))
    session_id = cd.active_session_id
    assert session_id is not None
    
    # Continuing
    cd.process_snapshot(BatterySnapshot(timestamp=2000, percent=60.0, power_plugged=True))
    assert cd.active_session_id == session_id
    
    # Unplugged, ends session
    cd.process_snapshot(BatterySnapshot(timestamp=3000, percent=70.0, power_plugged=False))
    assert cd.active_session_id is None
    
    session = test_db.get_charge_session_by_id(session_id)
    assert session is not None
    assert session.end_timestamp == 3000
    assert session.end_percent == 70.0
    assert session.full_charge_reached is False

def test_charge_ends_when_full(test_db):
    cd = ChargeDetector(test_db)
    
    cd.process_snapshot(BatterySnapshot(timestamp=1000, percent=90.0, power_plugged=True))
    session_id = cd.active_session_id
    assert session_id is not None
    
    # Hits 100%, ends session
    cd.process_snapshot(BatterySnapshot(timestamp=2000, percent=100.0, power_plugged=True))
    assert cd.active_session_id is None
    
    session = test_db.get_charge_session_by_id(session_id)
    assert session is not None
    assert session.end_timestamp == 2000
    assert session.end_percent == 100.0
    assert session.full_charge_reached is True

def test_resume_unfinished_charge_session(test_db):
    cd1 = ChargeDetector(test_db)
    cd1.process_snapshot(BatterySnapshot(timestamp=1000, percent=20.0, power_plugged=True))
    session_id = cd1.active_session_id
    
    cd2 = ChargeDetector(test_db)
    assert cd2.active_session_id == session_id
    assert cd2.active_session_start_timestamp == 1000
