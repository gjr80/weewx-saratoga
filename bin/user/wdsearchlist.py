"""
wdsearchlist.py

Search List Extensions support for WeeWX-WD.

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
        - logging is now WeeWX 3 and 4 compatible
    30 August 2020      v2.0.1
        - no change, version number change only
    20 August 2020      v2.0.0
        - WeeWX 3.2+/4.x python2/3 compatible
        - simplified logic used in WdHourRainTags calculation
        - simplified logic used in WdGdDays calculations
        - fixed typo where wet bulb was returned as feels_like temperature
        - Easter is now calculated on report time not system time

Previous Bitbucket revision history
    31 March 2017       v1.0.3
        - fix bug in WdMonthStats SLE that caused problems with monthRainMax_vh
          for archives with small amounts (partial months) of data
        - removed two lines of old commented out code from WdMonthStats SLE
    14 December 2016    v1.0.2
        - no change, version number change only
    30 November 2016    v1.0.1
        - revised for WeeWX v3.4.0
        - implemented a second debug level (ie debug = 2)
        - minor reformatting
        - added heatColorWord, feelsLike and density tags to WdSundryTags SLE
        - added day_windrun, yest_windrun, week_windrun, seven_day_windrun,
          month_windrun, year_windrun tags and alltime_windrun tags to
          WdWindRunTags SLE
    10 January 2015     v1.0.0
        - rewritten for WeeWX v3.0.0
        - added WdManualAverages SLE
        - fixed issues with WdRainThisDay SLE affecting databases with limited
          historical data
        - fixed bug in WdTimeSpanTags that was causing unit issues with
          $alltime tags
        - removed use of total_seconds() attribute in WdRainThisDay
        - fixed error in WdHourRainTags
        - removed redundant code in WdHourRainTags
        - fixed errors in wdTesttagsRainAgo
        - removed redundant wdClientrawRainAgo SLE
    dd September 2014   v0.9.4 (never released)
        - added execution time debug messages for all SLEs
        - added additional tags to WdMonthStats SLE
        - wdClientrawAgotags and wdTesttagsAgotags SLEs now use max_delta on
          archive queries
        - added additional tags to WdAvgWindTags SLE
        - WdSundryTags SLE now provides current_text and current_icon from
          current conditions text file if it exists
        - added additional tags to WdWindRunTags SLE
        - new SLEs WdGdDays, WdForToday, WdRainThisDay and WdRainDays
        - added helper functions get_first_day and doygen
        - added GNU license text
    August 2013         v0.1
        - initial implementation

# TODO. Growing degree days, use .convert to do conversions
# TODO. Growing degree days, can you have negative results
# TODO. Yesterday almanac needs to handle case where there is no data for yesterday
# TODO. Can avwind120 and fiends (in fact all in this SLE) be provided by standard WeeWX tags?
# TODO. Line 1319 is 600 really needed for max
"""

# python imports
import calendar
import datetime
import itertools
import math
import time

from datetime import date

# WeeWX imports
import user.wdtaggedstats
import weewx
import weewx.almanac
import weewx.cheetahgenerator
import weewx.tags
import weewx.units
import weewx.wxformulas
import weeutil.weeutil

from weewx.tags import TimespanBinder
from weeutil.weeutil import TimeSpan, genMonthSpans
from weewx.units import ValueHelper, getStandardUnitType, ValueTuple

# import/setup logging, WeeWX v3 is syslog based but WeeWX v4 is logging based,
# try v4 logging and if it fails use v3 logging
try:
    # WeeWX4 logging
    import logging

    log = logging.getLogger(__name__)

    def loginf(msg):
        log.info(msg)


    def logdbg(msg):
        log.debug(msg)

except ImportError:
    # WeeWX legacy (v3) logging via syslog
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'wdsearchlist: %s' % msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

WEEWXWD_SLE_VERSION = '2.1.3'


def get_first_day(dt, d_years=0, d_months=0):
    """Function to return date object holding 1st of month containing dt
       d_years, d_months are offsets that may be applied to dt
    """

    # get year number and month number applying offset as required
    _y, _m = dt.year + d_years, dt.month + d_months
    # calculate actual month number taking into account EOY rollover
    _a, _m = divmod(_m-1, 12)
    # calculate and return date object
    return date(_y+_a, _m+1, 1)


def doygen(start_ts, stop_ts):
    """Generator function yielding a timestamp of midnight for a given date
       each year.

       Yields a sequence of timestamps for midnight on the day of the year
       containing start_ts. Generator continues until stop_ts is reached unless
       stop_ts is midnight in current year in which case this years timestamp
       is not returned. See the example below.

       Example:

       >>> startstamp = 1143550356
       >>> print datetime.datetime.fromtimestamp(startstamp)
       2006-03-28 22:52:36
       >>> stopstamp = 1409230470
       >>> print datetime.datetime.fromtimestamp(stopstamp)
       2014-08-28 22:54:30

       >>> for span in doygen(startstamp, stopstamp):
       ...     print span
       2006-03-28 00:00:00
       2007-03-28 00:00:00
       2008-03-28 00:00:00
       2009-03-28 00:00:00
       2010-03-28 00:00:00
       2011-03-28 00:00:00
       2012-03-28 00:00:00
       2013-03-28 00:00:00
       2014-03-28 00:00:00

       start_ts: The start of the first interval in unix epoch time.

       stop_ts: The end of the last interval will be equal to or less than this.

       yields: A sequence of unix epoch timestamps. Each timestamp will be have time set to midnight
    """

    d1 = datetime.date.fromtimestamp(start_ts)
    stop_d = datetime.date.fromtimestamp(stop_ts)
    stop_dt = datetime.datetime.fromtimestamp(stop_ts)

    if stop_d >= d1:
        while d1 <= stop_d:
            t_tuple = d1.timetuple()
            year = t_tuple[0]
            month = t_tuple[1]
            day = t_tuple[2]
            if year != stop_dt.year or (stop_dt.hour != 0 and stop_dt.minute != 0):
                ts = time.mktime(t_tuple)
                yield ts
            if not calendar.isleap(year) or month != 2 or day != 29:
                year += 1
            else:
                year += 4
                if not calendar.isleap(year):
                    year += 4
            d1 = d1.replace(year=year)


def get_date_ago(dt, d_months=1):
    """Function to return date object d_months before dt.
       If d_months ago is an invalid date (eg 30 February) then the end of the
       month is returned. If dt is the end of the month then the end of the
       month concerned is returned.
    """

    _one_day = datetime.timedelta(days=1)
    # Get year number and month number applying offset as required
    _y, _m, _d = dt.year, dt.month - d_months, dt.day
    # Calculate actual month number taking into account EOY rollover
    _a, _m = divmod(_m, 12)
    # Calculate eom of date to be returned
    _eom = datetime.date(_y + _a, _m + 1, 1) - _one_day
    # Calculate and return date object
    # If we are not on the last of the month or our day is invalid return
    # the end of the month
    if dt.month != (dt + _one_day).month or dt.day >= _eom.day:
        return _eom
    # Otherwise return the eom using our day
    return _eom.replace(day=dt.day)


# ==============================================================================
#                              Class WdMonthStats
# ==============================================================================


