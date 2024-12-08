"""Config Flow for ISS Spotter."""

from urllib import parse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_URL
from homeassistant.helpers import config_validation as cv

from .const import DEFAULT_MAX_HEIGHT, DEFAULT_MIN_MINUTES, DEFAULT_URL, DOMAIN


class SpotStationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Spot Station."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._url = None
        self._max_height = None
        self._min_minutes = None

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the user input for the configuration."""
        errors = {}

        if user_input is not None:
            self._url = user_input[CONF_URL]
            self._max_height = user_input["max_height"]
            self._min_minutes = user_input["min_minutes"]

            try:
                cv.url(self._url)
                if (
                    "https://spotthestation.nasa.gov/sightings/view.cfm?"
                    in self._url.lower()
                ):
                    city = parse.parse_qs(parse.urlparse(self._url).query)["city"][
                        0
                    ].replace("_", " ")
                    return self.async_create_entry(
                        title="ISS Next Sightings " + city,
                        data={
                            CONF_URL: self._url,
                            "max_height": self._max_height,
                            "min_minutes": self._min_minutes,
                        },
                    )
                errors["base"] = "no_spot_the_station_address"
            except vol.Invalid:
                errors["base"] = "invalid_url"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_URL,
                        default=DEFAULT_URL,
                    ): str,
                    vol.Optional("max_height", default=DEFAULT_MAX_HEIGHT): int,
                    vol.Optional("min_minutes", default=DEFAULT_MIN_MINUTES): int,
                }
            ),
            errors=errors,
        )
