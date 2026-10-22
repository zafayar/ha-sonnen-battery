"""The sensors pass Home Assistant's own Energy dashboard validation.

This runs the same checks as Settings > Dashboards > Energy: device class,
unit, state class, recorded statistics and sign conventions.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.energy import data, validate
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
)

START = datetime.fromisoformat("2026-10-22T12:00:00+00:00")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock: None, enable_custom_integrations: None) -> None:
    """Overrides conftest's: the recorder has to start before hass does."""


async def test_energy_dashboard_accepts_sensors(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
) -> None:
    freezer.move_to(START)
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    freezer.move_to(START.replace(minute=2))
    await mock_config_entry.runtime_data.async_refresh()
    await async_wait_recording_done(hass)

    freezer.move_to(START.replace(minute=6))
    do_adhoc_statistics(hass, start=START)
    # Twice: the first wait commits the queued states, the second the compiled statistics.
    await async_wait_recording_done(hass)
    await async_wait_recording_done(hass)

    manager = await data.async_get_manager(hass)
    await manager.async_update(
        {
            "energy_sources": [
                {
                    "type": "grid",
                    "stat_energy_from": "sensor.sonnenbatterie_grid_import_energy",
                    "stat_energy_to": "sensor.sonnenbatterie_grid_export_energy",
                    "stat_rate": "sensor.sonnenbatterie_grid_power",
                    "cost_adjustment_day": 0,
                },
                {
                    "type": "solar",
                    "stat_energy_from": "sensor.sonnenbatterie_solar_production_energy",
                    "stat_rate": "sensor.sonnenbatterie_solar_production_power",
                    "config_entry_solar_forecast": None,
                },
                {
                    "type": "battery",
                    "stat_energy_from": "sensor.sonnenbatterie_battery_discharge_energy",
                    "stat_energy_to": "sensor.sonnenbatterie_battery_charge_energy",
                    "stat_rate": "sensor.sonnenbatterie_battery_power",
                },
            ],
            "device_consumption": [{"stat_consumption": "sensor.sonnenbatterie_house_consumption_energy"}],
        }
    )

    result = (await validate.async_validate(hass)).as_dict()
    assert result == {
        "energy_sources": [[], [], []],
        "device_consumption": [[]],
        "device_consumption_water": [],
    }
