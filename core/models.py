from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class BatterySnapshot:
    timestamp: int
    percent: float
    power_plugged: bool
    discharge_rate_mw: Optional[float] = None
    voltage_mv: Optional[float] = None
    full_charge_capacity_mwh: Optional[float] = None
    design_capacity_mwh: Optional[float] = None
    cycle_count: Optional[int] = None
    platform: str = "unknown"

@dataclass
class SessionRecord:
    start_timestamp: int
    start_percent: float
    id: Optional[int] = None
    end_timestamp: Optional[int] = None
    end_percent: Optional[float] = None
    duration_seconds: Optional[int] = None
    energy_consumed_mwh: Optional[float] = None
    avg_drain_rate_mw: Optional[float] = None

@dataclass
class SleepEvent:
    sleep_timestamp: int
    percent_before: float
    id: Optional[int] = None
    wake_timestamp: Optional[int] = None
    percent_after: Optional[float] = None
    drain_during_sleep: Optional[float] = None
    duration_minutes: Optional[float] = None
    drain_rate_per_hour: Optional[float] = None
    is_anomalous: bool = False

@dataclass
class ChargeSession:
    start_timestamp: int
    start_percent: float
    id: Optional[int] = None
    end_timestamp: Optional[int] = None
    end_percent: Optional[float] = None
    duration_seconds: Optional[int] = None
    charge_speed_avg_mw: Optional[float] = None
    full_charge_reached: bool = False

@dataclass
class ProcessSnapshot:
    timestamp: int
    session_id: int
    process_name: str
    cpu_percent: float
    memory_mb: float

@dataclass
class HealthRecord:
    timestamp: int
    full_charge_capacity_mwh: float
    design_capacity_mwh: float
    health_percent: float
    cycle_count: Optional[int] = None

@dataclass
class AnomalyEvent:
    timestamp: int
    anomaly_type: str
    severity: str
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommendation: Optional[str] = None
    acknowledged: bool = False
    id: Optional[int] = None

@dataclass
class AppSettings:
    poll_interval_seconds: int = 30
    sleep_drain_threshold_percent_per_hour: float = 3.0
    anomaly_drain_threshold_percent_above_baseline: float = 30.0
    history_retention_days: int = 90
    run_on_startup: bool = False
