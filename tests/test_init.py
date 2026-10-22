"""Setup, unload and failure handling."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonnen_battery.api import SonnenAuthError, SonnenConnectionError


async def test_setup_and_unload(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    assert init_integration.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_unreachable(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_api.async_get_status.side_effect = SonnenConnectionError("down")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_bad_token_starts_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    mock_api.async_get_status.side_effect = SonnenAuthError("rejected")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_optional_endpoints_may_fail(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Only /status is required; the rest just add entities when present."""
    mock_api.async_get_powermeter.side_effect = SonnenConnectionError("404")
    mock_api.async_get_battery.side_effect = SonnenConnectionError("404")
    mock_api.async_get_configurations.side_effect = SonnenAuthError("read only")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.sonnen_battery_state_of_charge").state == "55.0"
    assert hass.states.get("select.sonnen_battery_operating_mode") is None
    assert hass.states.get("sensor.sonnen_battery_cycle_count") is None


async def test_failed_optional_endpoint_keeps_last_value(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_api: MagicMock
) -> None:
    coordinator = init_integration.runtime_data
    mock_api.async_get_configurations.side_effect = SonnenConnectionError("blip")
    await coordinator.async_refresh()
    assert coordinator.data.configurations["EM_USOC"] == "10"
    assert "configurations" in coordinator.data.errors
