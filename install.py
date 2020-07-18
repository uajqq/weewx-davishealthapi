# installer for davishealthapi

from weecfg.extension import ExtensionInstaller

def loader():
    return DavisHealthAPIInstaller()

class DavisHealthAPIInstaller(ExtensionInstaller):
    def __init__(self):
        super(DavisHealthAPIInstaller, self).__init__(
            version='0.10',
            name='davishealthapi',
            description='Collect and display station health information from the Davis WeatherLink API.',
            author='uajqq',
            author_email='',
            data_services='user.davishealthapi.DavisHealthAPI',
            files=[('bin/user', ['bin/user/davishealthapi.py'])],
            config={
                'davishealthapi': {
                    'data_binding': 'davishealthapi_binding',
                    'station_id': '',
                    'api-key': '',
                    'api-secret': ''
                },
                'DataBindings': {
                    'davishealthapi_binding': {
                        'database': 'davishealthapi_sqlite',
                        'table_name': 'archive',
                        'manager': 'weewx.manager.DaySummaryManager',
                        'schema': 'user.davishealthapi.schema'
                    }
                },
                'Databases': {
                    'davishealthapi_sqlite': {
                        'database_type': 'SQLite',
                        'database_name': 'davishealthapi.sdb'}
                    },
                'StdReport': {
                    'Defaults': {
                        'Labels': {
                            'Generic': {
                                'signalQuality': 'Signal Quality',
                                'supercapVolt': 'Supercapacitor',
                                'solarVolt': 'Solar Cell',
                                'packetStreak': 'Good Packets Streak',
                                'txID': 'Transmitter ID',
                                'txBattery': 'Transmitter Battery',
                                'rainfallClicks': 'Bucket Tips',
                                'solarRadVolt': 'Solar Radiation Sensor Solar Cell',
                                'txBatteryFlag': 'Transmitter Battery Status',
                                'errorPackets': 'Error Packets',
                                'afc': 'AFC',
                                'rssi': 'Signal Strength',
                                'resynchs': 'Re-synchronizations',
                                'uvVolt': 'UV Sensor Solar Cell',
                                'consoleBattery': 'Console Battery',
                                'rapidRecords': 'Rapid Records',
                                'firmwareVersion': 'Firmware Version',
                                'uptime': 'Uptime',
                                'touchpadWakeups': 'Touchpad Wakeups',
                                'bootloaderVersion': 'Bootloader Version',
                                'localAPIQueries': 'Local API Queries',
                                'rxBytes': 'Data Received',
                                'healthVersion': 'Davis Health Version',
                                'radioVersion': 'Radio Version',
                                'espressIFVersion': 'EspressIF Version',
                                'linkUptime': 'Link Uptime',
                                'consolePower': 'Console AC Power',
                                'txBytes': 'Data Transmitted',
                            }
                        }
                    }
                }
            }
        )
