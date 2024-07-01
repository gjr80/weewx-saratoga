# -*- coding: utf-8 -*-
"""
wsxtypes.py

XTypes used to support WeeWX-Saratoga.

Copyright (C) 2021-2023 Gary Roderick                gjroderick<at>gmail.com

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

Version: 0.1.10                                          Date: 1 July 2024

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
        - ensure calc_air_density returns a 'None' ValueTuple if the air
          density pre-requisites exist but at least one is None
        - remove unnecessary unit conversion from calc_abs_humidity
    7 February 2022     v0.1.3
        - version number change only
    25 November 2021    v0.1.2
        - version number change only
    21 May 2021         v0.1.1
        - added version number string constant
    13 May 2021         v0.1.0
        - initial release

"""

# python imports
from __future__ import absolute_import
import datetime
import math
import time

# WeeWX imports
import weewx.engine
import weewx.xtypes

WS_XTYPES_VERSION = '0.1.10'


# ==============================================================================
#                               Class WSXTypes
# ==============================================================================

class WSXTypes(weewx.xtypes.XType):
    """XType to calculate various scalars.

    This XType supports calculation of scalars fo the following types:

    -   Wet bulb temperature
    -   Air density
    -   Absolute humidity
    -   Chandler Burning Index (CBI)
    -   Easter date
    -   Davis forecast text

    Each type to be calculated requires a method named calc_type() where 'type'
    is the name of the type to be calculated. The method must use the following
    signature:

    def calc_type(self, obs_type, record, db_manager):

    where:
        'obs_type' is the name of the type to be calculated
        'record' is a dict containing the current loop packet or archive record
        'db_manager' is a database manager

    The method may be declared static in which case 'self' should be removed.
    Additional types may be supported by adding an appropriately named
    calc_type method.

    The calculation of aggregates and series for supported types is not
    supported.
    """

    def __init__(self):
        # we will need various fields in Metric units so grab a Metric
        # converter to use as required
        self.converter = weewx.units.StdUnitConverters[weewx.METRIC]

    def get_scalar(self, obs_type, record, db_manager):
        # we only know how to calculate types for which we have a calc_type()
        # method, for everything else we raise an UnknownType exception
        # try to calculate obs_type and if we can't raise an UnknownType exception
        try:
            # form the method name, then call it with arguments
            return getattr(self, 'calc_%s' % obs_type)(obs_type, record, db_manager)
        except AttributeError:
            raise weewx.UnknownType(obs_type)

    def calc_wet_bulb(self, obs_type, record, db_manager):
        """Calculate wet bulb temperature."""

        # We need usUnits, outTemp, pressure and outHumidity in order to do the
        # calculation. If any are missing raise a CannotCalculate exception.
        if any(key not in record for key in ['usUnits', 'outTemp', 'pressure', 'outHumidity']):
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

        # We need usUnits, outTemp, pressure and outHumidity in order to do the
        # calculation. If any are missing raise a CannotCalculate exception.
        if any(key not in record for key in ['usUnits', 'outTemp', 'pressure', 'outHumidity']):
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
        else:
            # we could not calculate so save our result as a 'None'
            rho = None
        # return the result as a ValueTuple, no unit conversion needed as there
        # is only one unit
        return weewx.units.ValueTuple(rho, 'kg_per_meter_cubed', 'group_density')

    def calc_abs_humidity(self, obs_type, record, db_manager):
        """Calculate absolute humidity.

        Calculates absolute humidity using the equation:

        d = 100 * e / (tk * rw)

        where:
            e = 6.11 * 10 ** (7.5 * tdc / (237.7 + tdc))
            tk = temperature (K)
            rw = gas constant for water vapor 461.5 (J/kg*Kelvin)
            tdc = dewpoint (C)
        """

        # We need usUnits, outTemp and dewpoint in order to do the calculation.
        # If any are missing raise a CannotCalculate exception.
        if any(key not in record for key in ['usUnits', 'outTemp', 'dewpoint']):
            raise weewx.CannotCalculate(obs_type)

        # calculate if all of our pre-requisites are non-None
        if record['outTemp'] is not None and record['dewpoint'] is not None:
            # we need outTemp in degree_K, first get outTemp from the record as
            # a ValueTuple
            t_vt = weewx.units.as_value_tuple(record, 'outTemp')
            # now convert to degree_C then finally degree_K
            tk = weewx.units.CtoK(self.converter.convert(t_vt).value)
            # we need dewpoint in degree_C, first get dewpoint from the record
            # as a ValueTuple
            td_vt = weewx.units.as_value_tuple(record, 'dewpoint')
            # now convert to degree_C
            tdc = self.converter.convert(td_vt).value
            # do the calculations
            e = 6.11 * 10 ** (7.5 * tdc / (237.7 + tdc))
            d = 100 * e / (tk * 461.5)
        else:
            # we could not calculate so save our result as a 'None'
            d = None
        # return the result as a ValueTuple, no unit conversion is needed as
        # there is only one unit
        return weewx.units.ValueTuple(d, 'kg_per_meter_cubed', 'group_density')

    def calc_cbi(self, obs_type, record, db_manager):
        """Calculate Chandler Burning index."""

        # We need usUnits, outTemp and outHumidity in order to do the
        # calculation. If any are missing raise a CannotCalculate exception.
        if any(key not in record for key in ['usUnits', 'outTemp', 'outHumidity']):
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

    @staticmethod
    def calc_Easter(obs_type, record, db_manager):
        """Calculate the Easter Sunday date for the current year."""

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
        return weewx.units.ValueTuple(easter_ts, 'unix_epoch', 'group_time')

    @staticmethod
    def calc_forecastText(obs_type, record, db_manager):
        """Obtain the Davis forecast text string."""

        # Define a dictionary to look up Davis forecast rule and return
        # forecast text
        davis_fr_dict = {
            0: 'Mostly clear and cooler.',
            1: 'Mostly clear with little temperature change.',
            2: 'Mostly clear for 12 hours with little temperature change.',
            3: 'Mostly clear for 12 to 24 hours and cooler.',
            4: 'Mostly clear with little temperature change.',
            5: 'Partly cloudy and cooler.',
            6: 'Partly cloudy with little temperature change.',
            7: 'Partly cloudy with little temperature change.',
            8: 'Mostly clear and warmer.',
            9: 'Partly cloudy with little temperature change.',
            10: 'Partly cloudy with little temperature change.',
            11: 'Mostly clear with little temperature change.',
            12: 'Increasing clouds and warmer. Precipitation possible within 24 to 48 hours.',
            13: 'Partly cloudy with little temperature change.',
            14: 'Mostly clear with little temperature change.',
            15: 'Increasing clouds with little temperature change. Precipitation possible within 24 hours.',
            16: 'Mostly clear with little temperature change.',
            17: 'Partly cloudy with little temperature change.',
            18: 'Mostly clear with little temperature change.',
            19: 'Increasing clouds with little temperature change. Precipitation possible within 12 hours.',
            20: 'Mostly clear with little temperature change.',
            21: 'Partly cloudy with little temperature change.',
            22: 'Mostly clear with little temperature change.',
            23: 'Increasing clouds and warmer. Precipitation possible within 24 hours.',
            24: 'Mostly clear and warmer. Increasing winds.',
            25: 'Partly cloudy with little temperature change.',
            26: 'Mostly clear with little temperature change.',
            27: 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
            28: 'Mostly clear and warmer. Increasing winds.',
            29: 'Increasing clouds and warmer.',
            30: 'Partly cloudy with little temperature change.',
            31: 'Mostly clear with little temperature change.',
            32: 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
            33: 'Mostly clear and warmer. Increasing winds.',
            34: 'Increasing clouds and warmer.',
            35: 'Partly cloudy with little temperature change.',
            36: 'Mostly clear with little temperature change.',
            37: 'Increasing clouds and warmer. Precipitation possible within 12 hours. Increasing winds.',
            38: 'Partly cloudy with little temperature change.',
            39: 'Mostly clear with little temperature change.',
            40: 'Mostly clear and warmer. Precipitation possible within 48 hours.',
            41: 'Mostly clear and warmer.',
            42: 'Partly cloudy with little temperature change.',
            43: 'Mostly clear with little temperature change.',
            44: 'Increasing clouds with little temperature change. Precipitation possible within 24 to 48 hours.',
            45: 'Increasing clouds with little temperature change.',
            46: 'Partly cloudy with little temperature change.',
            47: 'Mostly clear with little temperature change.',
            48: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours.',
            49: 'Partly cloudy with little temperature change.',
            50: 'Mostly clear with little temperature change.',
            51: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
            52: 'Partly cloudy with little temperature change.',
            53: 'Mostly clear with little temperature change.',
            54: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
            55: 'Partly cloudy with little temperature change.',
            56: 'Mostly clear with little temperature change.',
            57: 'Increasing clouds and warmer. Precipitation possible within 6 to 12 hours.',
            58: 'Partly cloudy with little temperature change.',
            59: 'Mostly clear with little temperature change.',
            60: 'Increasing clouds and warmer. Precipitation possible within 6 to 12 hours. Windy.',
            61: 'Partly cloudy with little temperature change.',
            62: 'Mostly clear with little temperature change.',
            63: 'Increasing clouds and warmer. Precipitation possible within 12 to 24 hours. Windy.',
            64: 'Partly cloudy with little temperature change.',
            65: 'Mostly clear with little temperature change.',
            66: 'Increasing clouds and warmer. Precipitation possible within 12 hours.',
            67: 'Partly cloudy with little temperature change.',
            68: 'Mostly clear with little temperature change.',
            69: 'Increasing clouds and warmer. Precipitation likely.',
            70: 'Clearing and cooler. Precipitation ending within 6 hours.',
            71: 'Partly cloudy with little temperature change.',
            72: 'Clearing and cooler. Precipitation ending within 6 hours.',
            73: 'Mostly clear with little temperature change.',
            74: 'Clearing and cooler. Precipitation ending within 6 hours.',
            75: 'Partly cloudy and cooler.',
            76: 'Partly cloudy with little temperature change.',
            77: 'Mostly clear and cooler.',
            78: 'Clearing and cooler. Precipitation ending within 6 hours.',
            79: 'Mostly clear with little temperature change.',
            80: 'Clearing and cooler. Precipitation ending within 6 hours.',
            81: 'Mostly clear and cooler.',
            82: 'Partly cloudy with little temperature change.',
            83: 'Mostly clear with little temperature change.',
            84: 'Increasing clouds with little temperature change. Precipitation possible within 24 hours.',
            85: 'Mostly cloudy and cooler. Precipitation continuing.',
            86: 'Partly cloudy with little temperature change.',
            87: 'Mostly clear with little temperature change.',
            88: 'Mostly cloudy and cooler. Precipitation likely.',
            89: 'Mostly cloudy with little temperature change. Precipitation continuing.',
            90: 'Mostly cloudy with little temperature change. Precipitation likely.',
            91: 'Partly cloudy with little temperature change.',
            92: 'Mostly clear with little temperature change.',
            93: 'Increasing clouds and cooler. Precipitation possible and windy within 6 hours.',
            94: 'Increasing clouds with little temperature change. Precipitation possible and windy within 6 hours.',
            95: 'Mostly cloudy and cooler. Precipitation continuing. Increasing winds.',
            96: 'Partly cloudy with little temperature change.',
            97: 'Mostly clear with little temperature change.',
            98: 'Mostly cloudy and cooler. Precipitation likely. Increasing winds.',
            99: 'Mostly cloudy with little temperature change. Precipitation continuing. Increasing winds.',
            100: 'Mostly cloudy with little temperature change. Precipitation likely. Increasing winds.',
            101: 'Partly cloudy with little temperature change.',
            102: 'Mostly clear with little temperature change.',
            103: 'Increasing clouds and cooler. Precipitation possible within 12 to 24 hours possible wind shift '
                 'to the W, NW, or N.',
            104: 'Increasing clouds with little temperature change. Precipitation possible within 12 to 24 hours '
                 'possible wind shift to the W, NW, or N.',
            105: 'Partly cloudy with little temperature change.',
            106: 'Mostly clear with little temperature change.',
            107: 'Increasing clouds and cooler. Precipitation possible within 6 hours possible wind shift to the '
                 'W, NW, or N.',
            108: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours possible '
                 'wind shift to the W, NW, or N.',
            109: 'Mostly cloudy and cooler. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
            110: 'Mostly cloudy and cooler. Possible wind shift to the W, NW, or N.',
            111: 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours possible wind '
                 'shift to the W, NW, or N.',
            112: 'Mostly cloudy with little temperature change. Possible wind shift to the W, NW, or N.',
            113: 'Mostly cloudy and cooler. Precipitation ending within 12 hours possible wind shift to the W, NW, or N.',
            114: 'Partly cloudy with little temperature change.',
            115: 'Mostly clear with little temperature change.',
            116: 'Mostly cloudy and cooler. Precipitation possible within 24 hours possible wind shift to the W, NW, or N.',
            117: 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours possible wind '
                 'shift to the W, NW, or N.',
            118: 'Mostly cloudy with little temperature change. Precipitation possible within 24 hours possible wind '
                 'shift to the W, NW, or N.',
            119: 'Clearing, cooler and windy. Precipitation ending within 6 hours.',
            120: 'Clearing, cooler and windy.',
            121: 'Mostly cloudy and cooler. Precipitation ending within 6 hours. Windy with possible wind shift to the '
                 'W, NW, or N.',
            122: 'Mostly cloudy and cooler. Windy with possible wind shift o the W, NW, or N.',
            123: 'Clearing, cooler and windy.',
            124: 'Partly cloudy with little temperature change.',
            125: 'Mostly clear with little temperature change.',
            126: 'Mostly cloudy with little temperature change. Precipitation possible within 12 hours. Windy.',
            127: 'Partly cloudy with little temperature change.',
            128: 'Mostly clear with little temperature change.',
            129: 'Increasing clouds and cooler. Precipitation possible within 12 hours, possibly heavy at times. Windy.',
            130: 'Mostly cloudy and cooler. Precipitation ending within 6 hours. Windy.',
            131: 'Partly cloudy with little temperature change.',
            132: 'Mostly clear with little temperature change.',
            133: 'Mostly cloudy and cooler. Precipitation possible within 12 hours. Windy.',
            134: 'Mostly cloudy and cooler. Precipitation ending in 12 to 24 hours.',
            135: 'Mostly cloudy and cooler.',
            136: 'Mostly cloudy and cooler. Precipitation continuing, possible heavy at times. Windy.',
            137: 'Partly cloudy with little temperature change.',
            138: 'Mostly clear with little temperature change.',
            139: 'Mostly cloudy and cooler. Precipitation possible within 6 to 12 hours. Windy.',
            140: 'Mostly cloudy with little temperature change. Precipitation continuing, possibly heavy at times. Windy.',
            141: 'Partly cloudy with little temperature change.',
            142: 'Mostly clear with little temperature change.',
            143: 'Mostly cloudy with little temperature change. Precipitation possible within 6 to 12 hours. Windy.',
            144: 'Partly cloudy with little temperature change.',
            145: 'Mostly clear with little temperature change.',
            146: 'Increasing clouds with little temperature change. Precipitation possible within 12 hours, possibly '
                 'heavy at times. Windy.',
            147: 'Mostly cloudy and cooler. Windy.',
            148: 'Mostly cloudy and cooler. Precipitation continuing, possibly heavy at times. Windy.',
            149: 'Partly cloudy with little temperature change.',
            150: 'Mostly clear with little temperature change.',
            151: 'Mostly cloudy and cooler. Precipitation likely, possibly heavy at times. Windy.',
            152: 'Mostly cloudy with little temperature change. Precipitation continuing, possibly heavy at times. Windy.',
            153: 'Mostly cloudy with little temperature change. Precipitation likely, possibly heavy at times. Windy.',
            154: 'Partly cloudy with little temperature change.',
            155: 'Mostly clear with little temperature change.',
            156: 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy.',
            157: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy',
            158: 'Increasing clouds and cooler. Precipitation continuing. Windy with possible wind shift to the W, NW, '
                 'or N.',
            159: 'Partly cloudy with little temperature change.',
            160: 'Mostly clear with little temperature change.',
            161: 'Mostly cloudy and cooler. Precipitation likely. Windy with possible wind shift to the W, NW, or N.',
            162: 'Mostly cloudy with little temperature change. Precipitation continuing. Windy with possible wind shift '
                 'to the W, NW, or N.',
            163: 'Mostly cloudy with little temperature change. Precipitation likely. Windy with possible wind shift to '
                 'the W, NW, or N.',
            164: 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy with possible wind shift to '
                 'the W, NW, or N.',
            165: 'Partly cloudy with little temperature change.',
            166: 'Mostly clear with little temperature change.',
            167: 'Increasing clouds and cooler. Precipitation possible within 6 hours possible wind shift to the W, NW, '
                 'or N.',
            168: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy with '
                 'possible wind shift to the W, NW, or N.',
            169: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours possible wind '
                 'shift to the W, NW, or N.',
            170: 'Partly cloudy with little temperature change.',
            171: 'Mostly clear with little temperature change.',
            172: 'Increasing clouds and cooler. Precipitation possible within 6 hours. Windy with possible wind shift to '
                 'the W, NW, or N.',
            173: 'Increasing clouds with little temperature change. Precipitation possible within 6 hours. Windy with '
                 'possible wind shift to the W, NW, or N.',
            174: 'Partly cloudy with little temperature change.',
            175: 'Mostly clear with little temperature change.',
            176: 'Increasing clouds and cooler. Precipitation possible within 12 to 24 hours. Windy with possible wind '
                 'shift to the W, NW, or N.',
            177: 'Increasing clouds with little temperature change. Precipitation possible within 12 to 24 hours. Windy '
                 'with possible wind shift to the W, NW, or N.',
            178: 'Mostly cloudy and cooler. Precipitation possibly heavy at times and ending within 12 hours. Windy with '
                 'possible wind shift to the W, NW, or N.',
            179: 'Partly cloudy with little temperature change.',
            180: 'Mostly clear with little temperature change.',
            181: 'Mostly cloudy and cooler. Precipitation possible within 6 to 12 hours, possibly heavy at times. Windy '
                 'with possible wind shift to the W, NW, or N.',
            182: 'Mostly cloudy with little temperature change. Precipitation ending within 12 hours. Windy with possible '
                 'wind shift to the W, NW, or N.',
            183: 'Mostly cloudy with little temperature change. Precipitation possible within 6 to 12 hours, possibly '
                 'heavy at times. Windy with possible wind shift to the W, NW, or N.',
            184: 'Mostly cloudy and cooler. Precipitation continuing.',
            185: 'Partly cloudy with little temperature change.',
            186: 'Mostly clear with little temperature change.',
            187: 'Mostly cloudy and cooler. Precipitation likely. Windy with possible wind shift to the W, NW, or N.',
            188: 'Mostly cloudy with little temperature change. Precipitation continuing.',
            189: 'Mostly cloudy with little temperature change. Precipitation likely.',
            190: 'Partly cloudy with little temperature change.',
            191: 'Mostly clear with little temperature change.',
            192: 'Mostly cloudy and cooler. Precipitation possible within 12 hours, possibly heavy at times. Windy.',
            193: 'FORECAST REQUIRES 3 HOURS OF RECENT DATA',
            194: 'Mostly clear and cooler.',
            195: 'Mostly clear and cooler.',
            196: 'Mostly clear and cooler.'
        }

        # We need forecastRule in order to do the 'calculation'. If it is
        # missing raise a CannotCalculate exception.
        if 'forecastRule' not in record:
            raise weewx.CannotCalculate(obs_type)
        # calculate if all of our pre-requisites are non-None
        if record['forecastRule'] is not None:
            forecast_text = davis_fr_dict.get(int(record['forecastRule']))
        else:
            forecast_text = None
        # return our result as a ValueTuple using None as the units and group
        return weewx.units.ValueTuple(forecast_text, None, None)