class WdMonthStats(weewx.cheetahgenerator.SearchList):

    def __init__(self, generator):
        # initialise my superclass
        super(WdMonthStats, self).__init__(generator)

    def get_month_avg_highs(self, timespan, db_lookup):
        """Function to calculate alltime monthly:
           - average rainfall
           - record high temp
           - record low temp
           - average temp

           Results are calculated using daily data from stats database. Average
           rainfall is calculated by summing rainfall over each Jan, Feb...Dec
           then averaging these totals over the number of Jans, Febs... Decs
           in our data. Average temp
           Record high and low temps are max and min over all of each month.
           Partial months at start and end of our data are ignored. Assumes
           rest of our data is contiguous.

           Returned values are lists of ValueHelpers representing results for
           Jan, Feb thru Dec. Months that have no data are returned as None.
        """

        #
        # set up those things we need to get going
        #

        # get archive interval
        curr_rec = db_lookup().getRecord(timespan.stop)
        _interval = curr_rec['interval']
        # get our UoMs and Groups
        (rain_type, rain_group) = getStandardUnitType(curr_rec['usUnits'],
                                                      'rain')
        (temp_type, temp_group) = getStandardUnitType(curr_rec['usUnits'],
                                                      'outTemp')
        # set up a list to hold our average values
        # month rain average
        m_rain_av = [0 for x in range(12)]
        # month rain average now
        m_rain_av_n = [None for x in range(12)]
        # month temperature average
        m_temp_av = [0 for x in range(12)]
        # month temperature average now
        m_temp_av_n = [None for x in range(12)]
        # set up lists to hold our results in ValueHelpers
        m_rain_av_vh = [0 for x in range(12)]
        m_rain_av_n_vh = [0 for x in range(12)]
        m_rain_max_vh = [0 for x in range(12)]
        m_temp_av_vh = [0 for x in range(12)]
        m_temp_av_n_vh = [0 for x in range(12)]
        m_temp_max_vh = [0 for x in range(12)]
        m_temp_min_vh = [0 for x in range(12)]

        # set up a 2D list to hold our month running total and number of months
        # so we can calculate an average
        m_rain_bin = [[0 for x in range(2)] for x in range(12)]
        m_temp_bin = [[0 for x in range(2)] for x in range(12)]
        # set up lists to hold our max and min records
        m_rain_max = [None for x in range(12)]
        m_rain_max_ts = None
        # max month rain this year
        m_rain_max_n = [None for x in range(12)]
        m_temp_max = [None for x in range(12)]
        m_temp_min = [None for x in range(12)]
        # get time object for midnight
        _mn_time = datetime.time()
        # get timestamp for our first (earliest) and last (most recent) records
        _start_ts = db_lookup().firstGoodStamp()
        _end_ts = timespan.stop
        # get these as datetime objects
        _start_dt = datetime.datetime.fromtimestamp(_start_ts)
        _end_dt = datetime.datetime.fromtimestamp(_end_ts)
        # if we do not have a complete month of data then we really have not
        # much to do
        if ((_start_dt.hour != 0 or _start_dt.minute != 0 or _start_dt.day != 1) and
                ((_start_dt.month == _end_dt.month and _start_dt.year == _end_dt.year) or
                 (_end_dt < datetime.datetime.combine(get_first_day(_start_dt, 0, 2), _mn_time)))):
            # we do not have a complete month of data so get record highs/lows,
            # set everything else to None and return
            # first, set our results to None
            for m in range(12):
                # set our month averages/max/min to None
                m_rain_av[m] = ValueTuple(None, rain_type, rain_group)
                m_rain_av_n[m] = ValueTuple(None, rain_type, rain_group)
                m_temp_av[m] = ValueTuple(None, temp_type, temp_group)
                m_temp_av_n[m] = ValueTuple(None, temp_type, temp_group)
                m_temp_max[m] = ValueTuple(None, temp_type, temp_group)
                m_temp_min[m] = ValueTuple(None, temp_type, temp_group)
                # save our ValueTuples as ValueHelpers
                m_rain_av_vh[m] = ValueHelper(m_rain_av[m],
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)
                m_rain_av_n_vh[m] = ValueHelper(m_rain_av_n[m],
                                                formatter=self.generator.formatter,
                                                converter=self.generator.converter)
                m_rain_max_vh[m] = ValueHelper((m_rain_max[m], rain_type, rain_group),
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
                m_temp_av_vh[m] = ValueHelper(m_temp_av[m],
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)
                m_temp_av_n_vh[m] = ValueHelper(m_temp_av_n[m],
                                                formatter=self.generator.formatter,
                                                converter=self.generator.converter)

                m_temp_max_vh[m] = ValueHelper(m_temp_max[m],
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
                m_temp_min_vh[m] = ValueHelper(m_temp_min[m],
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
            # process max/min for month containing _start_ts
            m_tspan = weeutil.weeutil.archiveMonthSpan(_start_ts)
            # get our max and min
            m_temp_max_tuple = db_lookup().getAggregate(m_tspan,
                                                        'outTemp',
                                                        'max')
            # get the min temp for the month concerned
            m_temp_min_tuple = db_lookup().getAggregate(m_tspan,
                                                        'outTemp',
                                                        'min')
            # save our max/min to the correct month bin
            m_temp_max_vh[_start_dt.month-1] = ValueHelper(m_temp_max_tuple,
                                                           formatter=self.generator.formatter,
                                                           converter=self.generator.converter)
            m_temp_min_vh[_start_dt.month-1] = ValueHelper(m_temp_min_tuple,
                                                           formatter=self.generator.formatter,
                                                           converter=self.generator.converter)
            # do we have a 2nd month to process
            if _end_dt < datetime.datetime.combine(get_first_day(_start_dt, 0, 2), _mn_time):
                # We do cross a month boundary. Process max/min for month
                # containing _end_ts
                m_tspan = weeutil.weeutil.archiveMonthSpan(_end_ts)
                # get our max and min
                m_temp_max_tuple = db_lookup().getAggregate(m_tspan,
                                                            'outTemp',
                                                            'max')
                # get the min temp for the month concerned
                m_temp_min_tuple = db_lookup().getAggregate(m_tspan,
                                                            'outTemp',
                                                            'min')
                # save our max/min to the correct month bin
                m_temp_max_vh[_end_dt.month-1] = ValueHelper(m_temp_max_tuple,
                                                             formatter=self.generator.formatter,
                                                             converter=self.generator.converter)
                m_temp_min_vh[_end_dt.month-1] = ValueHelper(m_temp_min_tuple,
                                                             formatter=self.generator.formatter,
                                                             converter=self.generator.converter)
            y_max_rain_m = None
            y_max_rain_y = None
            y_max_m_rain_vh = ValueHelper((None, rain_type, rain_group),
                                          formatter=self.generator.formatter,
                                          converter=self.generator.converter)
        else:
            # we have more than a complete month of data so things are a bit
            # more complex
            #
            # work out our start times for looping through the months
            #

            # Determine timestamp of first record we will use. Will be midnight
            # on first of a month. We are using stats data to calculate our
            # results and the stats datetime for each day is midnight. We have
            # obtained our starting time from archive data where the first obs
            # of the day has a datetime of (archive interval) minutes after
            # midnight. Need to take this into account when choosing our start
            # time. Need to skip any partial months data at the start of data.

            # get the datetime from ts of our first data record
            _date = datetime.datetime.fromtimestamp(_start_ts)
            # if this is not the 1st of the month or if its after
            # (archive interval) after midnight on 1st then we have a partial
            # month and we need to skip to next month.
            if _date.day > 1 or _date.hour > 0 or _date.minute > _interval:
                _combined = datetime.datetime.combine(get_first_day(_date, 0, 1),
                                                      _mn_time)
                _start_ts = int(time.mktime(_combined.timetuple()))
            # if its midnight on the 1st of the month then leave it as is
            elif _date.day == 1 and _date.hour == 0 and _date.minute == 0:
                pass
            # otherwise its (archive interval) past midnight on 1st so we have
            # the right day just need to set our timestamp to midnight.
            else:
                _start_ts = int(time.mktime((_date.year, _date.month, _date.day,
                                             0, 0, 0, 0, 0, 0)))
            # Determine timestamp of last record we will use. Will be midnight
            # on last of a month. We are using stats data to calculate our
            # average and the stats datetime for each day is midnight. We have
            # obtained our starting time from archive data where the first obs
            # of the day has a datetime of (archive interval) minutes after
            # midnight. Need to take this into account when choosing our start
            # time. Need to skip any partial months data at the start of data.
            #
            # get the datetime from our ending point timestamp
            _date = datetime.datetime.fromtimestamp(_end_ts)
            if _date.day == 1 and _date.hour == 0 and _date.minute == 0:
                pass
            else:
                _end_ts = int(time.mktime((_date.year, _date.month, 1,
                                           0, 0, 0, 0, 0, 0)))

            # Determine timestamp to start our 'now' month stats ie stats for
            # the last 12 months. If we are part way though a month then want
            # midnight on 1st of month 11.something months ago eg if its
            # 5 November 2014 we want midnight 1 December 2013. If we are
            # (archive_interval) minutes after midnight on 1st of month we want
            # midnight 12 months and (archive_interval) minutes ago. If we are
            # at midnight on 1st of month we want midnight 12 months ago

            # we have a partial month so go back 11.something months
            if _date.day > 1 or _date.hour > 0 or _date.minute >= _interval:
                _combined = datetime.datetime.combine(get_first_day(_date, 0, -11),
                                                      _mn_time)
                _start_now_ts = int(time.mktime(_combined.timetuple()))
            # otherwise its midnight on the 1st of the month and we just need
            # to go back 12 months
            else:
                _combined = datetime.datetime.combine(get_first_day(_date, 1, 0),
                                                      _mn_time)
                _start_now_ts = int(time.mktime(_combined.timetuple()))
            # iterate over each month timespan between our start and end
            # timestamps
            for m_tspan in genMonthSpans(_start_ts, timespan.stop):
                # work out or month bin number
                _m_bin = datetime.datetime.fromtimestamp(m_tspan.start).month - 1
                # get our data
                # get the total rain for the month concerned
                m_rain_tuple = db_lookup().getAggregate(m_tspan, 'rain', 'sum')
                # get the 'avg' temp for the month concerned
                m_temp_tuple = db_lookup().getAggregate(m_tspan,
                                                        'outTemp',
                                                        'avg')
                # get the max temp for the month concerned
                m_temp_max_tuple = db_lookup().getAggregate(m_tspan,
                                                            'outTemp',
                                                            'max')
                # get the min temp for the month concerned
                m_temp_min_tuple = db_lookup().getAggregate(m_tspan,
                                                            'outTemp',
                                                            'min')
                # recordhigh/low, monthrainavg and monthtempavg all omit the
                # current (partial) month so check that we are not in that
                # partial month
                if m_tspan.stop <= _end_ts:
                    # not in a partial month so update
                    if m_rain_tuple[0] is not None:
                        # update our total rain for that month
                        m_rain_bin[_m_bin][0] += m_rain_tuple[0]
                        # increment our count
                        m_rain_bin[_m_bin][1] += 1
                    if m_temp_tuple[0] is not None:
                        # update our 'total' temp for that month
                        _date1 = get_first_day(datetime.datetime.fromtimestamp(m_tspan.start).date(), 0, 1)
                        _date2 = get_first_day(datetime.datetime.fromtimestamp(m_tspan.start).date(), 0, 0)
                        _days = (_date1 - _date2).days
                        m_temp_bin[_m_bin][0] += m_temp_tuple[0] * _days
                        # increment our count, in this case by the number of
                        # days in the month
                        m_temp_bin[_m_bin][1] += _days
                    # Check if we are within the last 12 odd months for 'now'
                    # stats, if so start accumulating. Averages are simply:
                    # rain - the total (sum) for the month
                    # temp - the avg for the month
                    if m_tspan.start >= _start_now_ts:
                        m_rain_av_n[_m_bin] = m_rain_tuple[0]
                        m_rain_max_n[_m_bin] = m_rain_tuple[0]
                        m_temp_av_n[_m_bin] = m_temp_tuple[0]
                # update max rain for the month
                if m_rain_tuple[0] is not None:
                    if m_rain_max[_m_bin] is None or m_rain_tuple[0] > m_rain_max[_m_bin]:
                        m_rain_max[_m_bin] = m_rain_tuple[0]
                        m_rain_max_ts = m_tspan.start
                if m_temp_max_tuple[0] is not None:
                    # if our record list holds None or the current value is
                    # greater than our record list then the current value must
                    # be the new max
                    if m_temp_max[_m_bin] is None or m_temp_max_tuple[0] > m_temp_max[_m_bin]:
                        m_temp_max[_m_bin] = m_temp_max_tuple[0]
                if m_temp_min_tuple[0] is not None:
                    # if our record list holds None or the current value is
                    # less than our record list then the current value must be
                    # the new min
                    if m_temp_min[_m_bin] is None or m_temp_min_tuple[0] < m_temp_min[_m_bin]:
                        m_temp_min[_m_bin] = m_temp_min_tuple[0]

            # iterate over each month:
            #  - calculating averages and saving as a ValueTuple
            #  - converting monthly averages, max and min ValueHelpers
            for m in range(12):
                # if we have a total > 0 then calc a simple average
                if m_rain_bin[m][1] != 0:
                    m_rain_av[m] = ValueTuple(m_rain_bin[m][0]/m_rain_bin[m][1],
                                              rain_type,
                                              rain_group)
                # if our sum == 0 and our count > 0 then set our average to 0
                elif m_rain_bin[m][1] > 0:
                    m_rain_av[m] = ValueTuple(0, rain_type, rain_group)
                # otherwise we must have no data for that month so set our
                # average to None
                else:
                    m_rain_av[m] = ValueTuple(None, rain_type, rain_group)
                # if we have a total > 0 then calc a simple average
                if m_temp_bin[m][1] != 0:
                    m_temp_av[m] = ValueTuple(m_temp_bin[m][0]/m_temp_bin[m][1],
                                              temp_type,
                                              temp_group)
                # if our sum == 0 and our count > 0 then set our average to 0
                elif m_temp_bin[m][1] > 0:
                    m_temp_av[m] = ValueTuple(0, temp_type, temp_group)
                # otherwise we must have no data for that month so set our
                # average to None
                else:
                    m_temp_av[m] = ValueTuple(None, temp_type, temp_group)

                # save our ValueTuples as a ValueHelpers
                m_rain_av_vh[m] = ValueHelper(m_rain_av[m],
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)
                m_temp_av_vh[m] = ValueHelper(m_temp_av[m],
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)
                # Save our max/min results as ValueHelpers
                m_rain_max_vh[m] = ValueHelper((m_rain_max[m], rain_type, rain_group),
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
                m_temp_max_vh[m] = ValueHelper((m_temp_max[m], temp_type, temp_group),
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
                m_temp_min_vh[m] = ValueHelper((m_temp_min[m], temp_type, temp_group),
                                               formatter=self.generator.formatter,
                                               converter=self.generator.converter)
                # Save our 'now' results as ValueHelpers
                m_rain_av_n_vh[m] = ValueHelper((m_rain_av_n[m], rain_type, rain_group),
                                                formatter=self.generator.formatter,
                                                converter=self.generator.converter)
                m_temp_av_n_vh[m] = ValueHelper((m_temp_av_n[m], temp_type, temp_group),
                                                formatter=self.generator.formatter,
                                                converter=self.generator.converter)
            c_month = datetime.date.fromtimestamp(timespan.stop).month
            y_max_rain = None
            y_max_rain_m = None
            y_max_rain_y = datetime.date.fromtimestamp(timespan.stop).year
            for _month in range(c_month):
                if m_rain_max_n[_month] is not None and (y_max_rain is None or m_rain_max_n[_month] > y_max_rain):
                    y_max_rain = m_rain_max_n[_month]
                    y_max_rain_m = _month + 1

            # save our year max month rain as ValueHelper
            y_max_m_rain_vh = ValueHelper((y_max_rain, rain_type, rain_group),
                                          formatter=self.generator.formatter,
                                          converter=self.generator.converter)

        # return our lists of ValueHelpers
        return (m_rain_av_vh, m_rain_av_n_vh, m_temp_av_vh, m_temp_av_n_vh,
                m_rain_max_vh, m_temp_max_vh, m_temp_min_vh, y_max_m_rain_vh,
                y_max_rain_m, y_max_rain_y, m_rain_max_ts)

    def get_extension_list(self, timespan, db_lookup):
        """Returns month avg/max/min stats based upon archive data.

        Provides:
        - avg rain
        - avg rain now (monthly rain for last 12 months incl current month)
        - avg temp
        - avg temp now (month avg temp for last 12 months incl current month)
        - record high temp
        - record low temp

        for January, February,..., December

        based upon all archive data with the exception of any partial months
        data at the start and end of the database (except for avgrainxxnow and
        avgtempxxnow which include current month.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.
        """

        t1 = time.time()

        # Get current month number
        curr_month = datetime.date.fromtimestamp(timespan.stop).month

        # Call get_month_avg_highs method to calculate average rain, temp
        # and max/min temps for each month
        (m_r_a, m_r_a_n, m_t_a, m_t_a_n, m_r_ma, m_t_ma,
         m_t_mi, y_m_m_r, y_ma_r_m, y_ma_r_y, m_r_ma_ts) = self.get_month_avg_highs(timespan,
                                                                                    db_lookup)
        ma_m_r_m = datetime.datetime.fromtimestamp(m_r_ma_ts).month if m_r_ma_ts is not None else None
        ma_m_r_y = datetime.datetime.fromtimestamp(m_r_ma_ts).year if m_r_ma_ts is not None else None
        # returned values are already ValueHelpers so can add each entry
        # straight to the search list
        # create a dictionary with the tag names (keys) we want to use
        search_list = {'avrainjan': m_r_a[0],
                       'avrainfeb': m_r_a[1],
                       'avrainmar': m_r_a[2],
                       'avrainapr': m_r_a[3],
                       'avrainmay': m_r_a[4],
                       'avrainjun': m_r_a[5],
                       'avrainjul': m_r_a[6],
                       'avrainaug': m_r_a[7],
                       'avrainsep': m_r_a[8],
                       'avrainoct': m_r_a[9],
                       'avrainnov': m_r_a[10],
                       'avraindec': m_r_a[11],
                       'avrainjannow': m_r_a_n[0],
                       'avrainfebnow': m_r_a_n[1],
                       'avrainmarnow': m_r_a_n[2],
                       'avrainaprnow': m_r_a_n[3],
                       'avrainmaynow': m_r_a_n[4],
                       'avrainjunnow': m_r_a_n[5],
                       'avrainjulnow': m_r_a_n[6],
                       'avrainaugnow': m_r_a_n[7],
                       'avrainsepnow': m_r_a_n[8],
                       'avrainoctnow': m_r_a_n[9],
                       'avrainnovnow': m_r_a_n[10],
                       'avraindecnow': m_r_a_n[11],
                       'avtempjan': m_t_a[0],
                       'avtempfeb': m_t_a[1],
                       'avtempmar': m_t_a[2],
                       'avtempapr': m_t_a[3],
                       'avtempmay': m_t_a[4],
                       'avtempjun': m_t_a[5],
                       'avtempjul': m_t_a[6],
                       'avtempaug': m_t_a[7],
                       'avtempsep': m_t_a[8],
                       'avtempoct': m_t_a[9],
                       'avtempnov': m_t_a[10],
                       'avtempdec': m_t_a[11],
                       'avtempjannow': m_t_a_n[0],
                       'avtempfebnow': m_t_a_n[1],
                       'avtempmarnow': m_t_a_n[2],
                       'avtempaprnow': m_t_a_n[3],
                       'avtempmaynow': m_t_a_n[4],
                       'avtempjunnow': m_t_a_n[5],
                       'avtempjulnow': m_t_a_n[6],
                       'avtempaugnow': m_t_a_n[7],
                       'avtempsepnow': m_t_a_n[8],
                       'avtempoctnow': m_t_a_n[9],
                       'avtempnovnow': m_t_a_n[10],
                       'avtempdecnow': m_t_a_n[11],
                       'recordhighrainjan': m_r_ma[0],
                       'recordhighrainfeb': m_r_ma[1],
                       'recordhighrainmar': m_r_ma[2],
                       'recordhighrainapr': m_r_ma[3],
                       'recordhighrainmay': m_r_ma[4],
                       'recordhighrainjun': m_r_ma[5],
                       'recordhighrainjul': m_r_ma[6],
                       'recordhighrainaug': m_r_ma[7],
                       'recordhighrainsep': m_r_ma[8],
                       'recordhighrainoct': m_r_ma[9],
                       'recordhighrainnov': m_r_ma[10],
                       'recordhighraindec': m_r_ma[11],
                       'recordhightempjan': m_t_ma[0],
                       'recordhightempfeb': m_t_ma[1],
                       'recordhightempmar': m_t_ma[2],
                       'recordhightempapr': m_t_ma[3],
                       'recordhightempmay': m_t_ma[4],
                       'recordhightempjun': m_t_ma[5],
                       'recordhightempjul': m_t_ma[6],
                       'recordhightempaug': m_t_ma[7],
                       'recordhightempsep': m_t_ma[8],
                       'recordhightempoct': m_t_ma[9],
                       'recordhightempnov': m_t_ma[10],
                       'recordhightempdec': m_t_ma[11],
                       'recordlowtempjan': m_t_mi[0],
                       'recordlowtempfeb': m_t_mi[1],
                       'recordlowtempmar': m_t_mi[2],
                       'recordlowtempapr': m_t_mi[3],
                       'recordlowtempmay': m_t_mi[4],
                       'recordlowtempjun': m_t_mi[5],
                       'recordlowtempjul': m_t_mi[6],
                       'recordlowtempaug': m_t_mi[7],
                       'recordlowtempsep': m_t_mi[8],
                       'recordlowtempoct': m_t_mi[9],
                       'recordlowtempnov': m_t_mi[10],
                       'recordlowtempdec': m_t_mi[11],
                       'currentmonthavrain': m_r_a[curr_month - 1],
                       'currentmonthrecordrain': m_r_a[curr_month - 1],
                       'yearmaxmonthrain': y_m_m_r,
                       'yearmaxmonthrainmonth': y_ma_r_m,
                       'yearmaxmonthrainyear': y_ma_r_y,
                       'maxmonthrainmonth': ma_m_r_m,
                       'maxmonthrainyear': ma_m_r_y
                       }

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdMonthStats SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                             class WdLastRainTags
# ==============================================================================


class WdLastRainTags(weewx.cheetahgenerator.SearchList):
    """SLE that returns the date and time of last rain."""

    def __init__(self, generator):
        # initialise our superclass
        super(WdLastRainTags, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with the date and time of last rain.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            last_rain: A ValueHelper containing the date and time of the last
                       rain.
        """

        t1 = time.time()

        # Use rain daily summary to find day of last rain. Result is timestamp
        # for midnight on the day the rain occurred.
        _sql = "SELECT MAX(dateTime) FROM archive_day_rain WHERE sum > 0"
        _row = db_lookup().getSql(_sql)
        if _row:
            last_rain_ts = _row[0]
            # if we found a timestamp use it to limit our search on the archive
            # so we can find the last archive record during which it rained,
            # wrap in a try..except just in case
            if last_rain_ts is not None:
                _sql = "SELECT MAX(dateTime) FROM archive "\
                       "WHERE rain > 0 "\
                       "AND dateTime > %(start)s AND dateTime <= %(stop)s"
                interpolate = {'start': last_rain_ts,
                               'stop': last_rain_ts + 86400}
                try:
                    _row = db_lookup().getSql(_sql % interpolate)
                    if _row:
                        last_rain_ts = _row[0]
                except:
                    last_rain_ts = None
        else:
            last_rain_ts = None
        # wrap timestamp in a ValueHelper
        last_rain_vt = ValueTuple(last_rain_ts, 'unix_epoch', 'group_time')
        last_rain_vh = ValueHelper(last_rain_vt,
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)
        # create a dictionary with the tag names (keys) we want to use
        search_list = {'last_rain': last_rain_vh}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdLastRainTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                              class WdTimeSpanTags
# ==============================================================================


class WdTimeSpanTags(weewx.cheetahgenerator.SearchList):
    """SLE to return various custom TimeSpanBinder based tags."""

    def __init__(self, generator):
        # initialise my superclass
        super(WdTimeSpanTags, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with various custom TimespanBinder tags.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            tspan_binder: A TimespanBinder object that allows a data binding to
                          be specified (default to None) when calling $alltime
                          eg $alltime.outTemp.max for the all time high outside
                          temp.
                          $alltime($data_binding='wd_binding').humidex.max
                          for the all time high humidex where humidex
                          resides in the 'wd_binding' database.

                          Standard WeeWX unit conversion and formatting options
                          are available.
        """

        t1 = time.time()

        class WdBinder(weewx.tags.TimeBinder):
            """Class supporting additional TimeSpan based aggregate tags."""

            def __init__(self, db_lookup, report_time,
                         formatter=weewx.units.Formatter(),
                         converter=weewx.units.Converter(), **option_dict):
                # initialise my superclass
                super(WdBinder, self).__init__(db_lookup, report_time,
                                               formatter=formatter,
                                               converter=converter,
                                               **option_dict)

            def dayagg(self, data_binding=None, ago=0):
                """Return a TimespanBinder from midnight until ago seconds ago."""

                # Get a TimeSpan object representing the period from midnight
                # until 'ago' seconds ago. Midnight is midnight at the start of
                # the day containing the timespan 'ago' seconds ago.

                # first get the ts of the start of the day containing the
                # timestamp 'ago' seconds ago
                _ago_ts = self.report_time - ago
                _tspan = weeutil.weeutil.archiveDaySpan(_ago_ts)
                # now construct the TimeSpan object
                ago_tspan = TimeSpan(_tspan.start, _ago_ts)
                # return a TimespanBinder object, using the timespan we just
                # calculated
                return TimespanBinder(ago_tspan,
                                      self.db_lookup, context='current',
                                      data_binding=data_binding,
                                      formatter=self.formatter,
                                      converter=self.converter)

            def alltime(self, data_binding=None):
                """Return a TimeSpanBinder covering all archive records.

                To avoid problems where our data_binding might have a first
                good timestamp that is different to timespan.start (and thus
                change which manager is used) we need to reset our
                timespan.start to the first good timestamp of our data_binding.
                """

                # get a manager
                db_manager = db_lookup(data_binding)
                # get our first good timestamp
                start_ts = db_manager.firstGoodStamp()
                # obtain a TimeSpan object representing all times
                alltime_tspan = TimeSpan(start_ts, timespan.stop)
                # return a TimespanBinder object, using the timespan we just
                # calculated
                return TimespanBinder(alltime_tspan,
                                      self.db_lookup, context='alltime',
                                      data_binding=data_binding,
                                      formatter=self.formatter,
                                      converter=self.converter)

            def seven_day(self, data_binding=None):
                """Return a TimeSpanBinder for the the last 7 days."""

                # calculate the time at midnight, seven days ago.
                _stop_d = datetime.date.fromtimestamp(timespan.stop)
                seven_day_dt = _stop_d - datetime.timedelta(weeks=1)
                # now convert it to unix epoch time:
                seven_day_ts = time.mktime(seven_day_dt.timetuple())
                # get our 7 day timespan
                seven_day_tspan = TimeSpan(seven_day_ts, timespan.stop)
                # now return a TimespanBinder object, using the timespan we just
                # calculated
                return TimespanBinder(seven_day_tspan,
                                      self.db_lookup, context='seven_day',
                                      data_binding=data_binding,
                                      formatter=self.formatter,
                                      converter=self.converter)

            def since(self, data_binding=None, hour=0, minute=0, second=0):
                """Return a TimeSpanBinder since the a given time."""

                # obtain the report time as a datetime object
                stop_dt = datetime.datetime.fromtimestamp(timespan.stop)
                # assume the 'since' time is today so obtain it as a datetime
                # object
                since_dt = stop_dt.replace(hour=hour, minute=minute, second=second)
                # but 'since' must be before the report time so check if the
                # assumption is correct, if not then 'since' must be yesterday
                # so subtract 1 day
                if since_dt > stop_dt:
                    since_dt -= datetime.timedelta(days=1)
                # now convert it to unix epoch time:
                since_ts = time.mktime(since_dt.timetuple())
                # get our timespan
                since_tspan = TimeSpan(since_ts, timespan.stop)
                # now return a TimespanBinder object, using the timespan we just
                # calculated
                return TimespanBinder(since_tspan,
                                      self.db_lookup, context='current',
                                      data_binding=data_binding,
                                      formatter=self.formatter,
                                      converter=self.converter)

        time_binder = WdBinder(db_lookup,
                               timespan.stop,
                               self.generator.formatter,
                               self.generator.converter)

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdTimeSpanTags SLE executed in %0.3f seconds" % (t2-t1))

        return [time_binder]


# ==============================================================================
#                              class WdAvgWindTags
# ==============================================================================


class WdAvgWindTags(weewx.cheetahgenerator.SearchList):
    """SLE to return various average wind speed stats."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdAvgWindTags, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with various average wind speed stats.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            avdir10: Average wind direction over the last 10 minutes.
        """

        t1 = time.time()

        # get units for use later with ValueHelpers
        # first, get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # get the unit in use for each group
        (d_unit, d_group) = getStandardUnitType(current_rec['usUnits'],
                                                'windDir')

        # get a TimeSpan object for the last 10 minutes
        tspan = TimeSpan(timespan.stop-600, timespan.stop)
        # obtain 10 minute average wind direction data
        (_vt1, _vt2, _dir10_vt) = db_lookup().getSqlVectors(tspan,
                                                            'windvec',
                                                            'avg',
                                                            600)
        # Our _vt holds x and an y component of wind direction, need to use
        # some trigonometry to get the angle. Wrap in try..except in case we
        # get a None in there somewhere
        try:
            avdir10 = 90.0 - math.degrees(math.atan2(_dir10_vt.value[0].imag,
                                                     _dir10_vt.value[0].real))
            avdir10 = round(avdir10 % 360, 0)
        except (AttributeError, TypeError):
            avdir10 = None
        # put our results into ValueHelpers
        avdir10_vt = ValueTuple(avdir10, d_unit, d_group)
        avdir10_vh = ValueHelper(avdir10_vt,
                                 formatter=self.generator.formatter,
                                 converter=self.generator.converter)

        # create a dictionary with the tag names (keys) we want to use
        search_list = {'avdir10': avdir10_vh}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdAvgWindTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                              class WdSundryTags
# ==============================================================================


class WdSundryTags(weewx.cheetahgenerator.SearchList):
    """SLE to return various sundry tags."""

    def __init__(self, generator):
        # initialise our superclass
        super(WdSundryTags, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns various tags.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            launchtime: A ValueHelper containing the epoch time that weewx was
                        started.
            heatColorWord: A string describing the current temperature
                           conditions. Based on outTemp, outHumidity and
                           humidex.
            feelsLike: A ValueHelper representing the perceived temperature.
                       Based on outTemp, windchill and humidex.
            density: A number representing the current air density in kg/m3.
            beaufort: The windSpeed as an integer on the Beaufort scale.
            beaufortDesc: The textual description/name of the current beaufort
                          wind speed.
            wetBulb: A ValueHelper containing the current wetbulb temperature.
            cbi: A ValueHelper containing the current Chandler Burning Index.
            cbitext: A string containing the current Chandler Burning Index
                     descriptive text.
            cloudbase: A ValueHelper containing the current cloudbase.
            Easter: A ValueHelper containing the date of the next Easter
                    Sunday. The time represented is midnight at the start of
                    Easter Sunday.
            trend_60_baro: A string representing the 1 hour barometer trend.
            trend_180_baro: A string representing the 3 hour barometer trend.
        """

        t1 = time.time()

        # get units for possible use later with ValueHelpers

        # first, get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        self.generator.gen_wd_ts = db_lookup('wd_binding').lastGoodStamp()
        curr_rec = db_lookup().getRecord(self.generator.gen_ts)
        curr_wd_rec = db_lookup().getRecord(self.generator.gen_wd_ts)
        # get the unit in use for each group
        (t_type, t_group) = getStandardUnitType(curr_rec['usUnits'],
                                                'dateTime')

        # get ts WeeWX was launched
        try:
            launchtime = weewx.launchtime_ts
        except ValueError:
            launchtime = time.time()
        # wrap in a ValueHelper
        launchtime_vt = (launchtime, t_type, t_group)
        launchtime_vh = ValueHelper(launchtime_vt,
                                    formatter=self.generator.formatter,
                                    converter=self.generator.converter)

        # heat color word
        heat_color_words = ['Unknown', 'Extreme Heat Danger', 'Heat Danger',
                            'Extreme Heat Caution', 'Extremely Hot',
                            'Uncomfortably Hot', 'Hot', 'Warm', 'Comfortable',
                            'Cool', 'Cold', 'Uncomfortably Cold', 'Very Cold',
                            'Extreme Cold']
        curr_rec_metric = weewx.units.to_METRIC(curr_rec)
        curr_wd_rec_metric = weewx.units.to_METRIC(curr_wd_rec)
        temperature = curr_rec_metric.get('outTemp')
        windchill = curr_rec_metric.get('windchill')
        humidex = curr_wd_rec_metric.get('humidex')
        heat_color_word = heat_color_words[0]
        if temperature is not None:
            if temperature > 32:
                if humidex is not None:
                    if humidex > 54:
                        heat_color_word = heat_color_words[1]
                    elif humidex > 45:
                        heat_color_word = heat_color_words[2]
                    elif humidex > 39:
                        heat_color_word = heat_color_words[4]
                    elif humidex > 29:
                        heat_color_word = heat_color_words[6]
                else:
                    heat_color_word = heat_color_words[0]
            elif windchill is not None:
                if windchill < 16:
                    if windchill < -18:
                        heat_color_word = heat_color_words[13]
                    elif windchill < -9:
                        heat_color_word = heat_color_words[12]
                    elif windchill < -1:
                        heat_color_word = heat_color_words[11]
                    elif windchill < 8:
                        heat_color_word = heat_color_words[10]
                    elif windchill < 16:
                        heat_color_word = heat_color_words[9]
                elif windchill >= 16 and temperature <= 32:
                    if temperature < 26:
                        heat_color_word = heat_color_words[8]
                    else:
                        heat_color_word = heat_color_words[7]
                else:
                    heat_color_word = heat_color_words[0]
            else:
                heat_color_word = heat_color_words[0]
        else:
            heat_color_word = heat_color_words[0]

        # feels like
        if temperature is not None:
            if temperature <= 16:
                feels_like_vt = ValueTuple(windchill,
                                           'degree_C',
                                           'group_temperature')
            elif temperature >= 27:
                feels_like_vt = ValueTuple(humidex,
                                           'degree_C',
                                           'group_temperature')
            else:
                feels_like_vt = ValueTuple(temperature,
                                           'degree_C',
                                           'group_temperature')
        else:
            feels_like_vt = ValueTuple(None, 'degree_C', 'group_temperature')
        feels_like_vh = ValueHelper(feels_like_vt,
                                    formatter=self.generator.formatter,
                                    converter=self.generator.converter)

        # air density
        dp = curr_rec_metric.get('dewpoint')
        p = curr_rec_metric.get('pressure')
        if dp is not None and temperature is not None and p is not None:
            kelvin = temperature + 273.15
            p = (0.99999683 + dp * (-0.90826951E-2 + dp * (0.78736169E-4 +
                 dp * (-0.61117958E-6 + dp * (0.43884187E-8 +
                       dp * (-0.29883885E-10 + dp * (0.21874425E-12 +
                             dp * (-0.17892321E-14 + dp * (0.11112018E-16 +
                                   dp * (-0.30994571E-19))))))))))
            pv = 100 * 6.1078 / (p**8)
            pd = p * 100 - pv
            density = round((pd/(287.05 * kelvin)) + (pv/(461.495 * kelvin)), 3)
        else:
            density = 0

        # Beaufort wind
        if 'windSpeed' in curr_rec_metric:
            if curr_rec_metric['windSpeed'] is not None:
                w_s = curr_rec_metric['windSpeed']
                if w_s >= 117.4:
                    beaufort = 12
                    beaufort_desc = "Hurricane"
                elif w_s >= 102.4:
                    beaufort = 11
                    beaufort_desc = "Violent Storm"
                elif w_s >= 88.1:
                    beaufort = 10
                    beaufort_desc = "Storm"
                elif w_s >= 74.6:
                    beaufort = 9
                    beaufort_desc = "Strong Gale"
                elif w_s >= 61.8:
                    beaufort = 8
                    beaufort_desc = "Gale"
                elif w_s >= 49.9:
                    beaufort = 7
                    beaufort_desc = "Moderate Gale"
                elif w_s >= 38.8:
                    beaufort = 6
                    beaufort_desc = "Strong Breeze"
                elif w_s >= 28.7:
                    beaufort = 5
                    beaufort_desc = "Fresh Breeze"
                elif w_s >= 19.7:
                    beaufort = 4
                    beaufort_desc = "Moderate Breeze"
                elif w_s >= 11.9:
                    beaufort = 3
                    beaufort_desc = "Gentle Breeze"
                elif w_s >= 5.5:
                    beaufort = 2
                    beaufort_desc = "Light Breeze"
                elif w_s >= 1.1:
                    beaufort = 1
                    beaufort_desc = "Light Air"
                else:
                    beaufort = 0
                    beaufort_desc = "Calm"
            else:
                beaufort = 0
                beaufort_desc = "Calm"
        else:
            beaufort = None
            beaufort_desc = "N/A"

        # wet bulb
        humidity = curr_rec_metric.get('outHumidity')
        if temperature is not None and humidity is not None and p is not None:
            tc = temperature
            rh = humidity
            tdc = ((tc - (14.55 + 0.114 * tc) * (1 - (0.01 * rh)) -
                   ((2.5 + 0.007 * tc) * (1 - (0.01 * rh))) ** 3 -
                   (15.9 + 0.117 * tc) * (1 - (0.01 * rh)) ** 14))
            e = (6.11 * 10 ** (7.5 * tdc / (237.7 + tdc)))
            wb = ((((0.00066 * p) * tc) + ((4098 * e) / ((tdc + 237.7) ** 2) * tdc)) /
                  ((0.00066 * p) + (4098 * e) / ((tdc + 237.7) ** 2)))
            wb_vt = ValueTuple(wb, 'degree_C', 'group_temperature')
        else:
            wb_vt = ValueTuple(None, 'degree_C', 'group_temperature')
        wb_vh = ValueHelper(wb_vt,
                            formatter=self.generator.formatter,
                            converter=self.generator.converter)

        # chandler burning index
        if humidity is not None and temperature is not None:
            cbi = max(0.0, round((((110 - 1.373 * humidity) - 0.54 *
                      (10.20 - temperature)) *
                      (124 * 10 ** (-0.0142 * humidity)))/60, 1))
        else:
            cbi = 0.0
        cbi_vt = ValueTuple(cbi, 'count', 'group_count')
        cbi_vh = ValueHelper(cbi_vt,
                             formatter=self.generator.formatter,
                             converter=self.generator.converter)
        if cbi_vh.raw > 97.5:
            cbi_text = "EXTREME"
        elif cbi_vh.raw >= 90:
            cbi_text = "VERY HIGH"
        elif cbi_vh.raw >= 75:
            cbi_text = "HIGH"
        elif cbi_vh.raw >= 50:
            cbi_text = "MODERATE"
        else:
            cbi_text = "LOW"

        # cloud base
        alt_vt = weewx.units.convert(self.generator.stn_info.altitude_vt, 'meter')
        try:
            cloudbase = weewx.wxformulas.cloudbase_Metric(temperature,
                                                          humidity,
                                                          alt_vt.value)
        except TypeError:
            # we likely have a None value for temperature or humidity
            cloudbase = None
        cloudbase_vt = ValueTuple(cloudbase, 'meter', 'group_altitude')
        cloudbase_vh = ValueHelper(cloudbase_vt,
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)

        # Easter. Calculate date for Easter Sunday this year
        def calc_easter(year):
            """Calculate Easter date.

            Uses a modified version of Butcher's Algorithm.
            Refer New Scientist, 30 March 1961 pp 828-829
            https://books.google.co.uk/books?id=zfzhCoOHurwC&printsec=frontcover&source=gbs_ge_summary_r&cad=0#v=onepage&q&f=false
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

        _year = date.fromtimestamp(timespan.stop).year
        easter_ts = calc_easter(_year)
        # check to see if we have past this calculated date, if so we want next
        # years date so increment year and recalculate
        if date.fromtimestamp(easter_ts) < date.fromtimestamp(timespan.stop):
            easter_ts = calc_easter(_year + 1)
        easter_vt = ValueTuple(easter_ts, 'unix_epoch', 'group_time')
        easter_vh = ValueHelper(easter_vt,
                                formatter=self.generator.formatter,
                                converter=self.generator.converter)

        #
        # Barometer trend
        #
        if 'barometer' in curr_rec_metric and curr_rec_metric['barometer'] is not None:
            curr_baro_hpa = curr_rec_metric['barometer']
            # 1 hour trend
            rec_60 = db_lookup().getRecord(self.generator.gen_ts - 3600, 300)
            if rec_60:
                rec_60_metric = weewx.units.to_METRIC(rec_60)
                if 'barometer' in rec_60_metric and rec_60_metric['barometer'] is not None:
                    baro_60_hpa = rec_60_metric['barometer']
                    trend_60_hpa = curr_baro_hpa - baro_60_hpa
                    if trend_60_hpa >= 2:
                        trend_60 = "Rising Rapidly"
                    elif trend_60_hpa >= 0.7:
                        trend_60 = "Rising Slowly"
                    elif trend_60_hpa <= -2:
                        trend_60 = "Falling Rapidly"
                    elif trend_60_hpa <= -0.7:
                        trend_60 = "Falling Slowly"
                    else:
                        trend_60 = "Steady"
                else:
                    trend_60 = "N/A"
            else:
                trend_60 = "N/A"
            # 3 hour trend
            rec_180 = db_lookup().getRecord(self.generator.gen_ts - 10800, 300)
            if rec_180:
                rec_180_metric = weewx.units.to_METRIC(rec_180)
                if 'barometer' in rec_180_metric and rec_180_metric['barometer'] is not None:
                    baro_180_hpa = rec_180_metric['barometer']
                    trend_180_hpa = curr_baro_hpa - baro_180_hpa
                    if trend_180_hpa >= 2:
                        trend_180 = "Rising Rapidly"
                    elif trend_180_hpa >= 0.7:
                        trend_180 = "Rising Slowly"
                    elif trend_180_hpa <= -2:
                        trend_180 = "Falling Rapidly"
                    elif trend_180_hpa <= -0.7:
                        trend_180 = "Falling Slowly"
                    else:
                        trend_180 = "Steady"
                else:
                    trend_180 = "N/A"
            else:
                trend_180 = "N/A"
        else:
            trend_60 = "N/A"
            trend_180 = "N/A"

        # system free memory
        meminfo = {}
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    meminfo[line.split(':')[0]] = line.split(':')[1].strip()
        except IOError:
            freemem = None
        else:
            freemem = meminfo.get('MemFree')

        # time of next update
        interval = curr_rec.get('interval')
        _next_update_ts = timespan.stop + 60.0 * interval if interval else None
        next_update_vt = ValueTuple(_next_update_ts,
                                    'unix_epoch',
                                    'group_time')
        next_update_vh = ValueHelper(next_update_vt,
                                     formatter=self.generator.formatter,
                                     converter=self.generator.converter)

        # latitude and longitude as a string in D:M:S format
        def ll_to_str(_ll_f):

            if _ll_f:
                _sign = math.copysign(1.0, _ll_f)
                (_min_f, _deg_i) = math.modf(abs(_ll_f))
                (_sec_f, _min_i) = math.modf(_min_f * 60.0)
                _sec_i = int(round(_sec_f * 60.0))
                if _sec_i == 60:
                    _min_i += 1
                    _sec_i = 0
                if _min_i == 60.0:
                    _deg_i += 1
                    _min_i = 0
                ll_str = "%d:%d:%d" % (_sign * _deg_i, _min_i, _sec_i)
            else:
                ll_str = "N/A"
            return ll_str

        # latitude
        _lat_f = self.generator.stn_info.latitude_f
        lat_str = ll_to_str(_lat_f)

        # longitude
        _long_f = self.generator.stn_info.longitude_f
        long_str = ll_to_str(_long_f)

        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'launchtime':     launchtime_vh,
                       'heatColorWord':  heat_color_word,
                       'feelsLike':      feels_like_vh,
                       'density':        density,
                       'beaufort':       beaufort,
                       'beaufortDesc':   beaufort_desc,
                       'wetBulb':        wb_vh,
                       'cbi':            cbi_vh,
                       'cbitext':        cbi_text,
                       'cloudbase':      cloudbase_vh,
                       'Easter':         easter_vh,
                       'trend_60_baro':  trend_60,
                       'trend_180_baro': trend_180,
                       'freeMemory':     freemem,
                       'next_update':    next_update_vh,
                       'lat_dms':        lat_str,
                       'long_dms':       long_str}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdSundryTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                              class WdTaggedStats
# ==============================================================================


class WdTaggedStats(weewx.cheetahgenerator.SearchList):
    """SLE to return custom tagged stats drawn from the daily summaries."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdTaggedStats, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with custom tagged stats drawn from the daily
           summaries.

        Permits the syntax:

            $stat_type.observation.agg_type

            where:

                stat_type is one of:
                    weekdaily: week of stats aggregated by day
                    monthdaily: month of stats aggregated by day
                    yearmonthy: year of stats aggregated by month

                observation is any WeeWX observation recorded in the archive
                eg outTemp or humidity

                agg_type is:
                    maxQuery: returns maximums/highs over the aggregate period
                    minQuery: returns minimums/lows over the aggregate period
                    avgQuery: returns averages over the aggregate period
                    sumQuery: returns sum over the aggregate period
                    vecdirQuery: returns vector direction over the aggregate
                                 period

           Also supports the $stat_type.observation.exists and
           $stat_type.observation.has_data properties which are true if the
           relevant observation exists and has data respectively.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            A list of ValueHelpers for custom stat concerned as follows:
                weekdaily: list of 7 ValueHelpers. Item [0] is the earliest
                           day, item [6] is the current day
                monthdaily: list of 31 ValueHelpers. Item [0] is the day 31
                            days ago, item [30] is the current day
                yearmonthy: list of 31 ValueHelpers. Item [0] is the month 12
                            months ago, item [11] is the current month

            So $weekdaily.outTemp.maxQuery.degree_F would return a list of the
            max temp in Fahrenheit for each day over the last 7 days.
            $weekdaily.outTemp.maxQuery[1].degree_C would return the max temp
            in Celsius of the day 6 days ago.
          """

        t1 = time.time()

        # Get a WDTaggedStats structure. This allows constructs such as
        # WDstats.monthdaily.outTemp.max
        _stats = user.wdtaggedstats.WdTimeBinder(db_lookup,
                                                 timespan.stop,
                                                 formatter=self.generator.formatter,
                                                 converter=self.generator.converter)

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdTaggedStats SLE executed in %0.3f seconds" % (t2-t1))

        return [_stats]


# ==============================================================================
#                           class WdTaggedArchiveStats
# ==============================================================================


class WdTaggedArchiveStats(weewx.cheetahgenerator.SearchList):
    """SLE to return custom tagged stats drawn from the archive."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdTaggedArchiveStats, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with custom tagged stats drawn from archive.

        Permits the syntax:

            $stat_type.observation.agg_type

            where:
                stat_type is one of:
                    minute: hour of stats aggregated by minute
                    fifteenminute: day of stats aggregated by 15 minutes
                    hour: day of stats aggregated by hour
                    sixhour: week of stats aggregated by 6 hours
                observation is any WeeWX observation recorded in the archive
                    eg outTemp or humidity
                agg_type is one of:
                    maxQuery: returns maximums/highs over the aggregate period
                    minQuery: returns minimums/lows over the aggregate period
                    avgQuery: returns averages over the aggregate period
                    sumQuery: returns sum over the aggregate period
                    datetimeQuery: returns datetime over the aggregate period

            Also supports the $stat_type.observation.exists and
            $stat_type.observation.has_data properties which are true if the
            relevant observation exists and has data respectively

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            A list of ValueHelpers for custom stat concerned as follows:

            minute: list of 60 ValueHelpers. Item [0] is the minute commencing
                    60 minutes ago, item [59] is the minute immediately before
                    valid_timespan.stop. For archive periods greater than
                    60 seconds the intervening minutes between archive records
                    are extrapolated linearly.
            fifteenminute: list of 96 ValueHelpers. Item [0] is the 15 minute
                           period commencing 24 hours ago, item [95] is the
                           15 minute period ending at valid_timespan.stop.
            hour: list of 24 ValueHelpers. Item [0] is the hours commencing
                  24 hours ago, item [23] is the hour ending at
                  valid_timespan.stop.
            sixhour: list of 42 ValueHelpers. Item [0] is the 6 hour period
                     commencing 192 hours ago, item [41] is the 6 hour period
                     ending at valid_timespan.stop.

          For example, $fifteenminute.outTemp.maxQuery.degree_F would return a
          list of the max temp in Fahrenheit for each 15 minute period over the
          last 24 hours.
          $fifteenminute.outTemp.maxQuery[1].degree_C would return the max temp
          in Celsius of the 15 minute period commencing 23hr 45min ago.
          """

        t1 = time.time()

        # Get a WDTaggedStats structure. This allows constructs such as
        # WDstats.minute.outTemp.max
        _stats = user.wdtaggedstats.WdArchiveTimeBinder(db_lookup,
                                                        timespan.stop,
                                                        formatter=self.generator.formatter,
                                                        converter=self.generator.converter)

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdTaggedArchiveStats SLE executed in %0.3f seconds" % (t2-t1))

        return [_stats]


# ==============================================================================
#                              class WdYestAlmanac
# ==============================================================================


class WdYestAlmanac(weewx.cheetahgenerator.SearchList):
    """SLE to return an Almanac object for yesterday."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdYestAlmanac, self).__init__(generator)

        t1 = time.time()

        celestial_ts = generator.gen_ts

        # For better accuracy, the almanac requires the current temperature
        # and barometric pressure, so retrieve them from the default archive,
        # using celestial_ts as the time

        temperature_c = pressure_mbar = None

        db = generator.db_binder.get_manager()
        if not celestial_ts:
            celestial_ts = db.lastGoodStamp() - 86400
        else:
            celestial_ts -= 86400
        rec = db.getRecord(celestial_ts, max_delta=3600)

        if rec is not None:
            out_temp_vt = weewx.units.as_value_tuple(rec, 'outTemp')
            pressure_vt = weewx.units.as_value_tuple(rec, 'barometer')

            if not isinstance(out_temp_vt, weewx.units.UnknownType):
                temperature_c = weewx.units.convert(out_temp_vt, 'degree_C')[0]
            if not isinstance(pressure_vt, weewx.units.UnknownType):
                pressure_mbar = weewx.units.convert(pressure_vt, 'mbar')[0]
        if temperature_c is None:
            temperature_c = 15.0
        if pressure_mbar is None:
            pressure_mbar = 1010.0

        _almanac_skin_dict = generator.skin_dict.get('Almanac', {})
        self.moonphases = _almanac_skin_dict.get('moon_phases',
                                                 weeutil.Moon.moon_phases)
        altitude_vt = weewx.units.convert(generator.stn_info.altitude_vt,
                                          "meter")
        self.yestAlmanac = weewx.almanac.Almanac(celestial_ts,
                                                 generator.stn_info.latitude_f,
                                                 generator.stn_info.longitude_f,
                                                 altitude=altitude_vt.value,
                                                 temperature=temperature_c,
                                                 pressure=pressure_mbar,
                                                 moon_phases=self.moonphases,
                                                 formatter=generator.formatter)

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdYestAlmanac SLE executed in %0.3f seconds" % (t2-t1))


# ================================================================================
#                                 class WdSkinDict
# ================================================================================


class WdSkinDict(weewx.cheetahgenerator.SearchList):
    """SLE to return skin settings."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdSkinDict, self).__init__(generator)

        t1 = time.time()

        self.skin_dict = generator.skin_dict

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdSkinDict SLE executed in %0.3f seconds" % (t2-t1))


# ================================================================================
#                            class WdMonthlyReportStats
# ================================================================================


class WdMonthlyReportStats(weewx.cheetahgenerator.SearchList):
    """SLE to return various date/time tags used in WD monthly report."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdMonthlyReportStats, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list extension with various date/time tags
           used in WD monthly report template.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            month_name:      abbreviated month name (eg Dec) of start of
                             timespan
            month_long_name: long month name (eg December) of start of timespan
            month_number:    month number (eg 12 for December) of start of
                             timespan
            year_name:       4 digit year (eg 2013) of start of timespan
            curr_minute:     current minute of time of last record
            curr_hour:       current hour of time of last record
            curr_day:        day of time of last archive record
            curr_month:      month of time of last archive record
            curr_year:       year of time of last archive record
        """

        t1 = time.time()

        # get a required times and convert to time tuples
        timespan_start_tt = time.localtime(timespan.start)
        stop_ts = db_lookup().lastGoodStamp()
        stop_tt = time.localtime(stop_ts)

        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'month_name':      time.strftime("%b", timespan_start_tt),
                       'month_long_name': time.strftime("%B", timespan_start_tt),
                       'month_number':    timespan_start_tt[1],
                       'year_name':       timespan_start_tt[0],
                       'curr_minute':     stop_tt[4],
                       'curr_hour':       stop_tt[3],
                       'curr_day':        stop_tt[2],
                       'curr_month':      stop_tt[1],
                       'curr_year':       stop_tt[0]}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdMonthlyReportStats SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                              class WdWindRunTags
# ==============================================================================


class WdWindRunTags(weewx.cheetahgenerator.SearchList):
    """ Search list extension to return windrun over variou speriods. Also
        returns max day windrun and the date on which this occurred.

        Whilst weewx supports windrun through inclusion of distance units and
        groups weewx only provides as cumulative daily windrun in each
        loop/archive record. This cumulative value is reset at midnight each
        day. Consequently, a SLE is required to provide windrun
        statistics/aggregates over various standard timespans.

        Definition:

        Windrun. The total distance of travelled wind over a period of time.
        Windrun is independent of any directional properties of the wind.
        For fixed periods windrun is calculated by the average wind speed over
        the period times the length of the period (eg 1 day). For variable
        length periods windrun is calculated by breaking the variable length
        period into a number of fixed length periods finding the sum of the
        periods time the average wind speed for the period. Special
        consideration is needed for partial periods.
    """

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdWindRunTags, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """ Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

            Returns:
            day_windrun       : windrun from midnight to current time
            yest_windrun      : yesterdays windrun
            week_windrun      : windrun so far this weeke. Start of week as per
                                weewx.conf week_start setting
            seven_days_windrun: windrun over the last 7 days (today is included)
            month_windrun     : this months windrun to date
            year_windrun      : this years windrun to date
            alltime_windrun   : alltime windrun
            max_windrun         : max daily windrun seen
            max_windrun_ts      : timestamp (midnight) of max daily windrun
            max_year_windrun    : max daily windrun this year
            max_year_windrun_ts : timestamp (midnight) of max daily windrun
                                  this year
            max_month_windrun   : max daily windrun this month
            max_month_windrun_ts: timestamp (midnight) of max windrun this
                                  month
        """

        t1 = time.time()

        #
        # Get windSpeed units for use later
        #

        # Get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # Get the unit in use
        _usUnits = current_rec['usUnits']
        (windrun_type, windrun_group) = getStandardUnitType(_usUnits,
                                                            'windrun')

        # Get timestamp for our first (earliest) and last record
        _first_ts = db_lookup().firstGoodStamp()
        _last_ts = timespan.stop

        #
        # Get timestamps for midnight at the start of our various periods
        #
        # Get time obj for midnight
        _mn_t = datetime.time(0)
        # Get date obj for now
        _today_d = datetime.datetime.today()
        # Get ts for midnight at the end of period
        _mn_ts = weeutil.weeutil.startOfDay(timespan.stop)
        # Go back 24hr to get midnight at start of yesterday as a timestamp
        _mn_yest_ts = _mn_ts - 86400
        # Get our 'start of week' as a timestamp
        # First day of week depends on a setting in weewx.conf
        _week_start = int(self.generator.config_dict['Station'].get('week_start', 6))
        _day_of_week = _today_d.weekday()
        _delta = _day_of_week - _week_start
        if _delta < 0:
            _delta += 7
        _week_date = _today_d - datetime.timedelta(days=_delta)
        _week_dt = datetime.datetime.combine(_week_date, _mn_t)
        _mn_week_ts = time.mktime(_week_dt.timetuple())
        # Go back 7 days to get midnight 7 days ago as a timestamp
        _mn_seven_days_ts = _mn_ts - 604800
        # Get midnight 1st of the month as a datetime object and then get it as a
        # timestamp
        first_of_month_dt = get_first_day(_today_d)
        _mn_first_of_month_dt = datetime.datetime.combine(first_of_month_dt, _mn_t)
        _mn_first_of_month_ts = time.mktime(_mn_first_of_month_dt.timetuple())
        # Get midnight 1st of the year as a datetime object and then get it as a
        # timestamp
        _first_of_year_dt = get_first_day(_today_d, 0, 1-_today_d.month)
        _mn_first_of_year_dt = datetime.datetime.combine(_first_of_year_dt, _mn_t)
        _mn_first_of_year_ts = time.mktime(_mn_first_of_year_dt.timetuple())

        # today's windrun
        # First get today's elapsed hours
        if _first_ts <= _mn_ts:
            # We have from midnight to now
            _day_hours = (_last_ts - _mn_ts)/3600.0
        else:
            # Our data starts some time after midnight
            _day_hours = (_last_ts - _first_ts)/3600.0
        # Get today's average wind speed
        wind_speed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_ts, _last_ts),
                                                     'windSpeed', 'avg')
        if wind_speed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _day_run = wind_speed_avg_vt.value * _day_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _day_run = wind_speed_avg_vt.value * _day_hours
        else:
            # No avg wind speed so set to None
            _day_run = None
        # Get our results as a ValueTuple
        day_run_vt = ValueTuple(_day_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        day_run_vh = ValueHelper(day_run_vt,
                                 formatter=self.generator.formatter,
                                 converter=self.generator.converter)

        # Yesterdays windrun
        # First get yesterdays elapsed hours
        if _first_ts <= _mn_yest_ts:
            # We have data for a full day
            _yest_hours = 24.0
        else:
            # Our data starts some time after midnight
            _yest_hours = (_mn_ts - _first_ts)/3600.0
        # Get yesterdays average wind speed
        wind_speed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_yest_ts, _mn_ts),
                                                     'windSpeed', 'avg')
        if wind_speed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _yest_run = wind_speed_avg_vt.value * _yest_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _yest_run = wind_speed_avg_vt.value * _yest_hours
        else:
            # No avg wind speed so set to None
            _yest_run = None
        # Get our results as a ValueTuple
        yest_run_vt = ValueTuple(_yest_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        yest_run_vh = ValueHelper(yest_run_vt,
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)

        # Week windrun
        # First get week elapsed hours
        if _first_ts <= _mn_week_ts:
            # We have data from midnight at start of week to now
            _week_hours = (_last_ts - _mn_week_ts)/3600.0
        else:
            # Our data starts some time after midnight on start of week
            _week_hours = (_last_ts - _first_ts)/3600.0
        # Get week average wind speed
        wind_speed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_week_ts, _last_ts),
                                                     'windSpeed', 'avg')
        if wind_speed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _week_run = wind_speed_avg_vt.value * _week_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _week_run = wind_speed_avg_vt.value * _week_hours
        else:
            # No avg wind speed so set to None
            _week_run = None
        # Get our results as a ValueTuple
        week_run_vt = ValueTuple(_week_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        week_run_vh = ValueHelper(week_run_vt,
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)

        # Seven days windrun
        # First get seven days elapsed hours
        if _first_ts <= _mn_seven_days_ts:
            # We have a data since midnight 7 days ago
            _seven_days_hours = 168.0
        else:
            # Our data starts some time after midnight
            _seven_days_hours = (_last_ts - _first_ts)/3600.0
        # Get 'seven days' average wind speed
        wind_speed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_seven_days_ts, _last_ts),
                                                     'windSpeed', 'avg')
        if wind_speed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _seven_days_run = wind_speed_avg_vt.value * _seven_days_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _seven_days_run = wind_speed_avg_vt.value * _seven_days_hours
        else:
            # No avg wind speed so set to None
            _seven_days_hours = None
        # Get our results as a ValueTuple
        seven_days_run_vt = ValueTuple(_seven_days_hours, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        seven_days_run_vh = ValueHelper(seven_days_run_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)

        # Month windrun
        # First get month elapsed hours
        if _first_ts <= _mn_first_of_month_ts:
            # We have a data since midnight on 1st of month
            _month_hours = (_last_ts - _mn_first_of_month_ts)/3600.0
        else:
            # Our data starts some time after midnight on 1st of month
            _month_hours = (_last_ts - _first_ts)/3600.0
        # Get month average wind speed
        wind_speed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_first_of_month_ts, _last_ts),
                                                     'windSpeed', 'avg')
        if wind_speed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _month_run = wind_speed_avg_vt.value * _month_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _month_run = wind_speed_avg_vt.value * _month_hours
        else:
            # No avg wind speed so set to None
            _month_run = None
        # Get our results as a ValueTuple
        month_run_vt = ValueTuple(_month_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        month_run_vh = ValueHelper(month_run_vt,
                                   formatter=self.generator.formatter,
                                   converter=self.generator.converter)

        # Year windrun
        # First get year elapsed hours
        if _first_ts <= _mn_first_of_year_ts:
            # We have a data since midnight on 1 Jan
            _year_hours = (_last_ts - _mn_first_of_year_ts)/3600.0
        else:
            # Our data starts some time after midnight on 1 Jan
            _year_hours = (_last_ts - _first_ts)/3600.0
        # Get year average wind speed
        wind_speed_avg_vt = db_lookup().getAggregate(TimeSpan(_mn_first_of_year_ts, _last_ts),
                                                     'windSpeed', 'avg')
        if wind_speed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _year_run = wind_speed_avg_vt.value * _year_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _year_run = wind_speed_avg_vt.value * _year_hours
        else:
            # No avg wind speed so set to None
            _year_run = None
        # Get our results as a ValueTuple
        year_run_vt = ValueTuple(_year_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        year_run_vh = ValueHelper(year_run_vt,
                                  formatter=self.generator.formatter,
                                  converter=self.generator.converter)

        # Alltime windrun
        # First get alltime elapsed hours
        _alltime_hours = (_last_ts - _first_ts)/3600.0
        # Get alltime average wind speed
        wind_speed_avg_vt = db_lookup().getAggregate(TimeSpan(_first_ts, _last_ts),
                                                     'windSpeed', 'avg')
        if wind_speed_avg_vt.value is not None:
            if _usUnits == weewx.METRICWX:
                # METRICWX so wind speed is m/s, div by 1000 for km
                _alltime_run = wind_speed_avg_vt.value * _alltime_hours / 1000.0
            else:
                # METRIC or US so its just a straight multiply
                _alltime_run = wind_speed_avg_vt.value * _alltime_hours
        else:
            # No avg wind speed so set to None
            _alltime_run = None
        # Get our results as a ValueTuple
        alltime_run_vt = ValueTuple(_alltime_run, windrun_type, windrun_group)
        # Get our results as a ValueHelper
        alltime_run_vh = ValueHelper(alltime_run_vt,
                                     formatter=self.generator.formatter,
                                     converter=self.generator.converter)

        #
        # Max day windrun over various periods (timespans)
        #

        # Alltime
        # Get alltime max day average wind excluding today and first day if its
        # a partial day
        if not weeutil.weeutil.isMidnight(_first_ts):
            _start_ts = weeutil.weeutil.startOfDay(_first_ts) + 86400
        else:
            _start_ts = _first_ts
        _row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed "
                                  "WHERE dateTime >= ? AND dateTime < ?", (_start_ts, _mn_ts))
        # Now get our max_day_windrun excluding first day and today
        if _row:
            if _row[0] is not None:
                _max_windrun_ts = _row[0]
                if _max_windrun_ts > _first_ts:
                    # Our data is for a full day
                    hours = 24.0
                else:
                    # Our data is for the first day in our archive and its a partial day
                    hours = (86400 - (_first_ts - _max_windrun_ts))/3600.0

                if _row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _max_windrun = _row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _max_windrun = _row[1] * hours
                else:
                    # No avg wind speed so set to None
                    _max_windrun = None
                    _max_windrun_ts = None
            else:
                # No max wind speed ts so set to None
                _max_windrun = None
                _max_windrun_ts = None
        else:
            # No result so set all to None
            _max_windrun_ts = None
            _max_windrun = None

        # Get our first days windrun and ts
        _first_mn_ts = weeutil.weeutil.startOfDay(_first_ts)
        _first_row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed "
                                        "WHERE dateTime = ?", (_first_mn_ts,))
        if _first_row:
            if _first_row[0] is not None:
                _first_windrun_ts = _first_row[0]
                hours = (_start_ts - _first_ts)/3600.0
                if _first_row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _first_windrun = _first_row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _first_windrun = _first_row[1] * hours
                else:
                    _first_windrun = None
                    _first_windrun_ts = None
            else:
                _first_windrun = None
                _first_windrun_ts = None
        else:
            _first_windrun = None
            _first_windrun_ts = None

        # Get today's windrun and ts.
        _today_windrun = _day_run
        _today_windrun_ts = _mn_ts if _day_run is not None else None

        # If today's partial day windrun is greater than max of any of previous
        # days then change our max_day_windrun
        if _max_windrun and _today_windrun:
            # We have values for both so compare
            if _today_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _today_windrun
                _max_windrun_ts = _today_windrun_ts
        elif _today_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _today_windrun
            _max_windrun_ts = _today_windrun_ts
        # If first day's windrun is greater than our max so far then change our
        # max_day_windrun
        if _max_windrun and _first_windrun:
            # We have values for both so compare
            if _first_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _first_windrun
                _max_windrun_ts = _first_windrun_ts
        elif _first_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _first_windrun
            _max_windrun_ts = _first_windrun_ts

        # Convert our results to ValueTuple and then ValueHelper
        max_windrun_vt = ValueTuple(_max_windrun, windrun_type, windrun_group)
        max_windrun_vh = ValueHelper(max_windrun_vt,
                                     formatter=self.generator.formatter,
                                     converter=self.generator.converter)
        max_windrun_ts_vt = ValueTuple(_max_windrun_ts,
                                       'unix_epoch',
                                       'group_time')
        max_windrun_ts_vh = ValueHelper(max_windrun_ts_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)

        # Year
        # Get ts and MAX(avg) of windSpeed from statsdb
        # ts value returned is ts for midnight on the day the MAX(avg) occurred
        _row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed "
                                  "WHERE dateTime >= ? AND dateTime < ?", (_mn_first_of_year_ts, _mn_ts))
        # Now get our max_day_windrun excluding first day and today
        if _row:
            if _row[0] is not None:
                _max_windrun_ts = _row[0]
                if _max_windrun_ts > _first_ts:
                    # Our data is for a full day
                    hours = 24.0
                else:
                    # Our data is for the first day in our archive and its a partial day
                    hours = (86400 - (_first_ts - _max_windrun_ts))/3600.0

                if _row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _max_windrun = _row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _max_windrun = _row[1] * hours
                else:
                    # No avg wind speed so set to None
                    _max_windrun = None
                    _max_windrun_ts = None
            else:
                # No max wind speed ts so set to None
                _max_windrun = None
                _max_windrun_ts = None
        else:
            # No result so set all to None
            _max_windrun_ts = None
            _max_windrun = None

        # Get our first days windrun and ts
        if _first_ts > _mn_first_of_year_ts:
            # we have a partial day that will not have been included
            _first_mn_ts = weeutil.weeutil.startOfDay(_first_ts)
            _first_row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed "
                                            "WHERE dateTime = ?", (_first_mn_ts,))
            if _first_row:
                if _first_row[0] is not None:
                    _first_windrun_ts = _first_row[0]
                    hours = (86400 - (_first_ts - _first_mn_ts))/3600.0
                    if _first_row[1] is not None:
                        if _usUnits == weewx.METRICWX:
                            # METRICWX so wind speed is m/s, div by 1000 for km
                            _first_windrun = _first_row[1] * hours / 1000.0
                        else:
                            # METRIC or US so its just a straight multiply
                            _first_windrun = _first_row[1] * hours
                    else:
                        _first_windrun = None
                        _first_windrun_ts = None
                else:
                    _first_windrun = None
                    _first_windrun_ts = None
            else:
                _first_windrun = None
                _first_windrun_ts = None
        else:
            _first_windrun = None
            _first_windrun_ts = None

        # Get today's windrun and ts.
        _today_windrun = _day_run
        _today_windrun_ts = _mn_ts if _day_run is not None else None

        # If today's partial day windrun is greater than max of any of previous
        # days then change our max_day_windrun
        if _max_windrun and _today_windrun:
            # We have values for both so compare
            if _today_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _today_windrun
                _max_windrun_ts = _today_windrun_ts
        elif _today_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _today_windrun
            _max_windrun_ts = _today_windrun_ts
        # If first day's windrun is greater than our max so far then change our
        # max_day_windrun
        if _max_windrun and _first_windrun:
            # We have values for both so compare
            if _first_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _first_windrun
                _max_windrun_ts = _first_windrun_ts
        elif _first_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _first_windrun
            _max_windrun_ts = _first_windrun_ts

        # Convert our results to ValueTuple and then ValueHelper
        max_year_windrun_vt = ValueTuple(_max_windrun,
                                         windrun_type,
                                         windrun_group)
        max_year_windrun_vh = ValueHelper(max_year_windrun_vt,
                                          formatter=self.generator.formatter,
                                          converter=self.generator.converter)
        max_year_windrun_ts_vt = ValueTuple(_max_windrun_ts,
                                            'unix_epoch',
                                            'group_time')
        max_year_windrun_ts_vh = ValueHelper(max_year_windrun_ts_vt,
                                             formatter=self.generator.formatter,
                                             converter=self.generator.converter)

        # Month
        # Get ts and MAX(avg) of windSpeed from statsdb
        # ts value returned is ts for midnight on the day the MAX(avg) occurred
        _row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed "
                                  "WHERE dateTime >= ? AND dateTime < ?", (_mn_first_of_month_ts, _mn_ts))
        # Now get our max_day_windrun excluding first day and today
        if _row:
            if _row[0] is not None:
                _max_windrun_ts = _row[0]
                if _max_windrun_ts > _first_ts:
                    # Our data is for a full day
                    hours = 24.0
                else:
                    # Our data is for the first day in our archive and its a partial day
                    hours = (86400 - (_first_ts - _max_windrun_ts))/3600.0

                if _row[1] is not None:
                    if _usUnits == weewx.METRICWX:
                        # METRICWX so wind speed is m/s, div by 1000 for km
                        _max_windrun = _row[1] * hours / 1000.0
                    else:
                        # METRIC or US so its just a straight multiply
                        _max_windrun = _row[1] * hours
                else:
                    # No avg wind speed so set to None
                    _max_windrun = None
                    _max_windrun_ts = None
            else:
                # No max wind speed ts so set to None
                _max_windrun = None
                _max_windrun_ts = None
        else:
            # No result so set all to None
            _max_windrun_ts = None
            _max_windrun = None

        # Get our first days windrun and ts
        if _first_ts > _mn_first_of_month_ts:
            # we have a partial day that will not have been included
            _first_mn_ts = weeutil.weeutil.startOfDay(_first_ts)
            _first_row = db_lookup().getSql("SELECT dateTime, MAX(sum/count) FROM archive_day_windSpeed "
                                            "WHERE dateTime = ?", (_first_mn_ts,))
            if _first_row:
                if _first_row[0] is not None:
                    _first_windrun_ts = _first_row[0]
                    hours = (86400 - (_first_ts - _first_mn_ts))/3600.0
                    if _first_row[1] is not None:
                        if _usUnits == weewx.METRICWX:
                            # METRICWX so wind speed is m/s, div by 1000 for km
                            _first_windrun = _first_row[1] * hours / 1000.0
                        else:
                            # METRIC or US so its just a straight multiply
                            _first_windrun = _first_row[1] * hours
                    else:
                        _first_windrun = None
                        _first_windrun_ts = None
                else:
                    _first_windrun = None
                    _first_windrun_ts = None
            else:
                _first_windrun = None
                _first_windrun_ts = None
        else:
            _first_windrun = None
            _first_windrun_ts = None

        # Get today's windrun and ts.
        _today_windrun = _day_run
        _today_windrun_ts = _mn_ts if _day_run is not None else None

        # If today's partial day windrun is greater than max of any of previous
        # days then change our max_day_windrun
        if _max_windrun and _today_windrun:
            # We have values for both so compare
            if _today_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _today_windrun
                _max_windrun_ts = _today_windrun_ts
        elif _today_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _today_windrun
            _max_windrun_ts = _today_windrun_ts
        # If first day's windrun is greater than our max so far then change our
        # max_day_windrun
        if _max_windrun and _first_windrun:
            # We have values for both so compare
            if _first_windrun >= _max_windrun:
                # Today is greater so reset
                _max_windrun = _first_windrun
                _max_windrun_ts = _first_windrun_ts
        elif _first_windrun:
            # We have no _maxWindRunKm but we do have today so reset
            _max_windrun = _first_windrun
            _max_windrun_ts = _first_windrun_ts

        # convert our results to ValueTuples and then ValueHelpers
        max_month_windrun_vt = ValueTuple(_max_windrun,
                                          windrun_type,
                                          windrun_group)
        max_month_windrun_vh = ValueHelper(max_month_windrun_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)
        max_month_windrun_ts_vt = ValueTuple(_max_windrun_ts,
                                             'unix_epoch',
                                             'group_time')
        max_month_windrun_ts_vh = ValueHelper(max_month_windrun_ts_vt,
                                              formatter=self.generator.formatter,
                                              converter=self.generator.converter)

        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'day_windrun':            day_run_vh,
                       'yest_windrun':           yest_run_vh,
                       'week_windrun':           week_run_vh,
                       'seven_days_windrun':     seven_days_run_vh,
                       'month_windrun':          month_run_vh,
                       'year_windrun':           year_run_vh,
                       'alltime_windrun':        alltime_run_vh,
                       'month_max_windrun':      max_month_windrun_vh,
                       'month_max_windrun_ts':   max_month_windrun_ts_vh,
                       'year_max_windrun':       max_year_windrun_vh,
                       'year_max_windrun_ts':    max_year_windrun_ts_vh,
                       'alltime_max_windrun':    max_windrun_vh,
                       'alltime_max_windrun_ts': max_windrun_ts_vh}

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdWindRunTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                              class WdHourRainTags
# ==============================================================================


