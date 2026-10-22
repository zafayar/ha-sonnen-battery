"""Base entity for the sonnenBatterie integration."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SonnenCoordinator


class SonnenEntity(CoordinatorEntity[SonnenCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SonnenCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_{key}"
        self._attr_device_info = coordinator.device_info
