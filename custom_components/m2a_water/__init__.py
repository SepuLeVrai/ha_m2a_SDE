"""The m2A Water integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .coordinator import M2AWaterConfigEntry, M2AWaterCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: M2AWaterConfigEntry,
) -> bool:
    """Set up m2A Water from a config entry."""
    # A private session is intentional: this API uses first-party cookies.
    session = async_create_clientsession(hass)
    coordinator = M2AWaterCoordinator(hass, entry, session)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_create_background_task(
        hass,
        coordinator.async_sync_history(full=not coordinator.full_history_synced),
        f"{entry.title} historical water import",
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: M2AWaterConfigEntry,
) -> bool:
    """Unload an m2A Water config entry."""
    # async_create_clientsession() was created while this config entry was
    # active, so Home Assistant automatically detaches it on unload.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
