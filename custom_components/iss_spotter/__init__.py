"""
Custom integration to integrate ISS Spot the Station.

ISS Spot the Station NASA Website.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

__version__ = "1.1.1"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Spot Station from a config entry."""
    _LOGGER.info("Spot Station Integration Version: %s", __version__)
    hass.async_create_task(
        await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Spot Station config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
