"""Class to manage fetching ISS sighting data from the Spot The Station website."""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from html import unescape
from zoneinfo import ZoneInfo

import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from skyfield.api import Loader, Topos, load
from skyfield.iokit import parse_tle_file
from sqlalchemy import false

from .const import (
    SUN_MAX_ELEVATION,
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
        except (requests.RequestException, ValueError, UpdateFailed) as e:
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
                t_culminate = t[i + 1]
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
                    bool(flag) and (alt < SUN_MAX_ELEVATION)
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
