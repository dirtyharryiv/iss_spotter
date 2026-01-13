"""Custom component for tracking ISS sightings in Home Assistant."""

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed

from .coordinator import ISSInfoUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


class ISSSpotterSensor(CoordinatorEntity):
    """Representation of the ISS Spotter sensor."""

    def __init__(
        self, coordinator: ISSInfoUpdateCoordinator, name: str, unique_id: str
    ) -> None:
        """Initialize the ISSSpotterSensor."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = "timestamp"

    @property
    def state(self) -> str | None:
        """Return the state as the next ISS sighting time."""
        next_sighting = self.coordinator.data.get("next_sighting")
        if next_sighting:
            return next_sighting.get("date")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes from the ISS feed."""
        next_sighting = self.coordinator.data.get("next_sighting", {})
        return {
            "latitude": self.coordinator.data.get("latitude"),
            "longitude": self.coordinator.data.get("longitude"),
            "elevation": self.coordinator.data.get("elevation"),
            "duration": next_sighting.get("duration"),
            "max_elevation": next_sighting.get("max_elevation"),
            "appear": next_sighting.get("appear"),
            "culminate": next_sighting.get("culminate"),
            "set": next_sighting.get("set"),
            "all_sightings": self.coordinator.data.get("all_sightings", []),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ISS Spotter sensor based on a config entry."""
    entity_name = config_entry.data["entity_name"]
    latitude = config_entry.data["latitude"]
    longitude = config_entry.data["longitude"]
    max_height = config_entry.data["max_height"]
    min_minutes = config_entry.data["min_minutes"]
    days = config_entry.data["days"]
    update_interval = SCAN_INTERVAL

    coordinator = ISSInfoUpdateCoordinator(
        hass,
        entity_name,
        latitude,
        longitude,
        max_height,
        min_minutes,
        days,
        update_interval,
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        raise ConfigEntryNotReady from err

    async_add_entities(
        [ISSSpotterSensor(coordinator, "ISS " + entity_name, config_entry.entry_id)]
    )
