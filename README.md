# ISS Spotter Integration for Home Assistant

The **ISS Spotter** integration for Home Assistant allows you to track upcoming ISS (International Space Station) sightings based on your location. This integration fetches data from the NASA Spot The Station website and presents it in Home Assistant as a `sensor` with the next visible sighting and additional details in the attributes.

## Features
- Displays the next ISS sighting time.
- Shows additional details, including duration, maximum elevation, and where the ISS will appear and disappear in the sky.
- Automatically updates when new sighting data is available.

## Installation

1. **Install via HACS:**
   - Open Home Assistant and go to **HACS**.
   - Click on the three dots in the upper right corner
   - Custom Repositories and add this repos url
   - Search for **ISS Spotter**.
   - Click **Install**.

2. **Manual Installation:**
   - Download or clone this repository.
   - Place the `iss_spotter` folder in your Home Assistant `custom_components` directory.
     ```bash
     /config/custom_components/iss_spotter/
     ```

3. Restart Home Assistant to load the integration.

## Configuration

### **Add the Integration via UI:**

- Go to **Configuration** > **Integrations** in Home Assistant.
- Click **+ Add Integration** and search for **ISS Spotter**.
- Enter the URL for the ISS sighting data (e.g., [Germany Freiburg im Breisgau](https://spotthestation.nasa.gov/sightings/view.cfm?country=Germany&region=None&city=Freiburg_im_Breisgau)).
- The integration will automatically fetch the sighting data.

### **How to Get the Correct URL for ISS Sightings**

To get the correct URL for the ISS sightings based on your location, follow these steps:

1. **Visit the NASA Spot the Station Website:**
   Go to [NASA Spot the Station](https://spotthestation.nasa.gov/sightings/).

2. **Enter Your Location:**
   - Click on the "View Sightings" button.
   - Enter your location in the **"City"** field. You can enter your city or a nearby city.
   - Optionally, choose the **country** and **region**.

3. **Get the URL:**
   After entering your location, you will see a list of upcoming ISS sightings for your city.
   - Look at the **URL** in your browser’s address bar. It should look something like this:
     ```
     https://spotthestation.nasa.gov/sightings/view.cfm?country=Germany&region=None&city=Freiburg_im_Breisgau
     ```
   - This URL is the one you need to use in the **ISS Spotter** integration configuration.

4. **Use the URL in Home Assistant:**
   Copy the URL from your browser's address bar and paste it into the configuration of the **ISS Spotter** integration in Home Assistant.