class WdHourRainTags(weewx.cheetahgenerator.SearchList):
    """SLE to return maximum 1 hour rainfall during the current day."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdHourRainTags, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns a search list with the maximum 1 hour rainfall and the time
           this occurred for current day.

            A sliding 1 hour window is used to find the 1 hour window that has
            the max rainfall. the 1 hour window aligns on the archive period
            boundary (ie for 5 min archive period the window could be from
            01:05 to 02:05 but not 01:03 to 02:03). The time returned is the
            end time of the one hour window with the max rain. As the end time
            is returned, the 1 hour window starts at 23:00:01 the previous day
            and slides to 23:00 on the current day.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            maxHourRainToday: Max rain that fell in any 1 hour window today.
                              Returned as a ValueHelper so that standard WeeWX
                              unit conversion and formatting options are
                              available.
            maxHourRainTodayTime: End time of 1 hour window during which max
                                  1 hour rain fell today. Returned as a
                                  ValueHelper so that standard WeeWX unit
                                  conversion and formatting options are
                                  available.
        """

        t1 = time.time()

        # get time obj for midnight
        midnight_t = datetime.time(0)
        # get datetime obj for now
        today_d = datetime.date.today()
        # get datetime obj for midnight at start of today
        midnight_dt = datetime.datetime.combine(today_d, midnight_t)
        # our start is 23:00:01 yesterday so go back 0:59:59
        start_dt = midnight_dt - datetime.timedelta(minutes=59, seconds=59)
        # get it as a timestamp
        start_ts = time.mktime(start_dt.timetuple())
        # our end time is 23:00 today so go forward 23 hours
        end_dt = midnight_dt + datetime.timedelta(hours=23)
        # get it as a timestamp
        end_ts = time.mktime(end_dt.timetuple())
        # get midnight as a timestamp
        midnight_ts = time.mktime(midnight_dt.timetuple())
        # enclose our query in a try..except block in case the earlier records
        # do not exist
        tspan = weeutil.weeutil.TimeSpan(start_ts, end_ts)
        try:
            (_start_vt, _stop_vt, _rain_vt) = db_lookup().getSqlVectors(tspan,
                                                                        'rain')
        except:
            loginf("WdHourRainTags: getSqlVectors exception")
        # set a few variables beforehand
        hour_start_ts = None
        hour_rain = []
        max_hour_rain = 0
        max_hour_rain_ts = midnight_ts
        # iterate over our records
        for time_t, rain_t in zip(_stop_vt[0], _rain_vt[0]):
            if time_t is not None:
                if hour_start_ts is None:
                    # our first non-None record
                    hour_start_ts = time_t
                hour_rain.append([time_t, rain_t if rain_t is not None else 0.0])
                # delete any records older than 1 hour
                old_ts = time_t - 3600
                hour_rain = [r for r in hour_rain if  r[0] > old_ts]
                # get the total rain for the hour in our list
                this_hour_rain = sum(rr[1] for rr in hour_rain)
                # if it is more than our current max then update our stats
                if this_hour_rain > max_hour_rain:
                    max_hour_rain = this_hour_rain
                    max_hour_rain_ts = time_t
        # get our results as ValueTuples
        max_hour_rain_vt = ValueTuple(max_hour_rain, _rain_vt[1], _rain_vt[2])
        max_hour_rain_time_vt = ValueTuple(max_hour_rain_ts,
                                           _stop_vt[1],
                                           _stop_vt[2])
        # wrap our results as ValueHelpers
        max_hour_rain_vh = ValueHelper(max_hour_rain_vt,
                                       formatter=self.generator.formatter,
                                       converter=self.generator.converter)
        max_hour_rain_time_vh = ValueHelper(max_hour_rain_time_vt,
                                            formatter=self.generator.formatter,
                                            converter=self.generator.converter)
        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'maxHourRainToday': max_hour_rain_vh,
                       'maxHourRainTodayTime': max_hour_rain_time_vh
                       }

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdHourRainTags SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                                 class WdGdDays
# ==============================================================================


