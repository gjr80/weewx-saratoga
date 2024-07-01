"""
wsastro.py

Astronomical search list extensions for WeeWX-Saratoga

Copyright (C) 2021-2023 Gary Roderick                gjroderick<at>gmail.com

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

Version: 0.1.1                                          Date: 1 July 2024

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
        -   initial release
"""

# python imports
from array import array
import bisect
import datetime
import math
import time

# python 2/3 compatibility shims
from six.moves import zip

# WeeWX imports
import weewx
from weewx.cheetahgenerator import SearchList
from weewx.units import ValueHelper, ValueTuple

# import/setup logging, WeeWX v3 is syslog based but WeeWX v4 is logging based,
# try v4 logging and if it fails use v3 logging
try:
    # WeeWX4 logging
    import logging

    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

except ImportError:
    # WeeWX legacy (v3) logging via syslog
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'wsastro: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

WS_ASTRO_VERSION = '0.1.10'


class MoonApsis(SearchList):
    """WeeWX SLE to provide various lunar apogee/perigee details.

       Code to calculate apogee and perigee details based on public domain
       Javascript code used at https://www.fourmilab.ch/earthview/pacalc.html
    """

    def __init__(self, generator):
        SearchList.__init__(self, generator)
        self.periarg = array('f', [2,  0,  0,  4,  0,  0,  6,  0,  0,  8,  0,  0,
                                   2, -1,  0,  0,  1,  0, 10,  0,  0,  4, -1,  0,
                                   6, -1,  0, 12,  0,  0,  1,  0,  0,  8, -1,  0,
                                   14,  0,  0,  0,  0,  2,  3,  0,  0, 10, -1,  0,
                                   16,  0,  0, 12, -1,  0,  5,  0,  0,  2,  0,  2,
                                   18,  0,  0, 14, -1,  0,  7,  0,  0,  2,  1,  0,
                                   20,  0,  0,  1,  1,  0, 16, -1,  0,  4,  1,  0,
                                   9,  0,  0,  4,  0,  2,  2, -2,  0,  4, -2,  0,
                                   6, -2,  0, 22,  0,  0, 18, -1,  0,  6,  1,  0,
                                   11,  0,  0,  8,  1,  0,  4,  0, -2,  6,  0,  2,
                                   3,  1,  0,  5,  1,  0, 13,  0,  0, 20, -1,  0,
                                   3,  2,  0,  4, -2,  2,  1,  2,  0, 22, -1,  0,
                                   0,  0,  4,  6,  0, -2,  2,  1, -2,  0,  2,  0,
                                   0, -1,  2,  2,  0,  4,  0, -2,  2,  2,  2, -2,
                                   24,  0,  0,  4,  0, -4,  2,  2,  0, 1, -1,  0])

        self.pericoeff = array('f', [-1.6769,  0.4589, -0.1856,  0.0883, -0.0773,
                                     0.0502, -0.0460,  0.0422, -0.0256,  0.0253,
                                     0.0237,  0.0162, -0.0145,  0.0129, -0.0112,
                                     -0.0104,  0.0086,  0.0069,  0.0066, -0.0053,
                                     -0.0052, -0.0046, -0.0041,  0.0040,  0.0032,
                                     -0.0032,  0.0031, -0.0029,  0.0027,  0.0027,
                                     -0.0027,  0.0024, -0.0021, -0.0021, -0.0021,
                                     0.0019, -0.0018, -0.0014, -0.0014, -0.0014,
                                     0.0014, -0.0014,  0.0013,  0.0013,  0.0011,
                                     -0.0011, -0.0010, -0.0009, -0.0008,  0.0008,
                                     0.0008,  0.0007,  0.0007,  0.0007, -0.0006,
                                     -0.0006,  0.0006,  0.0005,  0.0005, -0.0004,
                                     0])

        self.peritft = array('f', [4, 5, 7, -1])

        self.peritfc = array('f', [0.00019, -0.00013, -0.00011])

        self.apoarg = array('f', [2,  0,  0,  4,  0,  0,  0,  1,  0,  2, -1,  0,
                                  0,  0,  2,  1,  0,  0,  6,  0,  0,  4, -1,  0,
                                  2,  0,  2,  1,  1,  0,  8,  0,  0,  6, -1,  0,
                                  2,  0, -2,  2, -2,  0,  3,  0,  0,  4,  0,  2,
                                  8, -1,  0,  4, -2,  0, 10,  0,  0,  3,  1,  0,
                                  0,  2,  0,  2,  1,  0,  2,  2,  0,  6,  0,  2,
                                  6, -2,  0, 10, -1,  0,  5,  0,  0,  4,  0, -2,
                                  0,  1,  2, 12,  0,  0,  2, -1,  2,  1, -1,  0])

        self.apocoeff = array('f', [0.4392,  0.0684,  0.0456, 0.0426,  0.0212,
                                    -0.0189,  0.0144,  0.0113, 0.0047,  0.0036,
                                    0.0035,  0.0034, -0.0034, 0.0022, -0.0017,
                                    0.0013,  0.0011,  0.0010, 0.0009,  0.0007,
                                    0.0006,  0.0005,  0.0005, 0.0004,  0.0004,
                                    0.0004, -0.0004, -0.0004, 0.0003,  0.0003,
                                    0.0003, -0.0003,  0])

        self.apotft = array('f', [2, 3, -1])

        self.apotfc = array('f', [-0.00011, -0.00011])

        self.periparg = array('f', [0,  0,  0,  2,  0,  0,  4,  0,  0,  2, -1,  0,
                                    6,  0,  0,  1,  0,  0,  8,  0,  0,  0,  1,  0,
                                    0,  0,  2,  4, -1,  0,  2,  0, -2, 10,  0,  0,
                                    6, -1,  0,  3,  0,  0,  2,  1,  0,  1,  1,  0,
                                    12,  0,  0,  8, -1,  0,  2,  0,  2,  2, -2,  0,
                                    5,  0,  0, 14,  0,  0, 10, -1,  0,  4,  1,  0,
                                    12, -1,  0,  4, -2,  0,  7,  0,  0,  4,  0,  2,
                                    16,  0,  0,  3,  1,  0,  1, -1,  0,  6,  1,  0,
                                    0,  2,  0, 14, -1,  0,  2,  2,  0,  6, -2,  0,
                                    2, -1, -2,  9,  0,  0, 18,  0,  0,  6,  0,  2,
                                    0, -1,  2, 16, -1,  0,  4,  0, -2,  8,  1,  0,
                                    11,  0,  0,  5,  1,  0, 20,  0,  0])

        self.peripcoeff = array('f', [3629.215, 63.224, -6.990,  2.834,  1.927,
                                      -1.263, -0.702,  0.696, -0.690, -0.629,
                                      -0.392,  0.297,  0.260,  0.201, -0.161,
                                      0.157, -0.138, -0.127,  0.104,  0.104,
                                      -0.079,  0.068,  0.067,  0.054, -0.038,
                                      -0.038,  0.037, -0.037, -0.035, -0.030,
                                      0.029, -0.025,  0.023,  0.023, -0.023,
                                      0.022, -0.021, -0.020,  0.019,  0.017,
                                      0.014, -0.014,  0.013,  0.012,  0.011,
                                      0.010, -0.010,  0])

        self.periptft = array('f', [3, 7, 9, -1])

        self.periptfc = array('f', [-0.0071, -0.0017, 0.0016])

        self.apoparg = array('f', [0,  0,  0,  2,  0,  0,  1,  0,  0,  0,  0,
                                   2,  0,  1,  0,  4,  0,  0,  2, -1,  0,  1,
                                   1,  0,  4, -1,  0,  6,  0,  0,  2,  1,  0,
                                   2,  0,  2,  2,  0, -2,  2, -2,  0,  2,  2,
                                   0,  0,  2,  0,  6, -1,  0,  8,  0,  0])

        self.apopcoeff = array('f', [3245.251, -9.147, -0.841,  0.697, -0.656,
                                     0.355,  0.159,  0.127,  0.065,  0.052,
                                     0.043,  0.031, -0.023,  0.022,  0.019,
                                     -0.016,  0.014,  0.010,  0])

        self.apoptft = array('f', [4, -1])

        self.apoptfc = array('f', [0.0016, -1])
        self.apsis_type_lookup = {'p': 'perigee', 'a': 'apogee'}

    @staticmethod
    def fixangle(a):
        """Range reduce angle in degrees."""

        return a - 360.0 * (math.floor(a / 360.0))

    def sumser(self, trig, d, m, f, t, argtab, coeff, tfix, tfixc):
        """Sum the series of periodic terms."""

        j = 0
        n = 0
        summ = 0
        d = math.radians(self.fixangle(d))
        m = math.radians(self.fixangle(m))
        f = math.radians(self.fixangle(f))

        i = 0
        while coeff[i] != 0.0:
            arg = (d * argtab[j]) + (m * argtab[j + 1]) + (f * argtab[j + 2])
            j += 3
            coef = coeff[i]
            if i == tfix[n]:
                coef += t * tfixc[n]
                n += 1
            summ += coef * trig(arg)
            i += 1

        return summ

    def moonpa(self, k):
        """Calculate perigee or apogee from index number."""

        earth_radius = 6378.14

        t = k - math.floor(k)
        if 0.499 < t < 0.501:
            apg = True
        elif t > 0.999 or t < 0.001:
            apg = False
        else:
            return

        t = k / 1325.55
        t2 = t * t
        t3 = t2 * t
        t4 = t3 * t

        # Mean time of perigee or apogee
        jde = 2451534.6698 + 27.55454989 * k - 0.0006691 * t2 - 0.000001098 * t3 + 0.0000000052 * t4
        # Mean elongation of the Moon
        d = 171.9179 + 335.9106046 * k - 0.0100383 * t2 - 0.00001156 * t3 + 0.000000055 * t4
        # Mean anomaly of the Sun
        m = 347.3477 + 27.1577721 * k - 0.0008130 * t2 - 0.0000010 * t3
        # Moon's argument of latitude
        f = 316.6109 + 364.5287911 * k - 0.0125053 * t2 - 0.0000148 * t3
        jde += self.sumser(math.sin, d, m, f, t,
                           self.apoarg if apg else self.periarg,
                           self.apocoeff if apg else self.pericoeff,
                           self.apotft if apg else self.peritft,
                           self.apotfc if apg else self.peritfc)
        par = self.sumser(math.cos, d, m, f, t,
                          self.apoparg if apg else self.periparg,
                          self.apopcoeff if apg else self.peripcoeff,
                          self.apoptft if apg else self.periptft,
                          self.apoptfc if apg else self.periptfc)
        par = math.radians(par / 3600.0)

        return array('d', [jde, par, earth_radius / math.sin(par)])

    def get_extension_list(self, timespan, db_lookup):
        """Create a search list with various lunar perigee and apogee details.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will hold the
                    start and stop times of the domain of valid times.

          db_lookup: This is a function that, given a data binding as its only
                     parameter, will return a database manager object.

        Returns:
          moon_apsis: A list of tuples with details of each apogee/perigee in
                      the current year. Tuple format is:
                        (apsis_type, apsis_ts, apsis_distance)
                      where:
                        apsis_type is 'a' for apogee or 'p' for perigee
                        apsis_ts is a ValueHelper with the timestamp of the
                          apsis
                        apsis_distance is the distance in km of the moon from
                          earth at apsis.
          next_apogee_ts: ValueHelper containing date-time of next apogee
                          (could be next year)
          next_apogee_dist_km: Earth to Moon distance in km at next apogee
                               (WeeWX has no notion of km/mi so cannot use a
                               ValueHelper)
          next_perigee_ts: ValueHelper containing date-time of next apogee
                           (could be next year)
          next_perigee_dist_km: Earth to Moon distance in km at next perigee
                                (WeeWX has no notion of km/mi so cannot use a
                                ValueHelper)
          max_apogee: Tuple with details of apogee where Moon is furthest from
                      Earth (ie max apogee) this year.
                      Format is:
                        (apsis_ts, apsis_distance)
                      where apsis_ts and apsis_distance as per moon_apsis above
          min_perigee: Tuple with details of perigee where Moon is closest to
                       Earth (ie min apogee) this year.
                       Format is:
                         (apsis_ts, apsis_distance)
                       where apsis_ts and apsis_distance as per moon_apsis
                       above
        """

        t1 = time.time()

        # get starting date for our list of apogee/perigees
        curr_year = datetime.date.fromtimestamp(timespan.stop).year
        ssk = math.floor((curr_year - 1999.97) * 13.2555)
        apsis_list = []
        # Get our list of apogees/perigees for the current year. List will
        # include last apogee/perigee from previous year and first
        # apogee/perigee from next year
        for z in range(0, 40):
            sk = ssk + z * 0.5
            apsis = 'p' if (sk - math.floor(sk)) < 0.25 else 'a'
            pa = self.moonpa(sk)
            pa_ts = (pa[0]-2440587.5) * 86400.0
            # save our ts as a ValueHelper
            pa_ts_vh = ValueHelper((pa_ts, 'unix_epoch', 'group_time'),
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)
            # add the latest event to our list
            apsis_list.append((apsis, pa_ts_vh, pa[2]))
            if datetime.date.fromtimestamp(pa_ts).year > curr_year:
                # if we have an apsis from next year then grab one more then
                # stop, we have enough
                sk = ssk + (z + 1) * 0.5
                apsis = 'p' if (sk - math.floor(sk)) < 0.25 else 'a'
                pa = self.moonpa(sk)
                pa_ts = (pa[0]-2440587.5) * 86400.0
                # save our ts as a ValueHelper
                pa_ts_vh = ValueHelper((pa_ts, 'unix_epoch', 'group_time'),
                                       formatter=self.generator.formatter,
                                       converter=self.generator.converter)
                # add the latest event to our list
                apsis_list.append((apsis, pa_ts_vh, pa[2]))
                break

        # make sure our list is in date order
        apsis_list.sort(key=lambda ts: ts[1].raw)

        # get timestamps for start of this year and start of next year,
        # necessary so we can identify which events occur this year
        _tt = time.localtime(timespan.stop)
        _ts = time.mktime((_tt.tm_year, 1, 1, 0, 0, 0, 0, 0, -1))
        _ts_y = time.mktime((_tt.tm_year + 1, 1, 1, 0, 0, 0, 0, 0, -1))
        # get max apogee for the year (ie the greatest distance to moon)
        max_apogee = max(apsis_list,
                         key=lambda ap: ap[2] if _ts <= ap[1].raw < _ts_y else 0)
        max_apogee = (max_apogee[1], max_apogee[2])
        # get min perigee for the year (ie the least distance to moon)
        min_perigee = min(apsis_list,
                          key=lambda ap: ap[2] if _ts <= ap[1].raw < _ts_y else 1000000)
        min_perigee = (min_perigee[1], min_perigee[2])

        # split our apsis list into individual components so we can find the
        # next apogee and perigee
        apsis_type_list, apsis_ts_vh_list, apsis_dist_list = list(zip(*apsis_list))
        # ts list elements are ValueHelpers, so we need to break it down further
        apsis_ts_list = [ts_vh.raw for ts_vh in apsis_ts_vh_list]
        try:
            # find the index of the next apogee or perigee
            next_apsis_idx = bisect.bisect_left(apsis_ts_list, timespan.stop)
            if apsis_type_list[next_apsis_idx] == 'a':
                # if an apogee then capture apogee/perigee details accordingly
                next_apogee_ts_vh = apsis_ts_vh_list[next_apsis_idx]
                next_apogee_dist = apsis_dist_list[next_apsis_idx]
                next_perigee_ts_vh = apsis_ts_vh_list[next_apsis_idx + 1]
                next_perigee_dist = apsis_dist_list[next_apsis_idx + 1]
            else:
                # if a perigee then capture apogee/perigee details accordingly
                next_perigee_ts_vh = apsis_ts_vh_list[next_apsis_idx]
                next_perigee_dist = apsis_dist_list[next_apsis_idx]
                next_apogee_ts_vh = apsis_ts_vh_list[next_apsis_idx + 1]
                next_apogee_dist = apsis_dist_list[next_apsis_idx + 1]
        except ValueError:
            # if we had an error then set everything to None
            next_apogee_ts_vh = ValueHelper((None, 'unix_epoch', 'group_time'),
                                            formatter=self.generator.formatter,
                                            converter=self.generator.converter)
            next_apogee_dist = None
            next_perigee_ts_vh = ValueHelper((None, 'unix_epoch', 'group_time'),
                                             formatter=self.generator.formatter,
                                             converter=self.generator.converter)
            next_perigee_dist = None

        # now create a small dictionary with suitable keys
        search_list_extension = {'moon_apsis': apsis_list,
                                 'next_apogee_ts': next_apogee_ts_vh,
                                 'next_apogee_dist_km': next_apogee_dist,
                                 'next_perigee_ts': next_perigee_ts_vh,
                                 'next_perigee_dist_km': next_perigee_dist,
                                 'max_apogee': max_apogee,
                                 'min_perigee': min_perigee}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("MoonApsis SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]


class Eclipse(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)
        self.solar_eclipses = ((1414100739, 'A'), (1414100739, 'P'),
                               (1426844807, 'T'), (1442127319, 'P'),
                               (1457488699, 'T'), (1472720882, 'A'),
                               (1488120873, 'A'), (1503340000, 'T'),
                               (1518727953, 'P'), (1531450936, 'P'),
                               (1533980848, 'P'), (1546738958, 'P'),
                               (1562095447, 'T'), (1577337533, 'A'),
                               (1592721675, 'A'), (1607962479, 'T'),
                               (1623321787, 'A'), (1638603278, 'T'),
                               (1651351356, 'P'), (1666695680, 'P'),
                               (1681964276, 'H'), (1697306441, 'A'),
                               (1712600309, 'T'), (1727894773, 'A'),
                               (1743245316, 'P'), (1758483784, 'P'),
                               (1771330386, 'A'), (1786556826, 'T'),
                               (1801929648, 'A'), (1817201270, 'T'),
                               (1832512139, 'A'), (1847847400, 'T'),
                               (1863105228, 'P'), (1875931573, 'P'),
                               (1878478639, 'P'), (1891177438, 'P'),
                               (1906525753, 'A'), (1921819897, 'T'),
                               (1937114164, 'A'), (1952456851, 'H'),
                               (1967722002, 'A'), (1983072853, 'P'),
                               (1995818556, 'T'), (2011096471, 'P'),
                               (2026462725, 'T'), (2041690768, 'A'),
                               (2057094354, 'A'), (2072311006, 'T'),
                               (2087700409, 'P'), (2100421926, 'P'),
                               (2102952345, 'P'), (2115712135, 'P'),
                               (2131065636, 'T'), (2146312031, 'A'),
                               (2161690375, 'A'), (2176938010, 'T'),
                               (2192289174, 'A'), (2207579026, 'T'),
                               (2220320582, 'P'))
        self.solar_eclipse_type_lookup = {'A': 'Annular', 'H': 'Hybrid',
                                          'P': 'Partial', 'T': 'Total'
                                          }
        self.lunar_eclipses = ((1308168823, 'T'), (1323527576, 'T'),
                               (1338807860, 'P'), (1354113247, 'Pe'),
                               (1366920518, 'P'), (1369455066, 'Pe'),
                               (1382140285, 'Pe'), (1397548008, 'T'),
                               (1412765744, 'T'), (1428148884, 'T'),
                               (1443408497, 'T'), (1458733701, 'Pe'),
                               (1474052127, 'Pe'), (1486773903, 'Pe'),
                               (1502130098, 'P'), (1517405460, 'T'),
                               (1532722974, 'T'), (1548047607, 'T'),
                               (1563312715, 'P'), (1578683471, 'Pe'),
                               (1591385174, 'Pe'), (1593923472, 'Pe'),
                               (1606729441, 'Pe'), (1622027993, 'T'),
                               (1637312646, 'P'), (1652674362, 'T'),
                               (1667905222, 'T'), (1683307445, 'Pe'),
                               (1698524118, 'P'), (1711350839, 'Pe'),
                               (1726627525, 'P'), (1741935596, 'T'),
                               (1757268778, 'T'), (1772537692, 'T'),
                               (1787890444, 'P'), (1803165246, 'Pe'),
                               (1815926649, 'Pe'), (1818486899, 'Pe'),
                               (1831263253, 'P'), (1846520457, 'P'),
                               (1861894395, 'T'), (1877138602, 'T'),
                               (1892500992, 'T'), (1907778874, 'P'),
                               (1923085731, 'Pe'), (1935892322, 'Pe'),
                               (1938426317, 'Pe'), (1951112805, 'Pe'),
                               (1966518891, 'T'), (1981739020, 'T'),
                               (1997118831, 'T'), (2012381783, 'T'),
                               (2027704019, 'Pe'), (2043024457, 'P'),
                               (2055747972, 'Pe'), (2071098735, 'P'),
                               (2086380786, 'T'), (2101690352, 'T'),
                               (2117023298, 'T'), (2132280593, 'P'),
                               (2147658592, 'Pe'), (2160355502, 'Pe'),
                               (2162892956, 'Pe'), (2175702300, 'Pe'),
                               (2190999265, 'P'), (2206284988, 'P'),
                               (2221645582, 'T'), (2236878281, 'T'))
        self.lunar_eclipse_type_lookup = {'P': 'Partial',
                                          'Pe': 'Penumbral',
                                          'T': 'Total'
                                          }

    @staticmethod
    def delta_t(ts):
        """Calculates the difference between Universal Time (UT) and
           Terrestrial Dynamical Time (TD). This allows UT of an eclipse to be
           determined from the NASA provided eclipse time (which is in TD)
           using the formula:

                delta T = TD - UT

           delta T is calculated using the approximation:

                delta T = 62.92 + 0.32217 * t + 0.005589 * (t ** 2)

            where
                t = y - 2000
                y = year + (month number - 0.5)/12

           Source: http://eclipse.gsfc.nasa.gov/LEcat5/deltat.html
        """

        try:
            dt = datetime.datetime.fromtimestamp(ts)
            if 2005 < dt.year < 2050:
                y = dt.year + (dt.month - 0.5)/12
                t = y - 2000
                result = 62.92 + 0.32217 * t + 0.00589 * t ** 2
            else:
                result = None
        except ValueError:
            result = None
        return result

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with details of the next Solar and Lunar eclipse.

           Details provided include epoch timestamp of the eclipse as well as
           the type. Note that the dictionary of eclipses is all eclipses, not
           just eclipses visible at the station's location, so the eclipse
           returned may not be visible to the user. Eclipse data is based upon
           NASA Solar and Lunar eclipse tables at the following sites:

           http://eclipse.gsfc.nasa.gov/solar.html
           http://eclipse.gsfc.nasa.gov/lunar.html

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          next_solar_eclipse: Timestamp of next solar eclipse
          next_solar_eclipse_type: Type of next solar eclipse. Can be 'Annular',
                                   'Hybrid', 'Partial' or 'Total'
          next_lunar_eclipse: Timestamp of next lunar eclipse
          next_lunar_eclipse_type: Type of next lunar eclipse. Can be 'Partial',
                                   'Penumbral' or 'Total'
        """

        t1 = time.time()

        # get a timestamp for now
        search_ts = timespan.stop
        # split our eclipse list tuples into individual lists
        solar_eclipse_ts_list, solar_eclipse_type_list = list(zip(*self.solar_eclipses))
        try:
            # find the index of the next solar eclipse
            next_solar_eclipse_idx = bisect.bisect_left(solar_eclipse_ts_list,
                                                        search_ts)
            # get ts of next solar eclipse
            next_solar_eclipse_ts = (solar_eclipse_ts_list[next_solar_eclipse_idx] -
                                     self.delta_t(solar_eclipse_ts_list[next_solar_eclipse_idx]))
            # get the type code of next solar eclipse
            next_solar_eclipse_type = solar_eclipse_type_list[next_solar_eclipse_idx]
        except ValueError:
            # if an error then set them to None
            next_solar_eclipse_ts = None
            next_solar_eclipse_type = None

        # make our ts into a ValueHelper
        next_solar_eclipse_ts_vh = ValueHelper((next_solar_eclipse_ts, 'unix_epoch', 'group_time'),
                                               'current',
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
        # look up the eclipse type
        next_solar_eclipse_type = self.solar_eclipse_type_lookup[next_solar_eclipse_type]

        # split our eclipse list tuples into individual lists
        lunar_eclipse_ts_list, lunar_eclipse_data_list = list(zip(*self.lunar_eclipses))
        try:
            # find the index of the next lunar eclipse
            next_lunar_eclipse_idx = bisect.bisect_left(lunar_eclipse_ts_list,
                                                        search_ts)
            # get ts of next lunar eclipse
            next_lunar_eclipse_ts = (lunar_eclipse_ts_list[next_lunar_eclipse_idx] -
                                     self.delta_t(lunar_eclipse_ts_list[next_lunar_eclipse_idx]))
            # get the type code of next lunar eclipse
            next_lunar_eclipse_type = lunar_eclipse_data_list[next_lunar_eclipse_idx]
        except ValueError:
            # if an error then set them to None
            next_lunar_eclipse_ts = None
            next_lunar_eclipse_type = None

        # make our ts into a ValueHelper
        next_lunar_eclipse_ts_vh = ValueHelper((next_lunar_eclipse_ts, 'unix_epoch', 'group_time'),
                                               'current',
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
        # look up the eclipse type
        next_lunar_eclipse_type = self.lunar_eclipse_type_lookup[next_lunar_eclipse_type]

        # Now create a small dictionary with suitable keys:
        search_list_extension = {'next_solar_eclipse': next_solar_eclipse_ts_vh,
                                 'next_solar_eclipse_type': next_solar_eclipse_type,
                                 'next_lunar_eclipse': next_lunar_eclipse_ts_vh,
                                 'next_lunar_eclipse_type': next_lunar_eclipse_type}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("Eclipse SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]


class EarthApsis(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)
        self.perihelion = (1388815380, 1420363620, 1451783460, 1483527360,
                           1514949360, 1546507980, 1578217260, 1609577220,
                           1641258900, 1672862700, 1704240300, 1735977420,
                           1767458340, 1798957320, 1830688560, 1862057280,
                           1893677520, 1925343780, 1956710760, 1988427180,
                           2019967080, 2051406300, 2083146360, 2114556240,
                           2146121040, 2177834400, 2209189740
                           )
        self.aphelion = (1404429000, 1436187180, 1467647760, 1499129700,
                         1530893640, 1562265180, 1593874200, 1625538660,
                         1656902640, 1688634060, 1720158900, 1751581080,
                         1783350180, 1814758980, 1846304100, 1878020700,
                         1909383600, 1941064140, 1972653000, 2004036600,
                         2035802580, 2067270060, 2098750260, 2130495180,
                         2161871520, 2193490500, 2225143020
                         )

    def get_extension_list(self, timespan, db_lookup):
        """Create a search list with date-time of next perihelion and aphelion.

           Source: Earth perihelion and aphelion Table Courtesy of
                   Fred Espenak, www.Astropixels.com

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

          db_lookup: This is a function that, given a data binding as its only
                     parameter, will return a database manager object.

        Returns:
            next_perihelion: ValueHelper containing date-time of next perihelion
            next_aphelion: ValueHelper containing date-time of next aphelion
        """

        t1 = time.time()

        # get a timestamp for now
        search_ts = timespan.stop
        # wrap in a try..except just in case
        try:
            # find the index of the next perihelion
            next_perihelion_idx = bisect.bisect_left(self.perihelion, search_ts)
            # find the index of the next aphelion
            next_aphelion_idx = bisect.bisect_left(self.aphelion, search_ts)
            # get ts of next perihelion
            next_perihelion_ts = self.perihelion[next_perihelion_idx]
            # get ts of next aphelion
            next_aphelion_ts = self.aphelion[next_aphelion_idx]
        except IndexError:
            # if an error then set them to None
            next_perihelion_ts = None
            next_aphelion_ts = None

        # make our ts into ValueHelpers
        next_perihelion_ts_vh = ValueHelper((next_perihelion_ts, 'unix_epoch', 'group_time'),
                                            'current',
                                            formatter=self.generator.formatter,
                                            converter=self.generator.converter)
        next_aphelion_ts_vh = ValueHelper((next_aphelion_ts, 'unix_epoch', 'group_time'),
                                          'current',
                                          formatter=self.generator.formatter,
                                          converter=self.generator.converter)

        # now create a small dictionary with suitable keys
        search_list_extension = {'next_perihelion': next_perihelion_ts_vh,
                                 'next_aphelion': next_aphelion_ts_vh}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("EarthApsis SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]


class ChineseNewYear(SearchList):

    def __init__(self, generator):
        SearchList.__init__(self, generator)
        self.cny_dict = {2014: (1, 31), 2015: (2, 19), 2016: (2, 8),
                         2017: (1, 28), 2018: (2, 16), 2019: (2, 5),
                         2020: (1, 25), 2021: (2, 12), 2022: (2, 1),
                         2023: (1, 22), 2024: (2, 10), 2025: (1, 29),
                         2026: (2, 17), 2027: (2, 6), 2028: (1, 26),
                         2029: (2, 13), 2030: (2, 3), 2031: (1, 23),
                         2032: (2, 11), 2033: (1, 31), 2034: (2, 19),
                         2035: (2, 8), 2036: (1, 28), 2037: (2, 15),
                         2038: (2, 4), 2039: (1, 24), 2040: (2, 12)
                         }

    def get_extension_list(self, timespan, db_lookup):
        """Create a search list with the date of the next Chinese New Year.

           Source: http://en.wikipedia.org/wiki/Chinese_New_Year

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            next_cny: Tuple consisting of numeric values (day, month, year) for
                      next Chinese New Year
        """

        t1 = time.time()

        # get a date object for now so we can get the year
        _date = datetime.date.fromtimestamp(timespan.stop)
        _year = _date.year
        # wrap in a try..except just in case
        try:
            # construct our tuple using current year and a lookup
            cny_d = datetime.date(*((_year, ) + self.cny_dict.get(_year, ())))
        except (TypeError, ValueError):
            # if we strike an error then return None
            cny_vt = ValueTuple(None, 'unix_epoch', 'group_time')
        else:
            # we have a valid date object so obtain a timestamp and convert to
            # a ValueTuple
            cny_ts = time.mktime(cny_d.timetuple())
            cny_vt = ValueTuple(cny_ts, 'unix_epoch', 'group_time')
        # get our result as a ValueHelper, so we can easily format our tag in
        # reports
        cny_vh = ValueHelper(cny_vt,
                             'current',
                             formatter=self.generator.formatter,
                             converter=self.generator.converter)
        # now create a small dictionary with our result
        search_list_extension = {'cny': cny_vh}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("ChineseNewYear SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list_extension]