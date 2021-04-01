"""
install.py

An installer for the WeeWX-Saratoga extension

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

Version: 0.1.0                                          Date: xx xxxxx 2021

Revision History
    xx xxxxx 2021       v0.1.0
        -   initial release
"""

# python imports
from distutils.version import StrictVersion

# WeeWX imports
import weewx

from setup import ExtensionInstaller

REQUIRED_VERSION = "4.0.0"
WS_VERSION = "0.1.0"


def loader():
    return WSInstaller()


class WSInstaller(ExtensionInstaller):
    def __init__(self):
        if StrictVersion(weewx.__version__) < StrictVersion(REQUIRED_VERSION):
            msg = "%s requires WeeWX %s or greater, found %s" % ('WeeWX-Saratoga' + WS_VERSION,
                                                                 REQUIRED_VERSION,
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(WSInstaller, self).__init__(
            version=WS_VERSION,
            name='WeeWX-Saratoga',
            description='WeeWX support for the Saratoga Weather Website templates.',
            author="Gary Roderick",
            author_email="gjroderick<@>gmail.com",
            process_services=['user.ws.WsWXCalculate'],
            archive_services=['user.ws.WsArchive',
                              'user.ws.WsSuppArchive'],
            report_services=['user.rtcr.RealtimeClientraw'],
            config={
                'StdReport': {
                    'WEEWXtagsReport': {
                        'skin': 'WEEWXtags',
                        'enable': 'True',
                        'Units': {
                            'Groups': {
                                'group_altitude': 'foot',
                                'group_degree_day': 'degree_C_day',
                                'group_pressure': 'hPa',
                                'group_rain': 'mm',
                                'group_rainrate': 'mm_per_hour',
                                'group_speed': 'km_per_hour',
                                'group_speed2': 'km_per_hour2',
                                'group_temperature': 'degree_C'
                            },
                            'TimeFormats': {
                                'date_f': '%d/%m/%Y',
                                'date_time_f': '%d/%m/%Y %H:%M'
                            },
                        },
                    },
                    'ClientrawReport': {
                        'skin': 'Clientraw',
                        'enable': 'True',
                        'Units': {
                            'StringFormats': {
                                'degree_C': '%.1f',
                                'degree_compass': '%.0f',
                                'foot': '%.0f',
                                'hPa': '%.1f',
                                'km': '%.1f',
                                'knot': '%.1f',
                                'mm': '%.1f',
                                'percent': '%.0f',
                                'uv_index': '%.1f',
                                'watt_per_meter_squared': '%.0f',
                                'NONE': '--'
                            },
                        },
                    }
                },
                'DataBindings': {
                    'ws_binding': {
                        'database': 'ws_sqlite',
                        'table_name': 'archive',
                        'manager': 'weewx.manager.DaySummaryManager',
                        'schema': 'user.wsschema.ws_schema'
                    },
                    'ws_supp_binding': {
                        'database': 'ws_supp_sqlite',
                        'table_name': 'supp',
                        'manager': 'weewx.manager.Manager',
                        'schema': 'user.wsschema.ws_supp_schema'
                    }
                },
                'Databases': {
                    'ws_sqlite': {
                        'database_type': 'SQLite',
                        'database_name': 'weewxwd.sdb'
                    },
                    'ws_supp_sqlite': {
                        'database_type': 'SQLite',
                        'database_name': 'wdsupp.sdb'
                    },
                    'ws_mysql': {
                        'database_type': 'MySQL',
                        'database_name': 'weewxwd'
                    },
                    'ws_supp_mysql': {
                        'database_type': 'MySQL',
                        'database_name': 'wdsupp'
                    }
                },
                'WeewxSaratoga': {
                    'data_binding': 'ws_binding',
                    'sunshine_threshold': '120',
                    'Supplementary': {
                        'data_binding': 'ws_supp_binding',
                        'WU': {
                            'api_key': 'replace_me',
                            'enable': 'False'
                        },
                        'DS': {
                            'api_key': 'replace_me',
                            'enable': 'False'
                        },
                        'File': {
                            'file': '/path/and/filename',
                            'enable': 'False'
                        }
                    },
                    'RealtimeClientraw': {

                    }
                }
            },
            files=[('bin/user', ['bin/user/rtcr.py',
                                 'bin/user/stackedwindrose.py',
                                 'bin/user/wsastro.py',
                                 'bin/user/wsschema.py',
                                 'bin/user/wssearchlist.py',
                                 'bin/user/wstaggedstats.py',
                                 'bin/user/ws.py']),
                   ('skins/Clientraw', ['skins/Clientraw/clientraw.txt.tmpl',
                                        'skins/Clientraw/clientrawdaily.txt.tmpl',
                                        'skins/Clientraw/clientrawextra.txt.tmpl',
                                        'skins/Clientraw/clientrawhour.txt.tmpl',
                                        'skins/Clientraw/skin.conf']),
                   ('skins/WEEWXtags', ['skins/WEEWXtags/skin.conf',
                                        'skins/WEEWXtags/WEEWXtags.php.tmpl']),
                   ]
            )