class WdGdDays(weewx.cheetahgenerator.SearchList):
    """SLE to return Growing Degree Days tags."""

    def __init__(self, generator):
        # call our parent's initialisation
        super(WdGdDays, self).__init__(generator)

        # Get temperature group, this determines whether we return GDD in F or
        # C, enclose in try..except just in case. Default to degree_C if any
        # errors.
        try:
            group_dict = generator.skin_dict['Units']['Groups']
            self.temp_group = group_dict.get('group_temperature', 'degree_C')
        except KeyError:
            self.temp_group = 'degree_C'

        # Get GDD base temp and save as a ValueTuple, enclose in try..except
        # just in case. Default to 10 deg C if any errors.
        try:
            gdd_dict = generator.skin_dict['Extras']['GDD']
            _base_t = weeutil.weeutil.option_as_list(gdd_dict.get('base',
                                                                  (10, 'degree_C')))
            self.gdd_base_vt = ValueTuple(float(_base_t[0]),
                                          _base_t[1],
                                          'group_temperature')
        except KeyError:
            self.gdd_base_vt = ValueTuple(10.0,
                                          'degree_C',
                                          'group_temperature')

    def get_extension_list(self, timespan, db_lookup):
        """Returns Growing Degree Days tags.

            Returns a number representing to date Growing Degree Days (GDD) for
            various periods. GDD can be represented as GGD Fahrenheit (GDD F)
            or GDD Celsius (GDD C), 5 GDD C = 9 GDD F. As the standard
            Fahrenheit/Celsius conversion formula cannot be used to convert
            between GDD F and GDD C WeeWX ValueTuples cannot be used for the
            results and hence the results are returned in the group_temperature
            units specified in the associated skin.conf.

            The base temperature used in calculating GDD can be set using the
            'base' parameter under [Extras][[GDD]] in the associated skin.conf
            file. The base parameter consists of a numeric value followed by a
            unit string eg 10, degree_C or 50, degree_F. If the parameter is
            omitted or cannot be decoded then a default of 10, degree_C is
            used.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            month_gdd: Growing Degree Days to date this month. Numeric value
                       only, not a ValueTuple.
            year_gdd:  Growing Degree Days to date this year. Numeric value
                       only, not a ValueTuple.
        """

        t1 = time.time()

        # get units for use later with ValueHelpers
        # first, get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # get the unit in use for each group
        (t_type, t_group) = getStandardUnitType(current_rec['usUnits'],
                                                'outTemp')

        # get timestamps we need for the periods of interest
        # first, get ts for midnight at the end of period
        _mn_stop_ts = weeutil.weeutil.startOfDay(timespan.stop)
        # get time obj for midnight
        _mn_t = datetime.time(0)
        # get datetime obj for now
        _today_dt = datetime.datetime.today()
        # get midnight 1st of the month as a datetime object and then get it as
        # a timestamp
        first_of_month_dt = get_first_day(_today_dt)
        _mn_first_of_month_dt = datetime.datetime.combine(first_of_month_dt,
                                                          _mn_t)
        _mn_first_of_month_ts = time.mktime(_mn_first_of_month_dt.timetuple())
        # get midnight 1st of the year as a datetime object and then get it as
        # a timestamp
        _first_of_year_dt = get_first_day(_today_dt, 0, 1-_today_dt.month)
        _mn_first_of_year_dt = datetime.datetime.combine(_first_of_year_dt,
                                                         _mn_t)
        _mn_first_of_year_ts = time.mktime(_mn_first_of_year_dt.timetuple())

        _sql = "SELECT SUM(max), SUM(min), COUNT(*) FROM archive_day_outTemp "\
               "WHERE dateTime >= %(start)s AND dateTime < %(stop)s "\
               "ORDER BY dateTime"
        interpolate = {'start': _mn_first_of_month_ts,
                       'stop': _mn_stop_ts-1}
        _row = db_lookup().getSql(_sql % interpolate)
        if _row:
                _max_sum = _row[0]
                _min_sum = _row[1]
                _count = _row[2]
                _conv = weewx.units.convert(self.gdd_base_vt, t_type).value
                try:
                    _month_gdd = (_max_sum + _min_sum)/2 - _conv * _count
                    # now deal with the units
                    if t_type == self.temp_group:
                        # our input is in the same units as our output, so no
                        # conversion
                        _month_gdd = round(_month_gdd, 1)
                    elif self.temp_group == 'degree_C':
                        # our output is deg C but we have deg F so convert it
                        _month_gdd = round(_month_gdd * 1.8, 1)
                    else:
                        # our output is deg F but we have deg C so convert it
                        _month_gdd = round(_month_gdd * 5 / 9, 1)
                    if _month_gdd < 0.0:
                        _month_gdd = 0.0
                except (ValueError, TypeError):
                    _month_gdd = None
        else:
            _month_gdd = None

        _sql = "SELECT SUM(max), SUM(min), COUNT(*) FROM archive_day_outTemp "\
               "WHERE dateTime >= %(start)s AND dateTime < %(stop)s "\
               "ORDER BY dateTime"
        interpolate = {'start' : _mn_first_of_year_ts,
                       'stop'  : _mn_stop_ts-1}
        _row = db_lookup().getSql(_sql % interpolate)
        if _row:
            _t_max_sum = _row[0]
            _t_min_sum = _row[1]
            _count = _row[2]
            _conv = weewx.units.convert(self.gdd_base_vt, t_type).value
            try:
                _year_gdd = (_t_max_sum + _t_min_sum)/2 - _conv * _count
                # now deal with the units
                if t_type == self.temp_group:
                    # our input is in the same units as our output, so no
                    # conversion
                    _year_gdd = round(_year_gdd, 1)
                elif self.temp_group == 'degree_C':
                    # our output is deg C but we have deg F so convert it
                    _year_gdd = round(_year_gdd * 1.8, 1)
                else:
                    # our output is deg F but we have deg C so convert it
                    _year_gdd = round(_year_gdd * 5 / 9, 1)
                if _year_gdd < 0.0:
                    _year_gdd = 0.0
            except (ValueError, TypeError):
                _year_gdd = None
        else:
            _year_gdd = None

        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'month_gdd': _month_gdd,
                       'year_gdd': _year_gdd
                       }

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdGdDays SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                                class WdForToday
# ==============================================================================


class WdForToday(weewx.cheetahgenerator.SearchList):
    """SLE to return max and min temperature for this day."""

    def __init__(self, generator):
        # initialise our superclass
        super(WdForToday, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns max and min temp for this day as well as the year each
           occurred.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will hold the
                    start and stop times of the domain of valid times.

          db_lookup: This is a function that, given a data binding as its only
                     parameter, will return a database manager object.

        Returns:
            max_temp_today: Max temperature for this day of year from all
                            recorded data.
            max_temp_today_year: Year that max temperature for this day
                                 occurred.
            min_temp_today: Min temperature for this day of year from all
                            recorded data.
            min_temp_today_year: Year that min temperature for this day
                                 occurred.
        """

        t1 = time.time()

        # get units for use later with ValueHelpers
        # first, get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # get the unit in use for each group
        (t_type, t_group) = getStandardUnitType(current_rec['usUnits'],
                                                'outTemp')

        # get the dates/times we require for our queries
        # first, get timestamp for our first (earliest) record
        _first_good_ts = db_lookup().firstGoodStamp()
        # as a date object
        _first_good_d = datetime.date.fromtimestamp(_first_good_ts)
        # year of first (earliest) record
        _first_good_year = _first_good_d.year
        # get our stop time as a date object
        _stop_d = datetime.date.fromtimestamp(timespan.stop)
        # get our stop month and day
        _stop_month = _stop_d.month
        _stop_day = _stop_d.day
        # get a date object for todays day/month in the year of our first
        # (earliest) record
        _today_first_year_d = _stop_d.replace(year=_first_good_year)
        # Get a date object for the first occurrence of current day/month in
        # our recorded data. Need to handle Leap years differently
        # is it a leap year?
        if _stop_month != 2 or _stop_day != 29:
            # no, do we have day/month in this year or will we have to look
            # later
            if _today_first_year_d < _first_good_d:
                # no - jump to next year
                _today_first_year_d = _stop_d.replace(year=_first_good_year + 1)
        else:
            # Yes, so we need to find a leap year. Do we have 29 Feb in this
            # year of data? If not start by trying next year, if we do lets
            # try this year
            if _today_first_year_d < _first_good_d:
                _year = _first_good_d.year + 1
            else:
                _year = _first_good_d.year
            # check for a leap year and if not increment our year
            while not calendar.isleap(_year):
                _year += 1
            # get our date object with a leap year
            _today_first_year_d = _stop_d.replace(year=_year)

        # get our start and stop timestamps
        _start_ts = time.mktime(_today_first_year_d.timetuple())
        _stop_ts = timespan.stop
        # set our max/min and times
        _max = None
        _max_ts = None
        _min = None
        _min_ts = None

        # call our generator to step through the designated day/month each year
        for _ts in doygen(_start_ts, _stop_ts):
            _sql = "SELECT datetime, max, min FROM archive_day_outTemp "\
                   "WHERE dateTime >= %(start)s AND dateTime < %(stop)s"
            interpolate = {'start': _ts,
                           'stop':   _ts + 86399}
            # Execute our stats query. The answer is a ValueTuple in _row[0]
            _row = db_lookup().getSql(_sql % interpolate)
            if _row is not None:
                # update our max temp and timestamp if necessary
                if _row[1] is not None and (_max is None or (_max is not None and _row[1] > _max)):
                    _max = _row[1]
                    _max_ts = _row[0]
                # update our min temp and timestamp if necessary
                if _row[2] is not None and (_min is None or (_min is not None and _row[2] < _min)):
                    _min = _row[2]
                    _min_ts = _row[0]
        # get our max/min as ValueTuples
        _max_temp_today_vt = ValueTuple(_max, t_type, t_group)
        _min_temp_today_vt = ValueTuple(_min, t_type, t_group)
        # convert them to ValueHelpers
        _max_vh = ValueHelper(_max_temp_today_vt,
                              formatter=self.generator.formatter,
                              converter=self.generator.converter)
        _min_vh = ValueHelper(_min_temp_today_vt,
                              formatter=self.generator.formatter,
                              converter=self.generator.converter)
        # get our years of max/min, use try..except to catch any None values
        try:
            _max_year = datetime.date.fromtimestamp(_max_ts).timetuple()[0]
        except TypeError:
            _max_year = None
        try:
            _min_year = datetime.date.fromtimestamp(_min_ts).timetuple()[0]
        except TypeError:
            _min_year = None

        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'thisday': {'outTemp': {'max': _max_vh,
                                               'maxyear': _max_year,
                                               'min':  _min_vh,
                                               'minyear': _min_year}
                                   }
                       }

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdForToday SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                              class WdRainThisDay
# ==============================================================================


class WdRainThisDay(weewx.cheetahgenerator.SearchList):
    """SLE to return rain this time last month/year."""

    def __init__(self, generator):
        # initialise our superclass
        super(WdRainThisDay, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns rain to date for this time last month and this time
           last year.

           Defining 'this time last month/year' presents some challenges when
           the previous month has a different nubmer of days to the present
           month. In this SLE the following algorithm is used to come up with
           'this time last month/year':

           - If 'this date' last month or last year is invalid (eg 30 Feb) then
             last day of month concerned is used.
           - If it is the last day of this month (eg 30 Nov) then last day of
             previous month is used.

        Parameters:
          timespan: An instance of weeutil.weeutil.TimeSpan. This will
                    hold the start and stop times of the domain of
                    valid times.

          db_lookup: This is a function that, given a data binding
                     as its only parameter, will return a database manager
                     object.

        Returns:
          rain_this_time_last_month: Total month rainfall to date for this time last month
          rain_this_time_last_year: Total year rainfall to date for this time last year
        """

        t1 = time.time()

        # define a 'none ValueTuple'
        none_vt = (None, None, None)

        # get units for use later with ValueHelpers

        # get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # get the rain units
        (r_type, r_group) = getStandardUnitType(current_rec['usUnits'], 'rain')

        # get the dates/times we require for our queries
        # first, get timestamp for our first (earliest) record
        _first_good_ts = db_lookup().firstGoodStamp()
        # get midnight as a time object
        _mn_t = datetime.time(0)
        # get our stop time as a datetime object
        _stop_dt = datetime.datetime.fromtimestamp(timespan.stop)
        # get a datetime object for 1 month before our stop time
        _month_ago_dt = get_date_ago(_stop_dt, 1)
        # get date time object for midnight of that day
        _mn_month_ago_dt = datetime.datetime.combine(_month_ago_dt, _mn_t)
        # get timestamp for midnight of that day
        _mn_month_ago_td = _mn_month_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_month_ago_ts = _mn_month_ago_td.days * 86400 + _mn_month_ago_td.seconds
        # get datetime object for 1st of that month
        _first_month_ago_dt = get_first_day(_month_ago_dt)
        # get date time object for midnight on the 1st of that month
        _mn_first_month_ago_dt = datetime.datetime.combine(_first_month_ago_dt,
                                                           _mn_t)
        # get timestamp for midnight on the 1st of that month
        _mn_first_month_ago_td = _mn_first_month_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_first_month_ago_ts = _mn_first_month_ago_td.days * 86400 + _mn_first_month_ago_td.seconds
        # get a datetime object for 1 year before our stop time
        _year_ago_dt = get_date_ago(_stop_dt, 12)
        # get a datetime object for midnight of that day
        _mn_year_ago_dt = datetime.datetime.combine(_year_ago_dt, _mn_t)
        # get a timestamp for midnight of that day
        _mn_year_ago_td = _mn_year_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_year_ago_ts = _mn_year_ago_td.days * 86400 + _mn_year_ago_td.seconds
        # get datetime object for 1 Jan of that year
        _first_year_ago_dt = get_first_day(_year_ago_dt,
                                           0,
                                           1-_year_ago_dt.month)
        # get a datetime object for midnight of that day
        _mn_first_year_ago_dt = datetime.datetime.combine(_first_year_ago_dt,
                                                          _mn_t)
        # get a timestamp for midnight of that day
        _mn_first_year_ago_td = _mn_first_year_ago_dt - datetime.datetime.fromtimestamp(0)
        _mn_first_year_ago_ts = _mn_first_year_ago_td.days * 86400 + _mn_first_year_ago_td.seconds
        # get today's elapsed seconds
        today_s = _stop_dt.hour * 3600 + _stop_dt.minute * 60 + _stop_dt.second

        # Month ago queries. Month ago results are derived from 2 queries,
        # first a query on the rain daily summary to get the total rainfall
        # from 1st of previous month to midnight this day last month and
        # secondly a query on archive to get the total rain from midnight a
        # month ago to this time a month ago. 2 part query is used as it is
        # (mostly) substantially faster than a single query on archive.

        # get start/stop parameters for our 'month ago' query
        # start time for daily summary query is midnight on the 1st of previous
        # month
        _start_stats_ts = _mn_first_month_ago_ts
        # start time for our archive query is 1 second after midnight of this
        # day 1 month ago
        _start_archive_ts = _mn_month_ago_ts + 1
        # stop time for our daily summary query is 1 second before midnight on
        # the this day 1 month ago
        _stop_stats_ts = _mn_month_ago_ts - 1
        # stop time for our archive query is this time on this day 1 month ago
        _stop_archive_ts = _mn_month_ago_ts + today_s

        # do we have data for last month ?
        if _first_good_ts <= _stop_archive_ts:
            if _first_good_ts <= _stop_stats_ts:
                _sql = "SELECT SUM(sum) FROM archive_day_rain "\
                       "WHERE dateTime >= %(start)s AND dateTime < %(stop)s"
                interpolate = {'start': _start_stats_ts,
                               'stop':  _stop_stats_ts}
                # Execute our stats query. The answer is a ValueTuple in _row[0]
                _row = db_lookup().getSql(_sql % interpolate)
            else:
                _row = (None, )
            # is it midnight?
            if today_s != 0:
                # no, archive db query aggregate interval is the period from
                # midnight until this time less 1 second
                archive_agg = today_s - 1
                # execute our archive query, rain_vt is a ValueTuple with our
                # result
                tspan = TimeSpan(_start_archive_ts, _stop_archive_ts)
                (_vt1, _vt2, rain_vt) = db_lookup().getSqlVectors(tspan,
                                                                  'rain',
                                                                  'sum',
                                                                  archive_agg)
            else:
                rain_vt = ValueTuple([0, ], r_type, r_group)
        else:
            _row = (None,)
            rain_vt = ValueTuple([None, ], r_type, r_group)

        # Add our two query results being careful in case one or both is None.
        # Filter is slower than nested if..else but what's a few milliseconds
        # for the sake of neater code
        if rain_vt.value:
            _sum = rain_vt.value[0] if rain_vt.value[0] is not None else 0.0
            _sum += _row[0] if _row[0] is not None else 0.0
            # filtered = filter(None, [rain_vt.value[0], _row[0]])
            no_none = not (rain_vt.value[0] is None or _row[0] is None)
            month_rain_vt = ValueTuple(_sum, r_type, r_group) if no_none else none_vt
            # month_rain_vt = ValueTuple(sum(filtered), r_type, r_group) if no_none else none_vt
            month_rain_vh = ValueHelper(month_rain_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)
        else:
            month_rain_vh = ValueHelper(none_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)

        # Year ago queries. Year ago results are derived from 2 queries, first
        # a query on rain daily summary to get the total rainfall from 1st Jan
        # to midnight this day last year and secondly a query on archive to get
        # the total rain from midnight a year ago to this time a year ago.
        # 2 part query is used as it is (mostly) substantially faster than a
        # single query on archive.

        # get parameters for our 'year ago' queries
        # start time for daily summary query is midnight on the 1st of Jan the
        # previous year
        _start_stats_ts = _mn_first_year_ago_ts
        # start time for our archive query is 1 second after midnight of this
        # day 1 year ago
        _start_archive_ts = _mn_year_ago_ts + 1
        # stop time for our stats query is 1 second before midnight on the this
        # day 1 year ago
        _stop_stats_ts = _mn_year_ago_ts - 1
        # stop time for our archive query is this time on this day 1 year ago
        _stop_archive_ts = _mn_year_ago_ts + today_s

        # do we have data for last year ?
        if _first_good_ts <= _stop_archive_ts:
            if _first_good_ts <= _stop_stats_ts:
                _sql = "SELECT SUM(sum) FROM archive_day_rain "\
                       "WHERE dateTime >= %(start)s AND dateTime < %(stop)s"
                interpolate = {'start': _start_stats_ts,
                               'stop':  _stop_stats_ts}
                # Execute our stats query. The answer is a ValueTuple in _row[0]
                _row = db_lookup().getSql(_sql % interpolate)
            else:
                _row = (None, )
            # is it midnight
            if today_s != 0:
                # non, archive db query aggregate interval is the period from
                # midnight until this time less 1 second
                archive_agg = today_s - 1
                # execute our archive query, rain_vt is a ValueTuple with our
                # result
                tspan = TimeSpan(_start_archive_ts, _stop_archive_ts)
                (_vt1, _vt2, rain_vt) = db_lookup().getSqlVectors(tspan,
                                                                  'rain',
                                                                  'sum',
                                                                  archive_agg)
            else:
                rain_vt = ValueTuple([0, ], r_type, r_group)
        else:
            _row = (None,)
            rain_vt = ValueTuple([None, ], r_type, r_group)

        # Add our two query results being careful in case one or both is None.
        # Filter is slower than nested if..else but what's a few milliseconds
        # for the sake of neater code
        if rain_vt.value:
            _sum = rain_vt.value[0] if rain_vt.value[0] is not None else 0.0
            _sum += _row[0] if _row[0] is not None else 0.0
            # filtered = filter(None, [rain_vt.value[0], _row[0]])
            no_none = not (rain_vt.value[0] is None or _row[0] is None)
            year_rain_vt = ValueTuple(_sum, r_type, r_group) if no_none else none_vt
            # year_rain_vt = ValueTuple(sum(filtered), r_type, r_group) if no_none else none_vt
            year_rain_vh = ValueHelper(year_rain_vt,
                                       formatter=self.generator.formatter,
                                       converter=self.generator.converter)
        else:
            year_rain_vh = ValueHelper(none_vt,
                                       formatter=self.generator.formatter,
                                       converter=self.generator.converter)

        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'rainthisday': {'lastmonth': month_rain_vh,
                                       'lastyear': year_rain_vh}
                       }

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdRainThisDay SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                                class WdRainDays
# ==============================================================================


