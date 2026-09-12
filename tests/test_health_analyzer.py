import pytest
import os
import time
from core.database import Database
from core.models import HealthRecord
from analysis.health_analyzer import HealthAnalyzer

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_health_analyzer.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_health_analyzer(test_db):
    analyzer = HealthAnalyzer(test_db)
    
    assert analyzer.calculate_health_percent(45000, 50000) == 90.0
    assert analyzer.calculate_health_percent(55000, 50000) == 100.0 # capped
    
    # Insert trends
    now = int(time.time())
    
    # 30 days ago: 100% health
    test_db.insert_health_record(HealthRecord(
        timestamp=now - (30 * 86400),
        full_charge_capacity_mwh=50000.0,
        design_capacity_mwh=50000.0,
        health_percent=100.0
    ))
    
    # Now: 90% health
    test_db.insert_health_record(HealthRecord(
        timestamp=now,
        full_charge_capacity_mwh=45000.0,
        design_capacity_mwh=50000.0,
        health_percent=90.0
    ))
    
    trend = analyzer.get_health_trend()
    assert len(trend) == 2
    
    degradation = analyzer.get_degradation_rate()
    # Lost 10% over 30 days -> ~10% per month
    assert abs(degradation - 10.0) < 0.1
