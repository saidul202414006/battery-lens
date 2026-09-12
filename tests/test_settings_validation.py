"""
E3: Tests for settings input validation in SettingsView.
Tests validate() logic directly without needing a real Tk window.
"""
import pytest
import os
from core.database import Database


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_settings_val.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass


def test_settings_corruption_protection(test_db):
    """
    Verify that invalid settings written to DB are sanitized when read back.
    get_settings() must return valid defaults even if DB contains garbage.
    """
    # Simulate corrupted settings
    test_db.update_setting("poll_interval_seconds", "abc")
    test_db.update_setting("history_retention_days", "-999")
    test_db.update_setting("sleep_drain_threshold_percent_per_hour", "xyz")

    settings = test_db.get_settings()
    # poll_interval falls back to default (30) because "abc" is not parseable
    assert settings.poll_interval_seconds == 30
    # -999 is below min (7) so it clamps to 7
    assert settings.history_retention_days == 7
    # "xyz" is not parseable → default 3.0
    assert settings.sleep_drain_threshold_percent_per_hour == 3.0


def test_get_setting_single_key(test_db):
    """Test the new get_setting() single-key accessor."""
    test_db.update_setting("poll_interval_seconds", "60")
    val = test_db.get_setting("poll_interval_seconds")
    assert val == "60"


def test_get_setting_missing_key_returns_default(test_db):
    """Missing keys return the default value."""
    val = test_db.get_setting("nonexistent_key", default="fallback")
    assert val == "fallback"


def test_first_run_done_flag(test_db):
    """first_run_done starts as '0' and can be set to '1'."""
    assert test_db.get_setting("first_run_done") == "0"
    test_db.update_setting("first_run_done", "1")
    assert test_db.get_setting("first_run_done") == "1"


def test_acknowledge_anomaly(test_db):
    """Test the acknowledge_anomaly() DB method."""
    from core.models import AnomalyEvent
    anomaly = AnomalyEvent(
        timestamp=1000,
        anomaly_type="high_drain",
        severity="warning",
        description="Test anomaly",
    )
    test_db.insert_anomaly_event(anomaly)

    from contextlib import closing
    with closing(test_db._get_connection()) as conn:
        cursor = conn.execute("SELECT id, acknowledged FROM anomaly_events LIMIT 1")
        row = cursor.fetchone()
        event_id = row["id"]
        assert row["acknowledged"] == 0

    test_db.acknowledge_anomaly(event_id)

    with closing(test_db._get_connection()) as conn:
        cursor = conn.execute("SELECT acknowledged FROM anomaly_events WHERE id = ?", (event_id,))
        assert cursor.fetchone()["acknowledged"] == 1


def test_get_health_records(test_db):
    """Test the new public get_health_records() DB method."""
    from core.models import HealthRecord
    rec = HealthRecord(
        timestamp=1000,
        full_charge_capacity_mwh=50000.0,
        design_capacity_mwh=57000.0,
        health_percent=87.7,
    )
    test_db.insert_health_record(rec)
    records = test_db.get_health_records()
    assert len(records) == 1
    assert records[0]["health_percent"] == pytest.approx(87.7, abs=0.1)
