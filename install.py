"""
install.py

An installer for the WeeWX-Saratoga extension.

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 2 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

Version: 0.1.10                                          Date: 1 July 2024

Revision History
    1 July 2024         v0.1.10
        - version number change only
    29 February 2024    v0.1.9
        - fix bug in version_compare
    16 January 2024     v0.1.8
        - remove distutils.StrictVersion dependency
    31 August 2023      v0.1.7
        - set HTML_ROOT for each skin to avoid conflict with any existing skins
    24 March 2023       v0.1.6
        - version number change only
    17 January 2023     v0.1.5
        - version number change only
    3 April 2022        v0.1.4
        - version number change only
    7 February 2022     v0.1.3
        - version number change only
    25 November 2021    v0.1.2
        - version number change only
    21 May 2021         v0.1.1
        - version number change only
    13 May 2021         v0.1.0
        - initial release
"""

# python imports
import configobj

try:
    # Python 3
    from io import StringIO
except ImportError:
    # Python 2
    from StringIO import StringIO

# WeeWX imports
import weewx

from setup import ExtensionInstaller

REQUIRED_WEEWX_VERSION = "4.5.0"
WS_VERSION = "0.1.10"

# Multi-line config string, makes it easier to include comments. Needs to be
# explicitly set as unicode or python2 StringIO complains.
ws_config = u"""
[StdReport]
    [[WEEWXtagsReport]]
        HTML_ROOT = public_html/saratoga
        skin = WEEWXtags
        enable = True
        [[[Units]]]
            [[[[StringFormats]]]]
                NONE = --
            [[[[TimeFormats]]]]
                date_f = %d/%m/%Y
                date_time_f = %d/%m/%Y %H:%M
    [[ClientrawReport]]
        HTML_ROOT = public_html/saratoga
        skin = Clientraw
        enable = True
        [[[Units]]]
            [[[[StringFormats]]]]
                degree_C = %.1f
                degree_compass = %.0f
                foot = %.0f
                hPa = %.1f
                km = %.1f
                knot = %.1f
                mm = %.1f
                percent = %.0f
                uv_index = %.1f
                watt_per_meter_squared = %.0f
                NONE = --
                
[StdWXCalculate]
    [[Calculations]]
        wet_bulb = prefer_hardware
        abs_humidity = prefer_hardware, archive
        
[DataBindings]
    [[ws_binding]]
        database = ws_sqlite
        table_name = archive
        manager = weewx.manager.DaySummaryManager
        schema = user.wsschema.ws_schema
        
[Databases]
    [[ws_sqlite]]
        database_type = SQLite
        database_name = weewxwd.sdb
    [[ws_mysql]]
        database_type = MySQL
        database_name = weewxwd
        
[WeewxSaratoga]
    # WeewxSaratoga database binding
    data_binding = ws_binding
    
    # radiation (solar insolation) level above which the sun is considered 
    # shining
    sunshine_threshold = 120
    
    [[RealtimeClientraw]]

        # If using an external website, configure remote_server_url to point to 
        # the post_clientraw.php script on your website like:
        #   remote_server_url = http://your.website.com/post_clientraw.php
        #
        # To disable or use the webserver on this system, leave the entry 
        # commented out or blank.
        # remote_server_url = http://your.website.com/post_clientraw.php
        
        # min_interval sets the minimum clientraw.txt generation interval. 
        # 10 seconds is recommended for all Saratoga template users. Default 
        # is 0 seconds.
        min_interval = 10
        
        # Python date-time format strings. Format string codes as per 
        # https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
         
        # Date format. Recommended entries are:
        #   date_format = %-m/%-d/%Y  # recommended for USA users
        #   date_format = %-d/%-m/%Y  # recommended for non-USA users
        date_format = %-d/%-m/%Y

        # Long format times (HMS). Recommended entries are:
        #   long_time_format = %-I:%M:%S_%p  # recommended for USA users
        #   long_time_format = %H:%M:%S  # recommended for non-USA users 
        long_time_format = %H:%M:%S
        
        # Short format times (HM). Recommended entries are:
        #   short_time_format = %-I:%M_%p  # recommended for USA users
        #   short_time_format = %H:%M  # recommended for non-USA users
        short_time_format = %H:%M
        
[Accumulator]

    # Start WeeWX-Saratoga extractors
    [[forecastRule]]
        extractor = last
    [[forecastText]]
        accumulator = firstlast
        extractor = last
"""
# obtain our config string as a configobj dict
ws_dict = configobj.ConfigObj(StringIO(ws_config))


def version_compare(v1, v2):
    """Basic 'distutils' and 'packaging' free version comparison.

    v1 and v2 are WeeWX version numbers in string format.

    Returns:
        0 if v1 and v2 are the same
        -1 if v1 is less than v2
        +1 if v1 is greater than v2
    """

    import itertools
    mash = itertools.zip_longest(v1.split('.'), v2.split('.'), fillvalue='0')
    for x1, x2 in mash:
        try:
            y1, y2 = int(x1), int(x2)
        except ValueError:
            y1, y2 = x1, x2
        if y1 > y2:
            return 1
        if y1 < y2:
            return -1
    return 0


def loader():
    return WSInstaller()


class WSInstaller(ExtensionInstaller):
    def __init__(self):
        if version_compare(weewx.__version__, REQUIRED_WEEWX_VERSION) < 0:
            msg = "%s requires WeeWX %s or greater, found %s" % ('WeeWX-Saratoga' + WS_VERSION,
                                                                 REQUIRED_WEEWX_VERSION,
                                                                 weewx.__version__)
            raise weewx.UnsupportedFeature(msg)
        super(WSInstaller, self).__init__(
            version=WS_VERSION,
            name='WeeWX-Saratoga',
            description='WeeWX support for the Saratoga Weather Website Templates.',
            author="Gary Roderick",
            author_email="gjroderick<@>gmail.com",
            process_services=['user.ws.WsWXCalculate'],
            xtype_services=['user.wsxtypes.StdWSXTypes'],
            archive_services=['user.ws.WsArchive'],
            report_services=['user.rtcr.RealtimeClientraw'],
            config=ws_dict,
            files=[('bin/user', ['bin/user/rtcr.py',
                                 'bin/user/stackedwindrose.py',
                                 'bin/user/ws.py',
                                 'bin/user/wsastro.py',
                                 'bin/user/wsschema.py',
                                 'bin/user/wssearchlist.py',
                                 'bin/user/wstaggedstats.py',
                                 'bin/user/wsxtypes.py']),
                   ('skins/Clientraw', ['skins/Clientraw/clientrawdaily.txt.tmpl',
                                        'skins/Clientraw/clientrawextra.txt.tmpl',
                                        'skins/Clientraw/clientrawhour.txt.tmpl',
                                        'skins/Clientraw/skin.conf']),
                   ('skins/WEEWXtags', ['skins/WEEWXtags/skin.conf',
                                        'skins/WEEWXtags/WEEWXtags.php.tmpl',
                                        'skins/WEEWXtags/font/LICENSE.txt',
                                        'skins/WEEWXtags/font/OpenSans-Bold.ttf',
                                        'skins/WEEWXtags/font/OpenSans-Regular.ttf']),
                   ]
            )