"""Class to manage fetching ISS sighting data from the Spot The Station website."""

import logging
from datetime import UTC, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

MIN_COLUMNS = 5  # Magic value for column count


class ISSDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching ISS sighting data."""

    def __init__(
        self, hass: HomeAssistant, url: str, max_height: int, update_interval: timedelta
    ) -> None:
        """Initialize the coordinator."""
        self.url = url
        self.max_height = max_height
        super().__init__(
            hass,
            _LOGGER,
            name="ISS Spotter",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from the ISS feed."""

        def fetch_data() -> dict:
            """Inner function to fetch data and handle exceptions."""
            try:
                _LOGGER.debug("Fetching ISS data from URL: %s", self.url)
                response = requests.get(self.url, timeout=20)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                table = soup.select_one(
                    "#content > div.col-md-11.col-md-offset-1 > "
                    "div.table-responsive > table:nth-child(2)"
                )
                if not table:
                    return self._handle_error("No table found in the HTML response")

                rows = table.find_all("tr")
                sightings = []
                for row in rows:
                    columns = row.find_all("td")
                    if len(columns) >= MIN_COLUMNS:
                        now = datetime.now(UTC)
                        sighting_date = datetime.strptime(
                            columns[0].text.strip() + f" {now.year}",
                            "%a %b %d, %I:%M %p %Y",
                        ).replace(tzinfo=UTC)

                        datetime_object = datetime.strptime(
                            columns[0].text.strip() + " " + str(now.year),
                            "%a %b %d, %I:%M %p %Y",
                        ).astimezone() + timedelta(minutes=5)

                        if datetime_object < now:
                            continue

                        height = columns[2].text.strip().split("°")[0]
                        if int(height) < self.max_height:
                            continue

                        sightings.append(
                            {
                                "date": sighting_date.isoformat(),
                                "duration": columns[1].text.strip(),
                                "max_elevation": columns[2].text.strip(),
                                "appear": columns[3].text.strip(),
                                "disappear": columns[4].text.strip(),
                            }
                        )

                if not sightings:
                    return self._handle_error("No future sightings found")

                return {"next_sighting": sightings[0], "all_sightings": sightings}

            except requests.exceptions.RequestException as e:
                return self._handle_error(f"Request failed: {e}")
            except ValueError as e:
                return self._handle_error(f"Value error occurred: {e}")
            except UpdateFailed as e:
                return self._handle_error(f"Update failed: {e}")

        # Fetch data via the inner function
        return await self.hass.async_add_executor_job(fetch_data)

    def _handle_error(self, message: str) -> None:
        """Log and raise the error."""
        _LOGGER.error(message)
        raise UpdateFailed(message)
