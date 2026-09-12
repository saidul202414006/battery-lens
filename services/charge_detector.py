import logging
from contextlib import closing
from typing import Optional
from core.models import BatterySnapshot, ChargeSession
from core.database import Database

logger = logging.getLogger(__name__)


class ChargeDetector:
    def __init__(self, db: Database):
        self.db = db
        self.active_session_id: Optional[int] = None
        self.active_session_start_timestamp: Optional[int] = None
        self._resume_unfinished_session()

    def _resume_unfinished_session(self):
        session = self.db.get_unfinished_charge_session()
        if session:
            self.active_session_id = session.id
            self.active_session_start_timestamp = session.start_timestamp
            logger.info(f"Resumed open charge session id={session.id}")

    def process_snapshot(self, snapshot: BatterySnapshot):
        is_charging = snapshot.power_plugged

        if self.active_session_id is None:
            # Start a new charge session if plugged in and not fully charged
            if is_charging and snapshot.percent < 100.0:
                self._start_session(snapshot)
        else:
            # End when unplugged or fully charged
            if not is_charging or snapshot.percent >= 100.0:
                self._end_session(snapshot)

    def _start_session(self, snapshot: BatterySnapshot):
        session = ChargeSession(
            start_timestamp=snapshot.timestamp,
            start_percent=snapshot.percent,
        )
        self.active_session_id = self.db.insert_charge_session(session)
        self.active_session_start_timestamp = snapshot.timestamp
        logger.debug(f"Started charge session id={self.active_session_id}")

    def _end_session(self, snapshot: BatterySnapshot):
        if self.active_session_id is None:
            return

        db_session = self.db.get_charge_session_by_id(self.active_session_id)
        if not db_session:
            self.active_session_id = None
            return

        start_percent = db_session.start_percent
        duration = snapshot.timestamp - self.active_session_start_timestamp
        if duration < 0:
            duration = 0

        full_charge_reached = snapshot.percent >= 100.0

        # B2: Calculate average charge speed in mW
        charge_speed_mw = self._calculate_charge_speed_mw(
            start_percent=start_percent,
            end_percent=snapshot.percent,
            duration_seconds=duration,
            start_ts=self.active_session_start_timestamp,
            end_ts=snapshot.timestamp,
        )

        session = ChargeSession(
            id=self.active_session_id,
            start_timestamp=self.active_session_start_timestamp,
            start_percent=start_percent,
            end_timestamp=snapshot.timestamp,
            end_percent=snapshot.percent,
            duration_seconds=duration,
            charge_speed_avg_mw=charge_speed_mw,
            full_charge_reached=full_charge_reached,
        )
        self.db.update_charge_session(self.active_session_id, session)
        logger.debug(f"Ended charge session id={self.active_session_id}, speed={charge_speed_mw}")

        self.active_session_id = None
        self.active_session_start_timestamp = None

    def _calculate_charge_speed_mw(
        self,
        start_percent: float,
        end_percent: float,
        duration_seconds: int,
        start_ts: int,
        end_ts: int,
    ) -> Optional[float]:
        """
        B2: Calculates the average charge speed in mW for this session.

        Strategy 1 (preferred): Average the discharge_rate_mw values from snapshots taken
        while charging during this session. On Windows, discharge_rate_mw is estimated from
        Δ% × capacity, so it should reflect charge speed too.

        Strategy 2 (fallback): Use Δ% × capacity / duration if capacity is known.

        Strategy 3 (last resort): Use Δ% / duration as a proxy (returns None for mW).
        """
        if duration_seconds <= 0:
            return None

        # Strategy 1: From snapshot discharge_rate_mw during charge
        try:
            with closing(self.db._get_connection()) as conn:
                cursor = conn.execute(
                    """
                    SELECT discharge_rate_mw FROM battery_snapshots
                    WHERE timestamp >= ? AND timestamp <= ?
                    AND discharge_rate_mw IS NOT NULL AND discharge_rate_mw > 0
                    AND power_plugged = 1
                    """,
                    (start_ts, end_ts),
                )
                rates = [row["discharge_rate_mw"] for row in cursor.fetchall()]
            if rates:
                return sum(rates) / len(rates)
        except Exception as e:
            logger.debug(f"Strategy 1 charge speed failed: {e}")

        # Strategy 2: Δ% × capacity / duration
        try:
            with closing(self.db._get_connection()) as conn:
                cursor = conn.execute(
                    """
                    SELECT design_capacity_mwh, full_charge_capacity_mwh
                    FROM battery_snapshots
                    WHERE timestamp >= ? AND timestamp <= ?
                    AND (design_capacity_mwh IS NOT NULL OR full_charge_capacity_mwh IS NOT NULL)
                    LIMIT 1
                    """,
                    (start_ts, end_ts),
                )
                row = cursor.fetchone()
            if row:
                capacity = row["full_charge_capacity_mwh"] or row["design_capacity_mwh"]
                if capacity and capacity > 0:
                    percent_gained = max(0.0, end_percent - start_percent)
                    duration_hours = duration_seconds / 3600.0
                    if duration_hours > 0:
                        charge_mwh = (percent_gained / 100.0) * capacity
                        return charge_mwh / duration_hours  # mWh/h = mW
        except Exception as e:
            logger.debug(f"Strategy 2 charge speed failed: {e}")

        return None
