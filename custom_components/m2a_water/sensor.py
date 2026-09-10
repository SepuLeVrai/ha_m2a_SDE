"""Sensors for m2A Water."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import M2AWaterConfigEntry, M2AWaterCoordinator, M2AWaterData


@dataclass(frozen=True, kw_only=True)
class M2ASensorDescription(SensorEntityDescription):
    """Describe an m2A sensor."""

    value_fn: Callable[[M2AWaterData], Any]
    attr_fn: Callable[[M2AWaterData], dict[str, Any] | None] = lambda _: None


SENSORS: tuple[M2ASensorDescription, ...] = (
    M2ASensorDescription(
        key="meter_index",
        translation_key="meter_index",
        icon="mdi:counter",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        value_fn=lambda data: (
            round(data.index_l / 1000.0, 3)
            if data.index_l is not None
            else None
        ),
    ),
    M2ASensorDescription(
        key="last_reading_date",
        translation_key="last_reading_date",
        icon="mdi:calendar-check",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: data.last_reading_date,
    ),
    M2ASensorDescription(
        key="last_daily_consumption",
        translation_key="last_daily_consumption",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        value_fn=lambda data: data.last_daily_l,
        attr_fn=lambda data: {
            "measurement_date": (
                data.last_daily_date.isoformat()
                if data.last_daily_date
                else None
            ),
            "statistic_id": data.statistic_id,
        },
    ),
    M2ASensorDescription(
        key="month_consumption",
        translation_key="month_consumption",
        icon="mdi:water-circle",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        value_fn=lambda data: round(data.month_l, 1),
    ),
    M2ASensorDescription(
        key="previous_year_same_period",
        translation_key="previous_year_same_period",
        icon="mdi:calendar-arrow-left",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        value_fn=lambda data: (
            round(data.previous_year_same_period_l, 1)
            if data.previous_year_same_period_l is not None
            else None
        ),
    ),
    M2ASensorDescription(
        key="evolution",
        translation_key="evolution",
        icon="mdi:compare-horizontal",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: (
            round(data.evolution_percent, 1)
            if data.evolution_percent is not None
            else None
        ),
    ),
    M2ASensorDescription(
        key="average_daily",
        translation_key="average_daily",
        icon="mdi:water-percent",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        value_fn=lambda data: (
            round(data.average_daily_l, 1)
            if data.average_daily_l is not None
            else None
        ),
    ),
    M2ASensorDescription(
        key="previous_year_average_daily",
        translation_key="previous_year_average_daily",
        icon="mdi:water-sync",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        value_fn=lambda data: (
            round(data.previous_year_average_daily_l, 1)
            if data.previous_year_average_daily_l is not None
            else None
        ),
    ),
    M2ASensorDescription(
        key="history_days",
        translation_key="history_days",
        icon="mdi:database-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.history_days,
        attr_fn=lambda data: {
            "first_date": (
                data.history_first_date.isoformat()
                if data.history_first_date
                else None
            ),
            "last_date": (
                data.history_last_date.isoformat()
                if data.history_last_date
                else None
            ),
            "last_sync": (
                data.history_last_sync.isoformat()
                if data.history_last_sync
                else None
            ),
            "statistic_id": data.statistic_id,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: M2AWaterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up m2A water sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        M2AWaterSensor(coordinator, description) for description in SENSORS
    )


class M2AWaterSensor(CoordinatorEntity[M2AWaterCoordinator], SensorEntity):
    """Representation of an m2A water sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: M2AWaterCoordinator,
        description: M2ASensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.counter_number}_{description.key}".lower()
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.counter_number)},
            name=f"Compteur d'eau m2A {coordinator.counter_number}",
            manufacturer="Mulhouse Alsace Agglomération (m2A)",
            model="Télérelève SDE",
        )

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return sensor attributes."""
        return self.entity_description.attr_fn(self.coordinator.data)
