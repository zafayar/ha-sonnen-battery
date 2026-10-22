"""Binary sensors: charging, discharging, grid connection and problems."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonnenConfigEntry, SonnenCoordinator, SonnenData
from .entity import SonnenEntity
from .status_flags import has_problem

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SonnenBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[SonnenData], bool | None]
    exists_fn: Callable[[SonnenData], bool] = lambda _: True


def _flag(key: str) -> Callable[[SonnenData], bool | None]:
    def value(data: SonnenData) -> bool | None:
        raw = data.status.get(key)
        return None if raw is None else bool(raw)

    return value


def _on_grid(data: SonnenData) -> bool | None:
    status = data.status.get("SystemStatus")
    return None if status is None else str(status).lower() == "ongrid"


BINARY_SENSORS: tuple[SonnenBinarySensorDescription, ...] = (
    SonnenBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_flag("BatteryCharging"),
    ),
    SonnenBinarySensorDescription(
        key="discharging",
        translation_key="discharging",
        value_fn=_flag("BatteryDischarging"),
    ),
    SonnenBinarySensorDescription(
        key="on_grid",
        translation_key="on_grid",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=_on_grid,
    ),
    SonnenBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: has_problem(data.ic_status),
        exists_fn=lambda data: has_problem(data.ic_status) is not None,
    ),
    SonnenBinarySensorDescription(
        # sonnen's "battery care": discharging is blocked, e.g. at very low charge.
        key="discharge_not_allowed",
        translation_key="discharge_not_allowed",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_flag("dischargeNotAllowed"),
        exists_fn=lambda data: "dischargeNotAllowed" in data.status,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonnenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SonnenBinarySensor(coordinator, desc) for desc in BINARY_SENSORS if desc.exists_fn(coordinator.data)
    )


class SonnenBinarySensor(SonnenEntity, BinarySensorEntity):
    entity_description: SonnenBinarySensorDescription

    def __init__(self, coordinator: SonnenCoordinator, description: SonnenBinarySensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
