import time
import psutil
import logging
import os
from typing import List, Optional
from platform_adapters.base import BatteryAdapter
from core.models import BatterySnapshot, SleepEvent, ProcessSnapshot

logger = logging.getLogger(__name__)

_SYS_POWER_SUPPLY = "/sys/class/power_supply"


def _read_sys(path: str) -> Optional[str]:
    """Reads a single value from a /sys/ file, returns None if unavailable."""
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def _find_battery_path() -> Optional[str]:
    """Finds the first battery in /sys/class/power_supply/ or None."""
    try:
        entries = os.listdir(_SYS_POWER_SUPPLY)
    except OSError:
        return None
    for candidate in sorted(entries):
        full = os.path.join(_SYS_POWER_SUPPLY, candidate)
        bat_type = _read_sys(os.path.join(full, "type"))
        if bat_type and bat_type.lower() == "battery":
            return full
    return None


class LinuxAdapter(BatteryAdapter):
    def __init__(self):
        super().__init__()
        self._bat_path: Optional[str] = _find_battery_path()
        if self._bat_path:
            logger.info(f"Linux battery adapter using: {self._bat_path}")
        else:
            logger.warning("No battery found in /sys/class/power_supply/ -- running in AC-only mode.")

    def get_battery_snapshot(self) -> BatterySnapshot:
        timestamp = int(time.time())
        battery = psutil.sensors_battery()

        if not battery and not self._bat_path:
            return BatterySnapshot(
                timestamp=timestamp,
                percent=100.0,
                power_plugged=True,
                platform="linux"
            )

        percent = float(battery.percent) if battery else 100.0
        power_plugged = battery.power_plugged if battery else True

        full_charge_capacity_mwh: Optional[float] = None
        design_capacity_mwh: Optional[float] = None
        discharge_rate_mw: Optional[float] = None
        voltage_mv: Optional[float] = None
        cycle_count: Optional[int] = None

        if self._bat_path:
            energy_full = _read_sys(os.path.join(self._bat_path, "energy_full"))
            energy_full_design = _read_sys(os.path.join(self._bat_path, "energy_full_design"))
            power_now = _read_sys(os.path.join(self._bat_path, "power_now"))
            voltage_now = _read_sys(os.path.join(self._bat_path, "voltage_now"))
            cycle_count_raw = _read_sys(os.path.join(self._bat_path, "cycle_count"))

            if voltage_now:
                try:
                    voltage_mv = int(voltage_now) / 1000.0
                except (ValueError, TypeError):
                    pass

            if energy_full:
                try:
                    full_charge_capacity_mwh = int(energy_full) / 1000.0
                except (ValueError, TypeError):
                    pass

            if energy_full_design:
                try:
                    design_capacity_mwh = int(energy_full_design) / 1000.0
                except (ValueError, TypeError):
                    pass

            if power_now:
                try:
                    discharge_rate_mw = abs(int(power_now)) / 1000.0
                except (ValueError, TypeError):
                    pass

            # Fallback: charge_ prefix (uAh) -- convert using voltage
            if full_charge_capacity_mwh is None and voltage_mv:
                charge_full = _read_sys(os.path.join(self._bat_path, "charge_full"))
                charge_full_design = _read_sys(os.path.join(self._bat_path, "charge_full_design"))
                current_now = _read_sys(os.path.join(self._bat_path, "current_now"))

                if charge_full:
                    try:
                        full_charge_capacity_mwh = int(charge_full) * voltage_mv / 1_000_000.0
                    except (ValueError, TypeError):
                        pass

                if charge_full_design:
                    try:
                        design_capacity_mwh = int(charge_full_design) * voltage_mv / 1_000_000.0
                    except (ValueError, TypeError):
                        pass

                if current_now and discharge_rate_mw is None:
                    try:
                        discharge_rate_mw = abs(int(current_now)) * voltage_mv / 1_000_000.0
                    except (ValueError, TypeError):
                        pass

            if cycle_count_raw:
                try:
                    cycle_count = int(cycle_count_raw)
                except (ValueError, TypeError):
                    pass

        return BatterySnapshot(
            timestamp=timestamp,
            percent=percent,
            power_plugged=power_plugged,
            discharge_rate_mw=discharge_rate_mw,
            voltage_mv=voltage_mv,
            full_charge_capacity_mwh=full_charge_capacity_mwh,
            design_capacity_mwh=design_capacity_mwh,
            cycle_count=cycle_count,
            platform="linux"
        )

    def get_sleep_events_since(self, timestamp: int) -> List[SleepEvent]:
        """
        Returns sleep events since `timestamp` by parsing journalctl output.

        Uses two complementary strategies:
          1. `systemd-suspend.service` unit logs (most distros)
          2. Kernel PM messages (fallback for distros without systemd-suspend unit)

        Output format (`-o short-unix`) has Unix timestamps as the first field:
          1234567890.000000 hostname kernel: PM: suspend entry (deep)

        If journalctl is unavailable (non-systemd distros), returns [].
        SleepDetector's poll-gap approach still works without this data —
        this only refines the sleep timestamp.
        """
        import subprocess
        from datetime import datetime

        events: List[SleepEvent] = []

        def _parse_journalctl(args: list) -> List[int]:
            """Runs journalctl with args, returns list of Unix timestamps parsed."""
            timestamps = []
            try:
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    parts = line.split(None, 1)
                    if not parts:
                        continue
                    try:
                        ts = int(float(parts[0]))
                        timestamps.append(ts)
                    except (ValueError, IndexError):
                        continue
            except FileNotFoundError:
                logger.debug("journalctl not found — not a systemd system.")
            except Exception as e:
                logger.debug(f"journalctl call failed: {e}")
            return timestamps

        since_dt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        # Strategy 1: systemd-suspend unit logs
        suspend_timestamps = _parse_journalctl([
            "journalctl",
            "--since", since_dt,
            "-u", "systemd-suspend.service",
            "-o", "short-unix",
            "--no-pager",
            "-q",
        ])

        # Strategy 2: kernel PM messages (broader fallback)
        if not suspend_timestamps:
            suspend_timestamps = _parse_journalctl([
                "journalctl",
                "--since", since_dt,
                "-k",
                "-g", "PM: suspend entry",
                "-o", "short-unix",
                "--no-pager",
                "-q",
            ])

        for ts in sorted(set(suspend_timestamps)):
            if ts >= timestamp:
                events.append(SleepEvent(
                    sleep_timestamp=ts,
                    percent_before=0.0,  # Reconstructed from DB by SleepDetector
                ))

        return events

    def get_top_processes_by_cpu(self, limit: int = 5) -> List[ProcessSnapshot]:
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
                    mem = proc.info["memory_info"].rss / (1024 * 1024) if proc.info["memory_info"] else 0.0
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
                    memory_mb=p["mem"]
                ))
        except Exception as e:
            logger.error(f"Error getting top processes: {e}")
        return processes
