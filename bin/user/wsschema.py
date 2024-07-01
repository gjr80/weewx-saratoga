"""
wsschema.py

The WeeWX-Saratoga schema

Copyright (C) 2021-2023 Gary Roderick                gjroderick<at>gmail.com

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

Version: 0.1.10                                         Date: 1 July 2024

Revision History
    1 July 2024         v0.1.10
        - version number change only
    29 February 2024    v0.1.9
        - version number change only
    16 January 2024     v0.1.8
        - version number change only
    31 August 2023      v0.1.7
        - version number change only
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

Below are the default schemas for the WeeWX-Saratoga archive table and
WeeWX-Saratoga supplementary database supp table. They are only used for
initialization, or in conjunction with the wee_database --create-database and
--reconfigure options. Otherwise, once the tables are created the schema is
obtained dynamically from the database. Although a type may be listed here, it
may not necessarily be supported by your weather station hardware.

You may trim this list of any unused types if you wish, but it will not result
in saving as much space as you may think - most of the space is taken up by the
primary key indexes (type "dateTime").
"""

WS_SCHEMA_VERSION = '0.1.10'

# define schema for archive table
ws_schema = [
    ('dateTime',     'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
    ('usUnits',      'INTEGER NOT NULL'),
    ('interval',     'INTEGER NOT NULL'),
    ('outTempDay',   'REAL'),
    ('outTempNight', 'REAL'),
    ('sunshine',     'REAL')
    ]