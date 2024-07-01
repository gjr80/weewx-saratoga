"""
wstaggedstats.py

Specialised timespan stats for WeeWX-Saratoga

Copyright (C) 2021-2024 Gary Roderick                gjroderick<at>gmail.com

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
        - fix bug when calculating one hour of one minute sums when there is
          less than one hour of data in the archive
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
"""

# python imports
import datetime
import time

# WeeWX imports
import weewx
import weewx.units
import weeutil.weeutil

WS_TAGGED_STATS_VERSION = '0.1.10'


# ==============================================================================
#                              Class WsTimeBinder
# ==============================================================================

class WsTimeBinder(object):
    """WeeWX-Saratoga TimeBinder.

        This class allows custom tagged stats drawn from the archive database
        in support of the WeeWX-Saratoga templates. This class along with the
        associated WDTimeSpanStats and WDStatsTypeHelper classes support the
        following custom tagged stats:

        -   $weekdaily.xxxxxx.zzzzzz - week of stats aggregated by day
        -   $monthdaily.xxxxxx.zzzzzz - month of stats aggregated by day
        -   $yearmonthy.xxxxxx.zzzzzz - year of stats aggregated by month

        where xxxxxx is a WeeWX observation eg outTemp, wind (stats database),
        windSpeed (archive database) etc recorded in the relevant database.
        Note that WDATaggedStats uses the archive database and WDTaggedStats
        uses the stats database.

        where zzzzzz is either:
        -   maxQuery - returns maximums/highs over the aggregate period
        -   minQuery - returns minimums/lows over the aggregate period
        -   avgQuery - returns averages over the aggregate period
        -   sumQuery - returns sum over the aggregate period
        -   vecdirQuery - returns vector direction over the aggregate period

        In the WeeWX-Saratoga templates these tagged stats
        (eg $hour.outTemp.maxQuery) result in a list which is assigned to a
        variable and then each item in the list is reference using its
        index eg variable_name[0]

        This class sits on the top of chain of helper classes that enable
        syntax such as $hour.rain.sumQuery in the templates.

        When a time period is given as an attribute to it, such as obj.hour,
        the next item in the chain is returned, in this case an instance of
        WDTimeSpanStats, which binds the database with the time period.
    """

    def __init__(self, db_lookup, report_time,
                 formatter=weewx.units.Formatter(),
                 converter=weewx.units.Converter(),
                 **option_dict):
        """Initialize an instance of WsTimeBinder.

        db_lookup: A function with call signature db_lookup(data_binding),
                   which returns a database manager and where data_binding is
                   an optional binding name. If not given, then a default
                   binding will be used.

        report_time: The time for which the report should be run.

        formatter: An instance of weewx.units.Formatter() holding the
                   formatting information to be used. [Optional. If not given,
                   the default Formatter will be used.]

        converter: An instance of weewx.units.Converter() holding the target
                   unit information to be used. [Optional. If not given, the
                   default Converter will be used.]

        option_dict: Other options which can be used to customize calculations.
                     [Optional.]
        """
        self.db_lookup = db_lookup
        self.report_time = report_time
        self.formatter = formatter
        self.converter = converter
        self.option_dict = option_dict

    # what follows is the list of time period attributes
    @property
    def weekdaily(self, data_binding=None):
        return WsTimespanBinder((self.report_time - 518400, self.report_time),
                                weeutil.weeutil.genDaySpans, self.db_lookup,
                                data_binding, 'weekdaily',
                                self.formatter, self.converter, **self.option_dict)

    @property
    def monthdaily(self, data_binding=None):
        return WsTimespanBinder((self.report_time - 2678400, self.report_time),
                                weeutil.weeutil.genDaySpans, self.db_lookup,
                                data_binding, 'monthdaily',
                                self.formatter, self.converter, **self.option_dict)

    @property
    def yearmonthly(self, data_binding=None):
        _now_dt = datetime.datetime.fromtimestamp(self.report_time)
        _start_dt = datetime.date(day=1, month=_now_dt.month, year=_now_dt.year-1)
        _start_ts = time.mktime(_start_dt.timetuple())
        return WsTimespanBinder((_start_ts, self.report_time), weeutil.weeutil.genMonthSpans,
                                self.db_lookup, data_binding, 'yearmonthly',
                                self.formatter, self.converter, **self.option_dict)


