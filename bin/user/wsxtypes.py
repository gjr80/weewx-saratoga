# -*- coding: utf-8 -*-
"""
wsxtypes.py

XTypes used to support WeeWX-Saratoga.

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

# python imports
from __future__ import absolute_import
import datetime
import logging
import math
import time

# WeeWX imports
import weewx.engine
import weewx.xtypes

log = logging.getLogger(__name__)


class WSXTypes(weewx.xtypes.XType):
    """XType to calculate wet bulb temperature."""

    def __init__(self):
        # we will need temperature and pressure in C and hPa, grab a Metric
        # converter to use as required
        self.converter = weewx.units.StdUnitConverters[weewx.METRIC]

    def get_scalar(self, obs_type, record, db_manager):
        # We only know how to calculate wet bulb temperature 'wetBulb', air
        # density 'air_density', 'Chandler Burning Index 'cbi' and the date of
        # next Easter 'Easter'. For everything else, raise an UnknownType
        # exception.
        try:
            # form the method name, then call it with arguments
            return getattr(self, 'calc_%s' % obs_type)(obs_type, record, db_manager)
        except AttributeError:
            raise weewx.UnknownType(obs_type)

    def calc_wet_bulb(self, obs_type, record, db_manager):
        """Calculate wet bulb temperature."""

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
            tc = self.converter.convert(t_vt).value
            # we need pressure in hPa, first get pressure from the record as a
            # ValueTuple
            p_vt = weewx.units.as_value_tuple(record, 'pressure')
            # now convert to hPa
            p = self.converter.convert(p_vt).value
            # outHumidity is already in percent so no need to convert
            rh = record['outHumidity']
            # do the calculations
            tdc = ((tc - (14.55 + 0.114 * tc) * (1 - (0.01 * rh)) -
                    ((2.5 + 0.007 * tc) * (1 - (0.01 * rh))) ** 3 -
                    (15.9 + 0.117 * tc) * (1 - (0.01 * rh)) ** 14))
            e = (6.11 * 10 ** (7.5 * tdc / (237.7 + tdc)))
            wb = ((((0.00066 * p) * tc) + ((4098 * e) / ((tdc + 237.7) ** 2) * tdc)) /
                  ((0.00066 * p) + (4098 * e) / ((tdc + 237.7) ** 2)))
        else:
            # we could not calculate so save our result as a 'None'
            wb = None
        # finally return our wet bulb ValueTuple converting to the units
        # used in 'record'
        return weewx.units.convertStd(weewx.units.ValueTuple(wb, 'degree_C', 'group_temperature'),
                                      record['usUnits'])

    def calc_air_density(self, obs_type, record, db_manager):
        """Calculate air density.

        Calculates air density using the equation:

        rho = p_d/(R_d * Tk) + p_v/(R_v * Tk)

        where:
            rho = density of air (kg/cubic metre)
            p_d = partial pressure of dry air (Pa)
                = phpa * 100 - p_v
            phpa = atmospheric pressure (hPa)
            R_d = specific gas constant for dry air, 287.058 J/(kgK)
            Tk = temperature (K)
            p_v = pressure of water vapor (Pa)
                = rh * p_sat
            R_v = specific gas constant for water vapor, 461.495 J/(kgK)
            rh = relative humidity (0.0-1.0)
            p_sat = saturation vapor pressure (Pa)
                  = 611.21 * math.exp((18.678 - Tc / 234.5) * (Tc / (257.14 + Tc)) where Tc > 0
                  = 611.15 * math.exp((23.036 - Tc / 333.7) * (Tc / (279.82 + Tc)) where Tc < 0
            Tc = temperature (C)

        Saturation vapor pressure (p_sat) is approximated using the Arden Buck
        equations.
        """

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
            tc = self.converter.convert(t_vt).value
            # we need pressure in hPa, first get pressure from the record as a
            # ValueTuple
            p_vt = weewx.units.as_value_tuple(record, 'pressure')
            # now convert to hPa
            phpa = self.converter.convert(p_vt).value
            # outHumidity is already in percent so no need to convert but we do
            # need it in the range 0.0 - 1.0, so divide by 100
            rh = record['outHumidity'] / 100.0

            # do the calculations
            # calculate the saturation vapor pressure in Pa
            if tc >= 0:
                p_sat = 611.21 * math.exp((18.678 - tc / 234.5) * (tc / (257.14 + tc)))
            else:
                p_sat = 611.15 * math.exp((23.036 - tc / 333.7) * (tc / (279.82 + tc)))
            # calculate the pressure of water vapor in Pa
            p_v = rh * p_sat
            # calculate the partial pressure of dry air in Pa
            p_d = phpa * 100 - p_v
            # calculate air density in kg/meter cubed
            rho = p_d / (287.058 * (tc + 273.15)) + p_v / (461.495 * (tc + 273.15))
            # return the result as a ValueTuple, no unit conversion needed as
            # there is only one unit
            return weewx.units.ValueTuple(rho, 'kg_per_meter_cubed', 'group_density')

    def calc_cbi(self, obs_type, record, db_manager):
        """Calculate Chandler Burning index."""

        # we need outTemp and outHumidity in order to do the calculation
        if 'outTemp' not in record and 'outHumidity' not in record:
            raise weewx.CannotCalculate(obs_type)

        # calculate if all of our pre-requisites are non-None
        if record['outTemp'] is not None and record['outHumidity'] is not None:
            # we need outTemp in degree_C, first get outTemp from the record as
            # a ValueTuple
            t_vt = weewx.units.as_value_tuple(record, 'outTemp')
            # now convert to degree_C
            tc = self.converter.convert(t_vt).value
            # outHumidity is already in percent so no need to convert
            rh = record['outHumidity']
            # do the calculations
            cbi = max(0.0, round((((110 - 1.373 * rh) - 0.54 * (10.20 - tc)) *
                                  (124 * 10 ** (-0.0142 * rh))) / 60, 1))
        else:
            cbi = 0.0
        # return our result as a ValueTuple, there is no unit conversion
        # required as group_count only supports one unit
        return weewx.units.ValueTuple(cbi, 'count', 'group_count')

    def calc_Easter(self, obs_type, record, db_manager):
        """Calculate the date of the next Easter."""

        def calc_easter(year):
            """Calculate the date for Easter in a given year.

            Uses a modified version of Butcher's Algorithm. Refer New Scientist,
            30 March 1961 pp 828-829
            https://books.google.co.uk/books?id=zfzhCoOHurwC&printsec=frontcover&source=gbs_ge_summary_r&cad=0#v=onepage&q&f=false

            year: an integer representing the year of interest.

            Returns: An epoch timestamp representing the next Easter Sunday after
                     the current record timestamp. The time represented is midnight
                     at the start of Easter Sunday.
            """

            a = year % 19
            b = year // 100
            c = year % 100
            d = b // 4
            e = b % 4
            g = (8 * b + 13) // 25
            h = (19 * a + b - d - g + 15) % 30
            i = c // 4
            k = c % 4
            l = (2 * e + 2 * i - h - k + 32) % 7
            m = (a + 11 * h + 19 * l) // 433
            n = (h + l - 7 * m + 90) // 25
            p = (h + l - 7 * m + 33 * n + 19) % 32
            _dt = datetime.datetime(year=year, month=n, day=p)
            _ts = time.mktime(_dt.timetuple())
            return _ts

        # all we need is the timestamp from the record
        # first obtain the year of interest
        _year = datetime.date.fromtimestamp(record['dateTime']).year
        # calculate Easter for _year
        easter_ts = calc_easter(_year)
        # check to see if we have past this calculated date, if so we want next
        # years date so increment year and recalculate
        if datetime.date.fromtimestamp(easter_ts) < datetime.date.fromtimestamp(record['dateTime']):
            easter_ts = calc_easter(_year + 1)
        return weewx.units.ValueTuple(easter_ts, 'unix_epoch', 'group_time')


class StdWSXTypes(weewx.engine.StdService):
    """Instantiate and register the XTypes extension WSXTypes."""

    def __init__(self, engine, config_dict):
        super(StdWSXTypes, self).__init__(engine, config_dict)

        self.wet_bulb = WSXTypes()
        weewx.xtypes.xtypes.append(self.wet_bulb)

    def shutDown(self):
        weewx.xtypes.xtypes.remove(self.wet_bulb)


# define unit group 'group_density' with units 'kg_per_meter_cubed'
weewx.units.USUnits['group_density'] = 'kg_per_meter_cubed'
weewx.units.MetricUnits['group_density'] = 'kg_per_meter_cubed'
weewx.units.MetricWXUnits['group_density'] = 'kg_per_meter_cubed'
# set default formats and labels for density
weewx.units.default_unit_format_dict['kg_per_meter_cubed'] = '%.3f'
weewx.units.default_unit_label_dict['kg_per_meter_cubed'] = u' kg/m³'

# tell the unit system what group observation types 'wetBulb' and 'air_density'
# belong to
weewx.units.obs_group_dict['wetBulb'] = "group_temperature"
weewx.units.obs_group_dict['air_density'] = "group_density"

