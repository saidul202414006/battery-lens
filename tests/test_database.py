import pytest
import os
import sqlite3
import json
from core.database import Database
from core.models import (
    BatterySnapshot,
    SessionRecord,
    SleepEvent,
    ChargeSession,
    HealthRecord,
    AnomalyEvent,
    AppSettings
)

from contextlib import closing

@pytest.fixture
def test_db(tmp_path):
    # Use a temporary file for the database
    db_path = str(tmp_path / "test_battery.db")
    db = Database(db_path)
    yield db
    # Cleanup after tests
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass  # Windows might still hold a lock briefly, tmp_path cleans up anyway

def test_database_initialization(test_db):
    assert os.path.exists(test_db.db_path)
    
    # Check tables exist
    with closing(sqlite3.connect(test_db.db_path)) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert 'battery_snapshots' in tables
        assert 'sessions' in tables
        assert 'sleep_events' in tables
        assert 'charge_sessions' in tables
        assert 'process_snapshots' in tables
        assert 'health_records' in tables
        assert 'anomaly_events' in tables
        assert 'settings' in tables

def test_battery_snapshot_crud(test_db):
    snapshot1 = BatterySnapshot(
        timestamp=1000, percent=90.0, power_plugged=False,
        discharge_rate_mw=-10000.0, platform="windows"
    )
    snapshot2 = BatterySnapshot(
        timestamp=2000, percent=88.0, power_plugged=False,
        discharge_rate_mw=-12000.0, platform="windows"
    )
    
    test_db.insert_battery_snapshot(snapshot1)
    test_db.insert_battery_snapshot(snapshot2)
    
    recent = test_db.get_recent_battery_snapshots(limit=10)
    assert len(recent) == 2
    assert recent[0].timestamp == 1000  # First chronologically
    assert recent[1].timestamp == 2000
    assert recent[1].discharge_rate_mw == -12000.0

def test_session_crud(test_db):
    session = SessionRecord(start_timestamp=1000, start_percent=100.0)
    session_id = test_db.insert_session(session)
    assert session_id is not None
    
    session.id = session_id
    session.end_timestamp = 2000
    session.end_percent = 80.0
    session.duration_seconds = 1000
    test_db.update_session(session)
    
    with sqlite3.connect(test_db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        assert row['end_timestamp'] == 2000
        assert row['end_percent'] == 80.0

def test_sleep_event_crud(test_db):
    event = SleepEvent(sleep_timestamp=3000, percent_before=50.0)
    event_id = test_db.insert_sleep_event(event)
    assert event_id is not None
    
    event.wake_timestamp = 4000
    event.percent_after = 45.0
    event.is_anomalous = True
    test_db.update_sleep_event(event_id, event)
    
    with sqlite3.connect(test_db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM sleep_events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        assert row['percent_after'] == 45.0
        assert row['is_anomalous'] == 1

def test_charge_session_crud(test_db):
    charge = ChargeSession(start_timestamp=5000, start_percent=20.0)
    charge_id = test_db.insert_charge_session(charge)
    
    charge.end_timestamp = 6000
    charge.end_percent = 100.0
    charge.full_charge_reached = True
    test_db.update_charge_session(charge_id, charge)
    
    with sqlite3.connect(test_db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM charge_sessions WHERE id = ?", (charge_id,))
        row = cursor.fetchone()
        assert row['full_charge_reached'] == 1
        assert row['end_percent'] == 100.0

def test_health_record_crud(test_db):
    record = HealthRecord(
        timestamp=7000, full_charge_capacity_mwh=50000,
        design_capacity_mwh=60000, health_percent=83.3, cycle_count=250
    )
    test_db.insert_health_record(record)
    
    with sqlite3.connect(test_db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM health_records")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]['cycle_count'] == 250

def test_anomaly_event_crud(test_db):
    anomaly = AnomalyEvent(
        timestamp=8000, anomaly_type="high_drain", severity="warning",
        description="Drain is high", evidence={"drain_rate": -25000},
        recommendation="Close Chrome"
    )
    test_db.insert_anomaly_event(anomaly)
    
    with sqlite3.connect(test_db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM anomaly_events")
        row = cursor.fetchone()
        assert row['anomaly_type'] == "high_drain"
        assert row['acknowledged'] == 0
        evidence = json.loads(row['evidence'])
        assert evidence['drain_rate'] == -25000

def test_settings_crud(test_db):
    # Test getting defaults
    settings = test_db.get_settings()
    assert settings.poll_interval_seconds == 30
    
    # Test updating a setting
    test_db.update_setting("poll_interval_seconds", "60")
    
    # Test getting updated value
    settings = test_db.get_settings()
    assert settings.poll_interval_seconds == 60