# ==============================================================================
#                             Class StdWSXTypes
# ==============================================================================

class StdWSXTypes(weewx.engine.StdService):
    """Instantiate and register the XTypes extension WSXTypes."""

    def __init__(self, engine, config_dict):
        super(StdWSXTypes, self).__init__(engine, config_dict)

        self.wsxtypes = WSXTypes()
        weewx.xtypes.xtypes.append(self.wsxtypes)

    def shutDown(self):
        weewx.xtypes.xtypes.remove(self.wsxtypes)


# define unit group 'group_density' with units 'kg_per_meter_cubed'
weewx.units.USUnits['group_density'] = 'kg_per_meter_cubed'
weewx.units.MetricUnits['group_density'] = 'kg_per_meter_cubed'
weewx.units.MetricWXUnits['group_density'] = 'kg_per_meter_cubed'
# set default formats and labels for density
weewx.units.default_unit_format_dict['kg_per_meter_cubed'] = '%.3f'
weewx.units.default_unit_label_dict['kg_per_meter_cubed'] = u' kg/m³'

# tell the unit system what group observation types 'wetBulb' and 'air_density'
# belong to
weewx.units.obs_group_dict['wet_bulb'] = "group_temperature"
weewx.units.obs_group_dict['air_density'] = "group_density"