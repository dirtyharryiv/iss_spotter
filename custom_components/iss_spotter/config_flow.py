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
    DEFAULT_SUN_MAX_ELEVATION,
    DOMAIN,
    MAX_DAYS,
    MIN_DAYS,
    MIN_HEIGHT,
    MAX_HEIGHT,
    MIN_MINUTES,
    MAX_MINUTES,
    MAX_SUN_MAX_ELEVATION,
    MIN_SUN_MAX_ELEVATION,
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
        self._sun_max_elevation = None
        self._reconfigure_entry = None

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the user input for the configuration."""
        errors = {}

        if user_input is not None:
            use_ha_location = user_input["use_ha_location"]
            if use_ha_location:
                self._latitude = self.hass.config.latitude
                self._longitude = self.hass.config.longitude
                return await self.async_step_location()
            return await self.async_step_location()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("use_ha_location", default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry."""
        errors = {}
        entry_id = self.context.get("entry_id")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")

        self._reconfigure_entry = entry

        if user_input is not None:
            use_ha_location = user_input["use_ha_location"]
            if use_ha_location:
                self._latitude = self.hass.config.latitude
                self._longitude = self.hass.config.longitude
                return await self.async_step_reconfigure_location()
            return await self.async_step_reconfigure_location()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required("use_ha_location", default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure_location(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle reconfigure location and settings input."""
        if self._reconfigure_entry is None:
            return self.async_abort(reason="reconfigure_failed")

        errors = {}
        entry_data = self._reconfigure_entry.data

        if user_input is not None:
            if self._latitude is None or self._longitude is None:
                latitude = user_input["latitude"]
                longitude = user_input["longitude"]
                if not -90.0 <= latitude <= 90.0:
                    errors["latitude"] = "invalid_latitude"
                if not -180.0 <= longitude <= 180.0:
                    errors["longitude"] = "invalid_longitude"
                if errors:
                    return self.async_show_form(
                        step_id="reconfigure_location",
                        data_schema=vol.Schema(
                            {
                                vol.Required(
                                    "entity_name",
                                    default=entry_data.get("entity_name", DEFAULT_NAME),
                                ): str,
                                vol.Required(
                                    "latitude",
                                    default=latitude,
                                ): float,
                                vol.Required(
                                    "longitude",
                                    default=longitude,
                                ): float,
                                vol.Required(
                                    "max_height",
                                    default=entry_data.get(
                                        "max_height", DEFAULT_MAX_HEIGHT
                                    ),
                                ): vol.All(
                                    int, vol.Range(min=MIN_HEIGHT, max=MAX_HEIGHT)
                                ),
                                vol.Required(
                                    "sun_max_elevation",
                                    default=entry_data.get(
                                        "sun_max_elevation", DEFAULT_SUN_MAX_ELEVATION
                                    ),
                                ): vol.All(
                                    int,
                                    vol.Range(
                                        min=MIN_SUN_MAX_ELEVATION,
                                        max=MAX_SUN_MAX_ELEVATION,
                                    ),
                                ),
                                vol.Required(
                                    "min_minutes",
                                    default=entry_data.get(
                                        "min_minutes", DEFAULT_MIN_MINUTES
                                    ),
                                ): vol.All(
                                    int, vol.Range(min=MIN_MINUTES, max=MAX_MINUTES)
                                ),
                                vol.Required(
                                    "days",
                                    default=entry_data.get("days", DEFAULT_DAYS),
                                ): vol.All(int, vol.Range(min=MIN_DAYS, max=MAX_DAYS)),
                            }
                        ),
                        errors=errors,
                    )
                self._latitude = latitude
                self._longitude = longitude

            updated = {
                **entry_data,
                "entity_name": user_input["entity_name"],
                "latitude": self._latitude,
                "longitude": self._longitude,
                "max_height": user_input["max_height"],
                "sun_max_elevation": user_input["sun_max_elevation"],
                "min_minutes": user_input["min_minutes"],
                "days": user_input["days"],
            }
            self.hass.config_entries.async_update_entry(
                self._reconfigure_entry, data=updated
            )
            return self.async_abort(reason="reconfigure_successful")

        data_schema = {
            vol.Required(
                "entity_name", default=entry_data.get("entity_name", DEFAULT_NAME)
            ): str,
            vol.Required(
                "max_height", default=entry_data.get("max_height", DEFAULT_MAX_HEIGHT)
            ): vol.All(int, vol.Range(min=MIN_HEIGHT, max=MAX_HEIGHT)),
            vol.Required(
                "sun_max_elevation",
                default=entry_data.get("sun_max_elevation", DEFAULT_SUN_MAX_ELEVATION),
            ): vol.All(
                int, vol.Range(min=MIN_SUN_MAX_ELEVATION, max=MAX_SUN_MAX_ELEVATION)
            ),
            vol.Required(
                "min_minutes",
                default=entry_data.get("min_minutes", DEFAULT_MIN_MINUTES),
            ): vol.All(int, vol.Range(min=MIN_MINUTES, max=MAX_MINUTES)),
            vol.Required("days", default=entry_data.get("days", DEFAULT_DAYS)): vol.All(
                int, vol.Range(min=MIN_DAYS, max=MAX_DAYS)
            ),
        }
        if self._latitude is None or self._longitude is None:
            data_schema.update(
                {
                    vol.Required(
                        "latitude",
                        default=entry_data.get("latitude", DEFAULT_LATITUDE),
                    ): float,
                    vol.Required(
                        "longitude",
                        default=entry_data.get("longitude", DEFAULT_LONGITUDE),
                    ): float,
                }
            )

        return self.async_show_form(
            step_id="reconfigure_location",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )

    async def async_step_location(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle manual location and settings input."""
        errors = {}

        if user_input is not None:
            if self._latitude is None or self._longitude is None:
                latitude = user_input["latitude"]
                longitude = user_input["longitude"]
                if not -90.0 <= latitude <= 90.0:
                    errors["latitude"] = "invalid_latitude"
                if not -180.0 <= longitude <= 180.0:
                    errors["longitude"] = "invalid_longitude"
                if errors:
                    return self.async_show_form(
                        step_id="location",
                        data_schema=vol.Schema(
                            {
                                vol.Required("entity_name", default=DEFAULT_NAME): str,
                                vol.Required(
                                    "latitude",
                                    default=latitude,
                                ): float,
                                vol.Required(
                                    "longitude",
                                    default=longitude,
                                ): float,
                                vol.Required(
                                    "max_height", default=user_input["max_height"]
                                ): vol.All(
                                    int, vol.Range(min=MIN_HEIGHT, max=MAX_HEIGHT)
                                ),
                                vol.Required(
                                    "sun_max_elevation",
                                    default=user_input["sun_max_elevation"],
                                ): vol.All(
                                    int,
                                    vol.Range(
                                        min=MIN_SUN_MAX_ELEVATION,
                                        max=MAX_SUN_MAX_ELEVATION,
                                    ),
                                ),
                                vol.Required(
                                    "min_minutes", default=user_input["min_minutes"]
                                ): vol.All(
                                    int, vol.Range(min=MIN_MINUTES, max=MAX_MINUTES)
                                ),
                                vol.Required(
                                    "days", default=user_input["days"]
                                ): vol.All(int, vol.Range(min=MIN_DAYS, max=MAX_DAYS)),
                            }
                        ),
                        errors=errors,
                    )
                self._latitude = latitude
                self._longitude = longitude

            self._entity_name = user_input["entity_name"]
            self._max_height = user_input["max_height"]
            self._sun_max_elevation = user_input["sun_max_elevation"]
            self._min_minutes = user_input["min_minutes"]
            self._days = user_input["days"]

            return self.async_create_entry(
                title="ISS Next Sightings " + self._entity_name,
                data={
                    "entity_name": self._entity_name,
                    "latitude": self._latitude,
                    "longitude": self._longitude,
                    "max_height": self._max_height,
                    "sun_max_elevation": self._sun_max_elevation,
                    "min_minutes": self._min_minutes,
                    "days": self._days,
                },
            )

        data_schema = {
            vol.Required("entity_name", default=DEFAULT_NAME): str,
            vol.Required("max_height", default=DEFAULT_MAX_HEIGHT): vol.All(
                int, vol.Range(min=MIN_HEIGHT, max=MAX_HEIGHT)
            ),
            vol.Required(
                "sun_max_elevation", default=DEFAULT_SUN_MAX_ELEVATION
            ): vol.All(
                int,
                vol.Range(min=MIN_SUN_MAX_ELEVATION, max=MAX_SUN_MAX_ELEVATION),
            ),
            vol.Required("min_minutes", default=DEFAULT_MIN_MINUTES): vol.All(
                int, vol.Range(min=MIN_MINUTES, max=MAX_MINUTES)
            ),
            vol.Required("days", default=DEFAULT_DAYS): vol.All(
                int, vol.Range(min=MIN_DAYS, max=MAX_DAYS)
            ),
        }
        if self._latitude is None or self._longitude is None:
            data_schema.update(
                {
                    vol.Required(
                        "latitude",
                        default=DEFAULT_LATITUDE,
                    ): float,
                    vol.Required(
                        "longitude",
                        default=DEFAULT_LONGITUDE,
                    ): float,
                }
            )

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )
