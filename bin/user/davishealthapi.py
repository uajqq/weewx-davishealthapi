"""
weewx module that records health information from a Davis weather station using
the v2 API.

Adapted from the cmon driver by Matthew Hall

"""

from __future__ import with_statement
from __future__ import absolute_import
from __future__ import print_function
import time
import hashlib
import hmac
import requests

import weewx
import weewx.units
from weewx.engine import StdService

import weeutil.weeutil

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging

    log = logging.getLogger(__name__)

    def logdbg(msg):
        """Log debug messages"""
        log.debug(msg)

    def loginf(msg):
        """Log info messages"""
        log.info(msg)

    def logerr(msg):
        """Log error messages"""
        log.error(msg)


except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        """Log messages"""
        syslog.syslog(level, "davishealthapi: %s:" % msg)

    def logdbg(msg):
        """Log debug messages"""
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        """Log info messages"""
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        """Log error messages"""
        logmsg(syslog.LOG_ERR, msg)


DRIVER_NAME = "DavisHealthAPI"
DRIVER_VERSION = "0.10"

if weewx.__version__ < "3":
    raise weewx.UnsupportedFeature("weewx 3 is required, found %s" % weewx.__version__)

weewx.units.USUnits["group_decibels"] = "decibels"
weewx.units.MetricUnits["group_decibels"] = "decibels"
weewx.units.MetricWXUnits["group_decibels"] = "decibels"
weewx.units.default_unit_format_dict["decibels"] = "%.1f"
weewx.units.default_unit_label_dict["decibels"] = " dBm"

weewx.units.USUnits["group_millivolts"] = "millivolts"
weewx.units.MetricUnits["group_millivolts"] = "millivolts"
weewx.units.MetricWXUnits["group_millivolts"] = "millivolts"
weewx.units.default_unit_format_dict["millivolts"] = "%d"
weewx.units.default_unit_label_dict["millivolts"] = " mV"

weewx.units.obs_group_dict["supercapVolt"] = "group_volt"
weewx.units.obs_group_dict["solarVolt"] = "group_volt"
weewx.units.obs_group_dict["txBattery"] = "group_volt"
weewx.units.obs_group_dict["solarRadVolt"] = "group_volt"
weewx.units.obs_group_dict["uvVolt"] = "group_volt"
weewx.units.obs_group_dict["consoleBattery"] = "group_millivolts"
weewx.units.obs_group_dict["consolePower"] = "group_millivolts"
weewx.units.obs_group_dict["signalQuality"] = "group_percent"
weewx.units.obs_group_dict["rssi"] = "group_decibels"
weewx.units.obs_group_dict["uptime"] = "group_deltatime"
weewx.units.obs_group_dict["linkUptime"] = "group_deltatime"
weewx.units.obs_group_dict["packetStreak"] = "group_count"
weewx.units.obs_group_dict["rainfallClicks"] = "group_count"
weewx.units.obs_group_dict["errorPackets"] = "group_count"
weewx.units.obs_group_dict["touchpadWakeups"] = "group_count"
weewx.units.obs_group_dict["localAPIQueries"] = "group_count"
weewx.units.obs_group_dict["txID"] = "group_count"
weewx.units.obs_group_dict["txBatteryFlag"] = "group_count"
weewx.units.obs_group_dict["firmwareVersion"] = "group_count"
weewx.units.obs_group_dict["bootloaderVersion"] = "group_count"
weewx.units.obs_group_dict["healthVersion"] = "group_count"
weewx.units.obs_group_dict["radioVersion"] = "group_count"
weewx.units.obs_group_dict["espressIFVersion"] = "group_count"
weewx.units.obs_group_dict["resynchs"] = "group_count"
weewx.units.obs_group_dict["rxBytes"] = "group_data"
weewx.units.obs_group_dict["txBytes"] = "group_data"
weewx.units.obs_group_dict["rapidRecords"] = "group_data"

