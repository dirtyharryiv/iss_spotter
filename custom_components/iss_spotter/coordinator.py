"""Class to manage fetching ISS sighting data from the Spot The Station website."""

import asyncio
import logging
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import PEOPLE_API_URL

_LOGGER = logging.getLogger(__name__)

MIN_COLUMNS = 1
GRACE_PERIOD = timedelta(minutes=60)


class ISSInfoUpdateCoordinator(DataUpdateCoordinator):
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
        self._url = url
        self._max_height = max_height
        self._min_minutes = min_minutes
        self._last_valid_data = None
        self._last_successful_time = None
        super().__init__(
            hass,
            _LOGGER,
            name="ISS Spotter",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from all the ISS sources asynchronously."""

        async def fetch_astronaut_info() -> None:
            return await self.hass.async_add_executor_job(self._get_astronaut_info)

        async def fetch_sightings() -> None:
            return await self.hass.async_add_executor_job(self._get_spot_the_station)

        try:
            astronaut_info, sightings = await asyncio.gather(
                fetch_astronaut_info(), fetch_sightings()
            )

            data = {
                "next_sighting": sightings[0],
                "all_sightings": sightings,
                "astronaut_count": astronaut_info[0],
                "astronaut_names": astronaut_info[1],
            }
            self._last_valid_data = data
            self._last_successful_time = datetime.now().astimezone()
        except (requests.RequestException, ValueError, UpdateFailed) as e:
            if self._last_valid_data and self._last_successful_time:
                time_since_last_success = (
                    datetime.now().astimezone() - self._last_successful_time
                )
                if time_since_last_success <= GRACE_PERIOD:
                    _LOGGER.info("Using cached data due to grace period.")
                    return self._last_valid_data
            error_message = f"Error updating ISS data: {e}"
            raise UpdateFailed(error_message) from e
        else:
            return self._last_valid_data

    def _get_astronaut_info(self) -> tuple[int, list[str]]:
        """Get ISS Astronaut count and names from Open Notify API."""
        try:
            _LOGGER.debug("Fetching ISS people from URL: %s", PEOPLE_API_URL)
            response = requests.get(PEOPLE_API_URL, timeout=20)
            response.raise_for_status()
            data = response.json()
            astronaut_names = [
                astronaut["name"]
                for astronaut in data["people"]
                if astronaut["craft"] == "ISS"
            ]
            astronaut_count = len(astronaut_names)

        except requests.exceptions.RequestException as e:
            return self._handle_error(f"Request failed: {e}")
        except ValueError as e:
            return self._handle_error(f"Value error occurred: {e}")
        except UpdateFailed as e:
            return self._handle_error(f"Update failed: {e}")
        else:
            return astronaut_count, astronaut_names

    def _get_spot_the_station(self) -> list[str]:
        """Get ISS next sightings from spot the station."""
        try:
            _LOGGER.debug("Fetching ISS data from URL: %s", self._url)
            response = requests.get(self._url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.select_one(
                "#content > div.col-md-11.col-md-offset-1 > "
                "div.table-responsive > table:nth-child(2)"
            )
            if not table:
                return self._handle_error("No table found")

            rows = table.find_all("tr")
            sightings = []
            for row in rows:
                columns = row.find_all("td")
                if len(columns) >= MIN_COLUMNS:
                    now = datetime.now().astimezone()
                    sighting_date = datetime.strptime(
                        columns[0].text.strip() + f" {now.year}",
                        "%a %b %d, %I:%M %p %Y",
                    ).astimezone()

                    datetime_object = datetime.strptime(
                        columns[0].text.strip() + " " + str(now.year),
                        "%a %b %d, %I:%M %p %Y",
                    ).astimezone() + timedelta(minutes=5)

                    if datetime_object < now:
                        continue

                    if datetime_object.month == 12 and now.month == 1:
                        continue

                    visibility = columns[1].text.strip().split(" ")[0]
                    if int(visibility) < self._min_minutes:
                        continue

                    height = columns[2].text.strip().split("°")[0]
                    if int(height) < self._max_height:
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
                return self._handle_error("No future sightings")
        except requests.exceptions.RequestException as e:
            return self._handle_error(f"Request failed: {e}")
        except ValueError as e:
            return self._handle_error(f"Value error occurred: {e}")
        except UpdateFailed as e:
            return self._handle_error(f"Update failed: {e}")
        else:
            return sightings

    def _handle_error(self, message: str) -> None:
        """Log and raise the error."""
        _LOGGER.error(message)
        raise UpdateFailed(message)
