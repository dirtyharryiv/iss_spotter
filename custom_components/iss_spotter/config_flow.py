"""Adds config flow for ISS Spotter."""

from urllib import parse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv


class SpotStationConfigFlow(config_entries.ConfigFlow, domain="iss_spotter"):
    """Handle a config flow for Spot Station."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._url = None
        self._max_height = None

    async def async_step_user(self, user_input: dict | None = None) -> dict:
        """Handle the user input for the configuration."""
        errors = {}

        if user_input is not None:
            self._url = user_input["url"]
            self._max_height = user_input["max_height"]

            try:
                cv.url(self._url)  # Config Validation URL-Prüfung
                if (
                    "https://spotthestation.nasa.gov/sightings/view.cfm?"
                    in self._url.lower()
                ):
                    city = parse.parse_qs(parse.urlparse(self._url).query)["city"][
                        0
                    ].replace("_", " ")
                    return self.async_create_entry(
                        title="ISS Next Sightings " + city,
                        data={"url": self._url, "max_height": self._max_height},
                    )
                errors["base"] = "no_spot_the_station_address"
            except vol.Invalid:
                errors["base"] = "invalid_url"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "url",
                        default="https://spotthestation.nasa.gov/sightings/view.cfm?country=Germany&region=None&city=Freiburg_im_Breisgau",
                    ): str,
                    vol.Optional("max_height", default=20): int,
                }
            ),
            errors=errors,
        )
