"""Config Flow for ISS Spotter."""

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
)

from .const import (
    DEFAULT_DAYS,
    DEFAULT_LATITUDE,
    DEFAULT_LONGITUDE,
    DEFAULT_MAX_HEIGHT,
    DEFAULT_MIN_MINUTES,
    DEFAULT_NAME,
    DOMAIN,
)


class ISSSpotterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ISS Spotter."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._entity_name = None
        self._latitude = None
        self._longitude = None
        self._max_height = None
        self._min_minutes = None
        self._days = None

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the user input for the configuration."""
        errors = {}

        if user_input is not None:
            self._entity_name = user_input["entity_name"]
            self._latitude = user_input["latitude"]
            self._longitude = user_input["longitude"]
            self._max_height = user_input["max_height"]
            self._min_minutes = user_input["min_minutes"]
            self._days = user_input["days"]

            return self.async_create_entry(
                title="ISS Next Sightings " + self._entity_name,
                data={
                    "entity_name": self._entity_name,
                    "latitude": self._latitude,
                    "longitude": self._longitude,
                    "max_height": self._max_height,
                    "min_minutes": self._min_minutes,
                    "days": self._days,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("entity_name", default=DEFAULT_NAME): str,
                    vol.Required(
                        "latitude",
                        default=DEFAULT_LATITUDE,
                    ): float,
                    vol.Required(
                        "longitude",
                        default=DEFAULT_LONGITUDE,
                    ): float,
                    vol.Required("max_height", default=DEFAULT_MAX_HEIGHT): int,
                    vol.Required("min_minutes", default=DEFAULT_MIN_MINUTES): int,
                    vol.Required("days", default=DEFAULT_DAYS): int,
                }
            ),
            errors=errors,
        )
