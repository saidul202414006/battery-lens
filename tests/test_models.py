import pytest
from core.models import (
    BatterySnapshot,
    SessionRecord,
    SleepEvent,
    ChargeSession,
    ProcessSnapshot,
    HealthRecord,
    AnomalyEvent,
    AppSettings
)

def test_battery_snapshot_creation():
    snapshot = BatterySnapshot(
        timestamp=1000,
        percent=85.5,
        power_plugged=False,
        discharge_rate_mw=-15000.0
    )
    assert snapshot.timestamp == 1000
    assert snapshot.percent == 85.5
    assert snapshot.power_plugged is False
    assert snapshot.discharge_rate_mw == -15000.0
    assert snapshot.platform == "unknown"
    assert snapshot.cycle_count is None

def test_session_record_creation():
    session = SessionRecord(
        start_timestamp=2000,
        start_percent=100.0
    )
    assert session.start_timestamp == 2000
    assert session.start_percent == 100.0
    assert session.end_timestamp is None
    
    session.end_timestamp = 3000
    session.end_percent = 80.0
    session.duration_seconds = 1000
    assert session.end_timestamp == 3000

def test_sleep_event_creation():
    event = SleepEvent(
        sleep_timestamp=4000,
        percent_before=50.0
    )
    assert event.sleep_timestamp == 4000
    assert event.is_anomalous is False

def test_charge_session_creation():
    charge = ChargeSession(
        start_timestamp=5000,
        start_percent=20.0
    )
    assert charge.full_charge_reached is False

def test_process_snapshot_creation():
    process = ProcessSnapshot(
        timestamp=6000,
        session_id=1,
        process_name="chrome.exe",
        cpu_percent=15.5,
        memory_mb=500.0
    )
    assert process.process_name == "chrome.exe"
    assert process.cpu_percent == 15.5

def test_health_record_creation():
    health = HealthRecord(
        timestamp=7000,
        full_charge_capacity_mwh=55000.0,
        design_capacity_mwh=60000.0,
        health_percent=91.6
    )
    assert health.health_percent == 91.6
    assert health.cycle_count is None

def test_anomaly_event_creation():
    anomaly = AnomalyEvent(
        timestamp=8000,
        anomaly_type="high_drain",
        severity="warning",
        description="High battery drain detected"
    )
    assert anomaly.anomaly_type == "high_drain"
    assert anomaly.acknowledged is False
    assert isinstance(anomaly.evidence, dict)
    assert len(anomaly.evidence) == 0

def test_app_settings_defaults():
    settings = AppSettings()
    assert settings.poll_interval_seconds == 30
    assert settings.sleep_drain_threshold_percent_per_hour == 3.0
    assert settings.anomaly_drain_threshold_percent_above_baseline == 30.0
    assert settings.history_retention_days == 90
