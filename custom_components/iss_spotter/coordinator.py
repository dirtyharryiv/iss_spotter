"""Classes to manage fetching ISS Spotter data."""

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from skyfield.api import Loader, Topos, load
from skyfield.iokit import parse_tle_file

from .const import (
    SPACEDEVS_API_BASE_URL,
    SPACEDEVS_ISS_SPACE_STATION_ID,
    TLE_CACHE_DAYS,
    TLE_FILENAME,
    TLE_URL,
)

_LOGGER = logging.getLogger(__name__)

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
        sun_max_elevation: float,
        min_minutes: int,
        days: int,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        self._entity_name = entity_name
        self._latitude = latitude
        self._longitude = longitude
        self._max_height = max_height
        self._sun_max_elevation = sun_max_elevation
        self._min_minutes = min_minutes
        self._days = days
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

        async def fetch_sightings() -> None:
            return await self.hass.async_add_executor_job(self._get_skyfield_sightings)

        async def fetch_position() -> None:
            return await self.hass.async_add_executor_job(self._get_iss_position)

        try:
            sightings, position = await asyncio.gather(
                fetch_sightings(), fetch_position()
            )

            data = {
                "latitude": position["latitude"],
                "longitude": position["longitude"],
                "elevation": position["elevation"],
                "all_sightings": sightings,
            }
            if sightings:
                data["next_sighting"] = sightings[0]
        except (ValueError, UpdateFailed) as e:
            error_message = f"Error updating ISS data: {e}"
            raise UpdateFailed(error_message) from e
        else:
            return data

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
                t_set = t[i + 2]

                difference = satellite - observer

                start_dt = t_rise.utc_datetime().replace(tzinfo=ZoneInfo("UTC"))
                end_dt = t_set.utc_datetime().replace(tzinfo=ZoneInfo("UTC"))
                if end_dt <= start_dt:
                    continue

                step_seconds = 5
                times = []
                current = start_dt
                while current <= end_dt:
                    times.append(current)
                    current += timedelta(seconds=step_seconds)
                if times[-1] != end_dt:
                    times.append(end_dt)

                t_samples = ts.from_datetimes(times)
                sunlit = satellite.at(t_samples).is_sunlit(eph)
                observer_at = earth + observer
                sun_alt = (
                    observer_at.at(t_samples).observe(sun).apparent().altaz()[0].degrees
                )
                visible = [
                    bool(flag) and (alt < self._sun_max_elevation)
                    for flag, alt in zip(sunlit, sun_alt)
                ]
                if not any(visible):
                    continue

                visible_indices = [i for i, v in enumerate(visible) if v]
                first_idx = visible_indices[0]
                last_idx = visible_indices[-1]
                t_visible_rise = t_samples[first_idx]
                t_visible_set = t_samples[last_idx]

                alt_samples = difference.at(t_samples).altaz()[0].degrees
                max_idx = max(visible_indices, key=lambda i: alt_samples[i])
                t_visible_culm = t_samples[max_idx]
                max_elevation = alt_samples[max_idx]

                rise_dt = (
                    t_visible_rise.utc_datetime()
                    .replace(tzinfo=ZoneInfo("UTC"))
                    .astimezone(self._tz)
                )
                culminate_dt = (
                    t_visible_culm.utc_datetime()
                    .replace(tzinfo=ZoneInfo("UTC"))
                    .astimezone(self._tz)
                )
                set_dt = (
                    t_visible_set.utc_datetime()
                    .replace(tzinfo=ZoneInfo("UTC"))
                    .astimezone(self._tz)
                )

                duration_sec = (set_dt - rise_dt).total_seconds()
                duration_min = int(duration_sec // 60)
                duration_rem = int(duration_sec % 60)

                topocentric_rise = difference.at(t_visible_rise)
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
                        "date": rise_dt.replace(microsecond=0).isoformat(),
                        "culminate": culminate_dt.replace(microsecond=0).isoformat(),
                        "set": set_dt.replace(microsecond=0).isoformat(),
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

        except Exception:
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


class SpaceDevsAstronautsUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching current ISS astronaut data from SpaceDevs."""

    def __init__(self, hass: HomeAssistant, update_interval: timedelta) -> None:
        """Initialize the coordinator."""
        self._last_valid_data: dict[str, Any] | None = None
        super().__init__(
            hass,
            _LOGGER,
            name="ISS Spotter SpaceDevs Astronauts",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch current ISS astronaut data from SpaceDevs."""
        try:
            payload = await self._fetch_iss_expeditions()
            data = self._parse_iss_astronauts(payload)
        except (OSError, TypeError, ValueError) as err:
            if self._last_valid_data is not None:
                _LOGGER.info("Using cached SpaceDevs astronaut data.")
                return self._last_valid_data

            msg = f"Error updating SpaceDevs astronaut data: {err}"
            raise UpdateFailed(msg) from err

        self._last_valid_data = data
        return data

    async def _fetch_iss_expeditions(self) -> dict[str, Any]:
        """Fetch active ISS expeditions from SpaceDevs."""
        return await self.hass.async_add_executor_job(self._fetch_iss_expeditions_sync)

    def _fetch_iss_expeditions_sync(self) -> dict[str, Any]:
        """Fetch active ISS expeditions from SpaceDevs using the system resolver."""
        params = {
            "format": "json",
            "mode": "detailed",
            "is_active": "true",
            "space_station": str(SPACEDEVS_ISS_SPACE_STATION_ID),
            "limit": "10",
            "ordering": "-start",
        }
        query = urllib.parse.urlencode(params)
        url = f"{SPACEDEVS_API_BASE_URL}/expeditions/?{query}"
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "ISS Spotter"},
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())

    def _parse_iss_astronauts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Parse SpaceDevs expedition data into compact sensor data."""
        results = payload.get("results", [])
        if not isinstance(results, list):
            msg = "SpaceDevs response does not contain a results list"
            raise TypeError(msg)

        astronauts: dict[Any, dict[str, Any]] = {}
        for expedition in results:
            if not isinstance(expedition, dict):
                continue

            station = expedition.get("spacestation") or expedition.get("space_station")
            if not self._is_iss_station(station):
                continue

            for crew_member in expedition.get("crew") or []:
                if not isinstance(crew_member, dict):
                    continue

                astronaut = crew_member.get("astronaut")
                if not isinstance(astronaut, dict):
                    continue
                if not self._is_current_human(astronaut):
                    continue

                astronaut_key = (
                    astronaut.get("id") or astronaut.get("url") or astronaut.get("name")
                )
                if astronaut_key is None:
                    continue

                role = self._role_name(crew_member.get("role"))
                if astronaut_key not in astronauts:
                    astronauts[astronaut_key] = self._format_astronaut(astronaut)
                    astronauts[astronaut_key]["roles"] = []

                self._append_unique(astronauts[astronaut_key]["roles"], role)

        astronaut_list = sorted(
            astronauts.values(), key=lambda astronaut: astronaut.get("name", "")
        )

        return {
            "count": len(astronaut_list),
            "names": [
                astronaut["name"]
                for astronaut in astronaut_list
                if astronaut.get("name")
            ],
            "astronauts": astronaut_list,
            "last_updated": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        }

    @staticmethod
    def _is_iss_station(station: Any) -> bool:
        """Return whether a station object represents the ISS."""
        if not isinstance(station, dict):
            return False

        return (
            station.get("id") == SPACEDEVS_ISS_SPACE_STATION_ID
            or station.get("name") == "International Space Station"
        )

    @staticmethod
    def _is_current_human(astronaut: dict[str, Any]) -> bool:
        """Return whether an astronaut entry should be treated as current crew."""
        if astronaut.get("in_space") is False:
            return False
        return astronaut.get("is_human") is not False

    @staticmethod
    def _format_astronaut(astronaut: dict[str, Any]) -> dict[str, Any]:
        """Return a compact astronaut representation for entity attributes."""
        agency_name = SpaceDevsAstronautsUpdateCoordinator._agency_name(
            astronaut.get("agency")
        )
        image_url = SpaceDevsAstronautsUpdateCoordinator._image_url(astronaut)

        details = {
            "id": astronaut.get("id"),
            "name": astronaut.get("name"),
            "agency": agency_name,
            "nationality": SpaceDevsAstronautsUpdateCoordinator._nationality(
                astronaut.get("nationality")
            ),
            "time_in_space": astronaut.get("time_in_space"),
            "image": image_url,
        }
        return {key: value for key, value in details.items() if value not in (None, "")}

    @staticmethod
    def _agency_name(agency: Any) -> str | None:
        """Extract agency name."""
        if not isinstance(agency, dict):
            return None

        return agency.get("name")

    @staticmethod
    def _image_url(astronaut: dict[str, Any]) -> str | None:
        """Extract image URL from SpaceDevs 2.2 and 2.3 shapes."""
        image = astronaut.get("image")
        if isinstance(image, dict):
            return image.get("image_url")

        return astronaut.get("profile_image")

    @staticmethod
    def _nationality(nationality: Any) -> str | None:
        """Extract nationality from SpaceDevs 2.2 and 2.3 shapes."""
        if isinstance(nationality, str):
            return nationality
        if not isinstance(nationality, list):
            return None

        names = []
        for item in nationality:
            if not isinstance(item, dict):
                continue
            name = item.get("nationality_name") or item.get("name")
            if name:
                names.append(name)

        return ", ".join(names) if names else None

    @staticmethod
    def _nested_name(value: Any) -> str | None:
        """Extract a display name from nested SpaceDevs values."""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("name") or value.get("role")
        return None

    @staticmethod
    def _role_name(role: Any) -> str | None:
        """Extract a crew role."""
        return SpaceDevsAstronautsUpdateCoordinator._nested_name(role)

    @staticmethod
    def _append_unique(values: list[Any], value: Any) -> None:
        """Append a non-empty value once."""
        if value and value not in values:
            values.append(value)
