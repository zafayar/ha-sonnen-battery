"""Backup reserve: the charge kept back for power cuts. Needs write access."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SonnenError
from .const import CONF_KEY_BACKUP_RESERVE, DOMAIN
from .coordinator import SonnenConfigEntry, SonnenCoordinator
from .energy import to_float
from .entity import SonnenEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonnenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if CONF_KEY_BACKUP_RESERVE in (coordinator.data.configurations or {}):
        async_add_entities([SonnenBackupReserveNumber(coordinator)])


class SonnenBackupReserveNumber(SonnenEntity, NumberEntity):
    _attr_translation_key = "backup_reserve"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SonnenCoordinator) -> None:
        super().__init__(coordinator, "backup_reserve")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.configurations is not None

    @property
    def native_value(self) -> float | None:
        return to_float((self.coordinator.data.configurations or {}).get(CONF_KEY_BACKUP_RESERVE))

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.api.async_set_configuration(CONF_KEY_BACKUP_RESERVE, str(int(value)))
        except SonnenError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed") from err
        await self.coordinator.async_request_refresh()
