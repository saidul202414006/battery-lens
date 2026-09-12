import time
import threading
import logging
from typing import Optional, Callable
from core.database import Database
from core.models import BatterySnapshot, HealthRecord, AnomalyEvent
from platform_adapters.base import BatteryAdapter
from services.session_manager import SessionManager
from services.charge_detector import ChargeDetector
from services.sleep_detector import SleepDetector
from analysis.anomaly_detector import AnomalyDetector

logger = logging.getLogger(__name__)

# Interval for health records: record once per 24 hours
HEALTH_RECORD_INTERVAL_SECONDS = 24 * 3600

# Run anomaly checks every N successful polls
ANOMALY_CHECK_EVERY_N_POLLS = 5

# Data retention cleanup: run every 7 days
RETENTION_CLEANUP_INTERVAL_SECONDS = 7 * 24 * 3600


class MonitorService:
    """
    Core background service. Polls the battery adapter on a fixed interval and:
    - Saves battery snapshots
    - Tracks discharge and charge sessions
    - Detects sleep events
    - Records daily health data
    - Runs anomaly detection
    - Fires notifications for detected anomalies
    """

    def __init__(self, db: Database, adapter: BatteryAdapter):
        self.db = db
        self.adapter = adapter
        self.on_anomaly_detected: Optional[Callable[[str, str], None]] = None

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        settings = db.get_settings()
        self.poll_interval: int = settings.poll_interval_seconds

        # Sub-services
        self.session_manager  = SessionManager(db)
        self.charge_detector  = ChargeDetector(db)
        self.sleep_detector   = SleepDetector(db, adapter, self.poll_interval)
        self.anomaly_detector = AnomalyDetector(db)

        # Internal state
        self._poll_count: int = 0
        self._last_successful_snapshot: Optional[BatterySnapshot] = None
        self._last_health_record_time: float = 0.0
        self._last_cleanup_time: float = time.time()
        self._alert_cooldowns: dict = {}  # anomaly_type -> last_alerted_timestamp

        # Check whether a health record should be written on startup
        self._check_startup_health_record()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.is_running:
            logger.warning("MonitorService.start() called but already running.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="MonitorService", daemon=True)
        self._thread.start()
        logger.info(f"MonitorService started (poll_interval={self.poll_interval}s).")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("MonitorService stopped.")

    def reload_settings(self):
        """Hot-reload settings from the database (called after user saves settings)."""
        settings = self.db.get_settings()
        self.poll_interval = settings.poll_interval_seconds
        self.sleep_detector.poll_interval = self.poll_interval
        logger.info(f"MonitorService settings reloaded (poll_interval={self.poll_interval}s).")

    # ─────────────────────────────────────────────────────────
    # Main poll loop
    # ─────────────────────────────────────────────────────────

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as e:
                logger.error(f"Unhandled error in monitor poll: {e}", exc_info=True)
            self._stop_event.wait(self.poll_interval)

    def _poll(self):
        """One poll cycle."""
        try:
            snapshot = self.adapter.get_battery_snapshot()
        except Exception as e:
            logger.warning(f"Adapter failed to get snapshot: {e}")
            # C3: Do NOT update last_snapshot — prevents false sleep detection on next poll
            return

        # B3: Estimate discharge_rate_mw if adapter didn't provide it
        snapshot = self._maybe_estimate_discharge_rate(snapshot)

        # Persist snapshot
        self.db.insert_battery_snapshot(snapshot)

        # Feed sub-services
        self.sleep_detector.process_snapshot(snapshot)
        self.session_manager.process_snapshot(snapshot)
        self.charge_detector.process_snapshot(snapshot)

        self._poll_count += 1
        self._last_successful_snapshot = snapshot

        # Periodic tasks
        if self._poll_count % ANOMALY_CHECK_EVERY_N_POLLS == 0:
            self._check_anomalies()

        self._check_health_record(snapshot)
        self._maybe_run_data_retention()

    # ─────────────────────────────────────────────────────────
    # Discharge rate estimation (B3)
    # ─────────────────────────────────────────────────────────

    def _maybe_estimate_discharge_rate(self, snapshot: BatterySnapshot) -> BatterySnapshot:
        """
        B3 / SILENT-2b: If the adapter did not provide discharge_rate_mw (e.g. Windows WMI),
        estimate it from Δ% × battery capacity / Δt.

        Formula:
            power_mW = (percent_dropped / 100) × capacity_mWh / time_hours

        This is mathematically equivalent because:
            capacity_mWh / 100 = mWh per 1% of charge
            mWh per hour = mW  (by definition)
        """
        if snapshot.discharge_rate_mw is not None:
            return snapshot  # Adapter provided real data — don't override

        if self._last_successful_snapshot is None:
            return snapshot  # No prior snapshot to compare against

        prev = self._last_successful_snapshot
        time_diff_hours = (snapshot.timestamp - prev.timestamp) / 3600.0
        if time_diff_hours <= 0:
            return snapshot

        if not snapshot.power_plugged:
            # Discharging
            percent_drop = prev.percent - snapshot.percent
            if percent_drop > 0:
                capacity = (
                    snapshot.full_charge_capacity_mwh
                    or snapshot.design_capacity_mwh
                    or prev.full_charge_capacity_mwh
                    or prev.design_capacity_mwh
                )
                if capacity and capacity > 0:
                    snapshot.discharge_rate_mw = (percent_drop / 100.0) * capacity / time_diff_hours
        else:
            # Charging — estimate charge rate the same way
            percent_gain = snapshot.percent - prev.percent
            if percent_gain > 0:
                capacity = (
                    snapshot.full_charge_capacity_mwh
                    or snapshot.design_capacity_mwh
                    or prev.full_charge_capacity_mwh
                    or prev.design_capacity_mwh
                )
                if capacity and capacity > 0:
                    snapshot.discharge_rate_mw = (percent_gain / 100.0) * capacity / time_diff_hours

        return snapshot

    # ─────────────────────────────────────────────────────────
    # Health records
    # ─────────────────────────────────────────────────────────

    def _check_startup_health_record(self):
        """Checks if a health record should be written on startup."""
        from contextlib import closing
        with closing(self.db._get_connection()) as conn:
            cursor = conn.execute("SELECT MAX(timestamp) as last_ts FROM health_records")
            row = cursor.fetchone()
            last_ts = row["last_ts"] if row and row["last_ts"] else 0

        self._last_health_record_time = float(last_ts)
        # Force a check immediately on startup
        self._check_health_record(None)

    def _check_health_record(self, snapshot: Optional[BatterySnapshot]):
        """Records battery health if 24+ hours have passed since the last record."""
        now = time.time()
        if now - self._last_health_record_time < HEALTH_RECORD_INTERVAL_SECONDS:
            return

        # Get the latest snapshot with capacity data
        candidate = snapshot
        if candidate is None or candidate.full_charge_capacity_mwh is None:
            recent = self.db.get_recent_battery_snapshots(limit=10)
            for snap in recent:
                if snap.full_charge_capacity_mwh and snap.design_capacity_mwh:
                    candidate = snap
                    break

        if candidate is None or candidate.full_charge_capacity_mwh is None:
            logger.info(
                "Health record: skipped — no full_charge_capacity_mwh available. "
                "This is normal on desktops, or if WMI hasn't returned capacity data yet."
            )
            return

        if candidate.design_capacity_mwh is None or candidate.design_capacity_mwh <= 0:
            logger.info("Health record: skipped — design_capacity_mwh is missing or zero.")
            return

        health_percent = min(
            100.0,
            (candidate.full_charge_capacity_mwh / candidate.design_capacity_mwh) * 100.0
        )

        record = HealthRecord(
            timestamp=int(now),
            full_charge_capacity_mwh=candidate.full_charge_capacity_mwh,
            design_capacity_mwh=candidate.design_capacity_mwh,
            health_percent=health_percent,
            cycle_count=candidate.cycle_count,
        )
        self.db.insert_health_record(record)
        self._last_health_record_time = now
        logger.info(
            f"Daily health record saved: {health_percent:.1f}% "
            f"({candidate.full_charge_capacity_mwh:.0f}/{candidate.design_capacity_mwh:.0f} mWh)"
        )

    # ─────────────────────────────────────────────────────────
    # Anomaly detection
    # ─────────────────────────────────────────────────────────

    def _check_anomalies(self):
        """Runs all anomaly checks and fires notifications for new ones."""
        try:
            anomalies = self.anomaly_detector.check_all()
            for anomaly in anomalies:
                if self._was_recently_alerted(anomaly.anomaly_type):
                    continue
                self.db.insert_anomaly_event(anomaly)
                self._mark_alerted(anomaly.anomaly_type)
                if self.on_anomaly_detected:
                    self.on_anomaly_detected(
                        f"Battery Alert: {anomaly.severity.capitalize()}",
                        anomaly.description,
                    )
                logger.info(f"Anomaly detected: {anomaly.anomaly_type} — {anomaly.description}")
        except Exception as e:
            logger.error(f"Error in anomaly check: {e}", exc_info=True)

    def _was_recently_alerted(self, anomaly_type: str, cooldown_seconds: int = 3600) -> bool:
        last = self._alert_cooldowns.get(anomaly_type, 0)
        return (time.time() - last) < cooldown_seconds

    def _mark_alerted(self, anomaly_type: str):
        self._alert_cooldowns[anomaly_type] = time.time()

    # ─────────────────────────────────────────────────────────
    # Data retention cleanup (MISS-5)
    # ─────────────────────────────────────────────────────────

    def _maybe_run_data_retention(self):
        now = time.time()
        if now - self._last_cleanup_time < RETENTION_CLEANUP_INTERVAL_SECONDS:
            return
        try:
            settings = self.db.get_settings()
            retention_days = settings.history_retention_days
            cutoff = int(now) - (retention_days * 24 * 3600)
            from contextlib import closing
            with closing(self.db._get_connection()) as conn:
                with conn:
                    conn.execute("DELETE FROM battery_snapshots WHERE timestamp < ?", (cutoff,))
                    conn.execute("DELETE FROM sessions WHERE end_timestamp < ? AND end_timestamp IS NOT NULL", (cutoff,))
                    conn.execute("DELETE FROM sleep_events WHERE sleep_timestamp < ?", (cutoff,))
                    conn.execute("DELETE FROM charge_sessions WHERE end_timestamp < ? AND end_timestamp IS NOT NULL", (cutoff,))
                    conn.execute("DELETE FROM anomaly_events WHERE timestamp < ? AND acknowledged = 1", (cutoff,))
            self._last_cleanup_time = now
            logger.info(f"Data retention cleanup: removed records older than {retention_days} days.")
        except Exception as e:
            logger.error(f"Data retention cleanup failed: {e}", exc_info=True)