schema = [
    ("dateTime", "INTEGER NOT NULL PRIMARY KEY"),  # seconds
    ("usUnits", "INTEGER NOT NULL"),
    ("interval", "INTEGER NOT NULL"),  # seconds
    ("supercapVolt", "REAL"),  # volts
    ("solarVolt", "REAL"),  # volts
    ("packetStreak", "INTEGER"),
    ("txID", "INTEGER"),
    ("txBattery", "REAL"),  # volts
    ("rainfallClicks", "INTEGER"),
    ("solarRadVolt", "REAL"),  # volts
    ("txBatteryFlag", "INTEGER"),
    ("signalQuality", "INTEGER"),  # percent
    ("errorPackets", "INTEGER"),
    ("afc", "REAL"),
    ("rssi", "REAL"),  # decibel-milliwats
    ("resynchs", "INTEGER"),
    ("uvVolt", "REAL"),  # volts
    ("consoleBattery", "REAL"),  # millivolts
    ("rapidRecords", "INTEGER"),
    ("firmwareVersion", "REAL"),
    ("uptime", "REAL"),  # seconds
    ("touchpadWakeups", "INTEGER"),
    ("bootloaderVersion", "REAL"),
    ("localAPIQueries", "INTEGER"),
    ("rxBytes", "INTEGER"),  # bytes
    ("healthVersion", "REAL"),
    ("radioVersion", "REAL"),
    ("espressIFVersion", "REAL"),
    ("linkUptime", "REAL"),  # seconds
    ("consolePower", "REAL"),  # millivolts
    ("txBytes", "INTEGER"),  # bytes
]


