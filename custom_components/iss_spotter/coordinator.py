"""Class to manage fetching ISS sighting data from the Spot The Station website."""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from skyfield.api import Loader, Topos, load
from skyfield.iokit import parse_tle_file

from .const import (
    MAXIMUM_MINUTES,
    PEOPLE_API_URL,
    SUN_MAX_ELEVATION,
    TLE_CACHE_DAYS,
    TLE_FILENAME,
    TLE_URL,
)

_LOGGER = logging.getLogger(__name__)

GRACE_PERIOD = timedelta(minutes=60)
ASTRONAUT_UPDATE_INTERVAL = timedelta(minutes=30)


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
        self._last_successful_astronaut_time = None
        self._last_valid_sightings = None
        self._last_successful_sighting_time = None
        self._tz = ZoneInfo(hass.config.time_zone)
        cache_dir = hass.config.path("iss_spotter")
        os.makedirs(cache_dir, exist_ok=True)
        self._loader = Loader(cache_dir)
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

        now = datetime.now().astimezone(self._tz)
        if (
            self._last_valid_astronaut_count is not None
            and self._last_valid_astronaut_names is not None
            and self._last_successful_astronaut_time is not None
            and (now - self._last_successful_astronaut_time) < ASTRONAUT_UPDATE_INTERVAL
        ):
            _LOGGER.debug("Returning cached astronaut data (last update <1h)")
            return (
                self._last_valid_astronaut_count,
                self._last_valid_astronaut_names,
            )

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
            self._last_successful_astronaut_time = datetime.now().astimezone(self._tz)

        except (requests.RequestException, ValueError, UpdateFailed) as e:
            if (
                self._last_valid_astronaut_count
                and self._last_valid_astronaut_names
                and self._last_successful_astronaut_time
            ):
                time_since_last_success = (
                    datetime.now().astimezone(self._tz)
                    - self._last_successful_astronaut_time
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

            ts = load.timescale()
            satellite = self._load_satellite(ts)
            if satellite is None:
                _LOGGER.warning("ISS satellite not found in TLE data.")
                return []

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

                if observer_dark and sunlit:
                    rise_dt = (
                        t_rise.utc_datetime()
                        .replace(tzinfo=ZoneInfo("UTC"))
                        .astimezone(self._tz)
                    )
                    set_dt = (
                        t_set.utc_datetime()
                        .replace(tzinfo=ZoneInfo("UTC"))
                        .astimezone(self._tz)
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

                    if duration_min > MAXIMUM_MINUTES:
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
                _LOGGER.debug("No ISS sightings found for your location.")
            else:
                self._last_valid_sightings = sightings
                self._last_successful_sighting_time = datetime.now().astimezone(
                    self._tz
                )

            return sightings

        except Exception as err:
            if self._last_valid_sightings and self._last_successful_sighting_time:
                time_since_last_success = (
                    datetime.now().astimezone(self._tz)
                    - self._last_successful_sighting_time
                )
                if time_since_last_success <= GRACE_PERIOD:
                    _LOGGER.info("Using cached sightings data due to grace period.")
                    return self._last_valid_sightings
            else:
                return []

    def _get_iss_position(self) -> dict[str, float] | None:
        """Calculate ISS position with Skyfield."""
        try:
            _LOGGER.debug("Calculating ISS position with Skyfield")

            ts = load.timescale()
            satellite = self._load_satellite(ts)
            if satellite is None:
                _LOGGER.warning("ISS satellite not found in TLE data.")
                return None

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

    def _load_satellite(self, ts):
        """Load ISS satellite TLE with controlled caching."""
        if (
            not self._loader.exists(TLE_FILENAME)
            or self._loader.days_old(TLE_FILENAME) >= TLE_CACHE_DAYS
        ):
            _LOGGER.info("Refreshing TLE cache from %s", TLE_URL)
            self._loader.download(TLE_URL, filename=TLE_FILENAME)

        with self._loader.open(TLE_FILENAME) as fh:
            satellites = list(parse_tle_file(fh, ts))

        by_name = {sat.name: sat for sat in satellites}
        return by_name.get("ISS (ZARYA)")
