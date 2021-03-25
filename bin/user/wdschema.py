"""
wdschema.py

The WeeWX-WD schema

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

Version: 2.1.3                                          Date: 15 February 2021

Revision History
    15 February 2021    v2.1.3
        - no change, version number change only
    17 November 2020    v2.1.2
        - no change, version number change only
    11 November 2020    v2.1.1
        - no change, version number change only
    1 November 2020     v2.1.0
        - added field sunshine to weewxwd schema
    30 August 2020      v2.0.1
        - no change, version number change only
    20 August 2020          v2.0.0
      - initial release
      - removed WeeWX-WD schema data from wd.py
      - removed forecastTextMetric field
      - WeeWX 3.2+/4.x python2/3 compatible

Below are the default schemas for the WeeWX-WD archive table and WeeWX-WD
supplementary database supp table. They are only used for initialization, or
in conjunction with the weewxwd_config --create-database and --reconfigure
options. Otherwise, once the tables are created the schema is obtained
dynamically from the database. Although a type may be listed here, it may not
necessarily be supported by your weather station hardware.

You may trim this list of any unused types if you wish, but it will not result
in saving as much space as you may think - most of the space is taken up by the
primary key indexes (type "dateTime").
"""

WDSCHEMA_VERSION = '2.1.3'

# define schema for archive table
weewxwd_schema = [
    ('dateTime',     'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
    ('usUnits',      'INTEGER NOT NULL'),
    ('interval',     'INTEGER NOT NULL'),
    ('humidex',      'REAL'),
    ('appTemp',      'REAL'),
    ('outTempDay',   'REAL'),
    ('outTempNight', 'REAL'),
    ('sunshine',     'REAL')
    ]

# define schema for supp table
wdsupp_schema = [
    ('dateTime',            'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
    ('usUnits',             'INTEGER NOT NULL'),
    ('interval',            'INTEGER NOT NULL'),
    ('forecastIcon',        'INTEGER'),
    ('forecastText',        'VARCHAR(256)'),
    ('currentIcon',         'INTEGER'),
    ('currentText',         'VARCHAR(256)'),
    ('tempRecordHigh',      'REAL'),
    ('tempNormalHigh',      'REAL'),
    ('tempRecordHighYear',  'INTEGER'),
    ('tempRecordLow',       'REAL'),
    ('tempNormalLow',       'REAL'),
    ('tempRecordLowYear',   'INTEGER'),
    ('vantageForecastIcon', 'INTEGER'),
    ('vantageForecastRule', 'VARCHAR(256)'),
    ('stormRain',           'REAL'),
    ('stormStart',          'INTEGER'),
    ('maxSolarRad',         'REAL')
    ]
