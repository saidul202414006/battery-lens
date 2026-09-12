import sqlite3
import json
import logging
from contextlib import closing
from typing import List, Optional, Dict, Any
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
from utils.platform_utils import get_app_data_dir

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(get_app_data_dir() / "battery_lens.db")
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrent reads from UI + writes from monitor thread
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        """Initializes the database schema atomically."""
        with closing(self._get_connection()) as conn:
            with conn:  # Single transaction covers all CREATE TABLE calls
                cursor = conn.cursor()
                
                # battery_snapshots table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS battery_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        percent REAL NOT NULL,
                        power_plugged INTEGER NOT NULL,
                        discharge_rate_mw REAL,
                        voltage_mv REAL,
                        full_charge_capacity_mwh REAL,
                        design_capacity_mwh REAL,
                        cycle_count INTEGER,
                        platform TEXT NOT NULL
                    )
                ''')
                
                # sessions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        start_timestamp INTEGER NOT NULL,
                        end_timestamp INTEGER,
                        start_percent REAL NOT NULL,
                        end_percent REAL,
                        duration_seconds INTEGER,
                        energy_consumed_mwh REAL,
                        avg_drain_rate_mw REAL,
                        workload_tag TEXT
                    )
                ''')
                
                # sleep_events table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sleep_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sleep_timestamp INTEGER NOT NULL,
                        wake_timestamp INTEGER,
                        percent_before REAL NOT NULL,
                        percent_after REAL,
                        drain_during_sleep REAL,
                        duration_minutes REAL,
                        drain_rate_per_hour REAL,
                        is_anomalous INTEGER DEFAULT 0
                    )
                ''')
                
                # charge_sessions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS charge_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        start_timestamp INTEGER NOT NULL,
                        end_timestamp INTEGER,
                        start_percent REAL NOT NULL,
                        end_percent REAL,
                        duration_seconds INTEGER,
                        charge_speed_avg_mw REAL,
                        full_charge_reached INTEGER DEFAULT 0
                    )
                ''')
                
                # process_snapshots table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS process_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        session_id INTEGER,
                        process_name TEXT NOT NULL,
                        cpu_percent REAL,
                        memory_mb REAL,
                        FOREIGN KEY(session_id) REFERENCES sessions(id)
                    )
                ''')
                
                # health_records table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS health_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        full_charge_capacity_mwh REAL NOT NULL,
                        design_capacity_mwh REAL NOT NULL,
                        health_percent REAL NOT NULL,
                        cycle_count INTEGER
                    )
                ''')
                
                # anomaly_events table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS anomaly_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        anomaly_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        description TEXT,
                        evidence TEXT,
                        recommendation TEXT,
                        acknowledged INTEGER DEFAULT 0
                    )
                ''')
                
                # settings table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                ''')
                
                # Ensure all default settings exist (including run_on_startup)
                default_settings = AppSettings()
                self._ensure_setting(cursor, "poll_interval_seconds", str(default_settings.poll_interval_seconds))
                self._ensure_setting(cursor, "sleep_drain_threshold_percent_per_hour", str(default_settings.sleep_drain_threshold_percent_per_hour))
                self._ensure_setting(cursor, "anomaly_drain_threshold_percent_above_baseline", str(default_settings.anomaly_drain_threshold_percent_above_baseline))
                self._ensure_setting(cursor, "history_retention_days", str(default_settings.history_retention_days))
                self._ensure_setting(cursor, "run_on_startup", "0")
                self._ensure_setting(cursor, "first_run_done", "0")  # Welcome dialog flag

    def _ensure_setting(self, cursor: sqlite3.Cursor, key: str, default_value: str):
        cursor.execute("SELECT 1 FROM settings WHERE key = ?", (key,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, default_value))

    def insert_battery_snapshot(self, snapshot: BatterySnapshot):
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute('''
                INSERT INTO battery_snapshots (
                    timestamp, percent, power_plugged, discharge_rate_mw, 
                    voltage_mv, full_charge_capacity_mwh, design_capacity_mwh, 
                    cycle_count, platform
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot.timestamp, snapshot.percent, 1 if snapshot.power_plugged else 0,
                snapshot.discharge_rate_mw, snapshot.voltage_mv,
                snapshot.full_charge_capacity_mwh, snapshot.design_capacity_mwh,
                snapshot.cycle_count, snapshot.platform
            ))
            
    def get_recent_battery_snapshots(self, limit: int = 5) -> List[BatterySnapshot]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute('''
                SELECT * FROM battery_snapshots 
                ORDER BY timestamp DESC LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            
            return [BatterySnapshot(
                timestamp=row['timestamp'],
                percent=row['percent'],
                power_plugged=bool(row['power_plugged']),
                discharge_rate_mw=row['discharge_rate_mw'],
                voltage_mv=row['voltage_mv'],
                full_charge_capacity_mwh=row['full_charge_capacity_mwh'],
                design_capacity_mwh=row['design_capacity_mwh'],
                cycle_count=row['cycle_count'],
                platform=row['platform']
            ) for row in rows][::-1]  # Return in chronological order

    def insert_process_snapshots(self, snapshots: List[ProcessSnapshot]):
        with closing(self._get_connection()) as conn:
            with conn:
                conn.executemany('''
                INSERT INTO process_snapshots (
                    timestamp, session_id, process_name, cpu_percent, memory_mb
                ) VALUES (?, ?, ?, ?, ?)
            ''', [(
                s.timestamp, s.session_id, s.process_name, s.cpu_percent, s.memory_mb
            ) for s in snapshots])

    def insert_session(self, session: SessionRecord) -> int:
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.execute('''
                INSERT INTO sessions (start_timestamp, start_percent) 
                VALUES (?, ?)
            ''', (session.start_timestamp, session.start_percent))
            return cursor.lastrowid
            
    def update_session(self, session: SessionRecord):
        if not session.id:
            raise ValueError("Session ID required for update")
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute('''
                UPDATE sessions SET 
                    end_timestamp = ?, end_percent = ?, 
                    duration_seconds = ?, energy_consumed_mwh = ?, 
                    avg_drain_rate_mw = ?
                WHERE id = ?
            ''', (
                session.end_timestamp, session.end_percent,
                session.duration_seconds, session.energy_consumed_mwh,
                session.avg_drain_rate_mw, session.id
            ))

    def get_unfinished_session(self) -> Optional[SessionRecord]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM sessions ORDER BY start_timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            if row and row['end_timestamp'] is None:
                return SessionRecord(
                    id=row['id'],
                    start_timestamp=row['start_timestamp'],
                    start_percent=row['start_percent']
                )
        return None

    def get_session_by_id(self, session_id: int) -> Optional[SessionRecord]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return SessionRecord(
                    id=row['id'],
                    start_timestamp=row['start_timestamp'],
                    end_timestamp=row['end_timestamp'],
                    start_percent=row['start_percent'],
                    end_percent=row['end_percent'],
                    duration_seconds=row['duration_seconds'],
                    energy_consumed_mwh=row['energy_consumed_mwh'],
                    avg_drain_rate_mw=row['avg_drain_rate_mw']
                )
        return None

    def get_completed_sessions(self, limit: int = 30) -> List[SessionRecord]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE end_timestamp IS NOT NULL ORDER BY start_timestamp DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [SessionRecord(
                id=row['id'],
                start_timestamp=row['start_timestamp'],
                end_timestamp=row['end_timestamp'],
                start_percent=row['start_percent'],
                end_percent=row['end_percent'],
                duration_seconds=row['duration_seconds'],
                energy_consumed_mwh=row['energy_consumed_mwh'],
                avg_drain_rate_mw=row['avg_drain_rate_mw']
            ) for row in rows]

    def insert_sleep_event(self, event: SleepEvent) -> int:
        """Inserts a complete sleep event atomically. All fields are written in one operation."""
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.execute('''
                INSERT INTO sleep_events (
                    sleep_timestamp, percent_before, wake_timestamp, percent_after,
                    drain_during_sleep, duration_minutes, drain_rate_per_hour, is_anomalous
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.sleep_timestamp, event.percent_before,
                event.wake_timestamp, event.percent_after,
                event.drain_during_sleep, event.duration_minutes,
                event.drain_rate_per_hour, 1 if event.is_anomalous else 0
            ))
            return cursor.lastrowid

    def update_sleep_event(self, event_id: int, event: SleepEvent):
        """Updates an existing sleep event (used for legacy paths only)."""
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute('''
                UPDATE sleep_events SET
                    wake_timestamp = ?, percent_after = ?,
                    drain_during_sleep = ?, duration_minutes = ?,
                    drain_rate_per_hour = ?, is_anomalous = ?
                WHERE id = ?
            ''', (
                event.wake_timestamp, event.percent_after,
                event.drain_during_sleep, event.duration_minutes,
                event.drain_rate_per_hour, 1 if event.is_anomalous else 0,
                event_id
            ))

    def insert_charge_session(self, session: ChargeSession) -> int:
        with closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.execute('''
                INSERT INTO charge_sessions (start_timestamp, start_percent) 
                VALUES (?, ?)
            ''', (session.start_timestamp, session.start_percent))
            return cursor.lastrowid
            
    def update_charge_session(self, session_id: int, session: ChargeSession):
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute('''
                UPDATE charge_sessions SET 
                    end_timestamp = ?, end_percent = ?, 
                    duration_seconds = ?, charge_speed_avg_mw = ?, 
                    full_charge_reached = ?
                WHERE id = ?
            ''', (
                session.end_timestamp, session.end_percent,
                session.duration_seconds, session.charge_speed_avg_mw,
                1 if session.full_charge_reached else 0,
                session_id
            ))

    def get_unfinished_charge_session(self) -> Optional[ChargeSession]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM charge_sessions ORDER BY start_timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            if row and row['end_timestamp'] is None:
                return ChargeSession(
                    id=row['id'],
                    start_timestamp=row['start_timestamp'],
                    start_percent=row['start_percent']
                )
        return None

    def get_charge_session_by_id(self, session_id: int) -> Optional[ChargeSession]:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute("SELECT * FROM charge_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return ChargeSession(
                    id=row['id'],
                    start_timestamp=row['start_timestamp'],
                    start_percent=row['start_percent'],
                    end_timestamp=row['end_timestamp'],
                    end_percent=row['end_percent'],
                    duration_seconds=row['duration_seconds'],
                    charge_speed_avg_mw=row['charge_speed_avg_mw'],
                    full_charge_reached=bool(row['full_charge_reached'])
                )
        return None

    def insert_health_record(self, record: HealthRecord):
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute('''
                INSERT INTO health_records (
                    timestamp, full_charge_capacity_mwh, 
                    design_capacity_mwh, health_percent, cycle_count
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                record.timestamp, record.full_charge_capacity_mwh,
                record.design_capacity_mwh, record.health_percent,
                record.cycle_count
            ))

    def insert_anomaly_event(self, anomaly: AnomalyEvent):
        evidence_json = json.dumps(anomaly.evidence) if anomaly.evidence else "{}"
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute('''
                INSERT INTO anomaly_events (
                    timestamp, anomaly_type, severity, description,
                    evidence, recommendation, acknowledged
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                anomaly.timestamp, anomaly.anomaly_type, anomaly.severity,
                anomaly.description, evidence_json, anomaly.recommendation,
                1 if anomaly.acknowledged else 0
            ))

    def acknowledge_anomaly(self, event_id: int):
        """Marks a single anomaly event as acknowledged."""
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute("UPDATE anomaly_events SET acknowledged = 1 WHERE id = ?", (event_id,))

    def get_health_records(self, limit: int = 365) -> List[dict]:
        """Returns health records in ascending timestamp order."""
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                "SELECT * FROM health_records ORDER BY timestamp ASC LIMIT ?", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_settings(self) -> AppSettings:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute("SELECT key, value FROM settings")
            rows = cursor.fetchall()
            settings_dict = {row['key']: row['value'] for row in rows}

            # Guard against corrupted/non-numeric values by using defaults
            def _int(key, default):
                try:
                    return int(settings_dict.get(key, default))
                except (ValueError, TypeError):
                    return default

            def _float(key, default):
                try:
                    return float(settings_dict.get(key, default))
                except (ValueError, TypeError):
                    return default

            return AppSettings(
                poll_interval_seconds=max(10, min(3600, _int('poll_interval_seconds', 30))),
                sleep_drain_threshold_percent_per_hour=max(0.5, min(50.0, _float('sleep_drain_threshold_percent_per_hour', 3.0))),
                anomaly_drain_threshold_percent_above_baseline=max(5.0, min(200.0, _float('anomaly_drain_threshold_percent_above_baseline', 30.0))),
                history_retention_days=max(7, min(3650, _int('history_retention_days', 90))),
                run_on_startup=settings_dict.get('run_on_startup', '0') == '1'
            )

    def get_setting(self, key: str, default: str = "") -> str:
        """Returns a single setting value by key, or default if not found."""
        with closing(self._get_connection()) as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
            
    def update_setting(self, key: str, value: str):
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

    def purge_old_data(self, retention_days: int):
        """Deletes data older than retention_days from snapshot tables."""
        import time
        cutoff = int(time.time()) - (retention_days * 86400)
        with closing(self._get_connection()) as conn:
            with conn:
                conn.execute("DELETE FROM battery_snapshots WHERE timestamp < ?", (cutoff,))
                conn.execute("DELETE FROM process_snapshots WHERE timestamp < ?", (cutoff,))
                conn.execute("DELETE FROM anomaly_events WHERE timestamp < ? AND acknowledged = 1", (cutoff,))
                logger.info(f"Purged data older than {retention_days} days.")
