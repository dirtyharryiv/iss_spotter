"""Class to manage fetching ISS sighting data from the Spot The Station website."""

import logging
from datetime import UTC, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

MIN_COLUMNS = 5  # Magic value for column count

API_URL = (
    "http://api.open-notify.org/astros.json"  # URL der Open Notify API für Astronauten
)


def get_astronaut_info() -> tuple[int, list[str]]:
    """Get Astronaut count from Open Notify API."""
    try:
        response = requests.get(API_URL, timeout=20)
        data = response.json()
        astronaut_names = [
            astronaut["name"]
            for astronaut in data["people"]
            if astronaut["craft"] == "ISS"
        ]
        astronaut_count = len(astronaut_names)

    except Exception:
        _LOGGER.exception("Fehler beim Abrufen der Astronautenanzahl und Namen: %s")
        return 0, []
    else:
        return astronaut_count, astronaut_names


class ISSDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching ISS sighting data."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        max_height: int,
        min_minutes: int,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        self.url = url
        self.max_height = max_height
        self.min_minutes = min_minutes
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

                # Füge die Astronauten-Informationen hinzu
                astronaut_count, astronaut_names = get_astronaut_info()

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

                        visibility = columns[1].text.strip().split(" ")[0]
                        if int(visibility) < self.min_minutes:
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

                return {
                    "next_sighting": sightings[0],
                    "all_sightings": sightings,
                    "astronaut_count": astronaut_count,
                    "astronaut_names": astronaut_names,
                }

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
