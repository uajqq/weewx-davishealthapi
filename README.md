# weewx-davishealthapi
Driver/service that pulls device health information from a Davis Instruments weather sensor and displays it using weewx. I made this extension for users like me who have a WeatherLink Live device, which unfortunately gives very little sensor health data over the local API. 

The code makes two API calls per archive period: one to the "current" v2 API, which contains values like the console battery status and firmware version, and another to the "historical" v2 API, which contains most of the sensor's health information like signal strength, signal quality, solar cell voltage, and so on.

The data are stored in their own database, since most of the fields don't exist within the default weewx database. The code is patterned after the [cmon driver for weewx by Matthew Hall](https://github.com/uajqq/weewx-weatherlinkliveudp).

## Installation
Download the repository:

`wget -O davishealthapi.zip https://github.com/uajqq/weewx-davishealthapi/archive/master.zip`

Install the extension:

`sudo wee_extension --install davishealthapi.zip`

Alternatively, you could `git clone` the repository and point `wee_extension` towards the resulting folder.

## Configuration
By default, the installer installs `davishealthapi` as a service, allowing your station to keep collecting weather information via its usual driver. It runs during every archive interval and inserts data into its own SQL database. Alternatively, you could install it as a driver, in which case it runs as often as you specify in `weewx.conf`. Instructions are listed in the `davishealthapi.py` file.

### API keys
Once installed, you need to add your Davis WeatherLink Cloud API key, station ID, and secret. To obtain an API key and secret, go to your WeatherLink Cloud account page and look for a button marked "Generate v2 Token." Once you complete the process, enter your key and secret where indicated in weewx.conf.

### Station ID
Davis doesn't make it easy to make API calls, and you have to make an API call to get your station ID. To help the process along, I adapted one of Davis' example Python scripts to make an API call that shows your station ID. To use it, look for the file `davis_api_tool.py` in the zip file you downloaded. Open it in a text editor and type in your API key/secret where indicated. Save the file and run it like so:

`python3 davis_api_tool.py`

It should return a URL. Open that in a browser (don't delay, the timestamp is encoded in that URL and the Davis API will reject the call if you wait too long to make the call) and you'll get back a string of text. Your station ID will be near the beginning. Enter that number into weewx.conf and you should be good to go.

## Usage

Once you enable the service/driver and get it running, you won't notice anything different. You have to manually add the appropriate graphs and tags to see the information.

### Default skin
If you're using the default Seasons skin, you can replace the file `sensors.inc` in the `skins/Seasons/` folder of weewx with the example included in the download, `sensors.inc.EXAMPLE`. On your homepage, you should see a module called "Sensor Status" appear with the relevant data. Clicking on the header brings to you the `telemetry.html` page. 

If you want to display graphs on the `telemetry.html` page, add the following to `skins.conf` under `[[day_images]]`:

```
        [[[dayrx]]]
            title = Signal Quality
            data_binding = davishealthapi_binding
            yscale = 0.0, 100.0, 25.0
            [[[[signalQuality]]]]

        [[[daysignal]]]
            title = Signal Strength
            data_binding = davishealthapi_binding
            yscale = -90.0, -10.0, 10
            [[[[rssi]]]]

        [[[dayvoltSensor]]]
            data_binding = davishealthapi_binding
            title = Sensor voltages
            [[[[supercapVolt]]]]
            [[[[solarVolt]]]]
            [[[[txBattery]]]]

        [[[dayvoltConsole]]]
            data_binding = davishealthapi_binding
            [[[[consoleBattery]]]]
            [[[[consolePower]]]]
```

Do the same under `[[week_images]]`, `[[month_images]]`, etc. but change `[[[dayrx]]]` to `[[[weekrx]]]`, `[[[monthrx]]]`, and so on. That tells the generator to make the graphs, but you still have to display them. For that, you can replace `telemetry.html.tmpl` in the `skins/Seasons` folder with the file from the download, `telemetry.html.tmpl.EXAMPLE`. Make sure you rename the example file to match the file you're trying to replace!

### Belchertown skin
If you're using the excellent Belchertown skin to display your weather data, you can easily add graphs to `graphs.conf` like so:

```
[[signalChart]]
        title = Signal Strength 
        type = spline
        connectNulls = true
        data_binding = davishealthapi_binding  
        [[[signalQuality]]]     
```

*In all cases, note that you have to specify the database binding as `davishealthapi_binding` whenever you are referencing the DavisHealthAPI data!!* Take a look at the example files to see how that's been done so you can adapt it for your own purposes.