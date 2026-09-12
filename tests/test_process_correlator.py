import pytest
import os
import time
from core.database import Database
from core.models import ProcessSnapshot, SessionRecord
from analysis.process_correlator import ProcessCorrelator

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_process_correlator.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass

def test_get_high_impact_processes(test_db):
    correlator = ProcessCorrelator(test_db)
    
    # Create a session
    now = int(time.time())
    session = SessionRecord(start_timestamp=now, start_percent=100.0, id=None)
    session_id = test_db.insert_session(session)
    
    # Insert some process snapshots for this session
    snapshots = [
        ProcessSnapshot(timestamp=now, session_id=session_id, process_name="chrome.exe", cpu_percent=10.0, memory_mb=500.0),
        ProcessSnapshot(timestamp=now+10, session_id=session_id, process_name="chrome.exe", cpu_percent=12.0, memory_mb=510.0),
        ProcessSnapshot(timestamp=now+20, session_id=session_id, process_name="chrome.exe", cpu_percent=8.0, memory_mb=505.0), # Avg cpu = 10.0
        
        ProcessSnapshot(timestamp=now, session_id=session_id, process_name="idle.exe", cpu_percent=1.0, memory_mb=10.0),
        ProcessSnapshot(timestamp=now+10, session_id=session_id, process_name="idle.exe", cpu_percent=1.0, memory_mb=10.0), # Avg cpu = 1.0
        
        ProcessSnapshot(timestamp=now, session_id=session_id, process_name="heavy.exe", cpu_percent=50.0, memory_mb=1000.0),
        ProcessSnapshot(timestamp=now+10, session_id=session_id, process_name="heavy.exe", cpu_percent=60.0, memory_mb=1000.0) # Avg cpu = 55.0
    ]
    test_db.insert_process_snapshots(snapshots)
    
    # Get high impact (default > 5.0)
    high_impact = correlator.get_high_impact_processes(session_id, cpu_threshold=5.0)
    
    assert len(high_impact) == 2
    # Should be sorted by avg_cpu DESC
    assert high_impact[0]['process_name'] == "heavy.exe"
    assert abs(high_impact[0]['avg_cpu'] - 55.0) < 0.1
    assert high_impact[0]['sample_count'] == 2
    
    assert high_impact[1]['process_name'] == "chrome.exe"
    assert abs(high_impact[1]['avg_cpu'] - 10.0) < 0.1
    assert high_impact[1]['sample_count'] == 3
