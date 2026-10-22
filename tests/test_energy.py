"""Power-to-energy maths: sign handling and integration."""

from __future__ import annotations

import pytest

from custom_components.sonnen_battery.energy import (
    BATTERY_CHARGE,
    BATTERY_DISCHARGE,
    GRID_EXPORT,
    GRID_IMPORT,
    HOME_CONSUMPTION,
    SOLAR_PRODUCTION,
    EnergyIntegrator,
    split_flows,
    to_float,
)


def test_split_flows_exporting_and_charging() -> None:
    flows = split_flows(
        {"GridFeedIn_W": 1200, "Pac_total_W": -2000, "Production_W": 3700, "Consumption_W": 500}
    )
    assert flows == {
        GRID_IMPORT: 0.0,
        GRID_EXPORT: 1200.0,
        BATTERY_CHARGE: 2000.0,
        BATTERY_DISCHARGE: 0.0,
        SOLAR_PRODUCTION: 3700.0,
        HOME_CONSUMPTION: 500.0,
    }


def test_split_flows_importing_and_discharging_at_night() -> None:
    flows = split_flows({"GridFeedIn_W": -300, "Pac_total_W": 700, "Production_W": -4, "Consumption_W": 1000})
    assert flows[GRID_IMPORT] == 300.0
    assert flows[GRID_EXPORT] == 0.0
    assert flows[BATTERY_CHARGE] == 0.0
    assert flows[BATTERY_DISCHARGE] == 700.0
    # Small negative production at night is noise, not negative energy.
    assert flows[SOLAR_PRODUCTION] == 0.0


def test_split_flows_handles_strings_and_missing_values() -> None:
    flows = split_flows({"GridFeedIn_W": "-250", "Pac_total_W": None})
    assert flows[GRID_IMPORT] == 250.0
    assert flows[BATTERY_CHARGE] is None
    assert flows[SOLAR_PRODUCTION] is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(5, 5.0), ("3.5", 3.5), (None, None), ("abc", None), (True, None), (float("nan"), None)],
)
def test_to_float(raw, expected) -> None:
    assert to_float(raw) == expected


def test_integrator_constant_power() -> None:
    meter = EnergyIntegrator(max_gap=7200)
    meter.add(0, 1000)
    meter.add(3600, 1000)
    assert meter.total_kwh == pytest.approx(1.0)


def test_integrator_trapezoid() -> None:
    meter = EnergyIntegrator(max_gap=7200)
    meter.add(0, 0)
    meter.add(3600, 2000)
    assert meter.total_kwh == pytest.approx(1.0)


def test_integrator_ignores_long_gaps() -> None:
    meter = EnergyIntegrator(max_gap=300)
    meter.add(0, 1000)
    meter.add(10_000, 1000)  # battery was offline: don't invent 2.8 kWh
    assert meter.total_kwh == 0
    meter.add(10_036, 1000)  # integration resumes from the new baseline
    assert meter.total_kwh == pytest.approx(0.01)


def test_integrator_resets_on_missing_reading() -> None:
    meter = EnergyIntegrator()
    meter.add(0, 1000)
    meter.add(10, None)
    meter.add(20, 1000)
    assert meter.total_kwh == 0


def test_integrator_never_decreases() -> None:
    meter = EnergyIntegrator(total_kwh=5.0)
    meter.add(100, 500)
    meter.add(90, 500)  # older reading
    meter.add(100, 500)  # repeated reading
    meter.add(110, -50)  # impossible negative flow
    assert meter.total_kwh == 5.0
