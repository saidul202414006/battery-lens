from typing import List, Dict, Any
from core.database import Database

class ProcessCorrelator:
    def __init__(self, db: Database):
        self.db = db

    def get_high_impact_processes(self, session_id: int, cpu_threshold: float = 5.0) -> List[Dict[str, Any]]:
        """
        Returns a list of processes that had an average CPU percentage above the threshold
        during the given session.
        """
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            # We group by process_name and calculate the average CPU and Memory
            cursor = conn.execute('''
                SELECT process_name, 
                       AVG(cpu_percent) as avg_cpu, 
                       AVG(memory_mb) as avg_mem,
                       COUNT(*) as sample_count
                FROM process_snapshots
                WHERE session_id = ?
                GROUP BY process_name
                HAVING avg_cpu > ?
                ORDER BY avg_cpu DESC
            ''', (session_id, cpu_threshold))
            
            return [dict(row) for row in cursor.fetchall()]
