import csv
import os
from core.database import Database

class ReportExporter:
    def __init__(self, db: Database):
        self.db = db

    def export_sessions_to_csv(self, filepath: str, limit: int = 100) -> bool:
        """
        Exports the most recent sessions to a CSV file.
        Returns True if successful, False otherwise.
        """
        try:
            from contextlib import closing
            with closing(self.db._get_connection()) as conn:
                cursor = conn.execute("SELECT * FROM sessions ORDER BY end_timestamp DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                
            if not rows:
                return False
                
            headers = rows[0].keys()
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow([row[h] for h in headers])
                    
            return True
        except Exception as e:
            print(f"Failed to export CSV: {e}")
            return False
