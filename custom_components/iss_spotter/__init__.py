"""Custom integration to combine Celestrak data and Skyfield."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SPACEDEVS_ASTRONAUTS,
    DEFAULT_SPACEDEVS_ASTRONAUTS,
    DEFAULT_SUN_MAX_ELEVATION,
    DOMAIN,
    SPACEDEVS_UPDATE_MINUTES,
)
from .coordinator import (
    ISSInfoUpdateCoordinator,
    SpaceDevsAstronautsUpdateCoordinator,
)

__version__ = "2.4.0"

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ISS Spotter from a config entry."""
    _LOGGER.info("ISS Spotter Integration Version: %s", __version__)

    entity_name = entry.data["entity_name"]
    coordinator = ISSInfoUpdateCoordinator(
        hass,
        entity_name,
        entry.data["latitude"],
        entry.data["longitude"],
        entry.data["max_height"],
        entry.data.get("sun_max_elevation", DEFAULT_SUN_MAX_ELEVATION),
        entry.data["min_minutes"],
        entry.data["days"],
        SCAN_INTERVAL,
    )
    await coordinator.async_config_entry_first_refresh()

    spacedevs_coordinator = None
    if entry.data.get(CONF_SPACEDEVS_ASTRONAUTS, DEFAULT_SPACEDEVS_ASTRONAUTS):
        spacedevs_coordinator = SpaceDevsAstronautsUpdateCoordinator(
            hass, timedelta(minutes=SPACEDEVS_UPDATE_MINUTES)
        )
        await spacedevs_coordinator.async_refresh()
        if not spacedevs_coordinator.last_update_success:
            _LOGGER.warning("Could not fetch SpaceDevs astronaut data.")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "spacedevs_coordinator": spacedevs_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ISS Spotter config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
