"""Binary sensors, the operating mode select, backup reserve, and diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.sonnen_battery.api import SonnenConnectionError

from .conftest import SERIAL, TOKEN

SELECT = "select.sonnenbatterie_operating_mode"
NUMBER = "number.sonnenbatterie_backup_reserve"


async def test_binary_sensors(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    assert hass.states.get("binary_sensor.sonnenbatterie_charging").state == STATE_ON
    assert hass.states.get("binary_sensor.sonnenbatterie_discharging").state == STATE_OFF
    assert hass.states.get("binary_sensor.sonnenbatterie_on_grid").state == STATE_ON


async def test_operating_mode(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    state = hass.states.get(SELECT)
    assert state.state == "automatic"
    assert state.attributes["options"] == ["manual", "automatic", "time_of_use", "optimisation"]

    await hass.services.async_call(
        "select", SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: SELECT, ATTR_OPTION: "time_of_use"}, blocking=True
    )
    mock_api.async_set_configuration.assert_awaited_once_with("EM_OperatingMode", "10")


async def test_unknown_operating_mode(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_api.async_get_configurations.return_value["EM_OperatingMode"] = "6"
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).state == "unknown"


async def test_backup_reserve(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    assert hass.states.get(NUMBER).state == "10.0"
    await hass.services.async_call(
        "number", SERVICE_SET_VALUE, {ATTR_ENTITY_ID: NUMBER, ATTR_VALUE: 25}, blocking=True
    )
    mock_api.async_set_configuration.assert_awaited_once_with("EM_USOC", "25")


@pytest.mark.parametrize(
    ("domain", "service", "data"),
    [
        ("select", SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: SELECT, ATTR_OPTION: "manual"}),
        ("number", SERVICE_SET_VALUE, {ATTR_ENTITY_ID: NUMBER, ATTR_VALUE: 30}),
    ],
)
async def test_write_failure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_api: MagicMock,
    domain: str,
    service: str,
    data: dict,
) -> None:
    mock_api.async_set_configuration.side_effect = SonnenConnectionError("read only")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(domain, service, data, blocking=True)
    assert err.value.translation_key == "write_failed"


async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, init_integration: MockConfigEntry
) -> None:
    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    text = str(result)
    assert TOKEN not in text
    assert SERIAL not in text
    assert result["data"]["status"]["USOC"] == 55