# ==============================================================================
#                            Class WsTimespanBinder
# ==============================================================================

class WsTimespanBinder(object):
    """Nearly stateless class that holds a binding to a stats database and a timespan.

    This class is the next class in the chain of helper classes.

    When a statistical type is given as an attribute to it (such as 'obj.outTemp'),
    the next item in the chain is returned, in this case an instance of
    WDStatsTypeHelper, which binds the stats database, the time period, and
    the statistical type all together.

    """
    def __init__(self, timespan, genspans, db_lookup, data_binding=None,
                 context='current', formatter=weewx.units.Formatter(),
                 converter=weewx.units.Converter(), **option_dict):
        """Initialize an instance of WsTimespanBinder.

        timespan: An instance of weeutil.Timespan with the time span
        over which the statistics are to be calculated.

        db: The database the stats are to be extracted from.

        context: A tag name for the timespan. This is something like
        'monthdaily', 'weekdaily', or 'yearmonthly', etc. This is used to find
        an appropriate label, if necessary.

        formatter: An instance of weewx.units.Formatter() holding the formatting
        information to be used. [Optional. If not given, the default
        Formatter will be used.]

        converter: An instance of weewx.units.Converter() holding the target unit
        information to be used. [Optional. If not given, the default
        Converter will be used.]

        option_dict: Other options which can be used to customize calculations.
        [Optional.]
        """

        self.timespan = timespan
        self.db_lookup = db_lookup
        self.data_binding = data_binding
        self.genspans = genspans
        self.context = context
        self.formatter = formatter
        self.converter = converter
        self.option_dict = option_dict

    def __getattr__(self, obs_type):
        """Return a helper object that binds the stats database, a time period,
        and the given statistical type.

        obs_type: An observation type, such as 'outTemp', or 'outHumidity'

        returns: An instance of class WsObservationBinder.
        """

        # The following is so the Python version of Cheetah's NameMapper doesn't think
        # I'm a dictionary:
        if obs_type == 'has_key':
            raise AttributeError

        # Return the helper class, bound to the type:
        return WsObservationBinder(obs_type, self.timespan, self.db_lookup,
                                   self.data_binding, self.context,
                                   self.genspans, self.formatter,
                                   self.converter, **self.option_dict)


# ==============================================================================
#                           Class WsObservationBinder
# ==============================================================================

