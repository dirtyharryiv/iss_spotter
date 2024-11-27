from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Spot Station from a config entry."""
    hass.async_create_task(
        await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload Spot Station config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
