"""
wsxtypes.py

Xtypes used to support WeeWX-Saratoga.

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

Version: 0.1.0                                          Date: xx xxxxx 2021

Revision History
    xx xxxxx 2021       v0.1.0
        -   initial release

"""

from __future__ import absolute_import

import datetime
import logging

# WeeWX imports
import weewx.engine
import weewx.xtypes

log = logging.getLogger(__name__)


class OutTempDayNight(weewx.xtypes.XType):

    def __init__(self):
        pass

    @staticmethod
    def get_scalar(obs_type, record, db_manager):
        # We only know how to calculate 'outTempDay' and 'outTempNight'. For
        # everything else, raise an exception UnknownType
        if obs_type not in ['outTempDay', 'outTempNight']:
            raise weewx.UnknownType(obs_type)

        # we need outTemp in order to do the calculation
        if 'outTemp' not in record:
            raise weewx.CannotCalculate(obs_type)

        # if outTemp is None then we simply return None
        if record['outTemp'] is None:
            return None

        # otherwise we need to know the hour of the day
        hod = int(datetime.datetime.fromtimestamp(record['dateTime']).strftime('%H'))
        if 5 < hod < 18:
            # it's daytime
            if obs_type == 'outTempDay':
                return record['outTemp']
            else:
                # must be after outTempNight which is None
                return None
        else:
            # it's nighttime
            if obs_type == 'outTempNight':
                return record['outTemp']
            else:
                # must be after outTempDay which is None
                return None
"""
    @staticmethod
    def get_aggregate(obs_type, timespan, aggregate_type, db_manager, **option_dict):
        "Returns an aggregation of an observation type over a given time period, using the
        main archive table.

        obs_type: The type over which aggregation is to be done (e.g., 'barometer',
        'outTemp', 'rain', ...)

        timespan: An instance of weeutil.Timespan with the time period over which
        aggregation is to be done.

        aggregate_type: The type of aggregation to be done.

        db_manager: An instance of weewx.manager.Manager or subclass.

        option_dict: Not used in this version.

        returns: A ValueTuple containing the result.

        SELECT outTemp, dateTime FROM archive WHERE FROM_UNIXTIME(dateTime, "%H") > 5 AND FROM_UNIXTIME(dateTime, "%H") < 18 ORDER BY outTemp DESC LIMIT 1;
        SELECT inverterTemp, dateTime FROM archive WHERE strftime("%H", dateTime, 'unixepoch', 'localtime') > '11' AND strftime("%H", dateTime, 'unixepoch', 'localtime') < '15' ORDER BY inverterTemp DESC LIMIT 1;

        "
"""

class StdOutTempDayNight(weewx.engine.StdService):
    """Instantiate and register the XTypes extension outTempDayNight."""

    def __init__(self, engine, config_dict):
        super(StdOutTempDayNight, self).__init__(engine, config_dict)

        self.day_night_temp = OutTempDayNight()
        weewx.xtypes.xtypes.append(self.day_night_temp)

    def shutDown(self):
        weewx.xtypes.xtypes.remove(self.day_night_temp)


class WetBulb(weewx.xtypes.XType):

    def __init__(self):
        self.converter = weewx.units.StdUnitConverters[weewx.METRIC]

    def get_scalar(self, obs_type, record, db_manager):
        # We only know how to calculate 'wetBulb'. For everything else, raise
        # an exception UnknownType
        if obs_type not in ['wetBulb', ]:
            raise weewx.UnknownType(obs_type)

        # we need outTemp, pressure and outHumidity in order to do the
        # calculation
        if 'outTemp' not in record and 'pressure' not in record and 'outHumidity' not in record:
            raise weewx.CannotCalculate(obs_type)

        # calculate if all of our pre-requisites are non-None
        if record['outTemp'] is not None and record['pressure'] is not None and record['outHumidity'] is not None:
            # we need outTemp in degree_C, first get outTemp from the record as
            # a ValueTuple
            t_vt = weewx.units.as_value_tuple(record, 'outTemp')
            # now convert to degree_C
            tc = self.converter.convert(t_vt)
            # we need pressure in hPa, first get pressure from the record as a
            # ValueTuple
            p_vt = weewx.units.as_value_tuple(record, 'pressure')
            # now convert to hPa
            p = self.converter.convert(p_vt)
            # outHumidity is already in percent so no need to convert
            rh = record['outHumidity']
            # do the calculations
            tdc = ((tc - (14.55 + 0.114 * tc) * (1 - (0.01 * rh)) -
                   ((2.5 + 0.007 * tc) * (1 - (0.01 * rh))) ** 3 -
                   (15.9 + 0.117 * tc) * (1 - (0.01 * rh)) ** 14))
            e = (6.11 * 10 ** (7.5 * tdc / (237.7 + tdc)))
            wb = ((((0.00066 * p) * tc) + ((4098 * e) / ((tdc + 237.7) ** 2) * tdc)) /
                  ((0.00066 * p) + (4098 * e) / ((tdc + 237.7) ** 2)))
            # our result is in degree_C, put it in a ValueTuple so we can
            # convert it if needed
            wb_vt = weewx.units.ValueTuple(wb, 'degree_C', 'group_temperature')
        else:
            # we could not calculate so save our result as a 'None' ValueTuple
            wb_vt = weewx.units.ValueTuple(None, 'degree_C', 'group_temperature')
        # finally convert to our 'record' units and return the result
        return weewx.units.as_value_tuple(wb_vt, record['usUnits']).value


class StdWetBulb(weewx.engine.StdService):
    """Instantiate and register the XTypes extension WetBulb."""

    def __init__(self, engine, config_dict):
        super(StdWetBulb, self).__init__(engine, config_dict)

        self.wet_bulb = WetBulb()
        weewx.xtypes.xtypes.append(self.wet_bulb)

    def shutDown(self):
        weewx.xtypes.xtypes.remove(self.wet_bulb)
