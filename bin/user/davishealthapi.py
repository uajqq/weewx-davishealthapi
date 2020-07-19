'''
weewx module that records health information from a Davis weather station using
the v2 API.

Adapted from the cmon driver by Matthew Hall

This file contains both a weewx driver and a weewx service.

Installation

Put this file in the bin/user directory.


Service Configuration

Add the following to weewx.conf:

[davishealthapi]
    data_binding = davishealthapi_binding
    max_age = 2592000 # 30 days; None to store indefinitely

[DataBindings]
    [[davishealthapi_binding]]
        database = davishealthapi_sqlite
        manager = weewx.manager.DaySummaryManager
        table_name = archive
        schema = user.davishealthapi.schema

[Databases]
    [[davishealthapi_sqlite]]
        root = %(WEEWX_ROOT)s
        database_name = archive/davishealthapi.sdb
        driver = weedb.sqlite

[Engine]
    [[Services]]
        archive_services = ..., user.davishealthapi


Driver Configuration

Add the following to weewx.conf:

[Station]
    station_type = davishealthapi

[davishealthapi]
    polling_interval = 60
    driver = user.davishealthapi


Schema

The default schema is defined in this file.  If you prefer to maintain a schema
different than the default, specify the desired schema in the configuration.

[DataBindings]
    [[davishealthapi_binding]]
        database = davishealthapi_sqlite
        manager = weewx.manager.DaySummaryManager
        table_name = archive
        [[[schema]]]
            dateTime = INTEGER NOT NULL PRIMARY KEY
            usUnits = INTEGER NOT NULL
            ...etc

Another approach to maintaining a custom schema is to define the schema in the
file user/extensions.py as davishealthapiSchema:

davishealthapiSchema = [
    ('dateTime', 'INTEGER NOT NULL PRIMARY KEY'),
    ('usUnits', 'INTEGER NOT NULL'),
    ...etc
    ]

then load it using this configuration:

[DataBindings]
    [[davishealthapi_binding]]
        database = davishealthapi_sqlite
        manager = weewx.manager.DaySummaryManager
        table_name = archive
        schema = user.extensions.davishealthapiSchema
'''

from __future__ import with_statement
from __future__ import absolute_import
from __future__ import print_function
import time
import collections
import hashlib
import hmac
import requests

import weewx
import weeutil.weeutil
from weewx.drivers import AbstractDevice
from weewx.engine import StdService
import weewx.units

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging
    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'davishealthapi: %s:' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

DRIVER_NAME = 'DavisHealthAPI'
DRIVER_VERSION = '0.10'

if weewx.__version__ < '3':
    raise weewx.UnsupportedFeature('weewx 3 is required, found %s' %
                                   weewx.__version__)

weewx.units.USUnits['group_decibels'] = 'decibels'
weewx.units.MetricUnits['group_decibels'] = 'decibels'
weewx.units.MetricWXUnits['group_decibels'] = 'decibels'
weewx.units.default_unit_format_dict['decibels'] = '%.1f'
weewx.units.default_unit_label_dict['decibels'] = ' dBm'

weewx.units.USUnits['group_millivolts'] = 'millivolts'
weewx.units.MetricUnits['group_millivolts'] = 'millivolts'
weewx.units.MetricWXUnits['group_millivolts'] = 'millivolts'
weewx.units.default_unit_format_dict['millivolts'] = '%d'
weewx.units.default_unit_label_dict['millivolts'] = ' mV'


