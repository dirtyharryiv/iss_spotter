"""Custom component for tracking ISS sightings in Home Assistant."""

import logging
from datetime import timedelta
from typing import Any
from urllib import parse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ISSDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)  # Update interval


class SpotStationSensor(CoordinatorEntity):
    """Representation of the Spot Station sensor."""

    def __init__(
        self, coordinator: ISSDataUpdateCoordinator, name: str, unique_id: str
    ) -> None:
        """Initialize the SpotStationSensor."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

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
            "duration": next_sighting.get("duration"),
            "max_elevation": next_sighting.get("max_elevation"),
            "appear": next_sighting.get("appear"),
            "disappear": next_sighting.get("disappear"),
            "all_sightings": self.coordinator.data.get("all_sightings", []),
            "astronaut_count": self.coordinator.data.get("astronaut_count"),
            "astronaut_names": self.coordinator.data.get("astronaut_names"),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spot Station sensor based on a config entry."""
    url = config_entry.data["url"]
    max_height = config_entry.data["max_height"]
    update_interval = SCAN_INTERVAL

    # Initialize the coordinator
    coordinator = ISSDataUpdateCoordinator(hass, url, max_height, update_interval)
    await coordinator.async_config_entry_first_refresh()

    # Add the sensor with the coordinator
    city = parse.parse_qs(parse.urlparse(url).query)["city"][0].replace("_", " ")
    async_add_entities(
        [SpotStationSensor(coordinator, "ISS " + city, config_entry.entry_id)]
    )
