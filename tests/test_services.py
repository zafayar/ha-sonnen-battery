"""The set_power action."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonnen_battery.api import SonnenConnectionError
from custom_components.sonnen_battery.const import DOMAIN


async def _set_power(hass: HomeAssistant, entry_id: str, direction: str = "charge", power: int = 1500):
    await hass.services.async_call(
        DOMAIN,
        "set_power",
        {ATTR_CONFIG_ENTRY_ID: entry_id, "direction": direction, "power": power},
        blocking=True,
    )


@pytest.mark.parametrize("direction", ["charge", "discharge"])
async def test_set_power(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock, direction: str
) -> None:
    await _set_power(hass, init_integration.entry_id, direction, 2500)
    mock_api.async_set_power_setpoint.assert_awaited_once_with(direction, 2500)


async def test_set_power_rejected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_api.async_set_power_setpoint.side_effect = SonnenConnectionError("not manual")
    with pytest.raises(HomeAssistantError) as err:
        await _set_power(hass, init_integration.entry_id)
    assert err.value.translation_key == "setpoint_failed"


@pytest.mark.parametrize(("direction", "power"), [("sideways", 100), ("charge", -1), ("charge", 50_000)])
async def test_set_power_validates_input(
    hass: HomeAssistant, init_integration: MockConfigEntry, direction: str, power: int
) -> None:
    with pytest.raises(vol.Invalid):
        await _set_power(hass, init_integration.entry_id, direction, power)


async def test_set_power_unknown_entry(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await _set_power(hass, "nope")
    assert err.value.translation_key == "entry_not_found"


async def test_set_power_entry_not_loaded(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as err:
        await _set_power(hass, init_integration.entry_id)
    assert err.value.translation_key == "entry_not_loaded"
