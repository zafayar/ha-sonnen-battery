"""Actions: set a fixed charge or discharge power."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import SETPOINT_DIRECTIONS, SonnenError
from .const import DOMAIN
from .coordinator import SonnenConfigEntry
from .schema import vol

SERVICE_SET_POWER = "set_power"
ATTR_DIRECTION = "direction"
ATTR_POWER = "power"
MAX_SETPOINT_W = 20_000  # above any sonnen inverter; the battery clamps to its own limit

SET_POWER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_DIRECTION): vol.In(SETPOINT_DIRECTIONS),
        vol.Required(ATTR_POWER): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_SETPOINT_W)),
    }
)


def _get_entry(hass: HomeAssistant, entry_id: str) -> SonnenConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_found")
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
    return entry


async def _async_set_power(call: ServiceCall) -> None:
    entry = _get_entry(call.hass, call.data[ATTR_CONFIG_ENTRY_ID])
    coordinator = entry.runtime_data
    try:
        await coordinator.api.async_set_power_setpoint(call.data[ATTR_DIRECTION], call.data[ATTR_POWER])
    except SonnenError as err:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="setpoint_failed") from err
    await coordinator.async_request_refresh()


def async_setup_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, SERVICE_SET_POWER, _async_set_power, schema=SET_POWER_SCHEMA)
