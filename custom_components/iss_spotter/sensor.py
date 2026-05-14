"""Custom component for tracking ISS sightings in Home Assistant."""

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, IGNORE_SHIFT_SECONDS
from .coordinator import (
    ISSInfoUpdateCoordinator,
    SpaceDevsAstronautsUpdateCoordinator,
)


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
        self._attr_attribution = "ISS Data provided by Celestrak"
        self._last_state_dt: datetime | None = None

    @property
    def state(self) -> str | None:
        """Return the state as the next ISS sighting time."""
        next_sighting = self.coordinator.data.get("next_sighting")
        if next_sighting:
            date_value = next_sighting.get("date")
            return self._stable_state(date_value) if date_value else None
        return None

    def _stable_state(self, value: str) -> str:
        """Ignore minor time shifts to avoid noisy updates."""
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value

        if self._last_state_dt is None:
            self._last_state_dt = dt
            return value

        if abs((dt - self._last_state_dt).total_seconds()) <= IGNORE_SHIFT_SECONDS:
            return self._last_state_dt.isoformat()

        self._last_state_dt = dt
        return value

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


class SpaceDevsAstronautsSensor(CoordinatorEntity):
    """Representation of the SpaceDevs ISS astronaut sensor."""

    def __init__(
        self,
        coordinator: SpaceDevsAstronautsUpdateCoordinator,
        name: str,
        unique_id: str,
    ) -> None:
        """Initialize the SpaceDevsAstronautsSensor."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:account-group"
        self._attr_attribution = "Astronaut Data provided by The Space Devs"

    @property
    def state(self) -> int | None:
        """Return the number of astronauts currently listed for the ISS."""
        if self.coordinator.data is None:
            return None

        data = self.coordinator.data or {}
        return data.get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return compact SpaceDevs astronaut attributes."""
        data = self.coordinator.data or {}
        return {
            "names": data.get("names", []),
            "astronauts": data.get("astronauts", []),
            "last_updated": data.get("last_updated"),
        }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ISS Spotter sensor based on a config entry."""
    entity_name = config_entry.data["entity_name"]
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    coordinator = entry_data["coordinator"]

    entities.append(
        ISSSpotterSensor(coordinator, "ISS " + entity_name, config_entry.entry_id)
    )

    spacedevs_coordinator = entry_data.get("spacedevs_coordinator")
    if spacedevs_coordinator is not None:
        entities.append(
            SpaceDevsAstronautsSensor(
                spacedevs_coordinator,
                f"ISS {entity_name} Astronauts",
                f"{config_entry.entry_id}_spacedevs_astronauts",
            )
        )

    async_add_entities(entities)
