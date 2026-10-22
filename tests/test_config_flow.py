"""Config flow: setup, errors, duplicates, re-auth, reconfigure and options."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_TOKEN, CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonnen_battery.api import SonnenAuthError, SonnenConnectionError
from custom_components.sonnen_battery.const import DOMAIN

from .conftest import HOST, SERIAL, TOKEN


async def test_user_flow(hass: HomeAssistant, mock_api: MagicMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_API_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "sonnenBatterie"
    assert result["data"] == {CONF_HOST: HOST, CONF_API_TOKEN: TOKEN}
    assert result["result"].unique_id == SERIAL


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (SonnenAuthError("no"), "invalid_auth"),
        (SonnenConnectionError("down"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant, mock_api: MagicMock, exc: Exception, error: str
) -> None:
    mock_api.async_get_status.side_effect = exc
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_API_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_api.async_get_status.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_API_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_falls_back_to_host_without_serial(hass: HomeAssistant, mock_api: MagicMock) -> None:
    mock_api.async_get_configurations.return_value = {}
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.50", CONF_API_TOKEN: TOKEN}
    )
    assert result["result"].unique_id == HOST


async def test_already_configured_updates_host(
    hass: HomeAssistant, mock_api: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.99", CONF_API_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == "http://192.168.1.99"


async def test_reauth(hass: HomeAssistant, mock_api: MagicMock, mock_config_entry: MockConfigEntry) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_api.async_get_status.side_effect = SonnenAuthError("still wrong")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_TOKEN: "bad"})
    assert result["errors"] == {"base": "invalid_auth"}

    mock_api.async_get_status.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_TOKEN: "new-token"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_API_TOKEN] == "new-token"


async def test_reconfigure(
    hass: HomeAssistant, mock_api: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.5", CONF_API_TOKEN: "other"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data == {CONF_HOST: "http://10.0.0.5", CONF_API_TOKEN: "other"}


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, mock_api: MagicMock, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    mock_api.async_get_configurations.return_value = {"DE_Ticket_Number": "999999"}
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.5", CONF_API_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert mock_config_entry.data[CONF_HOST] == HOST


async def test_options_flow(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 30})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert init_integration.options == {CONF_SCAN_INTERVAL: 30}
    assert init_integration.runtime_data.update_interval.total_seconds() == 30
