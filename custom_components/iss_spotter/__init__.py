"""Custom integration to combine Celestrak data and Skyfield."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

__version__ = "2.1.2"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ISS Spotter from a config entry."""
    _LOGGER.info("ISS Spotter Integration Version: %s", __version__)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ISS Spotter config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
