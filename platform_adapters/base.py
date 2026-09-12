from abc import ABC, abstractmethod
from typing import List, Optional
from core.models import BatterySnapshot, SleepEvent, ProcessSnapshot

class BatteryAdapter(ABC):
    """
    Abstract base class for all platform-specific battery and system data adapters.
    This defines the interface that all OS-specific implementations must follow.
    """

    @abstractmethod
    def get_battery_snapshot(self) -> BatterySnapshot:
        """
        Gathers current battery and system data and returns a normalized BatterySnapshot.
        If a specific field is unavailable on this platform, it should be set to None.
        """
        pass

    @abstractmethod
    def get_sleep_events_since(self, timestamp: int) -> List[SleepEvent]:
        """
        Retrieves sleep/wake events that occurred after the given timestamp.
        """
        pass

    @abstractmethod
    def get_top_processes_by_cpu(self, limit: int = 5) -> List[ProcessSnapshot]:
        """
        Retrieves a snapshot of the top processes currently using the most CPU.
        """
        pass
