"""
macOS Battery Adapter for Battery Lens.

Battery data is read from the kernel's IOKit via `ioreg`:
  ioreg -r -c AppleSmartBattery -n AppleSmartBattery

Key fields read:
  MaxCapacity        → mAh (full charge capacity)
  DesignCapacity     → mAh (design capacity)
  Voltage            → mV
  CycleCount
  InstantAmperage    → mA (negative = discharging, positive = charging)

Power calculation (mW):
  power_mW = |InstantAmperage_mA| × Voltage_mV / 1000

Capacity in mWh:
  mWh = capacity_mAh × Voltage_mV / 1000
"""
import re
import time
import subprocess
import logging
from typing import List, Optional, Dict, Any
from platform_adapters.base import BatteryAdapter
from core.models import BatterySnapshot, SleepEvent, ProcessSnapshot

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# ioreg parsing helpers
# ─────────────────────────────────────────────────────────────

def _run_ioreg() -> Optional[str]:
    """
    Runs `ioreg -r -c AppleSmartBattery -n AppleSmartBattery`
    and returns stdout, or None on failure.
    """
    try:
        result = subprocess.run(
            ["ioreg", "-r", "-c", "AppleSmartBattery", "-n", "AppleSmartBattery"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout
        logger.warning(f"ioreg exited {result.returncode}: {result.stderr.strip()}")
        return None
    except FileNotFoundError:
        logger.debug("ioreg not found — not running on macOS?")
        return None
    except Exception as e:
        logger.debug(f"ioreg failed: {e}")
        return None


def _parse_ioreg_int(output: str, key: str) -> Optional[int]:
    """
    Extracts an integer value from ioreg text output.
    Matches:  "Key" = <integer>  OR  "Key" = integer
    """
    pattern = rf'"{re.escape(key)}"\s*=\s*<?(\-?\d+)>?'
    m = re.search(pattern, output)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def parse_ioreg_battery(output: str) -> Dict[str, Any]:
    """
    Parses ioreg AppleSmartBattery output and returns a dict of battery fields.
    All values are in their natural ioreg units (mA, mV, mAh) — conversion
    to mW and mWh is done in get_battery_snapshot().
    """
    fields = {}
    int_keys = [
        "MaxCapacity",
        "DesignCapacity",
        "CurrentCapacity",
        "Voltage",
        "CycleCount",
        "InstantAmperage",
        "IsCharging",
        "ExternalConnected",
        "FullyCharged",
    ]
    for k in int_keys:
        v = _parse_ioreg_int(output, k)
        if v is not None:
            fields[k] = v
    return fields


# ─────────────────────────────────────────────────────────────
# Adapter
# ─────────────────────────────────────────────────────────────

class macOSAdapter(BatteryAdapter):
    """
    Battery adapter for macOS 10.15+.

    Uses ioreg for accurate battery capacity and current flow data.
    Falls back to psutil if ioreg is unavailable or fails.
    """

    def __init__(self):
        super().__init__()
        # Test ioreg on init to log early if it's unavailable
        test = _run_ioreg()
        if test is None:
            logger.warning(
                "ioreg unavailable — battery capacity and power data will be limited. "
                "Falling back to psutil-only mode."
            )
        else:
            logger.info("macOS adapter: ioreg available.")

    def get_battery_snapshot(self) -> BatterySnapshot:
        import psutil
        timestamp = int(time.time())
        battery = psutil.sensors_battery()

        # Defaults from psutil
        percent = float(battery.percent) if battery else 100.0
        power_plugged = battery.power_plugged if battery else True

        full_charge_capacity_mwh: Optional[float] = None
        design_capacity_mwh: Optional[float] = None
        discharge_rate_mw: Optional[float] = None
        voltage_mv: Optional[float] = None
        cycle_count: Optional[int] = None

        # Override with ioreg data where available
        ioreg_out = _run_ioreg()
        if ioreg_out:
            fields = parse_ioreg_battery(ioreg_out)

            raw_voltage = fields.get("Voltage")  # mV
            if raw_voltage and raw_voltage > 0:
                voltage_mv = float(raw_voltage)

            max_cap = fields.get("MaxCapacity")     # mAh
            des_cap = fields.get("DesignCapacity")  # mAh
            cur_cap = fields.get("CurrentCapacity") # mAh

            if max_cap and max_cap > 0 and voltage_mv:
                full_charge_capacity_mwh = max_cap * voltage_mv / 1000.0

            if des_cap and des_cap > 0 and voltage_mv:
                design_capacity_mwh = des_cap * voltage_mv / 1000.0

            # Recalculate percent from ioreg data (more precise than psutil)
            if cur_cap is not None and max_cap and max_cap > 0:
                percent = min(100.0, (cur_cap / max_cap) * 100.0)

            # Power flow: InstantAmperage in mA (negative = discharging)
            instant_amp = fields.get("InstantAmperage")
            if instant_amp is not None and voltage_mv:
                # power_mW = |current_mA| × voltage_mV / 1000
                discharge_rate_mw = abs(instant_amp) * voltage_mv / 1000.0

            # ioreg represents booleans as "Yes"/"No" strings, not integers.
            # Parse them separately with simple string search on the raw output.
            import re as _re
            def _ioreg_bool(key: str, raw: str) -> Optional[bool]:
                m = _re.search(rf'"{_re.escape(key)}"\s*=\s*(Yes|No)', raw)
                if m:
                    return m.group(1) == "Yes"
                return None

            ext_connected = _ioreg_bool("ExternalConnected", ioreg_out)
            fully_charged = _ioreg_bool("FullyCharged", ioreg_out)

            if ext_connected is not None:
                power_plugged = ext_connected
            if fully_charged:
                percent = 100.0

            cycle_count = fields.get("CycleCount")

        if not battery and ioreg_out is None:
            # Desktop Mac or no battery at all
            return BatterySnapshot(
                timestamp=timestamp,
                percent=100.0,
                power_plugged=True,
                platform="macos",
            )

        return BatterySnapshot(
            timestamp=timestamp,
            percent=percent,
            power_plugged=power_plugged,
            discharge_rate_mw=discharge_rate_mw,
            voltage_mv=voltage_mv,
            full_charge_capacity_mwh=full_charge_capacity_mwh,
            design_capacity_mwh=design_capacity_mwh,
            cycle_count=cycle_count,
            platform="macos",
        )

    def get_sleep_events_since(self, timestamp: int) -> List[SleepEvent]:
        """
        Reads sleep events from pmset log.

        pmset -g log output lines look like:
          2024-01-15 03:22:05 +0000 Sleep               Entering Sleep state

        We parse lines containing "Sleep" or "Wake" with timestamps.
        SleepDetector's poll-gap approach already handles macOS sleep
        detection without this — this provides refinement of sleep timestamps.
        """
        events: List[SleepEvent] = []
        try:
            from datetime import datetime, timezone

            result = subprocess.run(
                ["pmset", "-g", "log"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return events

            # Pattern: "YYYY-MM-DD HH:MM:SS +ZZZZ Sleep ..."
            sleep_pattern = re.compile(
                r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+[+-]\d{4}\s+Sleep\s+Entering Sleep"
            )

            for line in result.stdout.splitlines():
                m = sleep_pattern.search(line)
                if not m:
                    continue
                try:
                    dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=timezone.utc)
                    event_ts = int(dt.timestamp())
                    if event_ts >= timestamp:
                        events.append(SleepEvent(
                            sleep_timestamp=event_ts,
                            percent_before=0.0,  # Reconstructed from DB by SleepDetector
                        ))
                except ValueError:
                    continue

        except Exception as e:
            logger.debug(f"pmset log parsing failed: {e}")

        return sorted(events, key=lambda x: x.sleep_timestamp)

    def get_top_processes_by_cpu(self, limit: int = 5) -> List[ProcessSnapshot]:
        import psutil
        processes = []
        timestamp = int(time.time())
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    proc.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            time.sleep(0.1)

            snapshot_list = []
            for proc in psutil.process_iter(["pid", "name", "memory_info"]):
                try:
                    name = proc.info["name"] or "unknown"
                    cpu = proc.cpu_percent(interval=None)
                    mem = (
                        proc.info["memory_info"].rss / (1024 * 1024)
                        if proc.info["memory_info"] else 0.0
                    )
                    snapshot_list.append({"name": name, "cpu": cpu, "mem": mem})
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass

            snapshot_list.sort(key=lambda x: x["cpu"], reverse=True)
            for p in snapshot_list[:limit]:
                processes.append(ProcessSnapshot(
                    timestamp=timestamp,
                    session_id=0,
                    process_name=p["name"],
                    cpu_percent=p["cpu"],
                    memory_mb=p["mem"],
                ))
        except Exception as e:
            logger.error(f"Error getting top processes: {e}")
        return processes
