"""Sensors, and the energy counters the Energy dashboard needs."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.sonnen_battery.api import SonnenConnectionError

ENERGY_SENSORS = {
    "grid_import": "sensor.sonnen_battery_grid_import_energy",
    "grid_export": "sensor.sonnen_battery_grid_export_energy",
    "battery_charge": "sensor.sonnen_battery_battery_charge_energy",
    "battery_discharge": "sensor.sonnen_battery_battery_discharge_energy",
    "solar_production": "sensor.sonnen_battery_solar_production_energy",
    "home_consumption": "sensor.sonnen_battery_house_consumption_energy",
}


@pytest.fixture
def clock() -> Generator[MagicMock]:
    """Controls the monotonic time the coordinator stamps each reading with."""
    with patch("custom_components.sonnen_battery.coordinator.time") as mock_time:
        mock_time.monotonic.return_value = 1000.0
        yield mock_time


async def _poll(hass: HomeAssistant, entry: MockConfigEntry, clock: MagicMock, at: float) -> None:
    clock.monotonic.return_value = at
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _value(hass: HomeAssistant, entity_id: str) -> float:
    return float(hass.states.get(entity_id).state)


async def test_power_sensors(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    expected = {
        "sensor.sonnen_battery_house_consumption_power": "500.0",
        "sensor.sonnen_battery_solar_production_power": "3700.0",
        "sensor.sonnen_battery_grid_power": "-1200.0",  # HA convention: negative = export
        "sensor.sonnen_battery_grid_import_power": "0.0",
        "sensor.sonnen_battery_grid_export_power": "1200.0",
        "sensor.sonnen_battery_battery_power": "-2000.0",  # negative = charging
        "sensor.sonnen_battery_battery_charge_power": "2000.0",
        "sensor.sonnen_battery_battery_discharge_power": "0.0",
    }
    for entity_id, value in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value, entity_id
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT
        assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.POWER
        assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT


async def test_battery_sensors(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    assert hass.states.get("sensor.sonnen_battery_state_of_charge").state == "55.0"
    remaining = hass.states.get("sensor.sonnen_battery_remaining_energy")
    assert remaining.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR
    assert float(remaining.state) == pytest.approx(5.8)
    assert hass.states.get("sensor.sonnen_battery_system_status").state == "OnGrid"
    assert hass.states.get("sensor.sonnen_battery_grid_frequency").state == "50.02"
    assert hass.states.get("sensor.sonnen_battery_cycle_count").state == "412.0"
    assert hass.states.get("sensor.sonnen_battery_state_of_health").state == "98.6"


async def test_energy_sensors_are_energy_dashboard_ready(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    for entity_id in ENERGY_SENSORS.values():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENERGY
        assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR
        assert float(state.state) == 0.0


async def test_energy_integration(
    hass: HomeAssistant, clock: MagicMock, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    # Fixture flows: 3700 W solar, 500 W house, 2000 W charging, 1200 W export.
    await _poll(hass, init_integration, clock, 1000.0 + 3600)  # one hour later... too long a gap
    assert _value(hass, ENERGY_SENSORS["solar_production"]) == 0.0

    for minute in range(1, 61):
        await _poll(hass, init_integration, clock, 4600.0 + minute * 60)
    assert _value(hass, ENERGY_SENSORS["solar_production"]) == pytest.approx(3.7)
    assert _value(hass, ENERGY_SENSORS["home_consumption"]) == pytest.approx(0.5)
    assert _value(hass, ENERGY_SENSORS["battery_charge"]) == pytest.approx(2.0)
    assert _value(hass, ENERGY_SENSORS["grid_export"]) == pytest.approx(1.2)
    assert _value(hass, ENERGY_SENSORS["grid_import"]) == 0.0
    assert _value(hass, ENERGY_SENSORS["battery_discharge"]) == 0.0

    # Night: importing 300 W and discharging 700 W for 30 minutes.
    status = mock_api.async_get_status.return_value
    status.update(GridFeedIn_W=-300, Pac_total_W=700, Production_W=-3, Consumption_W=1000)
    await _poll(hass, init_integration, clock, 8200.0 + 60)  # the change itself: trapezoid step
    for minute in range(2, 32):
        await _poll(hass, init_integration, clock, 8200.0 + minute * 60)
    assert _value(hass, ENERGY_SENSORS["grid_import"]) == pytest.approx(0.15 + 0.3 / 120, abs=1e-3)
    assert _value(hass, ENERGY_SENSORS["battery_discharge"]) == pytest.approx(0.35 + 0.7 / 120, abs=1e-3)
    # Totals never drop, even though production read negative.
    assert _value(hass, ENERGY_SENSORS["solar_production"]) >= 3.7


async def test_energy_survives_outage(
    hass: HomeAssistant, clock: MagicMock, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    await _poll(hass, init_integration, clock, 1060.0)
    before = _value(hass, ENERGY_SENSORS["solar_production"])
    assert before > 0

    mock_api.async_get_status.side_effect = SonnenConnectionError("offline")
    await _poll(hass, init_integration, clock, 1120.0)
    assert hass.states.get(ENERGY_SENSORS["solar_production"]).state == STATE_UNAVAILABLE

    # Back after 2 minutes: the outage interval isn't counted.
    mock_api.async_get_status.side_effect = None
    await _poll(hass, init_integration, clock, 1180.0)
    assert _value(hass, ENERGY_SENSORS["solar_production"]) == pytest.approx(before, abs=1e-3)
    await _poll(hass, init_integration, clock, 1240.0)
    assert _value(hass, ENERGY_SENSORS["solar_production"]) == pytest.approx(before + 3.7 / 60, abs=1e-3)


async def test_energy_restored_after_restart(
    hass: HomeAssistant, clock: MagicMock, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENERGY_SENSORS["grid_import"], "123.456"),
                {"native_value": 123.456, "native_unit_of_measurement": "kWh"},
            ),
            (
                State(ENERGY_SENSORS["grid_export"], "unknown"),
                {"native_value": None, "native_unit_of_measurement": "kWh"},
            ),
        ],
    )
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert _value(hass, ENERGY_SENSORS["grid_import"]) == pytest.approx(123.456)
    assert _value(hass, ENERGY_SENSORS["grid_export"]) == 0.0
    mock_api.async_get_status.return_value["GridFeedIn_W"] = -1000
    await _poll(hass, mock_config_entry, clock, 1036.0)
    await _poll(hass, mock_config_entry, clock, 1072.0)
    assert _value(hass, ENERGY_SENSORS["grid_import"]) > 123.456


async def test_meter_sensors_disabled_by_default(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    entries = er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)
    meters = {e.unique_id: e for e in entries if "_meter_" in e.unique_id}
    assert set(meters) == {
        "123456_meter_production_1_kwh_imported",
        "123456_meter_production_1_kwh_exported",
        "123456_meter_consumption_2_kwh_imported",
        "123456_meter_consumption_2_kwh_exported",
    }
    assert all(e.disabled_by is er.RegistryEntryDisabler.INTEGRATION for e in meters.values())


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_meter_sensor_values(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    imported = hass.states.get("sensor.sonnen_battery_meter_production_1_energy_imported")
    assert float(imported.state) == pytest.approx(12345.6)
    assert imported.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING
    # A 0 reading is a meter that hasn't answered, not a reset.
    assert hass.states.get("sensor.sonnen_battery_meter_production_1_energy_exported").state == "unknown"


async def test_unique_ids_use_serial(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    entry = entity_registry.async_get(ENERGY_SENSORS["grid_import"])
    assert entry.unique_id == "123456_grid_import_energy"


async def test_latest_data_sensors(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
) -> None:
    freezer.move_to("2026-10-22T12:00:30+00:00")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.sonnen_battery_status_light").state == "pulsing_white"
    # 7200 s before 12:00:30, to the minute.
    assert hass.states.get("sensor.sonnen_battery_last_full_charge").state == "2026-10-22T10:00:00+00:00"
    capacity = hass.states.get("sensor.sonnen_battery_full_charge_capacity")
    assert float(capacity.state) == pytest.approx(10.504)
    assert capacity.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_shutdown_reason(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    assert hass.states.get("sensor.sonnen_battery_shutdown_reason").state == "none"
    mock_api.async_get_latest_data.return_value["ic_status"]["DC Shutdown Reason"]["HW_Shutdown"] = True
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sonnen_battery_shutdown_reason").state == "HW_Shutdown"


async def test_no_latest_data_sensors_without_endpoint(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_api.async_get_latest_data.side_effect = SonnenConnectionError("404")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sonnen_battery_status_light") is None
    assert hass.states.get("sensor.sonnen_battery_last_full_charge") is None
    assert hass.states.get("binary_sensor.sonnen_battery_problem") is None


async def test_installed_capacity(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    state = hass.states.get("sensor.sonnen_battery_installed_capacity")
    assert float(state.state) == pytest.approx(10.0)  # 4 modules x 2500 Wh
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR

    mock_api.async_get_configurations.return_value["CM_MarketingModuleCapacity"] = "0"
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sonnen_battery_installed_capacity").state == "unknown"


async def test_no_installed_capacity_without_module_size(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    del mock_api.async_get_configurations.return_value["CM_MarketingModuleCapacity"]
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sonnen_battery_installed_capacity") is None
