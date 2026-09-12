import time
import psutil
import logging
import platform
from typing import List, Optional
from platform_adapters.base import BatteryAdapter
from core.models import BatterySnapshot, SleepEvent, ProcessSnapshot

logger = logging.getLogger(__name__)

# Attempt Windows-only imports gracefully
_wmi = None
_win32evtlog = None

if platform.system().lower() == "windows":
    try:
        import wmi as _wmi_module
        _wmi = _wmi_module
    except ImportError:
        logger.warning("WMI module not available. Battery capacity data will be estimated from Δ%.")

    try:
        import win32evtlog as _win32evtlog_module
        _win32evtlog = _win32evtlog_module
    except ImportError:
        logger.warning("pywin32 (win32evtlog) not available. Sleep events from Windows Event Log disabled.")


class WindowsAdapter(BatteryAdapter):
    def __init__(self):
        super().__init__()
        self._wmi_conn = None
        if _wmi is not None:
            try:
                self._wmi_conn = _wmi.WMI()
            except Exception as e:
                logger.warning(f"WMI connection failed: {e}. Battery capacity data unavailable.")

    def get_battery_snapshot(self) -> BatterySnapshot:
        timestamp = int(time.time())
        battery = psutil.sensors_battery()

        if not battery:
            # Desktop PC or no battery — return AC-only state
            return BatterySnapshot(
                timestamp=timestamp,
                percent=100.0,
                power_plugged=True,
                platform="windows",
            )

        percent = float(battery.percent)
        power_plugged = battery.power_plugged

        design_capacity = None
        full_charge_capacity = None
        voltage_mv = None

        if self._wmi_conn is not None:
            try:
                batt_info = self._wmi_conn.Win32_Battery()
                if batt_info:
                    b = batt_info[0]
                    if hasattr(b, "DesignCapacity") and b.DesignCapacity is not None:
                        design_capacity = float(b.DesignCapacity)
                    if hasattr(b, "FullChargeCapacity") and b.FullChargeCapacity is not None:
                        full_charge_capacity = float(b.FullChargeCapacity)
                    if hasattr(b, "DesignVoltage") and b.DesignVoltage is not None:
                        voltage_mv = float(b.DesignVoltage)
            except Exception as e:
                logger.debug(f"WMI battery query failed: {e}")

        # Note: discharge_rate_mw is NOT set here.
        # MonitorService._maybe_estimate_discharge_rate() will estimate it from Δ% × capacity / Δt.
        return BatterySnapshot(
            timestamp=timestamp,
            percent=percent,
            power_plugged=power_plugged,
            discharge_rate_mw=None,
            voltage_mv=voltage_mv,
            full_charge_capacity_mwh=full_charge_capacity,
            design_capacity_mwh=design_capacity,
            cycle_count=None,  # Not available via basic WMI
            platform="windows",
        )

    def get_sleep_events_since(self, timestamp: int) -> List[SleepEvent]:
        """
        Reads sleep events from the Windows System Event Log.

        CRASH-7 fix: Reads at most _MAX_RECORDS records to prevent blocking the monitor
        thread on machines with large event logs.

        Note: This is used ONLY for timestamp refinement. Battery % at sleep time
        is reconstructed from the snapshot database by SleepDetector, not from here.
        """
        events = []
        if _win32evtlog is None or platform.system().lower() != "windows":
            return events

        _MAX_RECORDS = 2000  # Hard limit to prevent infinite loop on large logs

        try:
            hand = _win32evtlog.OpenEventLog("localhost", "System")
            flags = (
                _win32evtlog.EVENTLOG_BACKWARDS_READ
                | _win32evtlog.EVENTLOG_SEQUENTIAL_READ
            )
            records_read = 0

            while records_read < _MAX_RECORDS:
                record_list = _win32evtlog.ReadEventLog(hand, flags, 0)
                if not record_list:
                    break

                for record in record_list:
                    records_read += 1
                    if records_read >= _MAX_RECORDS:
                        break

                    try:
                        event_time = int(record.TimeGenerated.timestamp())
                    except Exception:
                        continue

                    # Stop reading backwards once we're past our target timestamp
                    if event_time < timestamp:
                        _win32evtlog.CloseEventLog(hand)
                        return sorted(events, key=lambda x: x.sleep_timestamp)

                    # EventID 42: System entering sleep
                    if (record.EventID == 42 and
                            record.SourceName == "Microsoft-Windows-Kernel-Power"):
                        events.append(SleepEvent(
                            sleep_timestamp=event_time,
                            percent_before=0.0,  # Will be reconstructed from DB
                        ))

            _win32evtlog.CloseEventLog(hand)

        except Exception as e:
            logger.debug(f"Error reading Windows Event Log: {e}")

        return sorted(events, key=lambda x: x.sleep_timestamp)

    def get_top_processes_by_cpu(self, limit: int = 5) -> List[ProcessSnapshot]:
        processes = []
        timestamp = int(time.time())

        try:
            # Prime CPU measurement
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
                    if name == "System Idle Process":
                        continue
                    cpu = proc.cpu_percent(interval=None)
                    mem = (proc.info["memory_info"].rss / (1024 * 1024)
                           if proc.info["memory_info"] else 0.0)
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