class WsObservationBinder(object):
    """This is the final class in the chain of helper classes. It binds the
    statistical database, a time period, and a statistical type all together.

    When an aggregation type (eg, 'maxQuery') is given as an attribute to it,
    it runs the query against the database, assembles the result, and returns
    it as a list of ValueHelpers. For example 'maxQuery' will return a list of
    ValueHelpers each with the 'max' value of the observation over the
    aggregation period.

    Whilst the aggregation types are similar to those in the StatsTypeHelper
    class since we are seeking a list of aggregates over a number of periods
    the aggregate types are 'maxQuery', 'minQuery' etc to distinguish them
    from the standard 'max, 'min' etc aggregates.
    """

    def __init__(self, obs_type, timespan, db_lookup, data_binding, context,
                 genspans, formatter=weewx.units.Formatter(),
                 converter=weewx.units.Converter(), **option_dict):
        """ Initialize an instance of WsObservationBinder

        obs_type: A string with the stats type (e.g., 'outTemp') for which the
        query is to be done.

        timespan: An instance of TimeSpan holding the time period over which
        the query is to be run

        db: The database the stats are to be extracted from.

        context: A tag name for the timespan. This is something like 'current',
        'day', 'week', etc. This is used to find an appropriate label, if
        necessary.

        formatter: An instance of weewx.units.Formatter() holding the formatting
        information to be used. [Optional. If not given, the default
        Formatter will be used.]

        converter: An instance of weewx.units.Converter() holding the target
        unit information to be used. [Optional. If not given, the default
        Converter will be used.]

        option_dict: Other options which can be used to customize calculations.
        [Optional.]
        """

        self.obs_type = obs_type
        self.timespan = timespan
        self.db_lookup = db_lookup
        self.data_binding = data_binding
        self.context = context
        self.genspans = genspans
        self.formatter = formatter
        self.converter = converter
        self.option_dict = option_dict

    def maxQuery(self):
        final = []
        for tspan in self.genspans(self.timespan[0], self.timespan[1]):
            result = self.db_lookup().getAggregate(tspan, self.obs_type, 'max')
            final.append(weewx.units.ValueHelper(result, self.context, self.formatter, self.converter))
        return final

    def minQuery(self):
        final = []
        for tspan in self.genspans(self.timespan[0], self.timespan[1]):
            result = self.db_lookup().getAggregate(tspan, self.obs_type, 'min')
            final.append(weewx.units.ValueHelper(result, self.context, self.formatter, self.converter))
        return final

    def avgQuery(self):
        final = []
        for tspan in self.genspans(self.timespan[0], self.timespan[1]):
            result = self.db_lookup().getAggregate(tspan, self.obs_type, 'avg')
            final.append(weewx.units.ValueHelper(result, self.context, self.formatter, self.converter))
        return final

    def sumQuery(self):
        final = []
        for tspan in self.genspans(self.timespan[0], self.timespan[1]):
            result = self.db_lookup().getAggregate(tspan, self.obs_type, 'sum')
            final.append(weewx.units.ValueHelper(result, self.context, self.formatter, self.converter))
        return final

    def vecdirQuery(self):
        final = []
        for tspan in self.genspans(self.timespan[0], self.timespan[1]):
            result = self.db_lookup().getAggregate(tspan, self.obs_type, 'vecdir')
            final.append(weewx.units.ValueHelper(result, self.context, self.formatter, self.converter))
        return final

    def __getattr__(self, aggregate_type):
        """Return statistical summary using a given aggregate_type.

        aggregate_type: The type of aggregation over which the summary is to be
        done. This is normally something like 'sum', 'min', 'mintime', 'count',
        etc. However, there are two special aggregation types that can be used
        to determine the existence of data:
          'exists':   Return True if the observation type exists in the database.
          'has_data': Return True if the type exists and there is a non-zero
                      number of entries over the aggregation period.

        returns: For special types 'exists' and 'has_data', returns a Boolean
        value. Otherwise, a ValueHelper containing the aggregation data.
        """

        return self._do_query(aggregate_type)

    @property
    def exists(self):
        return self.db_lookup(self.data_binding).exists(self.obs_type)

    @property
    def has_data(self):
        return self.db_lookup(self.data_binding).has_data(self.obs_type,
                                                          self.timespan)

    def _do_query(self, aggregate_type, val=None):
        """Run a query against the databases, using the given aggregation type."""
        db_manager = self.db_lookup(self.data_binding)
        result = db_manager.getAggregate(self.timespan, self.obs_type,
                                         aggregate_type, val=val,
                                         **self.option_dict)
        # Wrap the result in a ValueHelper:
        return weewx.units.ValueHelper(result, self.context,
                                       self.formatter, self.converter)


# ==============================================================================
#                           Class WsArchiveTimeBinder
# ==============================================================================

