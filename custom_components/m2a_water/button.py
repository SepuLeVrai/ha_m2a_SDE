"""Buttons for m2A Water."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import M2AWaterConfigEntry, M2AWaterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: M2AWaterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the refresh button."""
    async_add_entities(
        [
            M2ARefreshButton(entry.runtime_data),
            M2AHistorySyncButton(entry.runtime_data),
        ]
    )


class M2ARefreshButton(CoordinatorEntity[M2AWaterCoordinator], ButtonEntity):
    """Force an update exactly like the portal button."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: M2AWaterCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.counter_number}_refresh".lower()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.counter_number)},
            name=f"Compteur d'eau m2A {coordinator.counter_number}",
            manufacturer="Mulhouse Alsace Agglomération (m2A)",
            model="Télérelève SDE",
        )

    async def async_press(self) -> None:
        """Force meter data refresh and reload current consumption."""
        await self.coordinator.async_manual_refresh()


class M2AHistorySyncButton(CoordinatorEntity[M2AWaterCoordinator], ButtonEntity):
    """Start a complete historical backfill in the background."""

    _attr_has_entity_name = True
    _attr_translation_key = "sync_history"
    _attr_icon = "mdi:database-sync"

    def __init__(self, coordinator: M2AWaterCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.counter_number}_sync_history".lower()
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.counter_number)},
            name=f"Compteur d'eau m2A {coordinator.counter_number}",
            manufacturer="Mulhouse Alsace Agglomération (m2A)",
            model="Télérelève SDE",
        )

    async def async_press(self) -> None:
        """Launch full backfill without blocking the HA service call."""
        self.hass.async_create_background_task(
            self.coordinator.async_sync_history(full=True),
            f"m2A full water history {self.coordinator.counter_number}",
        )
