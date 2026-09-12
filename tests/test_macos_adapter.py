"""
P9b: Tests for macOS adapter — specifically the ioreg output parser.

The ioreg parser (parse_ioreg_battery, _parse_ioreg_int) is pure Python
string processing, so these tests run on all platforms regardless of OS.
"""
import pytest
from unittest.mock import patch
from platform_adapters.macos_adapter import parse_ioreg_battery, _parse_ioreg_int

# ─────────────────────────────────────────────────────────────
# Representative ioreg output sample (from a real MacBook)
# ─────────────────────────────────────────────────────────────

SAMPLE_IOREG = """
+-o AppleSmartBattery  <class AppleSmartBattery>
    {
      "MaxCapacity" = 5800
      "DesignCapacity" = 6331
      "CurrentCapacity" = 4640
      "Voltage" = 12342
      "CycleCount" = 142
      "InstantAmperage" = -1823
      "IsCharging" = No
      "ExternalConnected" = No
      "FullyCharged" = No
    }
"""

SAMPLE_IOREG_CHARGING = """
+-o AppleSmartBattery  <class AppleSmartBattery>
    {
      "MaxCapacity" = 5800
      "DesignCapacity" = 6331
      "CurrentCapacity" = 4320
      "Voltage" = 12500
      "CycleCount" = 142
      "InstantAmperage" = 2100
      "IsCharging" = Yes
      "ExternalConnected" = Yes
      "FullyCharged" = No
    }
"""

SAMPLE_IOREG_FULL = """
+-o AppleSmartBattery  <class AppleSmartBattery>
    {
      "MaxCapacity" = 5800
      "DesignCapacity" = 6331
      "CurrentCapacity" = 5800
      "Voltage" = 12400
      "CycleCount" = 142
      "InstantAmperage" = 0
      "IsCharging" = No
      "ExternalConnected" = Yes
      "FullyCharged" = Yes
    }
"""


# ─────────────────────────────────────────────────────────────
# _parse_ioreg_int
# ─────────────────────────────────────────────────────────────

def test_parse_int_basic():
    out = '"MaxCapacity" = 5800'
    assert _parse_ioreg_int(out, "MaxCapacity") == 5800


def test_parse_int_negative():
    out = '"InstantAmperage" = -1823'
    assert _parse_ioreg_int(out, "InstantAmperage") == -1823


def test_parse_int_missing_key_returns_none():
    assert _parse_ioreg_int('"Voltage" = 12000', "NonExistent") is None


def test_parse_int_angle_bracket_format():
    """Some ioreg fields use <integer> notation."""
    out = '"CycleCount" = <142>'
    assert _parse_ioreg_int(out, "CycleCount") == 142


# ─────────────────────────────────────────────────────────────
# parse_ioreg_battery — field extraction
# ─────────────────────────────────────────────────────────────

def test_parse_ioreg_full_sample():
    fields = parse_ioreg_battery(SAMPLE_IOREG)
    assert fields["MaxCapacity"] == 5800
    assert fields["DesignCapacity"] == 6331
    assert fields["CurrentCapacity"] == 4640
    assert fields["Voltage"] == 12342
    assert fields["CycleCount"] == 142
    assert fields["InstantAmperage"] == -1823


def test_parse_ioreg_charging_sample():
    fields = parse_ioreg_battery(SAMPLE_IOREG_CHARGING)
    # InstantAmperage IS an integer — should be present
    assert fields["InstantAmperage"] == 2100
    # "Yes"/"No" strings are not parseable as integers, so these keys are absent.
    # get_battery_snapshot() handles the "ExternalConnected"/"IsCharging" boolean
    # text fields separately via regex on the raw output.
    assert "ExternalConnected" not in fields  # "Yes" is not an integer


def test_parse_ioreg_empty():
    """Empty string returns empty dict (no crash)."""
    fields = parse_ioreg_battery("")
    assert isinstance(fields, dict)
    # All optional fields should simply be missing
    assert "MaxCapacity" not in fields


def test_parse_ioreg_missing_fields():
    """Partial ioreg output — missing fields should not raise."""
    partial = '"MaxCapacity" = 5000\n"CycleCount" = 99\n'
    fields = parse_ioreg_battery(partial)
    assert fields["MaxCapacity"] == 5000
    assert fields["CycleCount"] == 99
    assert "Voltage" not in fields


# ─────────────────────────────────────────────────────────────
# Derived calculations (what get_battery_snapshot does with fields)
# ─────────────────────────────────────────────────────────────

