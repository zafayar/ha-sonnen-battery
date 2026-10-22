"""Shared fixtures: a fake battery API and a config entry."""

from __future__ import annotations

import json
from collections.abc import Generator
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.const import CONF_API_TOKEN, CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonnen_battery.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "http://192.168.1.50"
TOKEN = "test-token"
SERIAL = "123456"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components/ in every test."""


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Create entities that are disabled by default as enabled (as in HA core's tests)."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
        new_callable=PropertyMock,
    ):
        yield


@pytest.fixture
def mock_api() -> Generator[MagicMock]:
    """A SonnenApi stand-in, used by both setup and the config flow."""
    api = MagicMock()
    api.base_url = HOST
    api.async_get_status = AsyncMock(return_value=deepcopy(load_fixture("status.json")))
    api.async_get_latest_data = AsyncMock(return_value={})
    api.async_get_powermeter = AsyncMock(return_value=deepcopy(load_fixture("powermeter.json")))
    api.async_get_battery = AsyncMock(return_value=deepcopy(load_fixture("battery.json")))
    api.async_get_configurations = AsyncMock(return_value=deepcopy(load_fixture("configurations.json")))
    api.async_set_configuration = AsyncMock(return_value={})
    api.async_set_power_setpoint = AsyncMock(return_value=None)
    with (
        patch("custom_components.sonnen_battery.SonnenApi", return_value=api),
        patch("custom_components.sonnen_battery.config_flow.SonnenApi", return_value=api),
    ):
        yield api


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="sonnenBatterie",
        unique_id=SERIAL,
        data={CONF_HOST: HOST, CONF_API_TOKEN: TOKEN},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> MockConfigEntry:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
