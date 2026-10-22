"""Operating mode select. Needs a token with write access."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SonnenError
from .const import CONF_KEY_OPERATING_MODE, DOMAIN, OPERATING_MODES
from .coordinator import SonnenConfigEntry, SonnenCoordinator
from .entity import SonnenEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonnenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if CONF_KEY_OPERATING_MODE in (coordinator.data.configurations or {}):
        async_add_entities([SonnenOperatingModeSelect(coordinator)])


class SonnenOperatingModeSelect(SonnenEntity, SelectEntity):
    _attr_translation_key = "operating_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(OPERATING_MODES)

    def __init__(self, coordinator: SonnenCoordinator) -> None:
        super().__init__(coordinator, "operating_mode")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.configurations is not None

    @property
    def current_option(self) -> str | None:
        raw = (self.coordinator.data.configurations or {}).get(CONF_KEY_OPERATING_MODE)
        for option, code in OPERATING_MODES.items():
            if str(raw) == code:
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.api.async_set_configuration(
                CONF_KEY_OPERATING_MODE, OPERATING_MODES[option]
            )
        except SonnenError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed") from err
        await self.coordinator.async_request_refresh()
