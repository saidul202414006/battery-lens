import logging
from typing import Optional
from core.models import BatterySnapshot, SleepEvent
from core.database import Database
from platform_adapters.base import BatteryAdapter

logger = logging.getLogger(__name__)


class SleepDetector:
    def __init__(self, db: Database, adapter: BatteryAdapter, poll_interval: int):
        self.db = db
        self.adapter = adapter
        self.poll_interval = poll_interval
        self.last_snapshot: Optional[BatterySnapshot] = None

    def process_snapshot(self, snapshot: BatterySnapshot):
        if self.last_snapshot is None:
            self.last_snapshot = snapshot
            return

        time_diff = snapshot.timestamp - self.last_snapshot.timestamp
        # If gap is more than 2× poll interval + 15s buffer, treat as a sleep/suspend event
        threshold = self.poll_interval * 2 + 15

        if time_diff > threshold:
            self._handle_sleep_detected(self.last_snapshot, snapshot)

        self.last_snapshot = snapshot

    def _handle_sleep_detected(self, before: BatterySnapshot, after: BatterySnapshot):
        """
        Handles a detected sleep gap between two consecutive snapshots.

        B4: Inserts the complete sleep event atomically in one operation.
        Previously this used insert+update (two DB calls), which left zombie records
        if the app crashed between them.
        """
        # Try to refine sleep timestamp from OS event log
        sleep_timestamp = before.timestamp
        try:
            events = self.adapter.get_sleep_events_since(before.timestamp)
            if events:
                first_event_ts = events[0].sleep_timestamp
                # Only use the OS timestamp if it falls within the plausible window
                if before.timestamp <= first_event_ts <= after.timestamp:
                    sleep_timestamp = first_event_ts
        except Exception as e:
            logger.debug(f"Could not get OS sleep events: {e}")

        # Clamp to valid window
        sleep_timestamp = max(before.timestamp, min(sleep_timestamp, after.timestamp))

        duration_minutes = (after.timestamp - sleep_timestamp) / 60.0
        if duration_minutes <= 0:
            logger.debug("Sleep duration <= 0 minutes — skipping sleep event.")
            return

        drain_during_sleep = before.percent - after.percent
        if drain_during_sleep < 0:
            drain_during_sleep = 0.0  # Plugged in while sleeping

        drain_rate_per_hour = (drain_during_sleep / duration_minutes) * 60.0

        event = SleepEvent(
            sleep_timestamp=sleep_timestamp,
            percent_before=before.percent,
            wake_timestamp=after.timestamp,
            percent_after=after.percent,
            drain_during_sleep=drain_during_sleep,
            duration_minutes=duration_minutes,
            drain_rate_per_hour=drain_rate_per_hour,
        )
        # B4: Single atomic insert — no separate update needed
        self.db.insert_sleep_event(event)
        logger.info(
            f"Sleep event recorded: {duration_minutes:.1f} min, "
            f"drain={drain_during_sleep:.1f}% ({drain_rate_per_hour:.1f}%/hr)"
        )