class WdRainDays(weewx.cheetahgenerator.SearchList):
    """SLE to return various longest rainy/dry period tags."""

    def __init__(self, generator):
        # initialise our superclass
        super(WdRainDays, self).__init__(generator)

    def get_extension_list(self, timespan, db_lookup):
        """Returns various tags related to longest periods of rainy/dry days.

            This SLE uses the stats database daily rainfall totals to
            determine the longest runs of consecutive dry or wet days over
            various periods (month, year, alltime). The SLE also determines the
            start date of each run.

            Period (xxx_days) tags are returned as integer numbers of days.
            Times (xx_time) tags are returned as dateTime ValueHelpers set to
            midnight (at start) of the first day of the run concerned. If the
            length of the run is 0 then the corresponding start time of the run
            is returned as None.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            month_con_dry_days:        Length of longest run of consecutive dry
                                       days in current month
            month_con_dry_days_time:   Start dateTime of longest run of
                                       consecutive dry days in current month
            month_con_wet_days:        Length of longest run of consecutive wet
                                       days in current month
            month_con_wet_days_time:   Start dateTime of longest run of
                                       consecutive wet days in current month
            year_con_dry_days:         Length of longest run of consecutive dry
                                       days in current year
            year_con_dry_days_time:    Start dateTime of longest run of
                                       consecutive dry days in current year
            year_con_wet_days:         Length of longest run of consecutive wet
                                       days in current year
            year_con_wet_days_time:    Start dateTime of longest run of
                                       consecutive wet days in current year
            alltime_con_dry_days:      Length of alltime longest run of
                                       consecutive dry days
            alltime_con_dry_days_time: Start dateTime of alltime longest run of
                                       consecutive dry days
            alltime_con_wet_days:      Length of alltime longest run of
                                       consecutive wet days
            alltime_con_wet_days_time: Start dateTime of alltime longest run of
                                       consecutive wet days
        """

        t1 = time.time()

        # get units for use later with ValueHelpers
        # first get current record from the archive
        if not self.generator.gen_ts:
            self.generator.gen_ts = db_lookup().lastGoodStamp()
        current_rec = db_lookup().getRecord(self.generator.gen_ts)
        # get our time unit
        (dt_type, dt_group) = getStandardUnitType(current_rec['usUnits'],
                                                  'dateTime')

        # get timestamps we need for the periods of interest
        # first, get time obj for midnight
        _mn_t = datetime.time(0)
        # get date obj for now
        _today_d = datetime.datetime.today()
        # get midnight 1st of the month as a datetime object and then get it as
        # a timestamp
        first_of_month_dt = get_first_day(_today_d)
        _mn_first_of_month_dt = datetime.datetime.combine(first_of_month_dt,
                                                          _mn_t)
        _mn_first_of_month_ts = time.mktime(_mn_first_of_month_dt.timetuple())
        # get midnight 1st of the year as a datetime object and then get it as
        # a timestamp
        _first_of_year_dt = get_first_day(_today_d, 0, 1-_today_d.month)
        _mn_first_of_year_dt = datetime.datetime.combine(_first_of_year_dt,
                                                         _mn_t)
        _mn_first_of_year_ts = time.mktime(_mn_first_of_year_dt.timetuple())

        # get vectors of our month stats
        _rain_vector = []
        _time_vector = []
        # Iterate over each day in our month timespan and get our daily rain
        # total and timestamp. This is a day_archive version of the archive
        # getSqlVectors method.
        for tspan in weeutil.weeutil.genDaySpans(_mn_first_of_month_ts, timespan.stop):
            _sql = "SELECT dateTime, sum FROM archive_day_rain "\
                   "WHERE dateTime >= %(start)s AND dateTime < %(stop)s "\
                   "ORDER BY dateTime"
            interpolate_dict = {'start': tspan.start,
                                'stop': tspan.stop}
            _row = db_lookup().getSql(_sql % interpolate_dict)
            if _row is not None:
                _time_vector.append(_row[0])
                _rain_vector.append(_row[1])
        # ss an aside lets get our number of rainy days this month
        _month_rainy_days = sum(1 for i in _rain_vector if i > 0)
        # get our run of month dry days
        # list to hold details of any runs we might find
        _interim = []
        # placeholder so we can track the start dateTime of any runs
        _index = 0
        # use itertools groupby method to make our search for a run easier
        # iterate over the groups itertools has found
        for k, g in itertools.groupby(_rain_vector):
            _length = len(list(g))
            # do we have a run of 0s (ie no rain)?
            if k == 0:
                # yes, add it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # we found one or more runs so get our result, we want the longest
            # run
            (_temp, _m_dry_run, _pos) = max(_interim,
                                            key=lambda a: a[1])
            # our 'time' is the day the run ends so we need to add on run-1
            # days
            _m_dry_time_ts = _time_vector[_pos] + (_m_dry_run - 1) * 86400
        else:
            # if we did not find a run then set our results accordingly
            _m_dry_run = 0
            _m_dry_time_ts = None

        # get our run of month rainy days
        # list to hold details of any runs we might find
        _interim = []
        # placeholder so we can track the start dateTime of any runs_index
        _index = 0
        # use itertools groupby method to make our search for a run easier
        # iterate over the groups itertools has found
        for k, g in itertools.groupby(_rain_vector, key=lambda r: 1 if r > 0 else 0):
            _length = len(list(g))
            # do we have a run of something > 0 (ie some rain)?
            if k > 0:
                # we do so add it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # we found one or more runs so get our result, we want the longest
            # run
            (_temp, _m_wet_run, _pos) = max(_interim, key=lambda a: a[1])
            # our 'time' is the day the run ends so we need to add on run-1
            # days
            _m_wet_time_ts = _time_vector[_pos] + (_m_wet_run - 1) * 86400
        else:
            # if we did not find a run then set our results accordingly
            _m_wet_run = 0
            _m_wet_time_ts = None

        # get our year stats vectors
        _rain_vector = []
        _time_vector = []
        for tspan in weeutil.weeutil.genDaySpans(_mn_first_of_year_ts,
                                                 timespan.stop):
            _sql = "SELECT dateTime, sum FROM archive_day_rain "\
                   "WHERE dateTime >= %(start)s AND dateTime < %(stop)s "\
                   "ORDER BY dateTime"
            interpolate_dict = {'start': tspan.start,
                                'stop': tspan.stop}
            _row = db_lookup().getSql(_sql % interpolate_dict)
            if _row is not None:
                _time_vector.append(_row[0])
                _rain_vector.append(_row[1])
        # get our run of year dry days
        # list to hold details of any runs we might find
        _interim = []
        # placeholder so we can track the start dateTime of any runs
        _index = 0
        # use itertools groupby method to make our search for a run easier
        # iterate over the groups itertools has found
        for k, g in itertools.groupby(_rain_vector):
            _length = len(list(g))
            # do we have a run of 0s (ie no rain)?
            if k == 0:
                # yes, add it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # we found one or more runs so get our result, we want the longest
            # run
            (_temp, _y_dry_run, _pos) = max(_interim, key=lambda a: a[1])
            # our 'time' is the day the run ends so we need to add on run-1
            # days
            _y_dry_time_ts = _time_vector[_pos] + (_y_dry_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _y_dry_run = 0
            _y_dry_time_ts = None

        # get our run of year rainy days
        # list to hold details of any runs we might find
        _interim = []
        # placeholder so we can track the start dateTime of any runs
        _index = 0
        # use itertools groupby method to make our search for a run easier
        # iterate over the groups itertools has found
        for k, g in itertools.groupby(_rain_vector, key=lambda r: 1 if r > 0 else 0):
            _length = len(list(g))
            # do we have a run of something > 0 (ie some rain)?
            if k > 0:
                # yes, add it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # we found one or more runs so get our result, we want the longest
            # run
            (_temp, _y_wet_run, _pos) = max(_interim, key=lambda a: a[1])
            # our 'time' is the day the run ends so we need to add on run-1
            # days
            _y_wet_time_ts = _time_vector[_pos] + (_y_wet_run - 1) * 86400
        else:
            # if we did not find a run then set our results accordingly
            _y_wet_run = 0
            _y_wet_time_ts = None

        # get our alltime stats vectors
        _rain_vector = []
        _time_vector = []
        for tspan in weeutil.weeutil.genDaySpans(timespan.start, timespan.stop):
            _sql = "SELECT dateTime, sum FROM archive_day_rain "\
                   "WHERE dateTime >= %(start)s AND dateTime < %(stop)s "\
                   "ORDER BY dateTime"
            interpolate_dict = {'start': tspan.start,
                                'stop': tspan.stop}
            _row = db_lookup().getSql(_sql % interpolate_dict)
            if _row is not None:
                _time_vector.append(_row[0])
                _rain_vector.append(_row[1])
        # get our run of alltime dry days
        # list to hold details of any runs we might find
        _interim = []
        # placeholder so we can track the start dateTime of any runs
        _index = 0
        # use itertools groupby method to make our search for a run easier
        # iterate over the groups itertools has found
        for k, g in itertools.groupby(_rain_vector):
            _length = len(list(g))
            # do we have a run of 0s (ie no rain)?
            if k == 0:
                # yes, add it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # we found one or more runs so get our result, we want the longest
            # run
            (_temp, _a_dry_run, _pos) = max(_interim, key=lambda a: a[1])
            # our 'time' is the day the run ends so we need to add on run-1
            # days
            _a_dry_time_ts = _time_vector[_pos] + (_a_dry_run - 1) * 86400
        else:
            # If we did not find a run then set our results accordingly
            _a_dry_run = 0
            _a_dry_time_ts = None

        # get our run of alltime rainy days
        # list to hold details of any runs we might find
        _interim = []
        # placeholder so we can track the start dateTime of any runs
        _index = 0
        # use itertools groupby method to make our search for a run easier
        # iterate over the groups itertools has found
        for k, g in itertools.groupby(_rain_vector, key=lambda r: 1 if r > 0 else 0):
            _length = len(list(g))
            # do we have a run of something > 0 (ie some rain)?
            if k > 0:
                # yes, add it to our list of runs
                _interim.append((k, _length, _index))
            _index += _length
        if _interim:
            # if we found a run (we want the longest one) then get our results
            (_temp, _a_wet_run, _pos) = max(_interim, key=lambda a: a[1])
            # our 'time' is the day the run ends so we need to add on run-1
            # days
            _a_wet_time_ts = _time_vector[_pos] + (_a_wet_run - 1) * 86400
        else:
            # if we did not find a run then set our results accordingly
            _a_wet_run = 0
            _a_wet_time_ts = None

        # make our timestamps ValueHelpers to give more flexibility in how we
        # can format them in our reports
        _month_dry_time_vt = (_m_dry_time_ts, dt_type, dt_group)
        _month_dry_time_vh = ValueHelper(_month_dry_time_vt,
                                         formatter=self.generator.formatter,
                                         converter=self.generator.converter)
        _month_wet_time_vt = (_m_wet_time_ts, dt_type, dt_group)
        _month_wet_time_vh = ValueHelper(_month_wet_time_vt,
                                         formatter=self.generator.formatter,
                                         converter=self.generator.converter)
        _year_dry_time_vt = (_y_dry_time_ts, dt_type, dt_group)
        _year_dry_time_vh = ValueHelper(_year_dry_time_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)
        _year_wet_time_vt = (_y_wet_time_ts, dt_type, dt_group)
        _year_wet_time_vh = ValueHelper(_year_wet_time_vt,
                                        formatter=self.generator.formatter,
                                        converter=self.generator.converter)
        _alltime_dry_time_vt = (_a_dry_time_ts, dt_type, dt_group)
        _alltime_dry_time_vh = ValueHelper(_alltime_dry_time_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)
        _alltime_wet_time_vt = (_a_wet_time_ts, dt_type, dt_group)
        _alltime_wet_time_vh = ValueHelper(_alltime_wet_time_vt,
                                           formatter=self.generator.formatter,
                                           converter=self.generator.converter)

        # create a small dictionary with the tag names (keys) we want to use
        search_list = {'month_con_dry_days': _m_dry_run,
                       'month_con_dry_days_time': _month_dry_time_vh,
                       'year_con_dry_days': _y_dry_run,
                       'year_con_dry_days_time': _year_dry_time_vh,
                       'alltime_con_dry_days': _a_dry_run,
                       'alltime_con_dry_days_time': _alltime_dry_time_vh,
                       'month_con_wet_days': _m_wet_run,
                       'month_con_wet_days_time': _month_wet_time_vh,
                       'year_con_wet_days': _y_wet_run,
                       'year_con_wet_days_time': _year_wet_time_vh,
                       'alltime_con_wet_days': _a_wet_run,
                       'alltime_con_wet_days_time': _alltime_wet_time_vh,
                       'month_rainy_days': _month_rainy_days}
        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdRainDays SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]