weewx.units.obs_group_dict['supercapVolt'] = 'group_volt'
weewx.units.obs_group_dict['solarVolt'] = 'group_volt'
weewx.units.obs_group_dict['txBattery'] = 'group_volt'
weewx.units.obs_group_dict['solarRadVolt'] = 'group_volt'
weewx.units.obs_group_dict['uvVolt'] = 'group_volt'
weewx.units.obs_group_dict['consoleBattery'] = 'group_millivolts'
weewx.units.obs_group_dict['consolePower'] = 'group_millivolts'
weewx.units.obs_group_dict['signalQuality'] = 'group_percent'
weewx.units.obs_group_dict['rssi'] = 'group_decibels'
weewx.units.obs_group_dict['uptime'] = 'group_deltatime'
weewx.units.obs_group_dict['linkUptime'] = 'group_deltatime'
weewx.units.obs_group_dict['packetStreak'] = 'group_count'
weewx.units.obs_group_dict['rainfallClicks'] = 'group_count'
weewx.units.obs_group_dict['errorPackets'] = 'group_count'
weewx.units.obs_group_dict['touchpadWakeups'] = 'group_count'
weewx.units.obs_group_dict['localAPIQueries'] = 'group_count'
weewx.units.obs_group_dict['txID'] = 'group_count'
weewx.units.obs_group_dict['txBatteryFlag'] = 'group_count'
weewx.units.obs_group_dict['firmwareVersion'] = 'group_count'
weewx.units.obs_group_dict['bootloaderVersion'] = 'group_count'
weewx.units.obs_group_dict['healthVersion'] = 'group_count'
weewx.units.obs_group_dict['radioVersion'] = 'group_count'
weewx.units.obs_group_dict['espressIFVersion'] = 'group_count'
weewx.units.obs_group_dict['resynchs'] = 'group_count'
weewx.units.obs_group_dict['rxBytes'] = 'group_data'
weewx.units.obs_group_dict['txBytes'] = 'group_data'
weewx.units.obs_group_dict['rapidRecords'] = 'group_data'

schema = [
    ('dateTime', 'INTEGER NOT NULL PRIMARY KEY'), #seconds
    ('usUnits', 'INTEGER NOT NULL'),
    ('interval', 'INTEGER NOT NULL'), #seconds
    ('supercapVolt', 'REAL'), #volts
    ('solarVolt', 'REAL'), #volts
    ('packetStreak', 'INTEGER'),
    ('txID', 'INTEGER'),
    ('txBattery', 'REAL'), #volts
    ('rainfallClicks', 'INTEGER'),
    ('solarRadVolt', 'REAL'), #volts
    ('txBatteryFlag', 'INTEGER'),
    ('signalQuality', 'INTEGER'), #percent
    ('errorPackets', 'INTEGER'),
    ('afc', 'REAL'),
    ('rssi', 'REAL'), #decibel-milliwats
    ('resynchs', 'INTEGER'),
    ('uvVolt', 'REAL'), #volts
    ('consoleBattery', 'REAL'), #millivolts
    ('rapidRecords', 'INTEGER'),
    ('firmwareVersion', 'REAL'),
    ('uptime', 'REAL'), #seconds
    ('touchpadWakeups', 'INTEGER'),
    ('bootloaderVersion', 'REAL'),
    ('localAPIQueries', 'INTEGER'),
    ('rxBytes', 'INTEGER'), #bytes
    ('healthVersion', 'REAL'),
    ('radioVersion', 'REAL'),
    ('espressIFVersion', 'REAL'),
    ('linkUptime', 'REAL'), #seconds
    ('consolePower', 'REAL'), #millivolts
    ('txBytes', 'INTEGER'), #bytes
    ]