def get_historical_url(parameters, api_secret):
    """Construct a valid v2 historical API URL"""

    # Get historical API data
    # Now concatenate all parameters into a string
    urltext = ""
    for key in parameters:
        urltext = urltext + key + str(parameters[key])
    # Now calculate the API signature using the API secret
    api_signature = hmac.new(
        api_secret.encode("utf-8"), urltext.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    # Finally assemble the URL
    apiurl = (
        "https://api.weatherlink.com/v2/historic/%s?api-key=%s&start-timestamp=%s&end-timestamp=%s&api-signature=%s&t=%s"
        % (
            parameters["station-id"],
            parameters["api-key"],
            parameters["start-timestamp"],
            parameters["end-timestamp"],
            api_signature,
            parameters["t"],
        )
    )
    return apiurl


def get_current_url(parameters, api_secret):
    """Construct a valid v2 current API URL"""

    # Remove parameters the current API does not require
    parameters.pop("start-timestamp", None)
    parameters.pop("end-timestamp", None)
    urltext = ""
    for key in parameters:
        urltext = urltext + key + str(parameters[key])
    api_signature = hmac.new(
        api_secret.encode("utf-8"), urltext.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    apiurl = (
        "https://api.weatherlink.com/v2/current/%s?api-key=%s&api-signature=%s&t=%s"
        % (
            parameters["station-id"],
            parameters["api-key"],
            api_signature,
            parameters["t"],
        )
    )
    return apiurl


def get_json(url):
    """Retrieve JSON data from the API"""

    try:
        response = requests.get(url)
    except requests.Timeout as error:
        logerr("Message: %s" % error)
    except requests.RequestException as error:
        logerr("RequestException: %s" % error)

    return response.json()


def decode_historical_json(jdata):
    """Read the historical API JSON data"""

    h_packet = dict()
    try:
        # Iterate through the Historical Data sensor data response from Davis to get Health Metrics
        for sensor_results in iter(jdata["sensors"]):
            logdbg("Sensor Type: {}".format(sensor_results["sensor_type"]))
            logdbg("Data Structure Type : {}".format(sensor_results["data_structure_type"]))

            #Check to see if the Data Structure coincides with the WeatherLink or ISS Health Check
            if sensor_results["data"] and sensor_results["data_structure_type"] in (11, 13, 15):
                logdbg("Found historical data from response.")
                data_values = sensor_results["data"][0]
                
                #Post the data to the dictionary
                h_packet["rxCheckPercent"] = data_values.get("reception")
                h_packet["rssi"] = data_values.get("rssi")
                h_packet["supercapVolt"] = data_values.get("supercap_volt_last")
                h_packet["solarVolt"] = data_values.get("solar_volt_last")
                h_packet["packetStreak"] = data_values.get("good_packets_streak")
                h_packet["txID"] = data_values.get("tx_id")
                h_packet["txBattery"] = data_values.get("trans_battery")
                h_packet["rainfallClicks"] = data_values.get("rainfall_clicks")
                h_packet["solarRadVolt"] = data_values.get("solar_rad_volt_last")
                h_packet["txBatteryFlag"] = data_values.get("trans_battery_flag")
                h_packet["signalQuality"] = data_values.get("reception")
                h_packet["errorPackets"] = data_values.get("error_packets")
                h_packet["afc"] = data_values.get("afc")
                h_packet["resynchs"] = data_values.get("resynchs")
                h_packet["uvVolt"] = data_values.get("uv_volt_last")
            else:
                logdbg("Data not associated with Health Data. Data was : {}".format(sensor_results["data"][0]))                

    except KeyError as error:
        logerr(
            "No valid historical  API data recieved. Double-check API "
            "key/secret and station id. Error is: %s" % error
        )
        logerr("The API data returned was: %s" % jdata)
    except IndexError as error:
        logerr(
            "No valid historical data structure types found in API data. "
            "Error is: %s" % error
        )
        logerr("The API data returned was: %s" % jdata)
    
    return h_packet


def decode_current_json(jdata):
    """Read the current API JSON data"""

    c_packet = dict()

    try:
        # Iterate through the current Data sensor data response from Davis to get Health Metrics
        for sensor_results in iter(jdata["sensors"]):
            logdbg("Sensor Type: {}".format(sensor_results["sensor_type"]))
            logdbg("Data Structure Type : {}".format(sensor_results["data_structure_type"]))

            #We are only concerned with WeatherLinkLive Health data at this time. 
            if sensor_results["data"] and sensor_results["data_structure_type"] == 15:
                logdbg("Found current data from response.")
                data_values = sensor_results["data"][0]

                #Populate Dictionary with known values
                c_packet["rssi"] = data_values.get("wifi_rssi")
                c_packet["consoleBattery"] = data_values.get("battery_voltage")
                c_packet["rapidRecords"] = data_values.get("rapid_records_sent")
                c_packet["firmwareVersion"] = data_values.get("firmware_version")
                c_packet["uptime"] = data_values.get("uptime")
                c_packet["touchpadWakeups"] = data_values.get("touchpad_wakeups")
                c_packet["bootloaderVersion"] = data_values.get("bootloader_version")
                c_packet["localAPIQueries"] = data_values.get("local_api_queries")
                c_packet["rxBytes"] = data_values.get("rx_bytes")
                c_packet["healthVersion"] = data_values.get("health_version")
                c_packet["radioVersion"] = data_values.get("radio_version")
                c_packet["espressIFVersion"] = data_values.get("espressif_version")
                c_packet["linkUptime"] = data_values.get("link_uptime")
                c_packet["consolePower"] = data_values.get("input_voltage")
                c_packet["txBytes"] = data_values.get("tx_bytes")
            else:
                logdbg("Data not associated with Health Data. Data was : {}".format(sensor_results["data"][0]))          


    except KeyError as error:
        logerr(
            "No valid current API data recieved. Double-check API "
            "key/secret and station id. Error is: %s" % error
        )
        logerr("The API data returned was: %s" % jdata)
    except IndexError as error:
        logerr(
            "No valid current data structure types found in API data. "
            "Error is: %s" % error
        )
        logerr("The API data returned was: %s" % jdata)
    
    return c_packet 


class DavisHealthAPI(StdService):
    """Collect Davis sensor health information."""

    def __init__(self, engine, config_dict):
        super(DavisHealthAPI, self).__init__(engine, config_dict)
        self.polling_interval = 360  # FIX THIS
        loginf("service version is %s" % DRIVER_VERSION)
        loginf("archive interval is %s" % self.polling_interval)

        options = config_dict.get("davishealthapi", {})
        self.max_age = weeutil.weeutil.to_int(options.get("max_age", 2592000))
        self.api_key = options.get("api_key", None)
        self.api_secret = options.get("api_secret", None)
        self.station_id = options.get("station_id", None)

        # get the database parameters we need to function
        binding = options.get("data_binding", "davishealthapi_binding")
        self.dbm = self.engine.db_binder.get_manager(
            data_binding=binding, initialize=True
        )

        # be sure schema in database matches the schema we have
        dbcol = self.dbm.connection.columnsOf(self.dbm.table_name)
        dbm_dict = weewx.manager.get_manager_dict(
            config_dict["DataBindings"], config_dict["Databases"], binding
        )
        memcol = [x[0] for x in dbm_dict["schema"]]
        if dbcol != memcol:
            raise Exception(
                "davishealthapi schema mismatch: %s != %s" % (dbcol, memcol)
            )

        self.last_ts = None
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    @staticmethod
    def get_data(api_key, api_secret, station_id, polling_interval):
        """Make an API call and process the data"""
        packet = dict()
        packet["dateTime"] = int(time.time())
        packet["usUnits"] = weewx.US

        if not api_key or not station_id or not api_secret:
            logerr(
                "DavisHealthAPI is missing a required parameter. "
                "Double-check your configuration file. key: %s"
                "secret: %s station ID: %s" % (api_key, api_secret, station_id)
            )
            return packet

        # WL API expects all of the components of the API call to be in
        # alphabetical order before the signature is calculated
        parameters = {
            "api-key": api_key,
            "end-timestamp": int(time.time()),
            "start-timestamp": int(time.time() - polling_interval),
            "station-id": station_id,
            "t": int(time.time()),
        }

        url = get_historical_url(parameters, api_secret)
        logdbg("Historical data url is %s" % url)
        data = get_json(url)
        h_packet = decode_historical_json(data)

        url = get_current_url(parameters, api_secret)
        logdbg("Current data url is %s" % url)
        data = get_json(url)
        c_packet = decode_current_json(data)

        packet.update(h_packet)
        packet.update(c_packet)

        return packet

    def shutDown(self):
        """close database"""
        try:
            self.dbm.close()
        except Exception as error:
            logerr("Database exception: %s" % error)

    def new_archive_record(self, event):
        """save data to database then prune old records as needed"""
        now = int(time.time() + 0.5)
        delta = now - event.record["dateTime"]
        self.last_ts = event.record["dateTime"]
        if delta > event.record["interval"] * 60:
            loginf("Skipping record: time difference %s too big" % delta)
            return
        if self.last_ts is not None:
            self.save_data(self.get_packet(now, self.last_ts))
        self.last_ts = now
        if self.max_age is not None:
            self.prune_data(now - self.max_age)

    def save_data(self, record):
        """save data to database"""
        self.dbm.addRecord(record)

    def prune_data(self, timestamp):
        """delete records with dateTime older than ts"""
        try:
            sql = "delete from %s where dateTime < %d" % (self.dbm.table_name, timestamp)
            self.dbm.getSql(sql)
        
            # sqlite databases need some help to stay small
            # Commenting out as this throws SQL errors with MySQL. Also not sure if this is necessary with the newer SQLite libraries
            
            #self.dbm.getSql("vacuum")
        except Exception as error:
            logerr("Prune data error: %s" % error)

    def get_packet(self, now_ts, last_ts):
        """Retrieves and assembles the final packet"""
        record = self.get_data(
            self.api_key, self.api_secret, self.station_id, self.polling_interval
        )
        # calculate the interval (an integer), and be sure it is non-zero
        record["interval"] = max(1, int((now_ts - last_ts) / 60))
        logdbg("davishealthapi packet: %s" % record)
        return record