class WsArchiveTimeBinder(object):
    """WeeWX-Saratoga archive based TimeBinder.

        This class allows custom tagged stats drawn from the archive database
        in support of the WeeWX-Saratoga templates. This class along with the
        associated WsArchiveTimespanBinder and WsArchiveObservationBinder
        classes support the following custom tagged stats:

        -   $minute.xxxxxx.zzzzzz - hour of stats aggregated by minute
        -   $fifteenminute.xxxxxx.zzzzzz - day of stats aggregated by 15 minutes
        -   $hour.xxxxxx.zzzzzz - day of stats aggregated by hour
        -   $sixhour.xxxxxx.zzzzzz - week of stats aggregated by 6 hours

        where xxxxxx is a WeeWX observation eg outTemp, wind (stats database),
        windSpeed (archive database) etc recorded in the relevant database.
        Note that WDATaggedStats uses the archive database and WDTaggedStats
        uses the stats database.

        where zzzzzz is either:
        -   maxQuery - returns maximums/highs over the aggregate period
        -   minQuery - returns minimums/lows over the aggregate period
        -   avgQuery - returns averages over the aggregate period
        -   sumQuery - returns sum over the aggregate period
        -   datetimeQuery - returns datetime over the aggregate period

        In the WeeWX-Saratoga templates these tagged stats
        (eg $hour.outTemp.maxQuery) result in a list which is assigned to a
        variable and then each item in the list is reference using its index
        eg variable_name[0]

        This class sits on the top of chain of helper classes that enable
        syntax such as $hour.rain.sumQuery in the templates.

        When a time period is given as an attribute to it, such as obj.hour,
        the next item in the chain is returned, in this case an instance of
        WsArchiveTimespanBinder, which binds the database with the time period.
    """

    def __init__(self, db_lookup, report_time,
                 formatter=weewx.units.Formatter(),
                 converter=weewx.units.Converter(),
                 **option_dict):
        """Initialize an instance of TaggedStats.

        db: The database the stats are to be extracted from.

        report_time: The time the stats are to be current to.

        formatter: An instance of weewx.units.Formatter() holding the
                   formatting information to be used. [Optional. If not given,
                   the default Formatter will be used.]

        converter: An instance of weewx.units.Converter() holding the target
                   unit information to be used. [Optional. If not given, the
                   default Converter will be used.]

        option_dict: Other options which can be used to customize calculations.
                     [Optional.]
        """

        self.db_lookup = db_lookup
        self.report_time = report_time
        self.formatter = formatter
        self.converter = converter
        self.option_dict = option_dict

    # what follows is the list of time period attributes
    @property
    def minute(self, data_binding=None):
        return WsArchiveTimespanBinder((self.report_time - 3600, self.report_time),
                                       60, self.db_lookup, data_binding,
                                       'minute', self.formatter, self.converter,
                                       **self.option_dict)

    @property
    def fifteenminute(self, data_binding=None):
        return WsArchiveTimespanBinder((self.report_time - 86400, self.report_time),
                                       900, self.db_lookup, data_binding,
                                       'fifteenminute', self.formatter,
                                       self.converter, **self.option_dict)

    @property
    def onehour(self, data_binding=None):
        return WsArchiveTimespanBinder((self.report_time - 86400, self.report_time),
                                       3600, self.db_lookup, data_binding,
                                       'hour', self.formatter, self.converter,
                                       **self.option_dict)

    @property
    def sixhour(self, data_binding=None):
        return WsArchiveTimespanBinder((self.report_time - 604800, self.report_time),
                                       21600, self.db_lookup, data_binding,
                                       'sixhour', self.formatter,
                                       self.converter, **self.option_dict)


# ==============================================================================
#                         Class WsArchiveTimespanBinder
# ==============================================================================

