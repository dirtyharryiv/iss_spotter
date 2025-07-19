"""Class to manage fetching ISS sighting data from the Spot The Station website."""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from skyfield.api import Topos, load

from .const import PEOPLE_API_URL, SUN_MAX_ELEVATION, TLE_URL

_LOGGER = logging.getLogger(__name__)

MIN_COLUMNS = 1
GRACE_PERIOD = timedelta(minutes=60)


class ISSInfoUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching ISS sighting data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_name: str,
        latitude: float,
        longitude: float,
        max_height: int,
        min_minutes: int,
        days: int,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        self._entity_name = entity_name
        self._latitude = latitude
        self._longitude = longitude
        self._max_height = max_height
        self._min_minutes = min_minutes
        self._days = days
        self._last_valid_astronaut_count = None
        self._last_valid_astronaut_names = None
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
            return await self.hass.async_add_executor_job(self._get_skyfield_sightings)

        async def fetch_position() -> None:
            return await self.hass.async_add_executor_job(self._get_iss_position)

        try:
            astronaut_info, sightings, position = await asyncio.gather(
                fetch_astronaut_info(), fetch_sightings(), fetch_position()
            )

            data = {
                "latitude": position["latitude"],
                "longitude": position["longitude"],
                "elevation": position["elevation"],
                "all_sightings": sightings,
                "astronaut_count": astronaut_info[0],
                "astronaut_names": astronaut_info[1],
            }
            if sightings:
                data["next_sighting"] = sightings[0]
        except (requests.RequestException, ValueError, UpdateFailed) as e:
            error_message = f"Error updating ISS data: {e}"
            raise UpdateFailed(error_message) from e
        else:
            return data

    def _get_astronaut_info(self) -> tuple[int, list[str]]:
        """Get ISS Astronaut count and names from Open Notify API."""
        tz = ZoneInfo(self.hass.config.time_zone)

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

            self._last_valid_astronaut_count = astronaut_count
            self._last_valid_astronaut_names = astronaut_names
            self._last_successful_time = datetime.now().astimezone(tz)

        except (requests.RequestException, ValueError, UpdateFailed) as e:
            if (
                self._last_valid_astronaut_count
                and self._last_valid_astronaut_names
                and self._last_successful_time
            ):
                time_since_last_success = (
                    datetime.now().astimezone(tz) - self._last_successful_time
                )
                if time_since_last_success <= GRACE_PERIOD:
                    _LOGGER.info("Using cached astronaut data due to grace period.")
                    return (
                        self._last_valid_astronaut_count,
                        self._last_valid_astronaut_names,
                    )
            error_message = f"Error updating astronaut data: {e}"
            raise UpdateFailed(error_message) from e
        else:
            return astronaut_count, astronaut_names

    def _get_skyfield_sightings(self) -> list[dict]:
        """Calculate ISS-Sightings with Skyfield."""
        try:
            _LOGGER.debug("Calculating ISS-Sightings with Skyfield")

            satellites = load.tle_file(TLE_URL)
            by_name = {sat.name: sat for sat in satellites}
            satellite = by_name["ISS (ZARYA)"]

            ts = load.timescale()
            observer = Topos(
                latitude_degrees=self._latitude, longitude_degrees=self._longitude
            )

            t0 = ts.now()
            t1 = ts.now() + self._days

            eph = load("de421.bsp")
            sun = eph["sun"]
            earth = eph["earth"]

            t, events = satellite.find_events(
                observer, t0, t1, altitude_degrees=self._max_height
            )

            sightings = []
            for i in range(0, len(events), 3):
                if i + 2 >= len(events):
                    continue
                t_rise = t[i]
                t_culminate = t[i + 1]
                t_set = t[i + 2]

                difference = satellite - observer
                topocentric = difference.at(t_culminate)
                alt, az, _ = topocentric.altaz()
                max_elevation = alt.degrees

                observer_at_culm = earth + observer
                sun_alt = (
                    observer_at_culm.at(t_culminate)
                    .observe(sun)
                    .apparent()
                    .altaz()[0]
                    .degrees
                )
                observer_dark = sun_alt < SUN_MAX_ELEVATION

                sunlit = satellite.at(t_culminate).is_sunlit(eph)

                tz = ZoneInfo(self.hass.config.time_zone)

                if observer_dark and sunlit:
                    rise_dt = (
                        t_rise.utc_datetime()
                        .replace(tzinfo=ZoneInfo("UTC"))
                        .astimezone(tz)
                    )
                    set_dt = (
                        t_set.utc_datetime()
                        .replace(tzinfo=ZoneInfo("UTC"))
                        .astimezone(tz)
                    )

                    duration_sec = (set_dt - rise_dt).total_seconds()
                    duration_min = int(duration_sec // 60)
                    duration_rem = int(duration_sec % 60)

                    topocentric_rise = difference.at(t_rise)
                    az_rise = topocentric_rise.altaz()[1].degrees
                    directions = [
                        (0, "N"),
                        (22.5, "NNE"),
                        (45, "NE"),
                        (67.5, "ENE"),
                        (90, "E"),
                        (112.5, "ESE"),
                        (135, "SE"),
                        (157.5, "SSE"),
                        (180, "S"),
                        (202.5, "SSW"),
                        (225, "SW"),
                        (247.5, "WSW"),
                        (270, "W"),
                        (292.5, "WNW"),
                        (315, "NW"),
                        (337.5, "NNW"),
                        (360, "N"),
                    ]
                    direction = next(
                        name for angle, name in reversed(directions) if az_rise >= angle
                    )

                    if duration_min < self._min_minutes:
                        continue

                    sightings.append(
                        {
                            "date": rise_dt.replace(
                                second=0, microsecond=0
                            ).isoformat(),
                            "duration": f"{duration_min}m{duration_rem}s",
                            "max_elevation": f"{int(max_elevation)}°",
                            "appear": direction,
                        }
                    )

            if not sightings:
                msg = "No future visible ISS sightings"
                raise UpdateFailed(msg)
            return sightings

        except Exception as err:
            msg = f"Skyfield error: {err}"
            _LOGGER.exception(msg)
            raise UpdateFailed(msg) from err

    def _get_iss_position(self) -> dict[str, float] | None:
        """Calculate ISS position with Skyfield."""
        try:
            _LOGGER.debug("Calculating ISS position with Skyfield")

            satellites = load.tle_file(TLE_URL)
            by_name = {sat.name: sat for sat in satellites}
            satellite = by_name["ISS (ZARYA)"]

            ts = load.timescale()
            t_now = ts.now()
            geocentric = satellite.at(t_now).subpoint()
            if geocentric:
                return {
                    "latitude": geocentric.latitude.degrees,
                    "longitude": geocentric.longitude.degrees,
                    "elevation": geocentric.elevation.km,
                }

        except (KeyError, ValueError, OSError) as err:
            msg = f"Could not get live ISS position: {err}"
            _LOGGER.warning("%s", msg)
            return None