class GetAPIData:
    '''Assemble API URLs and makes the calls'''
    def get_data(station_id, api_key, api_secret, poll_interval):
        historical_response = None
        current_response = None
        packet = dict()
        packet['dateTime'] = int(time.time())
        packet['usUnits'] = weewx.US

        if not api_key or not station_id or not api_secret:
            logerr(
                'DavisHealthAPI is missing a required parameter. '
                'Double-check your configuration file. key: %s'
                'secret: %s station ID: %s' %
                (api_key, api_secret, station_id)
            )
            return packet

        # Get historical API data
        # WL API expects all of the components of the API call to be in
        # alphabetical order before the signature is calculated
        parameters = {
            'api-key': api_key,
            'station-id': station_id,
            't': int(time.time()),
            'start-timestamp': int(time.time()-poll_interval),
            'end-timestamp': int(time.time())
        }
        parameters = collections.OrderedDict(sorted(parameters.items()))
        for key in parameters:
            loginf('health: %s is %s' % (key, parameters[key]))
        # Now concatenate all parameters into a string
        urltext = ''
        for key in parameters:
            urltext = urltext + key + str(parameters[key])
        # Now calculate the API signature using the API secret
        api_signature = hmac.new(
            api_secret.encode('utf-8'),
            urltext.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        # Finally assemble the URL
        apiurl = (
            'https://api.weatherlink.com/v2/historic/%s?api-key=%s'
            '&start-timestamp=%s&end-timestamp=%s&api-signature=%s'
            '&t=%s' %
            (parameters['station-id'], parameters['api-key'],
             parameters['start-timestamp'], parameters['end-timestamp'],
             api_signature, parameters['t'])
        )
        # Make the API call and collect JSON
        try:
            historical_response = requests.get(apiurl).json()
        except requests.Timeout as error:
            logerr('Message: %s' % error)
        except requests.RequestException as error:
            logerr('RequestException: %s' % error)

        # Get current API data using same procedure as above
        parameters = {
            'api-key': api_key,
            'station-id': station_id,
            't': int(time.time())
        }
        parameters = collections.OrderedDict(sorted(parameters.items()))
        urltext = ''
        for key in parameters:
            urltext = urltext + key + str(parameters[key])
        api_signature = hmac.new(
            api_secret.encode('utf-8'),
            urltext.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        apiurl = (
            'https://api.weatherlink.com/v2/current/%s?api-key=%s'
            '&api-signature=%s&t=%s' %
            (parameters['station-id'], parameters['api-key'],
             api_signature, parameters['t']))
        try:
            current_response = requests.get(apiurl).json()
        except requests.Timeout as error:
            logerr('Message: %s' % error)
        except requests.RequestException as error:
            logerr('RequestException: %s' % error)

        try:
            historical_data = historical_response['sensors']
            for i in range(7):
                if (
                        historical_data[i]['data'] and (
                            historical_data[i]['data_structure_type'] == 11
                            or
                            historical_data[i]['data_structure_type'] == 13
                        )
                ):
                    loginf('Found historical data from data ID %s' % i)
                    values = historical_data[i]['data'][0]

                    packet['rxCheckPercent'] = values.get('reception')
                    packet['rssi'] = values.get('rssi')
                    packet['supercapVolt'] = values.get('supercap_volt_last')
                    packet['solarVolt'] = values.get('solar_volt_last')
                    packet['packetStreak'] = values.get('good_packets_streak')
                    packet['txID'] = values.get('tx_id')
                    packet['txBattery'] = values.get('trans_battery')
                    packet['rainfallClicks'] = values.get('rainfall_clicks')
                    packet['solarRadVolt'] = values.get('solar_rad_volt_last')
                    packet['txBatteryFlag'] = values.get('trans_battery_flag')
                    packet['signalQuality'] = values.get('reception')
                    packet['errorPackets'] = values.get('error_packets')
                    packet['afc'] = values.get('afc')
                    packet['resynchs'] = values.get('resynchs')
                    packet['uvVolt'] = values.get('uv_volt_last')

                    break
            current_data = current_response['sensors']
            for i in range(7):
                if (
                        current_data[i]['data']
                        and
                        current_data[i]['data_structure_type'] == 15
                ):
                    loginf('Found current data from data ID %s' % i)
                    values = current_data[i]['data'][0]

                    packet['consoleBattery'] = values.get('battery_voltage')
                    packet['rapidRecords'] = values.get('rapid_records_sent')
                    packet['firmwareVersion'] = values.get('firmware_version')
                    packet['uptime'] = values.get('uptime')
                    packet['touchpadWakeups'] = values.get('touchpad_wakeups')
                    packet['bootloaderVersion'] = values.get('bootloader_version')
                    packet['localAPIQueries'] = values.get('local_api_queries')
                    packet['rxBytes'] = values.get('rx_bytes')
                    packet['healthVersion'] = values.get('health_version')
                    packet['radioVersion'] = values.get('radio_version')
                    packet['espressIFVersion'] = values.get('espressif_version')
                    packet['linkUptime'] = values.get('link_uptime')
                    packet['consolePower'] = values.get('input_voltage')
                    packet['txBytes'] = values.get('tx_bytes')

                    break
        except KeyError as error:
            logerr(
                'No valid API data recieved. Double-check API '
                'key/secret and station id. Error is: %s' % error
            )
        except IndexError as error:
            logerr(
                'No valid data structure types found in API data. '
                'Error is: %s' % error
            )
        finally:
            return packet

def loader(config_dict, engine):
    return DavisHealthAPIDriver(**config_dict['DavisHealthAPI'])

class DavisHealthAPIDriver(AbstractDevice):
    '''Driver for collecting computer health data.'''

    def __init__(self, **stn_dict):
        loginf('driver version is %s' % DRIVER_VERSION)
        self.polling_interval = int(stn_dict.get('polling_interval', 60))
        loginf('polling interval is %s' % self.polling_interval)
        self.api_key = stn_dict.get('api_key', None)
        self.api_secret = stn_dict.get('api_secret', None)
        self.station_id = stn_dict.get('station_id', None)

    @property
    def hardware_name(self):
        return 'DavisHealthAPI'

    def genLoopPackets(self):
        while True:
            packet = (
                GetAPIData.get_data(self.station_id, self.api_key,
                                    self.api_secret, self.polling_interval)
            )
            yield packet
            time.sleep(self.polling_interval)


class DavisHealthAPI(StdService):
    '''Collect Davis sensor health information.'''

    def __init__(self, engine, config_dict):
        super(DavisHealthAPI, self).__init__(engine, config_dict)
        self.archive_interval = 360 #FIX THIS
        loginf('service version is %s' % DRIVER_VERSION)
        loginf('archive interval is %s' % self.archive_interval)

        options = config_dict.get('davishealthapi', {})
        self.max_age = weeutil.weeutil.to_int(options.get('max_age', 2592000))
        self.api_key = options.get('api_key', None)
        self.api_secret = options.get('api_secret', None)
        self.station_id = options.get('station_id', None)
        loginf('Collected config options are: %s %s %s' % (
            self.api_key, self.api_secret, self.station_id))

        # get the database parameters we need to function
        binding = options.get('data_binding', 'davishealthapi_binding')
        self.dbm = self.engine.db_binder.get_manager(data_binding=binding,
                                                     initialize=True)

        # be sure schema in database matches the schema we have
        dbcol = self.dbm.connection.columnsOf(self.dbm.table_name)
        dbm_dict = weewx.manager.get_manager_dict(
            config_dict['DataBindings'], config_dict['Databases'], binding)
        memcol = [x[0] for x in dbm_dict['schema']]
        if dbcol != memcol:
            raise Exception('davishealthapi schema mismatch: %s != %s' %
                            (dbcol, memcol))

        self.last_ts = None
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def shutDown(self):
        try:
            self.dbm.close()
        except:
            pass

    def new_archive_record(self, event):
        '''save data to database then prune old records as needed'''
        now = int(time.time() + 0.5)
        delta = now - event.record['dateTime']
        loginf('Now: %s Delta: %s' % (now, delta))
        self.last_ts = event.record['dateTime']
        if delta > event.record['interval'] * 60:
            logdbg('Skipping record: time difference %s too big' % delta)
            return
        if self.last_ts is not None:
            self.save_data(self.get_data(now, self.last_ts))
        self.last_ts = now
        if self.max_age is not None:
            self.prune_data(now - self.max_age)

    def save_data(self, record):
        '''save data to database'''
        self.dbm.addRecord(record)

    def prune_data(self, ts):
        '''delete records with dateTime older than ts'''
        sql = 'delete from %s where dateTime < %d' % (self.dbm.table_name, ts)
        self.dbm.getSql(sql)
        try:
            # sqlite databases need some help to stay small
            self.dbm.getSql('vacuum')
        except Exception:
            pass

    def get_data(self, now_ts, last_ts):
        record = (
            GetAPIData.get_data(self.station_id, self.api_key,
                                self.api_secret, self.archive_interval)
        )
        # calculate the interval (an integer), and be sure it is non-zero
        record['interval'] = max(1, int((now_ts - last_ts) / 60))
        loginf('davishealthapi packet: %s' % record)
        return record