class WsArchiveTimespanBinder(object):
    """WeeWX-Saratoga Archive based TimespanBinder.

        Nearly stateless class that holds a binding to a stats database and a
        timespan.

        This class is the next class in the chain of helper classes.

        When a statistical type is given as an attribute to it
        (such as 'obj.outTemp'), the next item in the chain is returned, in
        this case an instance of StatsTypeHelper, which binds the stats
        database, the time period, and the statistical type all together.

        It also includes a few "special attributes" that allow iteration over
        certain time periods. Example:

        # Iterate by month:
        for monthStats in yearStats.months:
            # Print maximum temperature for each month in the year:
            print monthStats.outTemp.max
    """
    def __init__(self, timespan, agg_intvl, db_lookup, data_binding=None,
                 context='hour', formatter=weewx.units.Formatter(),
                 converter=weewx.units.Converter(), **option_dict):
        """Initialize an instance of WsArchiveTimespanBinder.

            timespan: An instance of weeutil.Timespan with the time span
                      over which the statistics are to be calculated.

            db: The database the stats are to be extracted from.

            context: A tag name for the timespan. This is something like
                     'minute', 'hour', 'fifteenminute', etc. This is used to
                     find an appropriate label, if necessary.

            formatter: An instance of weewx.units.Formatter() holding the
                       formatting information to be used. [Optional. If not
                       given, the default Formatter will be used.]

            converter: An instance of weewx.units.Converter() holding the
                       target unit information to be used. [Optional. If not
                       given, the default Converter will be used.]

            option_dict: Other options which can be used to customize
                         calculations. [Optional.]
        """

        self.timespan = timespan
        self.agg_intvl = agg_intvl
        self.db_lookup = db_lookup
        self.data_binding = data_binding
        self.context = context
        self.formatter = formatter
        self.converter = converter
        self.option_dict = option_dict

    def __getattr__(self, obs_type):
        """Return a helper object that binds the database, a time period,
        and the given statistical type.

        obs_type: A observation type, such as 'outTemp', or 'outHumidity'

        returns: An instance of class WsArchiveObservationBinder."""

        # the following is so the Python version of Cheetah's NameMapper
        # doesn't think I'm a dictionary
        if obs_type == 'has_key':
            raise AttributeError

        # return the helper class, bound to the type
        return WsArchiveObservationBinder(obs_type, self.timespan,
                                          self.agg_intvl, self.db_lookup,
                                          self.data_binding, self.context,
                                          self.formatter, self.converter,
                                          **self.option_dict)


# ==============================================================================
#                        Class WsArchiveObservationBinder
# ==============================================================================