def test_discharge_rate_mw_calculation():
    """
    Power formula: |InstantAmperage_mA| × Voltage_mV / 1000 = power_mW
    From sample: |-1823| × 12342 / 1000 = 22499.5 mW ≈ 22.5 W
    """
    fields = parse_ioreg_battery(SAMPLE_IOREG)
    voltage_mv = fields["Voltage"]          # 12342
    instant_amp = fields["InstantAmperage"] # -1823
    power_mw = abs(instant_amp) * voltage_mv / 1000.0
    assert 22000 < power_mw < 23000, f"Expected ~22.5W, got {power_mw:.1f} mW"


def test_full_charge_capacity_mwh_calculation():
    """
    mWh formula: capacity_mAh × voltage_mV / 1000 = mWh
    From sample: 5800 × 12342 / 1000 = 71583.6 mWh ≈ 71.6 Wh
    """
    fields = parse_ioreg_battery(SAMPLE_IOREG)
    max_cap = fields["MaxCapacity"]  # 5800 mAh
    voltage = fields["Voltage"]      # 12342 mV
    mwh = max_cap * voltage / 1000.0
    assert 70000 < mwh < 73000, f"Expected ~71.6 Wh, got {mwh:.0f} mWh"


def test_health_percent_calculation():
    """
    Health = (MaxCapacity / DesignCapacity) × 100
    From sample: 5800 / 6331 × 100 = 91.6%
    """
    fields = parse_ioreg_battery(SAMPLE_IOREG)
    health = (fields["MaxCapacity"] / fields["DesignCapacity"]) * 100.0
    assert 91.0 < health < 92.5, f"Expected ~91.6%, got {health:.1f}%"


def test_percent_from_current_capacity():
    """
    Battery % from ioreg: CurrentCapacity / MaxCapacity × 100
    From sample: 4640 / 5800 × 100 = 80.0%
    """
    fields = parse_ioreg_battery(SAMPLE_IOREG)
    percent = (fields["CurrentCapacity"] / fields["MaxCapacity"]) * 100.0
    assert pytest.approx(percent, abs=0.1) == 80.0


# ─────────────────────────────────────────────────────────────
# get_battery_snapshot integration (with mocked ioreg)
# ─────────────────────────────────────────────────────────────

def test_get_snapshot_with_ioreg(tmp_path):
    """get_battery_snapshot() correctly populates capacity and rate from ioreg."""
    import psutil
    from unittest.mock import MagicMock
    from platform_adapters.macos_adapter import macOSAdapter
    import platform_adapters.macos_adapter as mod

    mock_battery = MagicMock()
    mock_battery.percent = 80.0
    mock_battery.power_plugged = False

    with patch.object(psutil, "sensors_battery", return_value=mock_battery), \
         patch.object(mod, "_run_ioreg", return_value=SAMPLE_IOREG):
        adapter = macOSAdapter()
        snapshot = adapter.get_battery_snapshot()

    # Capacity should be populated from ioreg
    assert snapshot.full_charge_capacity_mwh is not None
    assert snapshot.full_charge_capacity_mwh > 50000  # ~71 Wh

    assert snapshot.design_capacity_mwh is not None
    assert snapshot.design_capacity_mwh > snapshot.full_charge_capacity_mwh

    # Discharge rate should be populated
    assert snapshot.discharge_rate_mw is not None
    assert snapshot.discharge_rate_mw > 0

    # Cycle count
    assert snapshot.cycle_count == 142

    # Platform tag
    assert snapshot.platform == "macos"


def test_get_snapshot_fallback_when_ioreg_unavailable():
    """When ioreg fails, get_battery_snapshot falls back to psutil without crashing."""
    import psutil
    from unittest.mock import MagicMock
    from platform_adapters.macos_adapter import macOSAdapter
    import platform_adapters.macos_adapter as mod

    mock_battery = MagicMock()
    mock_battery.percent = 65.0
    mock_battery.power_plugged = False

    with patch.object(psutil, "sensors_battery", return_value=mock_battery), \
         patch.object(mod, "_run_ioreg", return_value=None):
        adapter = macOSAdapter()
        snapshot = adapter.get_battery_snapshot()

    assert snapshot.percent == pytest.approx(65.0, abs=0.1)
    assert snapshot.power_plugged is False
    # Capacity fields should be None when ioreg is unavailable
    assert snapshot.full_charge_capacity_mwh is None
    assert snapshot.platform == "macos"


def test_get_snapshot_no_battery():
    """On a Mac without a battery (Mac mini/Mac Pro), returns AC-only snapshot."""
    import psutil
    from platform_adapters.macos_adapter import macOSAdapter
    import platform_adapters.macos_adapter as mod

    with patch.object(psutil, "sensors_battery", return_value=None), \
         patch.object(mod, "_run_ioreg", return_value=None):
        adapter = macOSAdapter()
        snapshot = adapter.get_battery_snapshot()

    assert snapshot.power_plugged is True
    assert snapshot.percent == pytest.approx(100.0, abs=0.1)
    assert snapshot.platform == "macos"
