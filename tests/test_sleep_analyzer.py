import pytest
import os
from core.database import Database
from core.models import SleepEvent
from analysis.sleep_analyzer import SleepAnalyzer

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_sleep_analyzer.db")
    db = Database(db_path)
    db.update_setting("sleep_drain_threshold_percent_per_hour", "3.0")
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_sleep_analyzer(test_db):
    analyzer = SleepAnalyzer(test_db)
    
    event_normal = SleepEvent(
        sleep_timestamp=1000,
        percent_before=100.0,
        wake_timestamp=4600, # 1 hour later
        percent_after=98.0,
        drain_during_sleep=2.0,
        duration_minutes=60.0,
        drain_rate_per_hour=2.0
    )
    
    event_anomalous = SleepEvent(
        sleep_timestamp=5000,
        percent_before=98.0,
        wake_timestamp=8600, # 1 hour later
        percent_after=90.0,
        drain_during_sleep=8.0,
        duration_minutes=60.0,
        drain_rate_per_hour=8.0
    )
    
    id_normal = test_db.insert_sleep_event(event_normal)
    test_db.update_sleep_event(id_normal, event_normal)
    
    id_anom = test_db.insert_sleep_event(event_anomalous)
    test_db.update_sleep_event(id_anom, event_anomalous)
    
    history = analyzer.get_sleep_drain_history()
    assert len(history) == 2
    
    # Check normal
    res_normal = analyzer.analyze_sleep_drain(id_normal)
    assert res_normal['is_anomalous'] is False
    assert res_normal['drain_rate'] == 2.0
    
    # Check anomalous
    res_anom = analyzer.analyze_sleep_drain(id_anom)
    assert res_anom['is_anomalous'] is True
    assert res_anom['drain_rate'] == 8.0