# ==============================================================================
#                            class WdManualAverages
# ==============================================================================


class WdManualAverages(weewx.cheetahgenerator.SearchList):
    """SLE for manually set month averages defined in weewx.conf [Weewx-WD]."""

    def __init__(self, generator):
        # initialise our superclass
        super(WdManualAverages, self).__init__(generator)

        # dict to convert [[[Xxxxx]]] to WeeWX observation groups, if you add
        # more [[[Xxxxx]]] under [[Averages]] you must add additional entries in
        # this dict
        self.average_groups = {'Rainfall': 'group_rain',
                               'Temperature': 'group_temperature'}
        # dict to convert [[[Xxxxx]]] to labels for tags, if you add more
        # [[[Xxxxx]]] under [[Averages]] you must add additional entries in this
        # dict
        self.average_abb = {'Rainfall': 'rain',
                            'Temperature': 'temp'}
        # dict to convert units used for manual averages to WeeWX unit types,
        # if you add more [[[Xxxxx]]] under [[Averages]] you need to add any new
        # units to this dict
        self.units_dict = {'mm': 'mm', 'cm': 'cm', 'in': 'inch',
                           'inch': 'inch', 'c': 'degree_C', 'f': 'degree_F'}
        # list of setting names we expect under each [[[Xxxxxx]]]
        self.months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    def get_vh(self, string, group):
        """Create ValueHelper from a manual average entry and observation group.

        Unit labeled datum string is a number followed by one or more spaces
        followed by a unit label as defined in the keys in self.units_dict.
        ValueHelper datum and units are set to None if:
        - unit label is not a key in self.units_dict
        - either datum or units label cannot be extracted from string
        - string is None

        Parameters:
            string: unit labeled quanta string eg '24.6 mm' or '56 F'
            group: WeeWX observation group to be used

        Returns:
            ValueHelper derived from quanta, units and observation group
        """

        # do we have a string to work on?
        if string is not None:
            # yes, then split on the space
            elements = string.lower().split()
            # do we have 2 elements from the split
            if len(elements) == 2:
                # yes, then start processing
                value = float(elements[0])
                units = elements[1]
                # do we recognise the units used?
                if units in self.units_dict:
                    # yes, then create a ValueTuple
                    entry_vt = ValueTuple(value, self.units_dict[units], group)
                else:
                    # no, create ValueTuple but with None for value and units
                    entry_vt = ValueTuple(None, None, group)
            else:
                # no, all we can do is create ValueTuple but with None for
                # value and units
                entry_vt = ValueTuple(None, None, group)
        else:
            # no string, all we can do create ValueTuple but with None for
            # value and units
            entry_vt = ValueTuple(None, None, group)
        # return a ValueHelper from our ValueTuple
        return ValueHelper(entry_vt)

    def get_extension_list(self, timespan, db_lookup):
        """Create a search list with manually set month averages.

        Looks for a [Weewx-WD][[Averages]] section in weewx.conf. If found
        looks for user settable month averages under [[[Xxxxx]]]
        eg [[[Rainfall]]] or [[[Temperature]]]. Under each [[[Xxxxx]]] there
        must be 12 settings (Jan =, Feb = ... Dec =). Each setting consists of
        a number followed by a unit label eg 12 mm or 34.3 C. Note unit labels
        are not a Weewx unit type. Provided the 12 month settings exists the
        value are returned as ValueHelpers to allow unit conversion/formatting.
        If one or more month setting is invalid or missing the 'exists' flag
        (eg temp_man_avg_exists) is set to False indicating that there is not a
        valid, complete suite of average settings for that group. Additinal
        [[[Xxxxx]]] average groups can be catered for by adding to the
        self.average_groups, self.average_abb and self.units_dict dicts as
        required.

        Parameters:
            timespan: An instance of weeutil.weeutil.TimeSpan. This will hold
                      the start and stop times of the domain of valid times.

            db_lookup: This is a function that, given a data binding as its
                       only parameter, will return a database manager object.

        Returns:
            mmm_xxxx_man_avg: ValueHelper manual average setting for month mmm
                              (eg jan_rain_man_avg). xxxx is the looked up
                              values in the self.average_abb dict.

            xxxx_man_avg_exists: Flag (eg rain_man_avg_exists) set to False if
                                 a complete manual average group (12 months) is
                                 not available for xxxx. Flag is set true if
                                 entire 12 months of averages are available.
        """

        t1 = time.time()

        # clear our search list
        search_list = {}
        # get Weewx-WD config dict
        weewxwd_config = self.generator.config_dict.get('Weewx-WD', {})
        # do we have any manual month averages?
        if 'Averages' in weewxwd_config:
            # yes, get our dict
            man_avg_dict = weewxwd_config.get('Averages', {})
            # step through each of the average groups we might encounter
            for average_group in self.average_groups:
                # if we find an average group
                if average_group in man_avg_dict:
                    # get our settings
                    group_dict = man_avg_dict[average_group]
                    # initialise our 'exists' flag assuming we have settings
                    # for all 12 months
                    all_months = True
                    # iterate over the 12 months
                    for avg_month in self.months:
                        if avg_month in group_dict:
                            # we found a setting so get it as a ValueHelper
                            entry_vh = self.get_vh(group_dict[avg_month].strip(),
                                                   self.average_groups[average_group])
                        else:
                            # no setting for the month concerned so get a
                            # ValueHelper with None
                            entry_vh = self.get_vh(None,
                                                   self.average_groups[average_group])
                        # add the ValueHelper to our search list
                        _key = '%s_%s_man_avg' % (avg_month,
                                                  self.average_abb[average_group])
                        search_list[_key.lower()] = entry_vh
                        # update our 'exists' flag
                        all_months &= entry_vh.has_data()
                    # add our 'exists' flag to the search list
                    _key = '%s_man_avg_exists' % (average_group, )
                    search_list[_key.lower()] = all_months
                else:
                    # no average group for this one so set our 'exists' flag
                    # False and add it to the search list
                    _key = '%s_man_avg_exists' % (average_group, )
                    search_list[_key.lower()] = False
        else:
            # no, so set our 'exists' to False for each of our expected average
            # groups
            for average_group in self.average_groups:
                _key = '%s_man_avg_exists' % (average_group, )
                search_list[_key.lower()] = False

        t2 = time.time()
        if weewx.debug >= 2:
            logdbg("WdManualAverages SLE executed in %0.3f seconds" % (t2-t1))

        return [search_list]