class WsArchiveObservationBinder(object):
    """WeeWx-Saratoga Archive based ObservationBinder.

        This is the final class in the chain of helper classes. It binds the
        statistical database, a time period, and a statistical type all
        together.

        When an aggregation type (eg, 'maxQuery') is given as an attribute to
        it, it runs the query against the database, assembles the result, and
        returns it as a list of ValueHelpers. For example 'maxQuery' will
        return a list of ValueHelpers each with the 'max' value of the
        observation over the aggregation period.

        Whilst the aggregation types are similar to those in the
        WsArchiveObservationBinder class since we are seeking a list of
        aggregates over a number of periods the aggregate types are 'maxQuery',
        'minQuery' etc to distinguish them from the standard 'max, 'min' etc
        aggregates.
    """

    def __init__(self, obs_type, timespan, agg_intvl, db_lookup, data_binding,
                 context, formatter=weewx.units.Formatter(),
                 converter=weewx.units.Converter(), **option_dict):
        """ Initialize an instance of WsArchiveObservationBinder.

            In cases where the aggregate interval is greater than the archive
            interval it is not possible to calculate accurate stats over the
            timespan concerned due to the lack of granularity in the underlying
            archive data. In these cases the results of the query are padded
            with additional extrapolated data points.

            obs_type: A string with the stats type (e.g., 'outTemp') for which
                      the query is to be done.

            timespan: An instance of TimeSpan holding the time period over
                      which the query is to be run

            db: The database the stats are to be extracted from.

            context: A tag name for the timespan. This is something like
                     'hour', 'fifteenminute', 'sixhour', etc. This is used to
                     find an appropriate label, if necessary.

            formatter: An instance of weewx.units.Formatter() holding the
                       formatting information to be used. [Optional. If not
                       given, the default Formatter will be used.]

            converter: An instance of weewx.units.Converter() holding the
                       target unit information to be used. [Optional. If not
                       given, the default Converter will be used.]

            option_dict: Other options which can be used to customize
                         calculations. [Optional.]
        """

        self.obs_type = obs_type         # stat we are after eg 'outTemp', 'rain' etc
        self.timespan = timespan         # tuple of (start_ts, stop_ts)
        self.agg_intvl = agg_intvl       # aggregate interval in seconds
        self.db_lookup = db_lookup       # what db we are using
        self.data_binding = data_binding
        self.context = context           # context ?
        self.formatter = formatter       # our formatter
        self.converter = converter       # our converter
        self.option_dict = option_dict   # not used?
        db_manager = self.db_lookup()
        _current_rec = db_manager.getRecord(timespan[1])  # our current record
        self.interval = _current_rec['interval']*60       # our record interval in seconds

    def maxQuery(self):
        final = []
        if self.interval <= self.agg_intvl or self.context != 'minute':
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0], self.timespan[1])
            (start_vt, stop_vt, res_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                         self.obs_type,
                                                                         'max',
                                                                         self.agg_intvl)
            for elm in res_vt.value:
                final.append(weewx.units.ValueHelper((elm, res_vt.unit, res_vt.group),
                                                     self.context,
                                                     self.formatter,
                                                     self.converter))
        else:
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0]-self.interval, self.timespan[1])
            (start_vt, stop_vt, res_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                         self.obs_type,
                                                                         'max',
                                                                         self.agg_intvl)
            vc = 1
            for i in range(60):
                try:
                    curr_vec_ts = stop_vt.value[vc]
                    min_time = int((self.timespan.start + 60) + i * 60)
                    if min_time < curr_vec_ts:
                        try:
                            res = (res_vt.value[vc] - (curr_vec_ts - min_time) /
                                   float(self.interval) * (res_vt.value[vc] - res_vt.value[vc-1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, res_vt.unit, res_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                    elif min_time == curr_vec_ts:
                        final.append(weewx.units.ValueHelper((res_vt.value[vc], res_vt.unit, res_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                        vc += 1
                    else:
                        vc += 1
                        try:
                            res = (res_vt.value[vc] + (min_time - curr_vec_ts) /
                                   float(self.interval) * (res_vt.value[vc] - res_vt.value[vc-1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, res_vt.unit, res_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                except:
                    final.append(weewx.units.ValueHelper((0, res_vt.unit, res_vt.group),
                                                         'minute',
                                                         self.formatter,
                                                         self.converter))
        return final

    def minQuery(self):

        final = []
        if self.interval <= self.agg_intvl or self.context != 'minute':
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0], self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'min',
                                                                            self.agg_intvl)
            for elm in result_vt.value:
                final.append(weewx.units.ValueHelper((elm, result_vt.unit, result_vt.group),
                                                     self.context,
                                                     self.formatter,
                                                     self.converter))
        else:
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0] - self.interval, self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'min',
                                                                            self.agg_intvl)
            vc = 1
            for i in range(60):
                try:
                    curr_vector_ts = stop_vt.value[vc]
                    min_time = int((self.timespan[0] + 60) + i * 60)
                    if min_time < curr_vector_ts:
                        try:
                            res = (result_vt.value[vc] - (curr_vector_ts - min_time) /
                                   float(self.interval) * (result_vt.value[vc] - result_vt.value[vc - 1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                    elif min_time == curr_vector_ts:
                        final.append(weewx.units.ValueHelper((result_vt.value[vc], result_vt.unit, result_vt.group),
                                                             'minute', self.formatter, self.converter))
                        vc += 1
                    else:
                        vc += 1
                        try:
                            res = (result_vt.value[vc] + (min_time - curr_vector_ts) /
                                   float(self.interval) * (result_vt.value[vc] - result_vt.value[vc - 1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                except:
                    final.append(weewx.units.ValueHelper((0, result_vt.unit, result_vt.group),
                                                         'minute',
                                                         self.formatter,
                                                         self.converter))
        return final

    def avgQuery(self):
        final = []
        if self.interval <= self.agg_intvl or self.context != 'minute':
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0], self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'avg',
                                                                            self.agg_intvl)
            for elm in result_vt.value:
                final.append(weewx.units.ValueHelper((elm, result_vt.unit, result_vt.group), self.context,
                                                     self.formatter, self.converter))
        else:
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0] - self.interval, self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'avg',
                                                                            self.agg_intvl)
            vc = 1
            for i in range(60):
                try:
                    curr_vector_ts = stop_vt.value[vc]
                    min_time = int((self.timespan[0] + 60) + i * 60)
                    if min_time < curr_vector_ts:
                        try:
                            res = (result_vt.value[vc] - (curr_vector_ts - min_time) /
                                   float(self.interval) * (result_vt.value[vc] - result_vt.value[vc - 1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                    elif min_time == curr_vector_ts:
                        final.append(weewx.units.ValueHelper((result_vt.value[vc], result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                        vc += 1
                    else:
                        vc += 1
                        try:
                            res = (result_vt.value[vc] + (min_time - curr_vector_ts) /
                                   float(self.interval) * (result_vt.value[vc] - result_vt.value[vc - 1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                except:
                    final.append(weewx.units.ValueHelper((0, result_vt.unit, result_vt.group),
                                                         'minute',
                                                         self.formatter,
                                                         self.converter))
        return final

    def sumQuery(self):
        # set our result container
        final = []
        # if our record interval is less than the aggregate interval or if we
        # are using something other than a 'minute' query then it is very
        # easy - just do the aggregate query
        if self.interval <= self.agg_intvl or self.context != 'minute':
            # get our results
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0], self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'sum',
                                                                            self.agg_intvl)
            # step through each element and add to our result as a ValueHelper
            for elm in result_vt.value:
                final.append(weewx.units.ValueHelper((elm, result_vt.unit, result_vt.group),
                                                     self.context,
                                                     self.formatter,
                                                     self.converter))
        else:
            # otherwise it takes a bit more effort! Get our vector of data over
            # the timespan concerned
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0]-self.interval, self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'sum',
                                                                            self.agg_intvl)
            vec_counter = 1  # counter points to the result vector element we are working with
            prop = 60.0 / self.interval  # factor to scale vector elements
            # step through our 60 minute period minute by minute
            for i in range(60):
                try:
                    # get ts for our current vector
                    curr_vector_ts = stop_vt.value[vec_counter]
                    # get ts for our current 'minute'
                    min_time = int((self.timespan[0] + 60) + i * 60)
                    if min_time < curr_vector_ts:
                        # if our 'minute' ts is earlier than our current vector
                        # element we need to extrapolate
                        try:
                            res = result_vt.value[vec_counter] * prop
                        except (IndexError, ValueError):
                            res = 0
                        # add our extrapolated result as a ValueHelper
                        final.append(weewx.units.ValueHelper((res, result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                    elif min_time == curr_vector_ts:
                        # if 'minute' ts is the same as that of our current
                        # vector element we need to extrapolate and advance
                        try:
                            res = result_vt.value[vec_counter] * prop
                            # add our extrapolated result as a ValueHelper
                        except (IndexError, ValueError, TypeError):
                            res = 0
                        # add our extrapolated result as a ValueHelper
                        final.append(weewx.units.ValueHelper((res, result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                        # and we also need to move to the next vector
                        vec_counter += 1
                    else:
                        # otherwise our 'minute' ts is later than our current
                        # vector element we need to extrapolate and advance
                        try:
                            res = result_vt.value[vec_counter + 1] * prop
                        except (IndexError, TypeError, ValueError):
                            res = 0
                        # add our extrapolated result as a ValueHelper
                        final.append(weewx.units.ValueHelper((res, result_vt.unit, result_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                        # and we also need to move to the next vector
                        vec_counter += 1
                except IndexError:
                    # if we run into an error set our result for this 'minute' to 0
                    final.append(weewx.units.ValueHelper((0, result_vt.unit, result_vt.group),
                                                         'minute',
                                                         self.formatter,
                                                         self.converter))
        return final    # return our result

    def datetimeQuery(self):
        final = []
        if self.interval <= self.agg_intvl or self.context != 'minute':
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0], self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'max',
                                                                            self.agg_intvl)
            for elm in stop_vt.value:
                final.append(weewx.units.ValueHelper((elm, stop_vt.unit, stop_vt.group), self.context,
                                                     self.formatter, self.converter))
        else:
            _tspan = weeutil.weeutil.TimeSpan(self.timespan[0]-self.interval, self.timespan[1])
            (start_vt, stop_vt, result_vt) = self.db_lookup().getSqlVectors(_tspan,
                                                                            self.obs_type,
                                                                            'max',
                                                                            self.agg_intvl)
            vc = 1
            for i in range(60):
                try:
                    curr_vector_ts = stop_vt.value[vc]
                    min_time = int((self.timespan[0] + 60) + i * 60)
                    if min_time < curr_vector_ts:
                        try:
                            res = (stop_vt.value[vc] - (curr_vector_ts - min_time) /
                                   float(self.interval) * (stop_vt.value[vc] - stop_vt.value[vc-1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, stop_vt.unit, stop_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                    elif min_time == curr_vector_ts:
                        final.append(weewx.units.ValueHelper((stop_vt.value[vc], stop_vt.unit, stop_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                        vc += 1
                    else:
                        vc += 1
                        try:
                            res = (stop_vt.value[vc] + (min_time - curr_vector_ts) /
                                   float(self.interval) * (stop_vt.value[vc] - stop_vt.value[vc - 1]))
                        except IndexError:
                            res = 0
                        final.append(weewx.units.ValueHelper((res, stop_vt.unit, stop_vt.group),
                                                             'minute',
                                                             self.formatter,
                                                             self.converter))
                except (IndexError, ValueError):
                    final.append(weewx.units.ValueHelper((self.timespan[1], stop_vt.unit, stop_vt.group),
                                                         'minute',
                                                         self.formatter,
                                                         self.converter))
        return final

    def __getattr__(self, aggregate_type):
        """Return statistical summary using a given aggregate_type.

            aggregate_type: The type of aggregation over which the summary is to
                            be done. This is normally something like 'sum',
                            'min', 'mintime', 'count', etc.
                            However, there are two special aggregation types
                            that can be used to determine the existence of data:

                            'exists': return True if the observation type exists
                                      in the database
                            'has_data': return True if the type exists and there
                                        is a non-zero number of entries over the
                                        aggregation period.

            returns: For special types 'exists' and 'has_data', returns a
                     Boolean value. Otherwise, a ValueHelper containing the
                     aggregation data.
        """

        return self._do_query(aggregate_type)

    @property
    def exists(self):
        return self.db_lookup(self.data_binding).exists(self.obs_type)

    @property
    def has_data(self):
        return self.db_lookup(self.data_binding).has_data(self.obs_type, self.timespan)

    def _do_query(self, aggregate_type, val=None):
        """Run a query against the databases, using the given aggregation type."""

        db_manager = self.db_lookup(self.data_binding)
        _tspan = weeutil.weeutil.TimeSpan(self.timespan[0], self.timespan[1])
        (start_vt, stop_vt, result_vt) = db_manager.getSqlVectors(_tspan,
                                                                  self.obs_type,
                                                                  aggregate_type,
                                                                  self.agg_intvl)
        # wrap the result in a ValueHelper
        return self.converter.convert(result_vt)