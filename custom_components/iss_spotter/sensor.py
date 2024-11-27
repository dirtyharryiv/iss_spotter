"""Sensor platform for iss_spotter."""

import logging
from datetime import datetime, timedelta, timezone
from urllib import parse

import requests
from bs4 import BeautifulSoup
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

# Erstelle einen Logger
_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)


async def async_fetch_spot_station_data(
    hass: HomeAssistant, url: str, max_height: int
) -> list[dict] | None:
    """Fetch ISS sighting data asynchronously."""

    def fetch_data() -> list[dict] | None:
        try:
            _LOGGER.debug("URL at %s", url)
            europe_berlin = timezone(timedelta(hours=1))
            _LOGGER.debug(
                "Start Updating SpotStationSensor at %s", datetime.now(europe_berlin)
            )
            response = requests.get(url, timeout=20)
            response.raise_for_status()

            _LOGGER.debug("Got Data at %s", datetime.now(europe_berlin))

            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.select_one(
                "#content > div.col-md-11.col-md-offset-1 "
                "> div.table-responsive > table:nth-child(2)"
            )
            if not table:
                return None

            rows = table.find_all("tr")
            sightings = []

            min_columns = 5

            for row in rows:
                columns = row.find_all("td")
                if len(columns) >= min_columns:
                    now = datetime.now(europe_berlin)
                    datetime_object = datetime.strptime(
                        columns[0].text.strip() + " " + str(now.year),
                        "%a %b %d, %I:%M %p %Y",
                    ).astimezone() + timedelta(minutes=5)

                    if datetime_object < now:
                        continue

                    height = columns[2].text.strip().split("°")[0]
                    if int(height) < max_height:
                        continue

                    sightings.append(
                        {
                            "date": columns[0].text.strip(),
                            "duration": columns[1].text.strip(),
                            "max_elevation": columns[2].text.strip(),
                            "appear": columns[3].text.strip(),
                            "disappear": columns[4].text.strip(),
                        }
                    )
        except ValueError:
            _LOGGER.exception("ValueError occurred")
            return None

        except requests.exceptions.RequestException:
            _LOGGER.exception("Request failed")
            return None
        else:
            return sightings

    return await hass.async_add_executor_job(fetch_data)


class SpotStationSensor(Entity):
    """Representation of the Spot Station sensor."""

    def __init__(self, url: str, max_height: int, unique_id: str) -> None:
        """Initialize the SpotStationSensor."""
        self._state = None
        self._attributes = {}
        self._url = url
        self._max_height = max_height
        self._unique_id = unique_id

    @property
    def name(self) -> str:
        """Return the name as a string."""
        return "ISS " + parse.parse_qs(parse.urlparse(self._url).query)["city"][
            0
        ].replace("_", " ")

    @property
    def state(self) -> str | None:
        """Return the state as an ISO 8601 datetime string."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Return the sensor attributes."""
        return self._attributes

    @property
    def scan_interval(self) -> timedelta:
        """Gibt das Update-Intervall zurück."""
        return SCAN_INTERVAL

    @property
    def unique_id(self) -> str:
        """Return the unique ID for the entity."""
        return self._unique_id

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        data = await async_fetch_spot_station_data(
            self.hass, self._url, self._max_height
        )
        if data:
            next_sighting = data[0]  # Nächstes Ereignis
            future_sightings = data[1:]  # Alle zukünftigen Ereignisse
            date_time = next_sighting["date"]

            try:
                europe_berlin = timezone(timedelta(hours=1))
                now = datetime.now(europe_berlin)
                local_dt = datetime.strptime(
                    date_time + " " + str(now.year), "%a %b %d, %I:%M %p %Y"
                ).astimezone()

                # In ISO 8601 konvertieren
                self._state = local_dt.isoformat()
                future_sightings_list = [
                    {
                        "date": datetime.strptime(
                            sighting["date"]
                            + " "
                            + str(datetime.now(europe_berlin).year),
                            "%a %b %d, %I:%M %p %Y",
                        )
                        .astimezone()
                        .strftime(
                            "%d.%m.%Y %H:%M:%S"
                        ),  # Konvertierung ins 24-Stunden-Format
                        "duration": sighting["duration"],
                        "max_elevation": sighting["max_elevation"],
                        "appear": sighting["appear"],
                        "disappear": sighting["disappear"],
                    }
                    for sighting in future_sightings
                ]

                self._attributes = {
                    "duration": next_sighting["duration"],
                    "max_elevation": next_sighting["max_elevation"],
                    "appear": next_sighting["appear"],
                    "disappear": next_sighting["disappear"],
                    "future_sightings": future_sightings_list,
                }
            except ValueError as e:
                self._state = None
                self._attributes["error"] = str(e)
        else:
            self._state = None

    async def async_added_to_hass(self) -> None:
        """Wird aufgerufen, wenn der Sensor zu Home Assistant hinzugefügt wird."""
        # Sofortiges Update beim ersten Start
        await self.async_update()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Spot Station sensor based on a config entry."""
    # Hole die URL aus den Konfigurationsdaten des Eintrags
    url = config_entry.data.get("url")
    max_height = config_entry.data.get("max_height")

    # # Generiere eine eindeutige ID für den Sensor (z.B. basierend auf der entry_id)
    unique_id = f"iss_spotter_{config_entry.entry_id}"

    # Füge den Sensor mit der URL und der eindeutigen ID hinzu
    async_add_entities([SpotStationSensor(url, max_height, unique_id)])
