"""
E4: Tests for charge_speed_avg_mw calculation in ChargeDetector (B2).
"""
import pytest
import os
import time
from core.database import Database
from core.models import BatterySnapshot
from services.charge_detector import ChargeDetector


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_charge_speed.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass


def test_charge_speed_calculated_from_capacity(test_db):
    """
    When capacity data is available in snapshots, charge_speed_avg_mw should be estimated.
    Strategy 2: Δ% × capacity / duration.
    """
    cd = ChargeDetector(test_db)

    # Insert a snapshot WITH capacity data before starting the charge session
    snap_before = BatterySnapshot(
        timestamp=1000, percent=40.0, power_plugged=False,
        design_capacity_mwh=60000.0, full_charge_capacity_mwh=55000.0,
        platform="test"
    )
    test_db.insert_battery_snapshot(snap_before)

    # Start charging
    snap_start = BatterySnapshot(
        timestamp=2000, percent=40.0, power_plugged=True,
        design_capacity_mwh=60000.0, full_charge_capacity_mwh=55000.0,
        platform="test"
    )
    test_db.insert_battery_snapshot(snap_start)
    cd.process_snapshot(snap_start)
    session_id = cd.active_session_id
    assert session_id is not None

    # End charging 1 hour later at 80% (gained 40%)
    # Expected speed: (40/100) * 55000 mWh / 1h = 22000 mW = 22W
    snap_end = BatterySnapshot(
        timestamp=2000 + 3600, percent=80.0, power_plugged=False,
        design_capacity_mwh=60000.0, full_charge_capacity_mwh=55000.0,
        platform="test"
    )
    test_db.insert_battery_snapshot(snap_end)
    cd.process_snapshot(snap_end)
    assert cd.active_session_id is None

    session = test_db.get_charge_session_by_id(session_id)
    assert session is not None
    # charge_speed_avg_mw should be calculated (not None)
    assert session.charge_speed_avg_mw is not None
    assert session.charge_speed_avg_mw > 0
    # Should be approximately 22000 mW (40% of 55000 mWh in 1 hour)
    assert 20000 < session.charge_speed_avg_mw < 25000, (
        f"Expected ~22000 mW, got {session.charge_speed_avg_mw}"
    )


def test_discharge_rate_estimated_in_session(test_db):
    """
    B1: avg_drain_rate_mw should be set when ending a discharge session
    if discharge_rate_mw was recorded in snapshots during the session.
    """
    from services.session_manager import SessionManager
    sm = SessionManager(test_db)

    # Insert snapshots with discharge_rate_mw
    ts = int(time.time())
    snap1 = BatterySnapshot(
        timestamp=ts, percent=90.0, power_plugged=False,
        discharge_rate_mw=10000.0, platform="test"
    )
    test_db.insert_battery_snapshot(snap1)
    sm.process_snapshot(snap1)
    session_id = sm.active_session_id
    assert session_id is not None

    snap2 = BatterySnapshot(
        timestamp=ts + 1800, percent=85.0, power_plugged=False,
        discharge_rate_mw=12000.0, platform="test"
    )
    test_db.insert_battery_snapshot(snap2)
    sm.process_snapshot(snap2)

    # Plug in to end session
    snap3 = BatterySnapshot(
        timestamp=ts + 3600, percent=80.0, power_plugged=True,
        discharge_rate_mw=None, platform="test"
    )
    test_db.insert_battery_snapshot(snap3)
    sm.process_snapshot(snap3)
    assert sm.active_session_id is None

    session = test_db.get_session_by_id(session_id)
    assert session is not None
    # avg_drain_rate_mw should be set from the two discharging snapshots
    assert session.avg_drain_rate_mw is not None
    assert session.avg_drain_rate_mw == pytest.approx(11000.0, abs=1000.0)


def test_atomic_sleep_event_insert(test_db):
    """
    B4: insert_sleep_event() stores the complete event in ONE operation.
    No zombie records with wake_timestamp IS NULL.
    """
    from core.models import SleepEvent
    event = SleepEvent(
        sleep_timestamp=5000,
        percent_before=80.0,
        wake_timestamp=9000,
        percent_after=75.0,
        drain_during_sleep=5.0,
        duration_minutes=66.7,
        drain_rate_per_hour=4.5,
    )
    event_id = test_db.insert_sleep_event(event)
    assert event_id is not None

    from contextlib import closing
    with closing(test_db._get_connection()) as conn:
        cursor = conn.execute("SELECT * FROM sleep_events WHERE id = ?", (event_id,))
        row = cursor.fetchone()

    assert row is not None
    # All fields must be present — no zombie records
    assert row["wake_timestamp"] == 9000
    assert row["percent_after"] == 75.0
    assert row["duration_minutes"] == pytest.approx(66.7, abs=0.1)
    assert row["drain_rate_per_hour"] == pytest.approx(4.5, abs=0.1)
