import time
import logging
from contextlib import closing
from typing import Optional
from core.models import BatterySnapshot, SessionRecord
from core.database import Database

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, db: Database):
        self.db = db
        self.active_session_id: Optional[int] = None
        self.active_session_start_timestamp: Optional[int] = None

        # On startup, check for an unfinished session and handle it
        self._resume_or_close_stale_session()

    def _resume_or_close_stale_session(self):
        """
        On startup, look for an open (unfinished) discharge session.

        B5: If the last recorded snapshot is significantly older than the poll interval,
        the app was likely closed/restarted mid-session. Close the stale session using the
        last known snapshot data instead of leaving it forever open.
        """
        session = self.db.get_unfinished_session()
        if not session:
            return

        # Find the last snapshot to determine when data actually stopped
        snapshots = self.db.get_recent_battery_snapshots(limit=1)
        now = int(time.time())

        if snapshots:
            last_snap = snapshots[0]
            gap_seconds = now - last_snap.timestamp
            # If last snapshot is > 5 minutes old, the session is stale — close it
            if gap_seconds > 300:
                logger.info(
                    f"Stale discharge session {session.id} detected (last data {gap_seconds}s ago). "
                    f"Closing session as of last snapshot."
                )
                self._close_session_at(session, last_snap)
                return

        # Session is recent enough — resume it
        self.active_session_id = session.id
        self.active_session_start_timestamp = session.start_timestamp
        logger.info(f"Resumed open discharge session id={session.id}")

    def _close_session_at(self, session: SessionRecord, snap: BatterySnapshot):
        """Closes a session using the given snapshot as the end point."""
        duration = snap.timestamp - session.start_timestamp
        if duration < 0:
            duration = 0
        avg_drain_mw = self._calculate_avg_drain_mw(session.start_timestamp, snap.timestamp)
        closed = SessionRecord(
            id=session.id,
            start_timestamp=session.start_timestamp,
            start_percent=session.start_percent,
            end_timestamp=snap.timestamp,
            end_percent=snap.percent,
            duration_seconds=duration,
            avg_drain_rate_mw=avg_drain_mw,
        )
        self.db.update_session(closed)

    def process_snapshot(self, snapshot: BatterySnapshot):
        is_discharging = not snapshot.power_plugged

        if self.active_session_id is None:
            if is_discharging and snapshot.percent < 100.0:
                self._start_session(snapshot)
        else:
            if snapshot.power_plugged:
                self._end_session(snapshot)

    def _start_session(self, snapshot: BatterySnapshot):
        session = SessionRecord(
            start_timestamp=snapshot.timestamp,
            start_percent=snapshot.percent,
        )
        self.active_session_id = self.db.insert_session(session)
        self.active_session_start_timestamp = snapshot.timestamp
        logger.debug(f"Started discharge session id={self.active_session_id}")

    def _end_session(self, snapshot: BatterySnapshot):
        if self.active_session_id is None:
            return

        db_session = self.db.get_session_by_id(self.active_session_id)
        if not db_session:
            self.active_session_id = None
            return

        start_percent = db_session.start_percent
        duration = snapshot.timestamp - self.active_session_start_timestamp
        if duration < 0:
            duration = 0

        # B1: Calculate average drain rate in mW from snapshots in this session window
        avg_drain_mw = self._calculate_avg_drain_mw(
            self.active_session_start_timestamp, snapshot.timestamp
        )

        session = SessionRecord(
            id=self.active_session_id,
            start_timestamp=self.active_session_start_timestamp,
            start_percent=start_percent,
            end_timestamp=snapshot.timestamp,
            end_percent=snapshot.percent,
            duration_seconds=duration,
            avg_drain_rate_mw=avg_drain_mw,
        )
        self.db.update_session(session)
        logger.debug(f"Ended discharge session id={self.active_session_id}, avg_drain={avg_drain_mw}")

        self.active_session_id = None
        self.active_session_start_timestamp = None

    def _calculate_avg_drain_mw(self, start_ts: int, end_ts: int) -> Optional[float]:
        """
        B1: Estimates average drain rate in mW from discharge_rate_mw snapshots
        recorded during the given time window. Returns None if no data is available.
        """
        try:
            with closing(self.db._get_connection()) as conn:
                cursor = conn.execute(
                    """
                    SELECT discharge_rate_mw FROM battery_snapshots
                    WHERE timestamp >= ? AND timestamp <= ?
                    AND discharge_rate_mw IS NOT NULL AND discharge_rate_mw > 0
                    AND power_plugged = 0
                    """,
                    (start_ts, end_ts),
                )
                rates = [row["discharge_rate_mw"] for row in cursor.fetchall()]
            if rates:
                return sum(rates) / len(rates)
        except Exception as e:
            logger.debug(f"Could not calculate avg_drain_mw: {e}")
        return None
