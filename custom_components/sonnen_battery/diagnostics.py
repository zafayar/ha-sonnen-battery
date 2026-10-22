"""Diagnostics download, with the token and serial number removed."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant

from .const import CONF_KEY_SERIAL
from .coordinator import SonnenConfigEntry

TO_REDACT = {CONF_API_TOKEN, CONF_KEY_SERIAL, "serial_number", "unique_id", "title"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SonnenConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = asdict(coordinator.data) if coordinator.data else None
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "data": async_redact_data(data, TO_REDACT) if data else None,
    }
