"""Sensors: live power, energy counters for the Energy dashboard, and battery details."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import CONF_KEY_MODULE_CAPACITY, CONF_KEY_MODULES
from .coordinator import SonnenConfigEntry, SonnenCoordinator, SonnenData
from .energy import FLOWS, EnergyIntegrator, split_flows, to_float
from .entity import SonnenEntity
from .status_flags import LED_OPTIONS, shutdown_reason, status_led

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SonnenSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SonnenData], StateType | datetime]
    exists_fn: Callable[[SonnenData], bool] = lambda _: True


def _installed_capacity(data: SonnenData) -> float | None:
    """Nominal capacity when new: module count x rated capacity per module (Wh)."""
    config = data.configurations or {}
    modules = to_float(config.get(CONF_KEY_MODULES))
    per_module = to_float(config.get(CONF_KEY_MODULE_CAPACITY))
    if not modules or not per_module or modules < 0 or per_module < 0:
        return None
    return modules * per_module


def _last_full_charge(data: SonnenData) -> datetime | None:
    seconds = to_float(data.ic_status.get("secondssincefullcharge"))
    if seconds is None or seconds < 0:
        return None
    # Whole minutes, so polling jitter doesn't write a new state every poll.
    return (dt_util.utcnow() - timedelta(seconds=seconds)).replace(second=0, microsecond=0)


def _status(key: str) -> Callable[[SonnenData], float | None]:
    return lambda data: to_float(data.status.get(key))


def _flow(flow: str) -> Callable[[SonnenData], float | None]:
    return lambda data: split_flows(data.status)[flow]


def _battery(key: str) -> Callable[[SonnenData], float | None]:
    return lambda data: to_float((data.battery or {}).get(key))


def _grid_power(data: SonnenData) -> float | None:
    # Home Assistant's convention: positive = importing from the grid.
    # sonnen reports the opposite (GridFeedIn_W > 0 = exporting).
    feed_in = to_float(data.status.get("GridFeedIn_W"))
    return None if feed_in is None else -feed_in


def _power(
    key: str, value_fn: Callable[[SonnenData], float | None], **kwargs: Any
) -> SonnenSensorDescription:
    return SonnenSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=value_fn,
        **kwargs,
    )


SENSORS: tuple[SonnenSensorDescription, ...] = (
    _power("consumption_power", _flow("home_consumption")),
    _power("production_power", _flow("solar_production")),
    _power("grid_power", _grid_power),
    _power("grid_import_power", _flow("grid_import")),
    _power("grid_export_power", _flow("grid_export")),
    # Positive = discharging, which is also Home Assistant's battery convention.
    _power("battery_power", _status("Pac_total_W")),
    _power("battery_charge_power", _flow("battery_charge")),
    _power("battery_discharge_power", _flow("battery_discharge")),
    SonnenSensorDescription(
        key="state_of_charge",
        translation_key="state_of_charge",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_status("USOC"),
    ),
    SonnenSensorDescription(
        key="state_of_charge_real",
        translation_key="state_of_charge_real",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
        value_fn=_status("RSOC"),
    ),
    SonnenSensorDescription(
        key="remaining_energy",
        translation_key="remaining_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_status("RemainingCapacity_Wh"),
        exists_fn=lambda data: "RemainingCapacity_Wh" in data.status,
    ),
    SonnenSensorDescription(
        key="system_status",
        translation_key="system_status",
        value_fn=lambda data: data.status.get("SystemStatus"),
    ),
    SonnenSensorDescription(
        key="grid_frequency",
        translation_key="grid_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status("Fac"),
    ),
    SonnenSensorDescription(
        key="ac_voltage",
        translation_key="ac_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("Uac"),
    ),
    SonnenSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("Ubat"),
    ),
    SonnenSensorDescription(
        key="cycle_count",
        translation_key="cycle_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_battery("cyclecount"),
        exists_fn=lambda data: data.battery is not None,
    ),
    SonnenSensorDescription(
        key="installed_capacity",
        translation_key="installed_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_installed_capacity,
        exists_fn=lambda data: (
            CONF_KEY_MODULES in (data.configurations or {})
            and CONF_KEY_MODULE_CAPACITY in (data.configurations or {})
        ),
    ),
    SonnenSensorDescription(
        key="full_charge_capacity",
        translation_key="full_charge_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_battery("fullchargecapacitywh"),
        exists_fn=lambda data: "fullchargecapacitywh" in (data.battery or {}),
    ),
    SonnenSensorDescription(
        key="status_led",
        translation_key="status_led",
        device_class=SensorDeviceClass.ENUM,
        options=LED_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: status_led(data.ic_status),
        exists_fn=lambda data: "Eclipse Led" in data.ic_status,
    ),
    SonnenSensorDescription(
        key="shutdown_reason",
        translation_key="shutdown_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: shutdown_reason(data.ic_status),
        exists_fn=lambda data: "DC Shutdown Reason" in data.ic_status,
    ),
    SonnenSensorDescription(
        key="last_full_charge",
        translation_key="last_full_charge",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last_full_charge,
        exists_fn=lambda data: "secondssincefullcharge" in data.ic_status,
    ),
    SonnenSensorDescription(
        key="state_of_health",
        translation_key="state_of_health",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_battery("stateofhealth"),
        exists_fn=lambda data: data.battery is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonnenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data
    entities: list[SensorEntity] = [
        SonnenSensor(coordinator, desc) for desc in SENSORS if desc.exists_fn(data)
    ]
    entities += [SonnenEnergySensor(coordinator, flow) for flow in FLOWS]
    for meter in data.powermeter or []:
        direction = str(meter.get("direction", "")).lower()
        if direction not in ("production", "consumption"):
            continue
        channel = str(meter.get("channel", ""))
        for field in ("kwh_imported", "kwh_exported"):
            if field in meter:
                entities.append(SonnenMeterEnergySensor(coordinator, direction, channel, field))
    async_add_entities(entities)


class SonnenSensor(SonnenEntity, SensorEntity):
    entity_description: SonnenSensorDescription

    def __init__(self, coordinator: SonnenCoordinator, description: SonnenSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)


class SonnenEnergySensor(SonnenEntity, RestoreSensor):
    """kWh counter for one power flow, ready for the Energy dashboard.

    Integrates the live power between polls and restores its total after a
    restart, so the counter never goes backwards.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: SonnenCoordinator, flow: str) -> None:
        super().__init__(coordinator, f"{flow}_energy")
        self._flow = flow
        self._attr_translation_key = f"{flow}_energy"
        self._integrator = EnergyIntegrator()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        restored = to_float(last.native_value) if last else None
        if restored is not None and restored >= 0:
            self._integrator.total_kwh = restored
        self._feed()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._feed()
        super()._handle_coordinator_update()

    def _feed(self) -> None:
        data = self.coordinator.data
        if not self.coordinator.last_update_success:
            self._integrator.reset_baseline()
            return
        self._integrator.add(data.fetched_at, split_flows(data.status)[self._flow])

    @property
    def native_value(self) -> float:
        return round(self._integrator.total_kwh, 4)


class SonnenMeterEnergySensor(SonnenEntity, SensorEntity):
    """Lifetime kWh counter straight from one of the battery's internal meters.

    Off by default: which counter means what depends on how the meters were
    wired at installation. The integrated counters work for everyone.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SonnenCoordinator, direction: str, channel: str, field: str) -> None:
        super().__init__(coordinator, f"meter_{direction}_{channel}_{field}")
        self._direction = direction
        self._channel = channel
        self._field = field
        self._attr_translation_key = f"meter_{field}"
        self._attr_translation_placeholders = {"meter": direction, "channel": channel}

    @property
    def native_value(self) -> float | None:
        for meter in self.coordinator.data.powermeter or []:
            if (
                str(meter.get("direction", "")).lower() == self._direction
                and str(meter.get("channel", "")) == self._channel
            ):
                value = to_float(meter.get(self._field))
                # A meter that hasn't answered yet reads 0; reporting that would
                # look like a counter reset and double the next day's total.
                return value if value else None
        return None
