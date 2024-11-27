import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import logging
from urllib import parse
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant import config_entries
# from .const import DOMAIN

# Erstelle einen Logger
_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)

async def async_fetch_spot_station_data(hass, url, max_height):
    """Fetch ISS sighting data asynchronously."""
    def fetch_data():
        try:
            _LOGGER.debug("URL at %s", url)
            _LOGGER.debug("Start Updating SpotStationSensor at %s", datetime.now())
            response = requests.get(url)
            response.raise_for_status()
            _LOGGER.debug("Got Data at %s", datetime.now())

            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.select_one("#content > div.col-md-11.col-md-offset-1 > div.table-responsive > table:nth-child(2)")
            if not table:
                return None

            rows = table.find_all("tr")
            sightings = []
            for row in rows:
                columns = row.find_all("td")
                if len(columns) >= 5:
                    now = datetime.now()
                    datetime_object = datetime.strptime(columns[0].text.strip() + " " + str(now.year), '%a %b %d, %I:%M %p %Y') + timedelta(minutes=5)

                    if datetime_object < now:
                        continue

                    height = columns[2].text.strip().split("°")[0]
                    if int(height) < max_height:
                        continue


                    sightings.append({
                        "date": columns[0].text.strip(),
                        "duration": columns[1].text.strip(),
                        "max_elevation": columns[2].text.strip(),
                        "appear": columns[3].text.strip(),
                        "disappear": columns[4].text.strip(),
                    })
            return sightings
        except Exception as e:
            # Speichere den Fehler in einer Logdatei
            # with open("spot_station_error.log", "w", encoding="utf-8") as f:
            #     f.write(str(e))
            return None

    return await hass.async_add_executor_job(fetch_data)


class SpotStationSensor(Entity):
    """Representation of the Spot Station sensor."""

    def __init__(self, url, max_height, unique_id):
        """Initialize the SpotStationSensor."""
        self._state = None
        self._attributes = {}
        self._url = url
        self._max_height = max_height
        self._unique_id = unique_id

    @property
    def name(self):
        return "ISS " + parse.parse_qs(parse.urlparse(self._url).query)['city'][0].replace("_", " ")

    @property
    def state(self):
        """Return the state as an ISO 8601 datetime string."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the sensor attributes."""
        return self._attributes

    @property
    def scan_interval(self):
        """Gibt das Update-Intervall zurück."""
        return SCAN_INTERVAL

    @property
    def unique_id(self):
        """Return the unique ID for the entity."""
        return self._unique_id

    async def async_update(self):
        """Fetch new state data for the sensor."""
        data = await async_fetch_spot_station_data(self.hass, self._url, self._max_height)
        if data:
            next_sighting = data[0]  # Nächstes Ereignis
            future_sightings = data[1:]  # Alle zukünftigen Ereignisse
            date_time = next_sighting["date"]

            try:
                now = datetime.now()
                local_dt = datetime.strptime(date_time + " " + str(now.year), '%a %b %d, %I:%M %p %Y')
                # local_dt = pytz.timezone("Europe/Berlin").localize(local_dt)

                # In ISO 8601 konvertieren
                self._state = local_dt.isoformat()
                future_sightings_list = [
                    {
                        "date": datetime.strptime(
                            sighting["date"] + " " + str(datetime.now().year),
                            '%a %b %d, %I:%M %p %Y'
                        ).strftime('%d.%m.%Y %H:%M:%S'),  # Konvertierung ins 24-Stunden-Format
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

    async def async_added_to_hass(self):
        """Wird aufgerufen, wenn der Sensor zu Home Assistant hinzugefügt wird."""
        # Sofortiges Update beim ersten Start
        await self.async_update()

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up Spot Station sensor based on a config entry."""
    # Hole die URL aus den Konfigurationsdaten des Eintrags
    url = config_entry.data.get("url")
    max_height = config_entry.data.get("max_height")

    # # Generiere eine eindeutige ID für den Sensor (z.B. basierend auf der entry_id)
    unique_id = f"iss_spotter_{config_entry.entry_id}"

    # Füge den Sensor mit der URL und der eindeutigen ID hinzu
    async_add_entities([SpotStationSensor(url, max_height, unique_id)])
