"""
rtcr.py

A WeeWX service to generate a loop based clientraw.txt.

Copyright (C) 2017-2024 Gary Roderick                gjroderick<at>gmail.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program.  If not, see https://www.gnu.org/licenses/.

Version: 0.3.7                                          Date: 31 August 2023

Revision History
    31 August 2023      v0.3.7
        - fix bug where a non-existent destination directory would prevent
          local saving of clientraw.txt
    24 March 2023       v0.3.6
        - fix incorrect default source fields for soil moisture, soil
          temperature and leaf wetness
    22 January 2023     v0.3.5
        - improved support for extraTemp and extraHumid in a default install
    3 April 2022        v0.3.4
        - version number change only
    7 February 2022     v0.3.3
        - introduced support for hierarchical log_success and log_failure
          config options to control logging of HTTP POST results
        - user can now specify wind direction output when wind direction is
          null/None
    25 November 2021    v0.3.2
        - debug log output now controlled by [[RealtimeClientraw]] debug
          options rather than the WeeWX global debug option
        - fixed bug when obtaining average values from scalar buffers
    13 May 2021         v0.3.0
        - WeeWX 3.4+/4.x python 2.7/3.x compatible
        - dropped support for python 2.5, python 2.6 may be supported but not
          guaranteed
        - removed post_request() method from class RealtimeClientrawThread as
          we no longer have to worry about python 2.5 support
        - removed unnecessary setting of day accumulator unit system from the
          class RealtimeClientrawThread run() method
        - fixed bug in nineam reset control code in process_packet()
        - removed unnecessary packet unit conversion call from
          class RtcrBuffer add_packet() method
        - added support for various debug_xxx settings in [RealtimeClientraw]
        - default location for generated clientraw.txt is now HTML_ROOT
        - windrun is now derived from loop/archive field windrun only (was
          previously calculated from windSpeed)
        - added config option disable_local_save to disable saving of
          clientraw.txt locally on the WeeWX machine
    9 March 2020        v0.2.3
        - fixed missing conversion to integer on some numeric config items
        - added try..except around the main thread code so that thread
          exceptions can be trapped and logged rather than the thread silently
          dying
        - changed to python 2/3 compatible try..except syntax
        - fixed incorrect instructions for setting additional_binding config
          item when there is no additional binding
    1 March 2020        v0.2.2
        - fix exception caused when there is no windDir (windDir == None)
    22 June 2019        v0.2.1
        - clientraw.txt content can now be sent to a remote URL via HTTP POST.
        - day windrun calculations are now seeded on startup
        - field 117 average wind direction now calculated (assumed to be
          average direction over the current day)
    19 March 2017       v0.2.0
        - added trend period config options, reworked trend field calculations
        - buffer object is now seeded on startup
        - added support for 9am rain reset total
        - binding used for appTemp data is now set by additional_binding config
          option
        - added comments details supported fields as well as fields required by
          Saratoga dashboard and Alternative dashboard
        - now calculates maxSolarRad if pyphem is present
        - maxSolarRad algorithm now selectable through config options
        - removed a number of unused buffer object properties
    3 March 2017        v0.1.0
        - initial release


The RealtimeClientraw service generates a loop based clientraw.txt that can be
used to update the Saratoga Weather Web Templates dashboard and the
Alternative dashboard in near real time.

Whilst the RealtimeClientraw generated clientraw.txt is fully compatible with
with the Saratoga and Alternative dashboards, some of the other uses of
clientraw.txt are not fully supported. For example, clientraw.txt can also be
used as a data feed for Weather Display Live (WDL); however, a number of the
fields used by WDL are not populated by the RealtimeClientraw service. Other
applications of clientraw.txt may or may not be supported by the
RealtimeClientraw generated clientraw.txt depending on what clientraw.txt
fields are used.

A list showing which clientraw.txt fields are/are not populated by the
RealtimeClientraw service is included below.

Inspired by crt.py v0.5 by Matthew Wall, a WeeWX service to emit loop data to
file in Cumulus realtime format. Refer https://cumuluswiki.org/a/Realtime.txt

Abbreviated instructions for use:

1.  Put this file in $BIN_ROOT/user.

2.  If using with the WeeWX-Saratoga extension to support the Saratoga Weather
Web templates add a [[RealtimeClientraw]] stanza under [WeewxSaratoga] in
weewx.conf as follows:

[WeewxSaratoga]
    ....
    [[RealtimeClientraw]]

        # Path to clientraw.txt. Can be an absolute or relative path. Relative
        # paths are relative to HTML_ROOT. Optional, default setting is to use
        # HTML_ROOT.
        # rtcr_path = /home/weewx/public_html

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

3.  If this service is not being used as part of the WeeWX-Saratoga extension
add a [RealtimeClientraw] stanza to weewx.conf containing the settings at
step 2 above. Note the different number of square brackets and different
hierarchical location of the stanza.

4.  Add the RealtimeClientraw service to the list of report services under
[Engine] [[Services]] in weewx.conf:

[Engine]
    [[Services]]
        report_services = ..., user.rtcr.RealtimeClientraw

5.  Restart WeeWX

6.  Confirm that clientraw.txt is being generated regularly as per the
    min_interval setting under [RealtimeClientraw] in weewx.conf.

Fields to implemented/finalised:
    - 015 - forecast icon.
    - *048 - icon type.
    - *049 - weather description.

Saratoga Dashboard
    - fields required:
        0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 19, 29, 30, 31, 32, 34, 35, 36, 44,
        45, 46, 47, 48, 49, 50, 71, 72, 73, 74, 75, 76, 77, 78, 79, 90, 110,
        111, 112, 113, 127, 130, 131, 132, 135, 136, 137, 138, 139, 140, 141
    - fields to be implemented/finalised in order to support:
        48, 49

Alternative Dashboard
    - fields required (Saratoga fields plus)(#=will not implement):
        1, 12, 13, #114, #115, #116, #118, #119, 156, 159, 160, 173
    - fields to be implemented/finalised in order to support:
        48, 49
"""
# TODO. seed RtcrBuffer day stats properties with values from daily summaries on startup and perhaps again on the next archive record

# python imports
import datetime
import math
import os.path
import socket
import threading
import time

from operator import itemgetter
from io import open

# Python 2/3 compatibility shims
import six
from six import iteritems
from six.moves import http_client
from six.moves import queue
from six.moves import urllib

# WeeWX imports
import weewx
import weeutil.weeutil
import weewx.tags
import weewx.units
import weewx.wxformulas
from weewx.engine import StdService
from weewx.units import ValueTuple, convert, ListOfDicts, getStandardUnitType, convertStd
from weeutil.weeutil import to_bool, to_int

# import/setup logging, WeeWX v3 is syslog based but WeeWX v4 is logging based,
# try v4 logging and if it fails use v3 logging
try:
    # WeeWX4 logging
    import logging
    from weeutil.logger import log_traceback
    log = logging.getLogger(__name__)

    def logcrit(msg):
        log.critical(msg)

    def logdbg(msg):
        log.debug(msg)

    def logerr(msg):
        log.error(msg)

    def loginf(msg):
        log.info(msg)

    # log_traceback() generates the same output but the signature and code is
    # different between v3 and v4. We only need log_traceback at the log.error
    # level so define a suitable wrapper function.
    def log_traceback_error(prefix=''):
        log_traceback(log.error, prefix=prefix)

except ImportError:
    # WeeWX legacy (v3) logging via syslog
    import syslog
    from weeutil.weeutil import log_traceback

    def logmsg(level, msg):
        syslog.syslog(level, 'rtcr: %s' % msg)

    def logcrit(msg):
        logmsg(syslog.LOG_CRIT, msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    # log_traceback() generates the same output but the signature and code is
    # different between v3 and v4. We only need log_traceback at the log.error
    # level so define a suitable wrapper function.
    def log_traceback_error(prefix=''):
        log_traceback(prefix=prefix, loglevel=syslog.LOG_ERR)


# version number of this script
RTCR_VERSION = '0.3.7'

# the obs that we will buffer
MANIFEST = ['outTemp', 'barometer', 'outHumidity', 'rain', 'rainRate',
            'humidex', 'windchill', 'heatindex', 'windSpeed', 'inTemp',
            'appTemp', 'dewpoint', 'windDir', 'wind', 'windrun']
# obs for which we need hi/lo data
HILO_MANIFEST = ['outTemp', 'barometer', 'outHumidity',
                 'humidex', 'windchill', 'heatindex', 'windSpeed', 'inTemp',
                 'appTemp', 'dewpoint']
# obs for which we need a history
HIST_MANIFEST = ['windSpeed', 'windDir']
# obs for which we need a running sum
SUM_MANIFEST = ['rain', 'windrun']
MAX_AGE = 600
DEFAULT_MAX_CACHE_AGE = 600
DEFAULT_AV_SPEED_PERIOD = 300
DEFAULT_GUST_PERIOD = 300
DEFAULT_GRACE = 200
DEFAULT_TREND_PERIOD = 3600


# ============================================================================
#                          class RealtimeClientraw
# ============================================================================

class RealtimeClientraw(StdService):
    """Service that generates clientraw.txt in near realtime.

    Creates and controls a threaded object of class RealtimeClientrawThread
    that generates clientraw.txt. Data and control signals are passed to the
    RealtimeClientrawThread object via an instance of queue.Queue.
    """

    def __init__(self, engine, config_dict):
        # initialize my superclass
        super(RealtimeClientraw, self).__init__(engine, config_dict)

        # obtain a Queue object so we can communicate with our thread
        self.rtcr_queue = queue.Queue()

        # get a db manager object
        manager_dict = weewx.manager.get_manager_dict_from_config(config_dict,
                                                                  'wx_binding')
        self.db_manager = weewx.manager.open_manager(manager_dict)

        # Get our config dict. We might be part of WeeWX-Saratoga so first look
        # for a [[RealtimeClientraw]] stanza under [WeewxSaratoga]. If we don't
        # find one we might be running standalone so look at the root level of
        # config_dict.
        if 'WeewxSaratoga' in config_dict and 'RealtimeClientraw' in config_dict['WeewxSaratoga']:
            rtcr_config_dict = config_dict['WeewxSaratoga'].get('RealtimeClientraw',
                                                                {})
        else:
            rtcr_config_dict = config_dict.get('RealtimeClientraw', {})
        # get HTML_ROOT to pass to our RealtimeClientrawThread object, this is
        # the default location to which clientraw.txt is saved
        html_root = os.path.join(config_dict['WEEWX_ROOT'],
                                 config_dict['StdReport'].get('HTML_ROOT', ''))
        # get an instance of class RealtimeClientrawThread and start the thread
        # running
        self.rtcr_thread = RealtimeClientrawThread(self.rtcr_queue,
                                                   manager_dict,
                                                   rtcr_config_dict,
                                                   html_root,
                                                   location=engine.stn_info.location,
                                                   latitude=engine.stn_info.latitude_f,
                                                   longitude=engine.stn_info.longitude_f,
                                                   altitude=convert(engine.stn_info.altitude_vt, 'meter').value)
        self.rtcr_thread.start()

        # forecast and current conditions fields
        self.forecast_binding = rtcr_config_dict.get('forecast_binding', None)
        if self.forecast_binding:
            try:
                self.forecast_manager = weewx.manager.open_manager_with_config(config_dict,
                                                                               self.forecast_binding)
            except weewx.UnknownBinding:
                self.forecast_manager = None
            if self.forecast_binding:
                self.forecast_text_field = rtcr_config_dict.get('forecast_text_field', None)
                self.forecast_icon_field = rtcr_config_dict.get('forecast_icon_field', None)
                self.current_text_field = rtcr_config_dict.get('current_text_field', None)

        # grace
        self.grace = to_int(rtcr_config_dict.get('grace', DEFAULT_GRACE))

        # debug settings
        self.debug_loop = to_bool(rtcr_config_dict.get('debug_loop', False))
        self.debug_archive = to_bool(rtcr_config_dict.get('debug_archive',
                                                          False))
        self.debug_stats = to_bool(rtcr_config_dict.get('debug_stats', False))

        # seed our RealtimeClientrawThread object
        self.queue_stats(int(time.time()))

        # bind ourself to the relevant WeeWX events
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        self.bind(weewx.END_ARCHIVE_PERIOD, self.end_archive_period)

    def new_loop_packet(self, event):
        """Puts new loop packets in the queue."""

        # package the loop packet in a dict since this is not the only data
        # we send via the queue
        _package = {'type': 'loop',
                    'payload': event.packet}
        self.rtcr_queue.put(_package)
        if self.debug_loop:
            loginf("queued loop packet: %s" % _package['payload'])

    def new_archive_record(self, event):
        """Puts archive records in the rtcr queue."""

        # package the archive record in a dict since this is not the only data
        # we send via the queue
        _package = {'type': 'archive',
                    'payload': event.record}
        self.rtcr_queue.put(_package)
        if self.debug_archive:
            loginf("queued archive record: %s" % _package['payload'])
        self.queue_stats(event.record['dateTime'])

    def queue_stats(self, ts):

        # make sure our db_manager is in sync with anything the main WeeWX
        # db_manager has changed, this is mainly for when an empty database is
        # first populated, but it is good practise anyway
        self.db_manager._sync()
        # get yesterday's rainfall and put in the queue
        _rain_data = self.get_historical_rain(ts)
        # if we have anything to send then package the data in a dict since
        # this is not the only data we send via the queue
        if len(_rain_data) > 0:
            _package = {'type': 'stats',
                        'payload': _rain_data}
            self.rtcr_queue.put(_package)
            if self.debug_stats:
                loginf("queued historical rainfall data: %s" % _package['payload'])
        # get yesterdays windrun and put in the queue
        _windrun_data = self.get_historical_windrun(ts)
        # if we have anything to send then package the data in a dict since
        # this is not the only data we send via the queue
        if len(_windrun_data) > 0:
            _package = {'type': 'stats',
                        'payload': _windrun_data}
            self.rtcr_queue.put(_package)
            if self.debug_stats:
                loginf("queued historical windrun data: %s" % _package['payload'])
        # get max gust in the last hour and put in the queue
        _hour_gust = self.get_hour_gust(ts)
        # if we have anything to send then package the data in a dict since
        # this is not the only data we send via the queue
        if len(_hour_gust) > 0:
            _package = {'type': 'stats',
                        'payload': _hour_gust}
            self.rtcr_queue.put(_package)
            if self.debug_stats:
                loginf("queued last hour gust: %s" % _package['payload'])
        # get outTemp 1 hour ago and put in the queue
        _hour_temp = self.get_hour_ago_temp(ts)
        # if we have anything to send then package the data in a dict since
        # this is not the only data we send via the queue
        if len(_hour_temp) > 0:
            _package = {'type': 'stats',
                        'payload': _hour_temp}
            self.rtcr_queue.put(_package)
            if self.debug_stats:
                loginf("queued outTemp hour ago: %s" % _package['payload'])

    def end_archive_period(self, event):
        """Puts END_ARCHIVE_PERIOD event in the rtcr queue."""

        # package the event in a dict since this is not the only data we send
        # via the queue
        _package = {'type': 'event',
                    'payload': weewx.END_ARCHIVE_PERIOD}
        self.rtcr_queue.put(_package)
        if self.debug_archive:
            loginf("queued weewx.END_ARCHIVE_PERIOD event")

    def shutDown(self):
        """Shut down any threads."""

        if hasattr(self, 'rtcr_queue') and hasattr(self, 'rtcr_thread'):
            if self.rtcr_queue and self.rtcr_thread.is_alive():
                # Put a None in the queue to signal the thread to shut down
                self.rtcr_queue.put(None)
                # Wait up to 20 seconds for the thread to exit:
                self.rtcr_thread.join(20.0)
                if self.rtcr_thread.is_alive():
                    logerr("Unable to shut down %s thread" % self.rtcr_thread.name)
                else:
                    logdbg("Shut down %s thread." % self.rtcr_thread.name)

    def get_historical_rain(self, ts):
        """Obtain yesterday's total rainfall and return as a ValueTuple."""

        result = {}
        (unit, group) = weewx.units.getStandardUnitType(self.db_manager.std_unit_system,
                                                        'rain',
                                                        agg_type='sum')
        # Yesterday's rain
        # get a TimeSpan object for yesterday's archive day
        yest_tspan = weeutil.weeutil.archiveDaysAgoSpan(ts, days_ago=1)
        # create an interpolation dict
        inter_dict = {'table_name': self.db_manager.table_name,
                      'start': yest_tspan.start,
                      'stop': yest_tspan.stop}
        # the query to be used
        _sql = "SELECT SUM(rain) FROM %(table_name)s "\
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['yest_rain_vt'] = ValueTuple(_row[0], unit, group)

        # This month's rain
        # get a TimeSpan object for this month
        month_tspan = weeutil.weeutil.archiveMonthSpan(ts)
        # create an interpolation dict
        inter_dict = {'table_name': self.db_manager.table_name,
                      'start': month_tspan.start,
                      'stop': month_tspan.stop}
        # the query to be used
        _sql = "SELECT SUM(sum) FROM %(table_name)s_day_rain "\
               "WHERE dateTime >= %(start)s AND dateTime < %(stop)s"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['month_rain_vt'] = ValueTuple(_row[0], unit, group)

        # This year's rain
        # get a TimeSpan object for this year
        year_tspan = weeutil.weeutil.archiveYearSpan(ts)
        # create an interpolation dict
        inter_dict = {'table_name': self.db_manager.table_name,
                      'start': year_tspan.start,
                      'stop': year_tspan.stop}
        # the query to be used
        _sql = "SELECT SUM(sum) FROM %(table_name)s_day_rain "\
               "WHERE dateTime >= %(start)s AND dateTime < %(stop)s"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['year_rain_vt'] = ValueTuple(_row[0], unit, group)

        return result

    def get_historical_windrun(self, ts):
        """Obtain yesterdays total windrun and return as a ValueTuple."""

        result = {}
        (unit, group) = weewx.units.getStandardUnitType(self.db_manager.std_unit_system,
                                                        'windrun',
                                                        agg_type='sum')
        # Yesterday's windrun
        # get a TimeSpan object for yesterday's archive day
        yest_tspan = weeutil.weeutil.archiveDaysAgoSpan(ts, days_ago=1)
        # create an interpolation dict
        inter_dict = {'table_name': self.db_manager.table_name,
                      'start': yest_tspan.start,
                      'stop': yest_tspan.stop}
        # the query to be used
        _sql = "SELECT SUM(windrun) FROM %(table_name)s "\
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['yest_windrun_vt'] = ValueTuple(_row[0], unit, group)

        # This month's windrun
        # get a TimeSpan object for this month
        month_tspan = weeutil.weeutil.archiveMonthSpan(ts)
        # create an interpolation dict
        inter_dict = {'table_name': self.db_manager.table_name,
                      'start': month_tspan.start,
                      'stop': month_tspan.stop}
        # the query to be used
        _sql = "SELECT SUM(sum) FROM %(table_name)s_day_windrun "\
               "WHERE dateTime >= %(start)s AND dateTime < %(stop)s"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['month_windrun_vt'] = ValueTuple(_row[0], unit, group)

        # This year's windrun
        # get a TimeSpan object for this year
        year_tspan = weeutil.weeutil.archiveYearSpan(ts)
        # create an interpolation dict
        inter_dict = {'table_name': self.db_manager.table_name,
                      'start': year_tspan.start,
                      'stop': year_tspan.stop}
        # the query to be used
        _sql = "SELECT SUM(sum) FROM %(table_name)s_day_windrun "\
               "WHERE dateTime >= %(start)s AND dateTime < %(stop)s"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['year_windrun_vt'] = ValueTuple(_row[0], unit, group)

        return result

    def get_hour_gust(self, ts):
        """Obtain the max wind gust in the last hour."""

        result = {}
        (unit, group) = weewx.units.getStandardUnitType(self.db_manager.std_unit_system,
                                                        'windGust')
        # get a TimeSpan object for the last hour
        hour_tspan = weeutil.weeutil.archiveSpanSpan(ts, hour_delta=1)
        # create an interpolation dict
        inter_dict = {'table_name': self.db_manager.table_name,
                      'start': hour_tspan.start,
                      'stop': hour_tspan.stop}
        # the query to be used
        _sql = "SELECT MAX(windGust) FROM %(table_name)s "\
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['hour_gust_vt'] = ValueTuple(_row[0], unit, group)
        # now get the time it occurred
        _sql = "SELECT dateTime FROM %(table_name)s "\
               "WHERE dateTime > %(start)s AND dateTime <= %(stop)s AND "\
               "windGust = (SELECT MAX(windGust) FROM %(table_name)s "\
               "WHERE dateTime > %(start)s and dateTime <= %(stop)s) AND windGust IS NOT NULL"
        # execute the query
        _row = self.db_manager.getSql(_sql % inter_dict)
        if _row and None not in _row:
            result['hour_gust_ts'] = _row[0]
        return result

    def get_hour_ago_temp(self, ts):
        """Obtain the outTemp hour ago."""

        result = {}
        (unit, group) = weewx.units.getStandardUnitType(self.db_manager.std_unit_system,
                                                        'outTemp')
        # get a timestamp for one hour ago
        ago_dt = datetime.datetime.fromtimestamp(ts) - datetime.timedelta(hours=1)
        ago_ts = time.mktime(ago_dt.timetuple())
        _record = self.db_manager.getRecord(ago_ts, self.grace)
        if _record and 'outTemp' in _record:
            result['hour_ago_outTemp_vt'] = ValueTuple(_record['outTemp'], unit, group)
        return result


# ============================================================================
#                       class RealtimeClientrawThread
# ============================================================================

class RealtimeClientrawThread(threading.Thread):
    """Thread that generates clientraw.txt in near realtime."""

    # Format dict for clientraw.txt fields. None = no change, 0 = integer (no
    # decimal places), numeric = format to this many decimal places.
    field_formats = {
        0: None,  # start of fields marker
        1: 1,  # - avg speed
        2: 1,  # - gust
        3: 0,  # - windDir
        4: 1,  # - outTemp
        5: 0,  # - outHumidity
        6: 1,  # - barometer
        7: 1,  # - daily rain
        8: 1,  # - monthly rain
        9: 1,  # - yearly rain
        10: 1,  # - rain rate
        11: 1,  # - max daily rainRate
        12: 1,  # - inTemp
        13: 0,  # - inHumidity
        14: 1,  # - soil temperature
        15: 0,  # - forecast Icon
        16: 1,  # - WMR968 extra temperature - will not implement
        17: 0,  # - WMR968 extra humidity - will not implement
        18: 1,  # - WMR968 extra sensor - will not implement
        19: 1,  # - yesterday rain
        20: 1,  # - extra temperature sensor 1
        21: 1,  # - extra temperature sensor 2
        22: 1,  # - extra temperature sensor 3
        23: 1,  # - extra temperature sensor 4
        24: 1,  # - extra temperature sensor 5
        25: 1,  # - extra temperature sensor 6
        26: 0,  # - extra humidity sensor 1
        27: 0,  # - extra humidity sensor 2
        28: 0,  # - extra humidity sensor 3
        29: None,  # - hour
        30: None,  # - minute
        31: None,  # - seconds
        32: None,  # - station name
        33: 0,  # - dallas lightning count - will not implement
        34: 0,  # - Solar Reading - used as 'solar percent' in Saratoga dashboards
        35: None,  # - day
        36: None,  # - month
        37: 0,  # - WMR968/200 battery 1 - will not implement
        38: 0,  # - WMR968/200 battery 2 - will not implement
        39: 0,  # - WMR968/200 battery 3 - will not implement
        40: 0,  # - WMR968/200 battery 4 - will not implement
        41: 0,  # - WMR968/200 battery 5 - will not implement
        42: 0,  # - WMR968/200 battery 6 - will not implement
        43: 0,  # - WMR968/200 battery 7 - will not implement
        44: 1,  # - windchill
        45: 1,  # - humidex
        46: 1,  # - maximum day temperature
        47: 1,  # - minimum day temperature
        48: 0,  # - icon type
        49: None,  # - weather description
        50: 1,  # - barometer trend
        51: 1,  # - windspeed hour 1 - will not implement
        52: 1,  # - windspeed hour 2 - will not implement
        53: 1,  # - windspeed hour 3 - will not implement
        54: 1,  # - windspeed hour 4 - will not implement
        55: 1,  # - windspeed hour 5 - will not implement
        56: 1,  # - windspeed hour 6 - will not implement
        57: 1,  # - windspeed hour 7 - will not implement
        58: 1,  # - windspeed hour 8 - will not implement
        59: 1,  # - windspeed hour 9 - will not implement
        60: 1,  # - windspeed hour 10 - will not implement
        61: 1,  # - windspeed hour 11 - will not implement
        62: 1,  # - windspeed hour 12 - will not implement
        63: 1,  # - windspeed hour 13 - will not implement
        64: 1,  # - windspeed hour 14 - will not implement
        65: 1,  # - windspeed hour 15 - will not implement
        66: 1,  # - windspeed hour 16 - will not implement
        67: 1,  # - windspeed hour 17 - will not implement
        68: 1,  # - windspeed hour 18 - will not implement
        69: 1,  # - windspeed hour 19 - will not implement
        70: 1,  # - windspeed hour 20 - will not implement
        71: 1,  # - maximum wind gust today
        72: 1,  # - dewpoint
        73: 1,  # - cloud height
        74: None,  # - date
        75: 1,  # - maximum day humidex
        76: 1,  # - minimum day humidex
        77: 1,  # - maximum day windchill
        78: 1,  # - minimum day windchill
        79: 1,  # - Davis VP UV
        80: 1,  # - hour wind speed 1 - will not implement
        81: 1,  # - hour wind speed 2 - will not implement
        82: 1,  # - hour wind speed 3 - will not implement
        83: 1,  # - hour wind speed 4 - will not implement
        84: 1,  # - hour wind speed 5 - will not implement
        85: 1,  # - hour wind speed 6 - will not implement
        86: 1,  # - hour wind speed 7 - will not implement
        87: 1,  # - hour wind speed 8 - will not implement
        88: 1,  # - hour wind speed 9 - will not implement
        89: 1,  # - hour wind speed 10 - will not implement
        90: 1,  # - hour temperature 1
        91: 1,  # - hour temperature 2 - will not implement
        92: 1,  # - hour temperature 3 - will not implement
        93: 1,  # - hour temperature 4 - will not implement
        94: 1,  # - hour temperature 5 - will not implement
        95: 1,  # - hour temperature 6 - will not implement
        96: 1,  # - hour temperature 7 - will not implement
        97: 1,  # - hour temperature 8 - will not implement
        98: 1,  # - hour temperature 9 - will not implement
        99: 1,  # - hour temperature 10 - will not implement
        100: 1,  # - hour rain 1 - will not implement
        101: 1,  # - hour rain 2 - will not implement
        102: 1,  # - hour rain 3 - will not implement
        103: 1,  # - hour rain 4 - will not implement
        104: 1,  # - hour rain 5 - will not implement
        105: 1,  # - hour rain 6 - will not implement
        106: 1,  # - hour rain 7 - will not implement
        107: 1,  # - hour rain 8 - will not implement
        108: 1,  # - hour rain 9 - will not implement
        109: 1,  # - hour rain 10 - will not implement
        110: 1,  # - maximum day heatindex
        111: 1,  # - minimum day heatindex
        112: 1,  # - heatindex
        113: 1,  # - maximum average speed
        114: 0,  # - lightning count in last minute - will not implement
        115: None,  # - time of last lightning strike - will not implement
        116: None,  # - date of last lightning strike - will not implement
        117: 1,  # - wind average direction
        118: 1,  # - nexstorm distance - will not implement
        119: 1,  # - nexstorm bearing - will not implement
        120: 1,  # - extra temperature sensor 7
        121: 1,  # - extra temperature sensor 8
        122: 0,  # - extra humidity sensor 4
        123: 0,  # - extra humidity sensor 5
        124: 0,  # - extra humidity sensor 6
        125: 0,  # - extra humidity sensor 7
        126: 0,  # - extra humidity sensor 8
        127: 1,  # - VP solar
        128: 1,  # - maximum inTemp
        129: 1,  # - minimum inTemp
        130: 1,  # - appTemp
        131: 1,  # - maximum barometer
        132: 1,  # - minimum barometer
        133: 1,  # - maximum windGust last hour
        134: None,  # - maximum windGust in last hour time
        135: None,  # - maximum windGust today time
        136: 1,  # - maximum day appTemp
        137: 1,  # - minimum day appTemp
        138: 1,  # - maximum day dewpoint
        139: 1,  # - minimum day dewpoint
        140: 1,  # - maximum windGust in last minute
        141: None,  # - current year
        142: 1,  # - THSWS - will not implement
        143: None,  # - outTemp trend
        144: None,  # - outHumidity trend
        145: None,  # - humidex trend
        146: 1,  # - hour wind direction 1 - will not implement
        147: 1,  # - hour wind direction 2 - will not implement
        148: 1,  # - hour wind direction 3 - will not implement
        149: 1,  # - hour wind direction 4 - will not implement
        150: 1,  # - hour wind direction 5 - will not implement
        151: 1,  # - hour wind direction 6 - will not implement
        152: 1,  # - hour wind direction 7 - will not implement
        153: 1,  # - hour wind direction 8 - will not implement
        154: 1,  # - hour wind direction 9 - will not implement
        155: 1,  # - hour wind direction 10 - will not implement
        156: 1,  # - leaf wetness
        157: 1,  # - soil moisture
        158: 1,  # - 10-minute average wind speed
        159: 1,  # - wet bulb temperature
        160: None,  # - latitude
        161: None,  # - longitude
        162: 1,  # - 9am reset rainfall total
        163: 0,  # - high day outHumidity
        164: 0,  # - low day outHumidity
        165: 1,  # - midnight rain reset total
        166: None,  # - low day windchill time
        167: 1,  # - current Cost Channel 1 - will not implement
        168: 1,  # - current Cost Channel 2 - will not implement
        169: 1,  # - current Cost Channel 3 - will not implement
        170: 1,  # - current Cost Channel 4 - will not implement
        171: 1,  # - current Cost Channel 5 - will not implement
        172: 1,  # - current Cost Channel 6 - will not implement
        173: 1,  # - day windrun
        174: None,  # - time of daily max temp
        175: None,  # - time of daily min temp
        176: 0,  # - 10-minute average wind direction
        177: None,  # - record end
    }
    # default direction if no other non-None value can be found
    DEFAULT_DIR = 0
    # inter-cardinal to degrees lookup:
    ic_to_degrees = {'N': '0', 'NNE': '22.5', 'NE': '45', 'ENE': '67.5',
                     'E': '90', 'ESE': '112.5', 'SE': '135', 'SSE': '157.5',
                     'S': '180', 'SSW': '202.5', 'SW': '225', 'WSW': '247.5',
                     'W': '270', 'WNW': '292.5', 'NW': '315', 'NNW': '337.5'
                     }

    def __init__(self, rtcr_queue, manager_dict, rtcr_config_dict, html_root,
                 location, latitude, longitude, altitude):
        # initialize my superclass
        threading.Thread.__init__(self)

        self.setDaemon(True)
        self.rtcr_queue = rtcr_queue
        self.manager_dict = manager_dict

        # setup file generation timing
        self.min_interval = to_int(rtcr_config_dict.get('min_interval', None))
        # timestamp of last file generation
        self.last_write = 0

        # get our file paths and names
        _path = rtcr_config_dict.get('rtcr_path', '')
        rtcr_path = os.path.join(html_root, _path)
        rtcr_filename = rtcr_config_dict.get('rtcr_file_name', 'clientraw.txt')
        self.rtcr_path_file = os.path.join(rtcr_path, rtcr_filename)
        # has local the saving of clientraw.txt been disabled
        self.disable_local_save = to_bool(rtcr_config_dict.get('disable_local_save',
                                                               False))
        # create the directory that is to receive the generate file, but only
        # if we are saving the file locally
        if not self.disable_local_save:
            # create the directory, if it already exists an exception will be
            # thrown, so be prepared to catch it
            try:
                os.makedirs(rtcr_path)
            except OSError:
                pass
        # get the remote server URL if it exists, if it doesn't set it to None
        self.remote_server_url = rtcr_config_dict.get('remote_server_url', None)
        # timeout to be used for remote URL posts
        self.timeout = to_int(rtcr_config_dict.get('timeout', 2))

        # some field definition settings (mainly time periods for averages etc)
        self.avgspeed_period = to_int(rtcr_config_dict.get('avgspeed_period',
                                                           DEFAULT_AV_SPEED_PERIOD))
        self.gust_period = to_int(rtcr_config_dict.get('gust_period',
                                                       DEFAULT_GUST_PERIOD))

        # set some format strings
        self.date_fmt = rtcr_config_dict.get('date_format', '%-d/%-m/%Y')
        self.long_time_fmt = rtcr_config_dict.get('long_time_format', '%H:%M:%S')
        self.short_time_fmt = rtcr_config_dict.get('short_time_format', '%H:%M')
        self.flag_format = '%.0f'

        # get max cache age, used for caching loop data from partial packet
        # stations
        self.max_cache_age = to_int(rtcr_config_dict.get('max_cache_age',
                                                         DEFAULT_MAX_CACHE_AGE))

        # grace period when looking for archive records
        self.grace = to_int(rtcr_config_dict.get('grace', DEFAULT_GRACE))

        # determine how much logging is desired
        self.log_success = to_bool(weeutil.config.search_up(rtcr_config_dict,
                                                            'log_success',
                                                            False))
        self.log_failure = to_bool(weeutil.config.search_up(rtcr_config_dict,
                                                            'log_failure',
                                                            True))

        # How to treat wind direction that is None. If self.null_dir == 'LAST'
        # then we use the last known direction, otherwise we use whatever is
        # stored in self.null_dir.
        # first get the null_dir config option if it exists, default to 'LAST'
        _nd = rtcr_config_dict.get('null_dir', 'LAST')
        # no try to convert to an int
        try:
            _deg = "%d" % int(_nd)
        except (ValueError, TypeError):
            # perhaps we have a string inter-cardinal direction or it's 'LAST',
            # try to convert it to degrees, if we can't default to 'LAST'
            _deg = RealtimeClientrawThread.ic_to_degrees.get(_nd, 'LAST')
        self.null_dir = _deg

        # debug settings
        self.debug_loop = to_bool(rtcr_config_dict.get('debug_loop', False))
        self.debug_archive = to_bool(rtcr_config_dict.get('debug_archive',
                                                          False))
        self.debug_stats = to_bool(rtcr_config_dict.get('debug_stats', False))
        self.debug_cache = to_bool(rtcr_config_dict.get('debug_cache', False))
        self.debug_queue = to_bool(rtcr_config_dict.get('debug_queue', False))
        self.debug_gen = to_bool(rtcr_config_dict.get('debug_gen', False))
        self.debug_post = to_bool(rtcr_config_dict.get('debug_post', False))

        # are we updating windrun using archive data only or archive and loop
        # data?
        self.windrun_loop = to_bool(rtcr_config_dict.get('windrun_loop',
                                                         'False'))

        # extra sensors
        extra_sensor_config_dict = rtcr_config_dict.get('ExtraSensors', {})
        # temperature
        self.extra_temp1 = extra_sensor_config_dict.get('extraTempSensor1', 'extraTemp1')
        self.extra_temp2 = extra_sensor_config_dict.get('extraTempSensor2', 'extraTemp2')
        self.extra_temp3 = extra_sensor_config_dict.get('extraTempSensor3', 'extraTemp3')
        self.extra_temp4 = extra_sensor_config_dict.get('extraTempSensor4', 'extraTemp4')
        self.extra_temp5 = extra_sensor_config_dict.get('extraTempSensor5', 'extraTemp5')
        self.extra_temp6 = extra_sensor_config_dict.get('extraTempSensor6', 'extraTemp6')
        self.extra_temp7 = extra_sensor_config_dict.get('extraTempSensor7', 'extraTemp7')
        self.extra_temp8 = extra_sensor_config_dict.get('extraTempSensor8', 'extraTemp8')
        # humidity
        self.extra_hum1 = extra_sensor_config_dict.get('extraHumSensor1', 'extraHumid1')
        self.extra_hum2 = extra_sensor_config_dict.get('extraHumSensor2', 'extraHumid2')
        self.extra_hum3 = extra_sensor_config_dict.get('extraHumSensor3', 'extraHumid3')
        self.extra_hum4 = extra_sensor_config_dict.get('extraHumSensor4', 'extraHumid4')
        self.extra_hum5 = extra_sensor_config_dict.get('extraHumSensor5', 'extraHumid5')
        self.extra_hum6 = extra_sensor_config_dict.get('extraHumSensor6', 'extraHumid6')
        self.extra_hum7 = extra_sensor_config_dict.get('extraHumSensor7', 'extraHumid7')
        self.extra_hum8 = extra_sensor_config_dict.get('extraHumSensor8', 'extraHumid8')
        # soil moisture
        self.soil_moist = extra_sensor_config_dict.get('soilMoistSensor', 'soilMoist1')
        # soil temp
        self.soil_temp = extra_sensor_config_dict.get('soilTempSensor', 'soilTemp1')
        # leaf wetness
        self.leaf_wet = extra_sensor_config_dict.get('leafWetSensor', 'leafWet1')
        # set trend periods
        self.baro_trend_period = to_int(rtcr_config_dict.get('baro_trend_period',
                                                             DEFAULT_TREND_PERIOD))
        self.temp_trend_period = to_int(rtcr_config_dict.get('temp_trend_period',
                                                             DEFAULT_TREND_PERIOD))
        self.humidity_trend_period = to_int(rtcr_config_dict.get('humidity_trend_period',
                                                                 DEFAULT_TREND_PERIOD))
        self.humidex_trend_period = to_int(rtcr_config_dict.get('humidex_trend_period',
                                                                DEFAULT_TREND_PERIOD))

        # flag to indicate a change of day has occurred
        self.new_day = False
        # initialise a day of the week property so we know when it's a new day
        self.dow = None
        # initialise some properties used to hold archive period wind data
        self.min_barometer = None
        self.max_barometer = None
        # get some station info
        self.location = location
        self.latitude = latitude
        self.longitude = longitude
        self.altitude_m = altitude

        # initialise some properties to be used later
        self.db_manager = None
        self.additional_manager = None
        self.day_stats = None
        self.buffer = None
        self.packet_cache = None

        # inform the user what we are going to do
        loginf("RealtimeClientraw version %s" % RTCR_VERSION)
        if not self.disable_local_save:
            loginf("RealtimeClientraw will generate %s" % self.rtcr_path_file)
            if self.min_interval is None:
                _msg = "min_interval is None (0 seconds)"
            elif to_int(self.min_interval) == 1:
                _msg = "min_interval is 1 second"
            else:
                _msg = "min_interval is %s seconds" % self.min_interval
            loginf(_msg)
        if self.remote_server_url is not None:
            loginf("%s will be posted to %s by HTTP POST" % (rtcr_filename,
                                                             self.remote_server_url))
            if self.timeout == 1:
                _msg = "HTTP POST timeout is 1 second"
            else:
                _msg = "HTTP POST timeout is %d seconds" % self.timeout
            logdbg(_msg)
        if self.disable_local_save and self.remote_server_url is None:
            loginf("Warning: clientraw.txt will not be saved locally "
                   "nor will it be posted via HTTP POST")
        logdbg("Date format: '%s', long time format: '%s', short time format: '%s'" % (self.date_fmt,
                                                                                       self.long_time_fmt,
                                                                                       self.short_time_fmt))
        logdbg("Archive record grace period is %d seconds" % self.grace)
        logdbg("Maximum cache age is %d seconds" % self.max_cache_age)
        logdbg("barometer trend period: %d seconds, temperature trend period: %d seconds" % (self.baro_trend_period,
                                                                                             self.temp_trend_period))
        logdbg("humidity trend period: %d seconds, humidex trend period: %d seconds" % (self.humidity_trend_period,
                                                                                        self.humidex_trend_period))
        if self.windrun_loop:
            logdbg("windrun will be updated using archive and loop data")
        else:
            logdbg("windrun will be updated using archive data")
        for i in range(8):
            _prop = "".join(("extra_temp", str(i + 1)))
            if getattr(self, _prop) is not None:
                logdbg("WeeWX field '%s' is mapped to clientraw.txt "
                       "field 'Extra Temp Sensor %d'" % (getattr(self, _prop),
                                                         i + 1))
        for i in range(8):
            _prop = "".join(("extra_hum", str(i + 1)))
            if getattr(self, _prop) is not None:
                logdbg("WeeWX field '%s' is mapped to clientraw.txt "
                       "field 'Extra Hum Sensor %d'" % (getattr(self, _prop),
                                                        i + 1))
        if self.soil_temp is not None:
            logdbg("WeeWX field '%s' is mapped to clientraw.txt field 'Soil Temp'" % self.soil_temp)
        if self.soil_moist is not None:
            logdbg("WeeWX field '%s' is mapped to clientraw.txt field 'VP Soil Moisture'" % self.soil_moist)
        if self.leaf_wet is not None:
            logdbg("WeeWX field '%s' is mapped to clientraw.txt field 'VP Leaf Wetness'" % self.leaf_wet)

    def run(self):
        """Collect packets from the rtcr queue and manage their processing.

        Now that we are in a thread get a manager for our db, so we can
        initialise our forecast and day stats. Once this is done we wait for
        something in the rtcr queue.
        """

        # since we are running in a thread wrap in a try..except, so we can trap
        # and log any errors rather than the thread silently dying
        try:
            # would normally do this in our objects __init__ but since we are
            # running in a thread we need to wait until the thread is actually
            # running before getting db managers
            # get a db manager
            self.db_manager = weewx.manager.open_manager(self.manager_dict)
            # initialise our day stats
            self.day_stats = self.db_manager._get_day_summary(time.time())
            # create a RtcrBuffer object to hold our loop 'stats'
            self.buffer = RtcrBuffer(day_stats=self.day_stats)
            # set up our loop cache and set some starting wind values
            # get the last good record
            _ts = self.db_manager.lastGoodStamp()
            if _ts is not None:
                _rec = self.db_manager.getRecord(_ts)
            else:
                _rec = {'usUnits': None}
            # convert it to our buffer unit system
            _rec = weewx.units.to_std_system(_rec,
                                             self.buffer.unit_system)
            # get a CachedPacket object as our loop packet cache and prime it with
            # values from the last good archive record if available
            if self.debug_loop or self.debug_cache:
                loginf("initialising loop packet cache ...")
            self.packet_cache = CachedPacket(_rec)
            if self.debug_loop or self.debug_cache:
                loginf("loop packet cache initialised")

            # now run a continuous loop, waiting for records to appear in the rtcr
            # queue then processing them.
            while True:
                while True:
                    _package = self.rtcr_queue.get()
                    # a None record is our signal to exit
                    if _package is None:
                        return
                    elif _package['type'] == 'archive':
                        self.new_archive_record(_package['payload'])
                        if self.debug_archive or self.debug_queue:
                            loginf("received archive record")
                        continue
                    elif _package['type'] == 'event':
                        if _package['payload'] == weewx.END_ARCHIVE_PERIOD:
                            if self.debug_archive or self.debug_queue:
                                loginf("received event - END_ARCHIVE_PERIOD")
                            self.end_archive_period()
                        continue
                    elif _package['type'] == 'stats':
                        if self.debug_stats or self.debug_queue:
                            loginf("received stats package payload=%s" % (_package['payload'], ))
                        self.process_stats(_package['payload'])
                        if self.debug_stats or self.debug_queue:
                            loginf("processed stats package")
                        continue
                    # if packets have backed up in the rtcr queue, trim it until
                    # it's no bigger than the max allowed backlog
                    if self.rtcr_queue.qsize() <= 5:
                        break

                # if we made it here we have a loop packet to process
                if self.debug_loop or self.debug_queue:
                    loginf("received packet: %s" % _package['payload'])
                self.process_packet(_package['payload'])
        except Exception as e:
            # Some unknown exception occurred. This is probably a serious
            # problem. Exit.
            logcrit("Unexpected exception of type %s" % (type(e), ))
            log_traceback_error('**** ')
            logcrit("Thread exiting. Reason: %s" % (e, ))
            return

    def process_packet(self, packet):
        """Process incoming loop packets and generate clientraw.txt."""

        # get time for debug timing
        t1 = time.time()

        # If the buffer unit system is None adopt the unit system of the
        # incoming loop packet, this should only ever happen if we were started
        # with an empty database
        if self.buffer.unit_system is not None:
            # make sure the packet is in our buffer unit system
            conv_packet = weewx.units.to_std_system(packet,
                                                    self.buffer.unit_system)
        else:
            # have the buffer adopt the unit system of the packet
            self.buffer.unit_system = packet['usUnits']
            # there is no need ot convert the packet
            conv_packet = packet

        # update the packet cache with this packet
        self.packet_cache.update(conv_packet, conv_packet['dateTime'])

        # is this the first packet of the day, if so we need to reset our
        # buffer day stats
        dow = time.strftime('%w', time.localtime(conv_packet['dateTime']))
        if self.dow is not None and self.dow != dow:
            self.new_day = True
            self.buffer.start_of_day_reset()
        self.dow = dow

        # if this is the first packet after 9am we need to reset any 9am sums
        # first get the current hour as an int
        _hour = int(time.strftime('%H', time.localtime(conv_packet['dateTime'])))
        # if it's a new day and hour >= 9 we need to reset any 9am sums
        if self.new_day and _hour >= 9:
            self.new_day = False
            self.buffer.nineam_reset()

        # now add the packet to our buffer
        self.buffer.add_packet(conv_packet)

        # generate if we have no minimum interval setting or if minimum
        # interval seconds have elapsed since our last generation
        if self.min_interval is None or (self.last_write + float(self.min_interval)) < time.time():
            try:
                # get a cached packet
                cached_packet = self.packet_cache.get_packet(conv_packet['dateTime'],
                                                             self.max_cache_age)
                if self.debug_loop or self.debug_cache:
                    loginf("cached loop packet: %s" % (cached_packet,))
                # get a data dict from which to construct our file
                data = self.calculate(cached_packet)
                # convert our data dict to a clientraw string
                cr_string = self.create_clientraw_string(data)
                if not self.disable_local_save:
                    # write our file
                    self.write_data(cr_string)
                # set our write time, this is only used to determine our next
                # generation time
                self.last_write = time.time()
                # if required send the data to a remote URL via HTTP POST
                if self.remote_server_url is not None:
                    # post the data
                    self.post_data(cr_string)
                # log the generation
                if self.debug_gen:
                    loginf("packet (%s) clientraw.txt generated in %.5f seconds" % (cached_packet['dateTime'],
                                                                                    (self.last_write-t1)))
            except Exception as e:
                log_traceback_error('rtcrthread: **** ')
        else:
            # we skipped this packet so log it
            if self.debug_gen:
                loginf("packet (%s) skipped" % conv_packet['dateTime'])

    def process_stats(self, package):
        """Process a stats package.

        Inputs:
            package: dict containing the stats data
        """

        if package is not None:
            for key, value in iteritems(package):
                setattr(self, key, value)

    def new_archive_record(self, record):
        """Control processing when a new archive record is presented.

        When a new archive record is available our interest is in the updated
        daily summaries.
        """

        # refresh our day (archive record based) stats
        self.day_stats = self.db_manager._get_day_summary(record['dateTime'])

    def end_archive_period(self):
        """Control processing at the end of each archive period."""

        for obs in SUM_MANIFEST:
            self.buffer[obs].interval_reset()

    def post_data(self, data):
        """Post data to a remote URL via HTTP POST.

        This code is modelled on the WeeWX RESTful API, but rather than
        retrying a failed post the failure is logged and then ignored. If
        remote posts are not working then the user should set debug=1 and
        restart WeeWX to see what the log says.

        The data to be posted is sent as a utf-8 text string.

        Inputs:
            data: clientraw data string
        """

        # get a Request object
        req = urllib.request.Request(self.remote_server_url)
        # set our content type to plain text
        req.add_header('Content-Type', 'text/plain')
        # POST the data but wrap in a try..except, so we can trap any errors
        try:
            response = self.post_request(req, data)
            if 200 <= response.code <= 299:
                # no exception thrown and we received a good response code, log
                # it and return.
                if self.log_success or self.debug_post:
                    loginf("Data successfully posted. Received response: '%s %s'" % (response.getcode(),
                                                                                     response.msg))
                return
            # we received a bad response code, log it and continue
            if self.log_failure or self.debug_post:
                loginf("Failed to post data. Received response: '%s %s'" % (response.getcode(),
                                                                            response.msg))
        except (urllib.error.URLError, socket.error,
                http_client.BadStatusLine, http_client.IncompleteRead) as e:
            # an exception was thrown, log it and continue
            if self.log_failure or self.debug_post:
                loginf("Failed to post data. Exception error message: '%s'" % e)

    def post_request(self, request, payload):
        """Post a Request object.

        Inputs:
            request: Request object
            payload: the data to sent as a unicode string

        Returns:
            The urlopen() response
        """

        # The POST data needs to be urlencoded, under python2 urlencoding
        # unicode characters that have no ascii equivalent raises a
        # UnicodeEncodeError, the solution is to encode the characters before
        # urlencoding. Under python3 POST data should be bytes or an iterable
        # of bytes and not of type str so python3 requires the encoding occur
        # after the data is urlencoded. So assume we are working under python3
        # and be prepared to catch the errors.
        try:
            enc_payload = urllib.parse.urlencode({"clientraw": payload}).encode('utf-8')
            _response = urllib.request.urlopen(request,
                                               data=enc_payload,
                                               timeout=self.timeout)
        except UnicodeEncodeError:
            enc_payload = urllib.parse.urlencode({"clientraw": payload.encode('utf-8')})
            _response = urllib.request.urlopen(request,
                                               data=enc_payload,
                                               timeout=self.timeout)
        return _response

    def write_data(self, data):
        """Write the clientraw.txt file.

        Takes a string containing the clientraw.txt data and writes it to file.

        Inputs:
            data:   clientraw.txt data string
        """

        with open(self.rtcr_path_file, "w", encoding='utf-8') as f:
            f.write(data)
            f.write(u'\n')

    def calculate(self, packet):
        """Calculate the raw clientraw numeric fields.

        Input:
            packet: a cached loop data packet

        Returns:
            Dictionary containing the raw numeric clientraw.txt elements.
        """

        # convert out packet to METRICWX
        packet_wx = weewx.units.to_std_system(packet, weewx.METRICWX)
        # obtain the unit and unit groups for the buffer obs we will use
        speed_unit, speed_group = getStandardUnitType(self.buffer.unit_system,
                                                      'windSpeed')
        temp_unit, temp_group = getStandardUnitType(self.buffer.unit_system,
                                                    'outTemp')
        rain_unit, rain_group = getStandardUnitType(self.buffer.unit_system,
                                                    'rain')
        rainrate_unit, rainrate_group = getStandardUnitType(self.buffer.unit_system,
                                                            'rainRate')
        press_unit, press_group = getStandardUnitType(self.buffer.unit_system,
                                                      'pressure')
        dist_unit, dist_group = getStandardUnitType(self.buffer.unit_system,
                                                    'windrun')
        # get an empty dict for our results
        data = dict()
        # preamble
        data[0] = '12345'
        # 001 - avg speed (knots)
        if 'windSpeed' in self.buffer:
            av_speed = self.buffer['windSpeed'].history_avg(packet_wx['dateTime'],
                                                            age=self.avgspeed_period)

            av_speed_vt = ValueTuple(av_speed, speed_unit, speed_group)
            try:
                av_speed = convert(av_speed_vt, 'knot').value
            except KeyError:
                av_speed = None
        else:
            av_speed = None
        data[1] = av_speed if av_speed is not None else 0.0
        # 002 - gust (knots)
        if 'windSpeed' in self.buffer:
            if self.gust_period > 0:
                _gust = self.buffer['windSpeed'].history_max(packet_wx['dateTime'],
                                                             age=self.gust_period).value
            else:
                _gust = self.buffer['windSpeed'].last
            gust_vt = ValueTuple(_gust, speed_unit, speed_group)
            try:
                gust = convert(gust_vt, 'knot').value
            except KeyError:
                gust = None
        else:
            gust = None
        data[2] = gust if gust is not None else 0.0
        # 003 - windDir
        # do we have a non-None direction
        if packet_wx['windDir'] is None:
            # direction is None, so what are we to use
            if self.null_dir == 'LAST':
                # we should use the last known direction, see if we can get it
                # from our buffer
                try:
                    _dir = self.buffer['windDir'].last
                except KeyError:
                    # could not get last known direction from the buffer so use
                    # our default
                    _dir = RealtimeClientrawThread.DEFAULT_DIR
            else:
                # we have a user specified default to use so use it
                _dir = self.null_dir
        else:
            # we have a direction in the packet so use it
            _dir = packet_wx['windDir']
        data[3] = _dir
        # 004 - outTemp (Celsius)
        data[4] = packet_wx['outTemp'] if packet_wx['outTemp'] is not None else 0.0
        # 005 - outHumidity
        data[5] = packet_wx['outHumidity'] if packet_wx['outHumidity'] is not None else 0.0
        # 006 - barometer(hPa)
        data[6] = packet_wx['barometer'] if packet_wx['barometer'] is not None else 0.0
        # 007 - daily rain (mm)
        if 'dayRain' in packet_wx:
            day_rain_vt = ValueTuple(packet_wx['dayRain'], 'mm', 'group_rain')
        elif 'rain' in self.buffer:
            day_rain_vt = ValueTuple(self.buffer['rain'].day_sum,
                                     rain_unit,
                                     rain_group)
        else:
            day_rain_vt = ValueTuple(None, 'mm', 'group_rain')
        day_rain = convert(day_rain_vt, 'mm').value
        data[7] = day_rain if day_rain is not None else 0.0
        # 008 - monthly rain
        month_rain_vt = getattr(self, 'month_rain_vt',
                                ValueTuple(0, 'mm', 'group_rain'))
        try:
            month_rain = convert(month_rain_vt, 'mm').value
        except KeyError:
            month_rain = None
        if month_rain and 'rain' in self.buffer:
            month_rain += self.buffer['rain'].interval_sum
        elif 'rain' in self.buffer:
            month_rain = self.buffer['rain'].interval_sum
        else:
            month_rain = None
        data[8] = month_rain if month_rain is not None else 0.0
        # 009 - yearly rain
        year_rain_vt = getattr(self, 'year_rain_vt',
                               ValueTuple(0, 'mm', 'group_rain'))
        try:
            year_rain = convert(year_rain_vt, 'mm').value
        except KeyError:
            year_rain = None
        if year_rain and 'rain' in self.buffer:
            year_rain += self.buffer['rain'].interval_sum
        elif 'rain' in self.buffer:
            year_rain = self.buffer['rain'].interval_sum
        else:
            year_rain = None
        data[9] = year_rain if year_rain is not None else 0.0
        # 010 - rain rate (mm per minute - not hour)
        data[10] = packet_wx['rainRate'] / 60.0 if packet_wx['rainRate'] is not None else 0.0
        # 011 - max daily rainRate (mm per minute - not hour)
        if 'rainRate' in self.buffer:
            rain_rate_th_vt = ValueTuple(self.buffer['rainRate'].day_max,
                                         rainrate_unit,
                                         rainrate_group)
        else:
            rain_rate_th_vt = ValueTuple(None, rainrate_unit, rainrate_group)
        rain_rate_th = convert(rain_rate_th_vt, 'mm_per_hour').value
        data[11] = rain_rate_th/60.0 if rain_rate_th is not None else 0.0
        # 012 - inTemp (Celsius)
        data[12] = packet_wx['inTemp'] if packet_wx['inTemp'] is not None else 0.0
        # 013 - inHumidity
        data[13] = packet_wx['inHumidity'] if packet_wx['inHumidity'] is not None else 0.0
        # 014 - soil temperature (Celsius)
        if self.soil_temp and self.soil_temp in packet_wx:
            soil_temp = packet_wx[self.soil_temp]
        else:
            soil_temp = None
        data[14] = soil_temp if soil_temp is not None else 100.0
        # TODO. Need to implement field 15
        # 015 - Forecast Icon
        data[15] = 0
        # 016 - WMR968 extra temperature (Celsius) - will not implement
        data[16] = 0.0
        # 017 - WMR968 extra humidity (Celsius) - will not implement
        data[17] = 0.0
        # 018 - WMR968 extra sensor (Celsius) - will not implement
        data[18] = 0.0
        # 019 - yesterday rain (mm)
        yest_rain_vt = getattr(self, 'yest_rain_vt',
                               ValueTuple(0, 'mm', 'group_rain'))
        try:
            yest_rain = convert(yest_rain_vt, 'mm').value
        except KeyError:
            yest_rain = None
        data[19] = yest_rain if yest_rain is not None else 0.0
        # 020 - extra temperature sensor 1 (Celsius)
        if self.extra_temp1 and self.extra_temp1 in packet_wx:
            extra_temp1 = packet_wx[self.extra_temp1]
        else:
            extra_temp1 = None
        data[20] = extra_temp1 if extra_temp1 is not None else -100.0
        # 021 - extra temperature sensor 2 (Celsius)
        if self.extra_temp2 and self.extra_temp2 in packet_wx:
            extra_temp2 = packet_wx[self.extra_temp2]
        else:
            extra_temp2 = None
        data[21] = extra_temp2 if extra_temp2 is not None else -100.0
        # 022 - extra temperature sensor 3 (Celsius)
        if self.extra_temp3 and self.extra_temp3 in packet_wx:
            extra_temp3 = packet_wx[self.extra_temp3]
        else:
            extra_temp3 = None
        data[22] = extra_temp3 if extra_temp3 is not None else -100.0
        # 023 - extra temperature sensor 4 (Celsius)
        if self.extra_temp4 and self.extra_temp4 in packet_wx:
            extra_temp4 = packet_wx[self.extra_temp4]
        else:
            extra_temp4 = None
        data[23] = extra_temp4 if extra_temp4 is not None else -100.0
        # 024 - extra temperature sensor 5 (Celsius)
        if self.extra_temp5 and self.extra_temp5 in packet_wx:
            extra_temp5 = packet_wx[self.extra_temp5]
        else:
            extra_temp5 = None
        data[24] = extra_temp5 if extra_temp5 is not None else -100.0
        # 025 - extra temperature sensor 6 (Celsius)
        if self.extra_temp6 and self.extra_temp6 in packet_wx:
            extra_temp6 = packet_wx[self.extra_temp6]
        else:
            extra_temp6 = None
        data[25] = extra_temp6 if extra_temp6 is not None else -100.0
        # 026 - extra humidity sensor 1
        if self.extra_hum1 and self.extra_hum1 in packet_wx:
            extra_hum1 = packet_wx[self.extra_hum1]
        else:
            extra_hum1 = None
        data[26] = extra_hum1 if extra_hum1 is not None else -100
        # 027 - extra humidity sensor 2
        if self.extra_hum2 and self.extra_hum2 in packet_wx:
            extra_hum2 = packet_wx[self.extra_hum2]
        else:
            extra_hum2 = None
        data[27] = extra_hum2 if extra_hum2 is not None else -100
        # 028 - extra humidity sensor 3
        if self.extra_hum3 and self.extra_hum3 in packet_wx:
            extra_hum3 = packet_wx[self.extra_hum3]
        else:
            extra_hum3 = None
        data[28] = extra_hum3 if extra_hum3 is not None else -100
        # 029 - hour
        data[29] = time.strftime('%H', time.localtime(packet_wx['dateTime']))
        # 030 - minute
        data[30] = time.strftime('%M', time.localtime(packet_wx['dateTime']))
        # 031 - seconds
        data[31] = time.strftime('%S', time.localtime(packet_wx['dateTime']))
        # 032 - station name
        hms_string = time.strftime(self.long_time_fmt,
                                   time.localtime(packet_wx['dateTime']))
        # to maintain fidelity of station names that include dashes and spaces
        # replace any dashes with en dashes and replace any spaces with
        # underscores
        loc_string = self.location.replace('-', '&ndash;')
        data[32] = '-'.join([loc_string.replace(' ', '_'), hms_string])
        # 033 - dallas lightning count - will not implement
        data[33] = 0
        # 034 - Solar Reading - used as 'solar percent' in Saratoga dashboards
        percent = None
        if 'radiation' in packet_wx and 'maxSolarRad' in packet_wx:
            try:
                percent = 100.0 * packet_wx['radiation'] / packet_wx['maxSolarRad']
            except (ZeroDivisionError, TypeError):
                # Perhaps it's nighttime, or one or both of radiation and
                # maxSolarRad are None. We can ignore as percent will
                # remain None
                pass
        data[34] = percent if percent is not None else 0.0
        # 035 - Day
        data[35] = time.strftime('%-d', time.localtime(packet_wx['dateTime']))
        # 036 - Month
        data[36] = time.strftime('%-m', time.localtime(packet_wx['dateTime']))
        # 037 - WMR968/200 battery 1 - will not implement
        data[37] = 0.0
        # 038 - WMR968/200 battery 2 - will not implement
        data[38] = 0.0
        # 039 - WMR968/200 battery 3 - will not implement
        data[39] = 100
        # 040 - WMR968/200 battery 4 - will not implement
        data[40] = 100
        # 041 - WMR968/200 battery 5 - will not implement
        data[41] = 100
        # 042 - WMR968/200 battery 6 - will not implement
        data[42] = 100
        # 043 - WMR968/200 battery 7 - will not implement
        data[43] = 100
        # 044 - windchill (Celsius)
        data[44] = packet_wx['windchill'] if packet_wx['windchill'] is not None else 0.0
        # 045 - humidex (Celsius)
        if 'humidex' in packet_wx:
            humidex = packet_wx['humidex']
        elif 'outTemp' in packet_wx and 'outHumidity' in packet_wx:
            humidex = weewx.wxformulas.humidexC(packet_wx['outTemp'],
                                                packet_wx['outHumidity'])
        else:
            humidex = None
        data[45] = humidex if humidex is not None else 0.0
        # 046 - maximum day temperature (Celsius)
        if 'outTemp' in self.buffer:
            temp_th_vt = ValueTuple(self.buffer['outTemp'].day_max,
                                    temp_unit,
                                    temp_group)
        else:
            temp_th_vt = ValueTuple(None, temp_unit, temp_group)
        temp_th = convert(temp_th_vt, 'degree_C').value
        data[46] = temp_th if temp_th is not None else 0.0
        # 047 - minimum day temperature (Celsius)
        if 'outTemp' in self.buffer:
            temp_tl_vt = ValueTuple(self.buffer['outTemp'].day_min,
                                    temp_unit,
                                    temp_group)
        else:
            temp_tl_vt = ValueTuple(None, temp_unit, temp_group)
        temp_tl = convert(temp_tl_vt, 'degree_C').value
        data[47] = temp_tl if temp_tl is not None else 0.0
        # TODO. Need to implement field 48
        # 048 - icon type
        data[48] = 0
        # TODO. Need to implement field 49
        # 049 - weather description
        data[49] = '---'
        # 050 - barometer trend (hPa)
        baro_vt = ValueTuple(packet_wx['barometer'], 'hPa', 'group_pressure')
        baro_trend = calc_trend('barometer', baro_vt, self.db_manager,
                                packet_wx['dateTime'] - self.baro_trend_period,
                                self.grace)
        data[50] = baro_trend if baro_trend is not None else 0.0
        # 051-070 incl - windspeed hour 01-20 incl (knots) - will not implement
        for h in range(0, 20):
            data[51+h] = 0.0
        # 071 - maximum wind gust today
        if 'windSpeed' in self.buffer:
            wind_gust_tm = self.buffer['windSpeed'].day_max
        else:
            wind_gust_tm = 0.0
        # our speeds are in m/s need to convert to knots
        wind_gust_tm_vt = ValueTuple(wind_gust_tm, speed_unit, speed_group)
        try:
            wind_gust_tm = convert(wind_gust_tm_vt, 'knot').value
        except KeyError:
            wind_gust_tm = None
        data[71] = wind_gust_tm if wind_gust_tm is not None else 0.0
        # 072 - dewpoint (Celsius)
        data[72] = packet_wx['dewpoint'] if packet_wx['dewpoint'] is not None else 0.0
        # 073 - cloud height (foot)
        if 'cloudbase' in packet_wx:
            cb = packet_wx['cloudbase']
        else:
            if 'outTemp' in packet_wx and 'outHumidity' in packet_wx:
                cb = weewx.wxformulas.cloudbase_Metric(packet_wx['outTemp'],
                                                       packet_wx['outHumidity'],
                                                       self.altitude_m)
            else:
                cb = None
        # our altitudes are in metres, need to convert to feet
        cloudbase_vt = ValueTuple(cb, 'meter', 'group_altitude')
        try:
            cloudbase = convert(cloudbase_vt, 'foot').value
        except KeyError:
            cloudbase = None
        data[73] = cloudbase if cloudbase is not None else 0.0
        # 074 -  date
        data[74] = time.strftime(self.date_fmt, time.localtime(packet_wx['dateTime']))
        # 075 - maximum day humidex (Celsius)
        # 076 - minimum day humidex (Celsius)
        if 'humidex' in self.buffer:
            humidex_th_vt = ValueTuple(self.buffer['humidex'].day_max,
                                       temp_unit,
                                       temp_group)
            humidex_tl_vt = ValueTuple(self.buffer['humidex'].day_min,
                                       temp_unit,
                                       temp_group)
        else:
            humidex_th_vt = ValueTuple(None, temp_unit, temp_group)
            humidex_tl_vt = ValueTuple(None, temp_unit, temp_group)
        humidex_th = convert(humidex_th_vt, 'degree_C').value
        humidex_tl = convert(humidex_tl_vt, 'degree_C').value
        data[75] = humidex_th if humidex_th is not None else 0.0
        data[76] = humidex_tl if humidex_tl is not None else 0.0
        # 077 - maximum day windchill (Celsius)
        # 078 - minimum day windchill (Celsius)
        if 'windchill' in self.buffer:
            windchill_th_vt = ValueTuple(self.buffer['windchill'].day_max,
                                         temp_unit,
                                         temp_group)
            windchill_tl_vt = ValueTuple(self.buffer['windchill'].day_min,
                                         temp_unit,
                                         temp_group)
        else:
            windchill_th_vt = ValueTuple(None, temp_unit, temp_group)
            windchill_tl_vt = ValueTuple(None, temp_unit, temp_group)
        windchill_th = convert(windchill_th_vt, 'degree_C').value
        windchill_tl = convert(windchill_tl_vt, 'degree_C').value
        data[77] = windchill_th if windchill_th is not None else 0.0
        data[78] = windchill_tl if windchill_tl is not None else 0.0
        # 079 - Davis VP UV
        data[79] = packet_wx['UV'] if packet_wx['UV'] is not None else 0
        # 080-089 - hour wind speed 01-10 - will not implement
        for h in range(0, 10):
            data[80+h] = 0.0
        # 090 - hour temperature 01 (Celsius)
        hour_ago_outtemp_vt = getattr(self, 'hour_ago_outTemp_vt',
                                      ValueTuple(None, 'degree_C', 'group_temperature'))
        try:
            hour_ago_outtemp = convert(hour_ago_outtemp_vt, 'degree_C').value
        except KeyError:
            hour_ago_outtemp = None
        data[90] = hour_ago_outtemp if hour_ago_outtemp is not None else 0.0
        # 091-099 - hour temperature 02-10 (Celsius) - will not implement
        for h in range(0, 9):
            data[91+h] = 0.0
        # 100-109 - hour rain 01-10 (mm) - will not implement
        for h in range(0, 10):
            data[100+h] = 0.0
        # 110 - maximum day heatindex (Celsius)
        # 111 - minimum day heatindex (Celsius)
        if 'heatindex' in self.buffer:
            heatindex_th_vt = ValueTuple(self.buffer['heatindex'].day_max,
                                         temp_unit,
                                         temp_group)
            heatindex_tl_vt = ValueTuple(self.buffer['heatindex'].day_min,
                                         temp_unit,
                                         temp_group)
        else:
            heatindex_th_vt = ValueTuple(None, temp_unit, temp_group)
            heatindex_tl_vt = ValueTuple(None, temp_unit, temp_group)
        heatindex_th = convert(heatindex_th_vt, 'degree_C').value
        heatindex_tl = convert(heatindex_tl_vt, 'degree_C').value
        data[110] = heatindex_th if heatindex_th is not None else 0.0
        data[111] = heatindex_tl if heatindex_tl is not None else 0.0
        # 112 - heatindex (Celsius)
        data[112] = packet_wx['heatindex'] if packet_wx['heatindex'] is not None else 0.0
        # 113 - maximum average speed (knot)
        if 'windSpeed' in self.buffer:
            windspeed_tm_loop = self.buffer['windSpeed'].day_max
        else:
            windspeed_tm_loop = 0.0
        if 'windSpeed' in self.day_stats:
            windspeed_tm = self.day_stats['windSpeed'].max
        else:
            windspeed_tm = 0.0
        windspeed_tm = weeutil.weeutil.max_with_none([windspeed_tm, windspeed_tm_loop])
        windspeed_tm_vt = ValueTuple(windspeed_tm, speed_unit, speed_group)
        try:
            windspeed_tm = convert(windspeed_tm_vt, 'knot').value
        except KeyError:
            windspeed_tm = None
        data[113] = windspeed_tm if windspeed_tm is not None else 0.0
        # 114 - lightning count in last minute - will not implement
        data[114] = 0
        # 115 - time of last lightning strike - will not implement
        data[115] = '---'
        # 116 - date of last lightning strike - will not implement
        data[116] = '---'
        # 117 - wind average direction
        data[117] = self.buffer['wind'].vec_dir
        # 118 - nexstorm distance - will not implement
        data[118] = 0.0
        # 119 - nexstorm bearing - will not implement
        data[119] = 0.0
        # 120 - extra temperature sensor 7 (Celsius)
        if self.extra_temp7 and self.extra_temp7 in packet_wx:
            extra_temp7 = packet_wx[self.extra_temp7]
        else:
            extra_temp7 = None
        data[120] = extra_temp7 if extra_temp7 is not None else -100
        # 121 - extra temperature sensor 8 (Celsius)
        if self.extra_temp8 and self.extra_temp8 in packet_wx:
            extra_temp8 = packet_wx[self.extra_temp8]
        else:
            extra_temp8 = None
        data[121] = extra_temp8 if extra_temp8 is not None else -100
        # 122 - extra humidity sensor 4
        if self.extra_hum4 and self.extra_hum4 in packet_wx:
            extra_hum4 = packet_wx[self.extra_hum4]
        else:
            extra_hum4 = None
        data[122] = extra_hum4 if extra_hum4 is not None else -100
        # 123 - extra humidity sensor 5
        if self.extra_hum5 and self.extra_hum5 in packet_wx:
            extra_hum5 = packet_wx[self.extra_hum5]
        else:
            extra_hum5 = None
        data[123] = extra_hum5 if extra_hum5 is not None else -100
        # 124 - extra humidity sensor 6
        if self.extra_hum6 and self.extra_hum6 in packet_wx:
            extra_hum6 = packet_wx[self.extra_hum6]
        else:
            extra_hum6 = None
        data[124] = extra_hum6 if extra_hum6 is not None else -100
        # 125 - extra humidity sensor 7
        if self.extra_hum7 and self.extra_hum7 in packet_wx:
            extra_hum7 = packet_wx[self.extra_hum7]
        else:
            extra_hum7 = None
        data[125] = extra_hum7 if extra_hum7 is not None else -100
        # 126 - extra humidity sensor 8
        if self.extra_hum8 and self.extra_hum8 in packet_wx:
            extra_hum8 = packet_wx[self.extra_hum8]
        else:
            extra_hum8 = None
        data[126] = extra_hum8 if extra_hum8 is not None else -100
        # 127 - VP solar
        data[127] = packet_wx['radiation'] if packet_wx['radiation'] is not None else 0.0
        # 128 - maximum inTemp (Celsius)
        # 129 - minimum inTemp (Celsius)
        if 'inTemp' in self.buffer:
            intemp_th_vt = ValueTuple(self.buffer['inTemp'].day_max,
                                      temp_unit,
                                      temp_group)
            intemp_tl_vt = ValueTuple(self.buffer['inTemp'].day_min,
                                      temp_unit,
                                      temp_group)
        else:
            intemp_th_vt = ValueTuple(None, temp_unit, temp_group)
            intemp_tl_vt = ValueTuple(None, temp_unit, temp_group)
        intemp_th = convert(intemp_th_vt, 'degree_C').value
        intemp_tl = convert(intemp_tl_vt, 'degree_C').value
        data[128] = intemp_th if intemp_th is not None else 0.0
        data[129] = intemp_tl if intemp_tl is not None else 0.0
        # 130 - appTemp (Celsius)
        if 'appTemp' in packet_wx:
            app_temp = packet_wx['appTemp']
        elif 'windSpeed' in packet_wx and 'outTemp' in packet_wx and 'outHumidity' in packet_wx:
            app_temp = weewx.wxformulas.apptempC(packet_wx['outTemp'],
                                                 packet_wx['outHumidity'],
                                                 packet_wx['windSpeed'])
        else:
            app_temp = None
        data[130] = app_temp if app_temp is not None else 0.0
        # 131 - maximum barometer (hPa)
        # 132 - minimum barometer (hPa)
        if 'barometer' in self.buffer:
            barometer_th_vt = ValueTuple(self.buffer['barometer'].day_max,
                                         press_unit,
                                         press_group)
            barometer_tl_vt = ValueTuple(self.buffer['barometer'].day_min,
                                         press_unit,
                                         press_group)
        else:
            barometer_th_vt = ValueTuple(None, press_unit, press_group)
            barometer_tl_vt = ValueTuple(None, press_unit, press_group)
        barometer_th = convert(barometer_th_vt, 'hPa').value
        barometer_tl = convert(barometer_tl_vt, 'hPa').value
        data[131] = barometer_th if barometer_th is not None else 0.0
        data[132] = barometer_tl if barometer_tl is not None else 0.0
        # 133 - maximum windGust last hour (knot)
        hour_gust_vt = getattr(self, 'hour_gust_vt',
                               ValueTuple(0.0, 'knot', 'group_speed'))
        if hour_gust_vt.value is not None:
            hour_gust = convert(hour_gust_vt, 'knot').value
        else:
            hour_gust = 0.0
        if hour_gust_vt.value and 'windSpeed' in self.buffer:
            windspeed_tm_loop_vt = ValueTuple(self.buffer['windSpeed'].day_max,
                                              speed_unit,
                                              speed_group)
            windspeed_tm_loop = convert(windspeed_tm_loop_vt, 'knot').value
        else:
            windspeed_tm_loop = None
        windgust60 = weeutil.weeutil.max_with_none([hour_gust,
                                                    windspeed_tm_loop])
        data[133] = windgust60 if windgust60 is not None else 0.0
        # 134 - maximum windGust in last hour time
        hour_gust_ts = getattr(self, 'hour_gust_ts', None)
        if 'windSpeed' in self.buffer:
            buffer_ot = self.buffer['windSpeed'].history_max(packet_wx['dateTime'])
        else:
            buffer_ot = ObsTuple(None, None)
        buffer_ot_knot = convert(ValueTuple(buffer_ot.value, speed_unit, speed_group),
                                 'knot').value
        if hour_gust is None:
            windgust60_ts = buffer_ot.ts
        elif buffer_ot.value is None:
            windgust60_ts = hour_gust_ts
        elif buffer_ot_knot > windgust60:
            windgust60_ts = buffer_ot.ts
        else:
            windgust60_ts = hour_gust_ts
        data[134] = time.strftime(self.short_time_fmt, time.localtime(windgust60_ts)) if \
            windgust60_ts is not None else '00:00'
        # 135 - maximum windGust today time
        if 'windSpeed' in self.buffer:
            t_windgust_tm_ts = self.buffer['windSpeed'].day_maxtime
            if t_windgust_tm_ts is not None:
                t_windgust_tm = time.localtime(t_windgust_tm_ts)
            else:
                t_windgust_tm = time.localtime(packet_wx['dateTime'])
        else:
            t_windgust_tm = time.localtime(packet_wx['dateTime'])
        data[135] = time.strftime(self.short_time_fmt, t_windgust_tm)
        # 136 - maximum day appTemp (Celsius)
        # 137 - minimum day appTemp (Celsius)
        if 'appTemp' in self.buffer:
            apptemp_th_vt = ValueTuple(self.buffer['appTemp'].day_max,
                                       temp_unit,
                                       temp_group)
            apptemp_tl_vt = ValueTuple(self.buffer['appTemp'].day_min,
                                       temp_unit,
                                       temp_group)
        else:
            apptemp_th_vt = ValueTuple(None, temp_unit, temp_group)
            apptemp_tl_vt = ValueTuple(None, temp_unit, temp_group)
        apptemp_th = convert(apptemp_th_vt, 'degree_C').value
        apptemp_tl = convert(apptemp_tl_vt, 'degree_C').value
        data[136] = apptemp_th if apptemp_th is not None else 0.0
        data[137] = apptemp_tl if apptemp_tl is not None else 0.0
        # 138 - maximum day dewpoint (Celsius)
        # 139 - minimum day dewpoint (Celsius)
        if 'dewpoint' in self.buffer:
            dewpoint_th_vt = ValueTuple(self.buffer['dewpoint'].day_max,
                                        temp_unit,
                                        temp_group)
            dewpoint_tl_vt = ValueTuple(self.buffer['dewpoint'].day_min,
                                        temp_unit,
                                        temp_group)
        else:
            dewpoint_th_vt = ValueTuple(None, temp_unit, temp_group)
            dewpoint_tl_vt = ValueTuple(None, temp_unit, temp_group)
        dewpoint_th = convert(dewpoint_th_vt, 'degree_C').value
        dewpoint_tl = convert(dewpoint_tl_vt, 'degree_C').value
        data[138] = dewpoint_th if dewpoint_th is not None else 0.0
        data[139] = dewpoint_tl if dewpoint_tl is not None else 0.0
        # 140 - maximum windGust in last minute (knot)
        if 'windSpeed' in self.buffer:
            _gust1_ot = self.buffer['windSpeed'].history_max(packet_wx['dateTime'],
                                                             age=60)
            gust1_vt = ValueTuple(_gust1_ot.value, speed_unit, speed_group)
            try:
                gust1 = convert(gust1_vt, 'knot').value
            except KeyError:
                gust1 = None
        else:
            gust1 = None
        data[140] = gust1 if gust1 is not None else 0.0
        # 141 - current year
        data[141] = time.strftime('%Y', time.localtime(packet_wx['dateTime']))
        # 142 - THSWS - will not implement
        data[142] = 0.0
        # 143 - outTemp trend (logic)
        temp_vt = ValueTuple(packet_wx['outTemp'], 'degree_C', 'group_temperature')
        temp_trend = calc_trend('outTemp', temp_vt, self.db_manager,
                                packet_wx['dateTime'] - self.temp_trend_period,
                                self.grace)
        if temp_trend is None or temp_trend == 0:
            _trend = '0'
        elif temp_trend > 0:
            _trend = '+1'
        else:
            _trend = '-1'
        data[143] = _trend
        # 144 - outHumidity trend (logic)
        hum_vt = ValueTuple(packet_wx['outHumidity'], 'percent', 'group_percent')
        hum_trend = calc_trend('outHumidity', hum_vt, self.db_manager,
                               packet_wx['dateTime'] - self.humidity_trend_period,
                               self.grace)
        if hum_trend is None or hum_trend == 0:
            _trend = '0'
        elif hum_trend > 0:
            _trend = '+1'
        else:
            _trend = '-1'
        data[144] = _trend
        # 145 - humidex trend (logic)
        humidex_vt = ValueTuple(packet_wx['humidex'], 'degree_C', 'group_temperature')
        humidex_trend = calc_trend('humidex', humidex_vt, self.db_manager,
                                   packet_wx['dateTime'] - self.humidex_trend_period,
                                   self.grace)
        if humidex_trend is None or humidex_trend == 0:
            _trend = '0'
        elif humidex_trend > 0:
            _trend = '+1'
        else:
            _trend = '-1'
        data[145] = _trend
        # 146-155 - hour wind direction 01-10 - will not implement
        for h in range(0, 10):
            data[146+h] = 0.0
        # 156 - leaf wetness
        if self.leaf_wet and self.leaf_wet in packet_wx:
            leaf_wet = packet_wx[self.leaf_wet]
        else:
            leaf_wet = None
        data[156] = leaf_wet if leaf_wet is not None else 0.0
        # 157 - soil moisture
        if self.soil_moist and self.soil_moist in packet_wx:
            soil_moist = packet_wx[self.soil_moist]
        else:
            soil_moist = None
        data[157] = soil_moist if soil_moist is not None else 255.0
        # 158 - 10-minute average wind speed (knot)
        if 'windSpeed' in self.buffer:
            av_speed10 = self.buffer['windSpeed'].history_avg(packet_wx['dateTime'],
                                                              age=600)
            av_speed10_vt = ValueTuple(av_speed10, speed_unit, speed_group)
            try:
                av_speed10 = convert(av_speed10_vt, 'knot').value
            except KeyError:
                av_speed10 = None
        else:
            av_speed10 = None
        data[158] = av_speed10 if av_speed10 is not None else 0.0
        # 159 - wet bulb temperature (Celsius)
        wb = packet_wx.get('wet_bulb')
        data[159] = wb if wb is not None else 0.0
        # 160 - latitude (-ve for south)
        data[160] = self.latitude
        # 161 -  longitude (-ve for east)
        data[161] = -1 * self.longitude
        # 162 - 9am reset rainfall total (mm)
        nineam_rain_vt = ValueTuple(self.buffer['rain'].nineam_sum,
                                    rain_unit,
                                    rain_group)
        data[162] = convert(nineam_rain_vt, 'mm').value
        # 163 - high day outHumidity
        # 164 - low day outHumidity
        if 'outHumidity' in self.buffer:
            outhumidity_th = self.buffer['outHumidity'].day_max
            outhumidity_tl = self.buffer['outHumidity'].day_min
        else:
            outhumidity_th = None
            outhumidity_tl = None
        data[163] = outhumidity_th if outhumidity_th is not None else 0.0
        data[164] = outhumidity_tl if outhumidity_tl is not None else 0.0
        # 165 - midnight rain reset total (mm)
        if 'dayRain' in packet_wx:
            day_rain = packet_wx['dayRain']
        elif 'rain' in self.buffer:
            day_rain_vt = ValueTuple(self.buffer['rain'].day_sum,
                                     rain_unit,
                                     rain_group)
            day_rain = convert(day_rain_vt, 'mm').value
        else:
            day_rain = None
        data[165] = day_rain if day_rain is not None else 0.0
        # 166 - low day windchill time
        if 'windchill' in self.buffer:
            t_windchill_tm_ts = self.buffer['windchill'].day_mintime
            if t_windchill_tm_ts is not None:
                t_windchill_tm = time.localtime(t_windchill_tm_ts)
            else:
                t_windchill_tm = time.localtime(packet_wx['dateTime'])
        else:
            t_windchill_tm = time.localtime(packet_wx['dateTime'])
        data[166] = time.strftime(self.short_time_fmt, t_windchill_tm)
        # 167 - Current Cost Channel 1 - will not implement
        data[167] = 0.0
        # 168 - Current Cost Channel 2 - will not implement
        data[168] = 0.0
        # 169 - Current Cost Channel 3 - will not implement
        data[169] = 0.0
        # 170 - Current Cost Channel 4 - will not implement
        data[170] = 0.0
        # 171 - Current Cost Channel 5 - will not implement
        data[171] = 0.0
        # 172 - Current Cost Channel 6 - will not implement
        data[172] = 0.0
        # 173 - day windrun
        if 'windrun' in self.buffer:
            day_windrun_vt = ValueTuple(self.buffer['windrun'].day_sum,
                                        dist_unit,
                                        dist_group)
        else:
            day_windrun_vt = ValueTuple(None, 'km', 'group_distance')
        day_windrun = convert(day_windrun_vt, 'km').value
        data[173] = day_windrun if day_windrun is not None else 0.0
        # 174 - Time of daily max temp
        if 'outTemp' in self.buffer:
            t_outtemp_tm_ts = self.buffer['outTemp'].day_maxtime
            if t_outtemp_tm_ts is not None:
                t_outtemp_tm = time.localtime(t_outtemp_tm_ts)
            else:
                t_outtemp_tm = time.localtime(packet_wx['dateTime'])
        else:
            t_outtemp_tm = time.localtime(packet_wx['dateTime'])
        data[174] = time.strftime(self.short_time_fmt, t_outtemp_tm)
        # 175 - Time of daily min temp
        if 'outTemp' in self.buffer:
            t_outtemp_tm_ts = self.buffer['outTemp'].day_mintime
            if t_outtemp_tm_ts is not None:
                t_outtemp_tm = time.localtime(t_outtemp_tm_ts)
            else:
                t_outtemp_tm = time.localtime(packet_wx['dateTime'])
        else:
            t_outtemp_tm = time.localtime(packet_wx['dateTime'])
        data[175] = time.strftime(self.short_time_fmt, t_outtemp_tm)
        # TODO. Need to verify #176 calculation
        # 176 - 10 minute average wind direction
        _mag, _dir = self.buffer['wind'].history_vec_avg(packet_wx['dateTime'],
                                                         age=600)
        data[176] = _dir if _dir is not None else 0
        # 177 - record end (WD Version)
        data[177] = '!!WS%s!!' % RTCR_VERSION
        return data

    def create_clientraw_string(self, data):
        """Create the clientraw string from the clientraw data.

        The raw clientraw data is a dict of numbers and strings. This method
        formats each field appropriately and generates the unicode string that
        comprises the clientraw.txt file contents.

        Input:
            data: a dict containing the raw clientraw data

        Returns:
            A unicode string containing the formatted clientraw.txt contents.
        """

        # initialise a list to hold our fields in order
        fields = list()
        # iterate over the number of fields we know how to format
        for field_num in range(len(self.field_formats)):
            # format the field using the lookup result from the fields_format
            # dict and append it to the field list
            fields.append(self.format(data[field_num],
                                      self.field_formats[field_num]))
        # join the fields with a space between fields and force the result to
        # be a unicode string
        return six.ensure_text(' '.join(fields))

    @staticmethod
    def format(data, places=None):
        """Format a number as a string with a given number of decimal places.

        Inputs:
            data:   The data to be formatted. May be a number or string
                    representation of a number.
            places: The number of decimal places to which the data will be
                    rounded.

        Returns:
            A string containing the data rounded and formatted to places
            decimal places. If data is None '0.0' is returned. If places is
            None or omitted the data is returned as received but converted to a
            string.
        """

        # Attempt to convert our data to a string, this will be the result we
        # return if we cannot format as specified. Our data could be a unicode
        # string so be prepared to catch the error.
        try:
            result = str(data)
        except UnicodeEncodeError:
            # our data is a unicode string so coalesce to a six.text_type
            result = six.ensure_text(data)
        # if our data is None then w don't want to return 'None'
        # (str(None) == 'None') so return '0.0' instead
        if data is None:
            result = '0.0'
        # If places is not None then format as a float to 'places' decimal
        # places. Be prepared to catch any errors and pass through our original
        # data.
        elif places is not None:
            try:
                _v = float(data)
                _format = "%%.%df" % places
                result = _format % _v
            except ValueError:
                pass
        # finally return our result
        return result


# ============================================================================
#                             class VectorBuffer
# ============================================================================

class VectorBuffer(object):
    """Class to buffer vector obs."""

    default_init = (None, None, None, None)

    def __init__(self, stats, history=False, sum=False):
        self.last = None
        self.lasttime = None
        if stats:
            self.day_min = stats.min
            self.day_mintime = stats.mintime
            self.day_max = stats.max
            self.day_maxtime = stats.maxtime
        else:
            (self.day_min, self.day_mintime,
             self.day_max, self.day_maxtime) = VectorBuffer.default_init
        if history:
            self.history = []
            self.history_full = False
        if sum:
            if stats:
                self.day_sum = stats.sum
                self.day_xsum = stats.xsum
                self.day_ysum = stats.ysum
            else:
                self.day_sum = 0.0
                self.day_xsum = 0.0
                self.day_ysum = 0.0
            self.nineam_sum = 0.0
            self.interval_sum = 0.0

    def _add_value(self, val, ts, hilo, history, sum):
        """Add a value to my hilo and history stats as required."""

        (w_speed, w_dir) = val
        if w_speed is not None:
            if self.lasttime is None or ts >= self.lasttime:
                self.last = (w_speed, w_dir)
                self.lasttime = ts
            if hilo:
                if self.day_min is None or w_speed < self.day_min:
                    self.day_min = w_speed
                    self.day_mintime = ts
                if self.day_max is None or w_speed > self.day_max:
                    self.day_max = w_speed
                    self.day_maxtime = ts
            if history:
                if w_dir is not None:
                    self.history.append(ObsTuple((w_speed,
                                                  math.cos(math.radians(90.0 - w_dir)),
                                                  math.sin(math.radians(90.0 - w_dir))), ts))
                self.trim_history(ts)
            if sum:
                self.day_sum += w_speed
                if w_dir is not None:
                    self.day_xsum = w_speed * math.cos(math.radians(90.0 - w_dir))
                    self.day_ysum = w_speed * math.sin(math.radians(90.0 - w_dir))

    def day_reset(self):
        """Reset the vector obs buffer."""

        (self.day_min, self.day_mintime,
         self.day_max, self.day_maxtime) = VectorBuffer.default_init
        try:
            self.day_sum = 0.0
        except AttributeError:
            pass

    def nineam_reset(self):
        """Reset the vector obs buffer."""

        self.nineam_sum = 0.0

    def interval_reset(self):
        """Reset the vector obs buffer."""

        self.interval_sum = 0.0

    def trim_history(self, ts):
        """Trim an old data from the history list."""

        if len(self.history) > 0:
            # calc ts of the oldest sample we want to retain
            oldest_ts = ts - MAX_AGE
            # set history_full
            self.history_full = min([a.ts for a in self.history if a.ts is not None]) <= oldest_ts
            # remove any values older than oldest_ts
            self.history = [s for s in self.history if s.ts > oldest_ts]

    def history_max(self, ts, age=MAX_AGE):
        """Return the max value in my history.

        Search the last age seconds of my history for the max value and the
        corresponding timestamp.

        Inputs:
            ts:  the timestamp to start searching back from
            age: the max age of the records being searched

        Returns:
            An object of type ObsTuple where value is a 3 way tuple of
            (value, x component, y component) and ts is the timestamp when
            it occurred.
        """

        born = ts - age
        snapshot = [a for a in self.history if a.ts >= born]
        if len(snapshot) > 0:
            _max = max(snapshot, key=itemgetter(1)[0])
            return ObsTuple(_max[0], _max[1])
        else:
            return ObsTuple(None, None)

    def history_avg(self, ts, age=MAX_AGE):
        """Return the average value in my history.

        Search the last 'age' seconds of my history and calculate the simple
        average of my values.

        Inputs:
            ts:  the timestamp to start searching back from
            age: the max age of the records being searched

        Returns:
            The average value or None if there were no values to average.
        """

        born = ts - age
        snapshot = [a.value[0] for a in self.history if a.ts >= born]
        if len(snapshot) > 0:
            return sum(snapshot)/len(snapshot)
        else:
            return None

    def history_vec_avg(self, ts, age=MAX_AGE):
        """Return the history vector average.

        Search the last 'age' seconds of my history and calculate the vector
        average of my values.

        Inputs:
            ts:  the timestamp to start searching back from
            age: the max age of the records being searched

        Returns:
            The vector average value in polar (magnitude, angle) format. If the
            vector average value cannot be calculated None is returned.
        """

        born = ts - age
        rec = [a.value for a in self.history if a.ts >= born]
        if len(rec) > 0:
            x = 0
            y = 0
            for sample in rec:
                x += sample[0] * sample[1] if sample[1] is not None else 0.0
                y += sample[0] * sample[2] if sample[2] is not None else 0.0
            _dir = 90.0 - math.degrees(math.atan2(y, x))
            if _dir < 0.0:
                _dir += 360.0
            _value = math.sqrt(pow(x, 2) + pow(y, 2))
            return _value, _dir
        else:
            return None, None

    @property
    def vec_dir(self):
        """The day vector average direction."""

        _result = 90.0 - math.degrees(math.atan2(self.day_ysum, self.day_xsum))
        if _result < 0.0:
            _result += 360.0
        return _result


# ============================================================================
#                             class ScalarBuffer
# ============================================================================

class ScalarBuffer(object):
    """Class to buffer scalar obs."""

    default_init = (None, None, None, None)

    def __init__(self, stats, history=False, sum=False):
        self.last = None
        self.lasttime = None
        if stats:
            self.day_min = stats.min
            self.day_mintime = stats.mintime
            self.day_max = stats.max
            self.day_maxtime = stats.maxtime
        else:
            (self.day_min, self.day_mintime,
             self.day_max, self.day_maxtime) = ScalarBuffer.default_init
        if history:
            self.history = []
            self.history_full = False
        if sum:
            if stats:
                self.day_sum = stats.sum
            else:
                self.day_sum = 0.0
            self.nineam_sum = 0.0
            self.interval_sum = 0.0

    def _add_value(self, val, ts, hilo, history, sum):
        """Add a value to my hilo and history stats as required."""

        if val is not None:
            if self.lasttime is None or ts >= self.lasttime:
                self.last = val
                self.lasttime = ts
            if hilo:
                if self.day_min is None or val < self.day_min:
                    self.day_min = val
                    self.day_mintime = ts
                if self.day_max is None or val > self.day_max:
                    self.day_max = val
                    self.day_maxtime = ts
            if history:
                self.history.append(ObsTuple(val, ts))
                self.trim_history(ts)
            if sum:
                self.day_sum += val
                self.nineam_sum += val
                self.interval_sum += val

    def day_reset(self):
        """Reset the scalar obs buffer."""

        (self.day_min, self.day_mintime,
         self.day_max, self.day_maxtime) = ScalarBuffer.default_init
        try:
            self.day_sum = 0.0
        except AttributeError:
            pass

    def nineam_reset(self):
        """Reset the scalar obs buffer."""

        self.nineam_sum = 0.0

    def interval_reset(self):
        """Reset the scalar obs buffer."""

        self.interval_sum = 0.0

    def trim_history(self, ts):
        """Trim an old data from the history list."""

        # calc ts of the oldest sample we want to retain
        oldest_ts = ts - MAX_AGE
        # set history_full
        self.history_full = min([a.ts for a in self.history if a.ts is not None]) <= oldest_ts
        # remove any values older than oldest_ts
        self.history = [s for s in self.history if s.ts > oldest_ts]

    def history_max(self, ts, age=MAX_AGE):
        """Return the max value in my history.

        Search the last age seconds of my history for the max value and the
        corresponding timestamp.

        Inputs:
            ts:  the timestamp to start searching back from
            age: the max age of the records being searched

        Returns:
            An object of type ObsTuple where value is the max value found and
            ts is the timestamp when it occurred.
        """

        born = ts - age
        snapshot = [a for a in self.history if a.ts >= born]
        if len(snapshot) > 0:
            _max = max(snapshot, key=itemgetter(1))
            return ObsTuple(_max[0], _max[1])
        else:
            return ObsTuple(None, None)

    def history_avg(self, ts, age=MAX_AGE):
        """Return my average."""

        if len(self.history) > 0:
            born = ts - age
            rec = [a.value for a in self.history if a.ts >= born]
            if len(rec) > 0:
                return float(sum(rec))/len(rec)
            else:
                return None
        else:
            return None


# ============================================================================
#                             class RtcrBuffer
# ============================================================================

class RtcrBuffer(dict):
    """Class to buffer various loop packet obs.

    Archive based stats are an efficient means of obtaining stats for today.
    However, their use ignores any max/min etc (eg today's max outTemp) that
    'occurs' after the most recent archive record but before the next archive
    record is written to archive. For this reason selected loop data is
    buffered to enable 'loop' stats to be calculated. Accurate daily stats can
    then be determined at any time using a combination of archive based and
    loop based stats.

    The loop based stats are maintained over the period since generation of the
    last archive record. The loop based stats are reset when an archive record
    is generated.

    Selected observations also have a history of loop value, timestamp pairs
    maintained to enable calculation of short term ma/min stats eg 'max
    windSpeed in last minute'. These histories are based on a moving window of
    a given period eg 10 minutes and are updated each time a loop packet is
    received.
    """

    def __init__(self, day_stats):
        """Initialise an instance of our class."""
        # initialize my superclass
        super(RtcrBuffer, self).__init__()

        self.unit_system = day_stats.unit_system
        # seed our buffer objects from day_stats
        for obs_type in [f for f in day_stats if f in MANIFEST]:
            seed_func = seed_functions.get(obs_type, RtcrBuffer.seed_scalar)
            seed_func(self, day_stats[obs_type], obs_type,
                      obs_type in HIST_MANIFEST,
                      obs_type in SUM_MANIFEST)
        self.last_windSpeed_ts = None

    def seed_scalar(self, stats, obs_type, hist, sum):
        """Seed a scalar buffer."""

        self[obs_type] = init_dict.get(obs_type, ScalarBuffer)(stats=stats,
                                                               history=hist,
                                                               sum=sum)

    def seed_vector(self, stats, obs_type, hist, sum):
        """Seed a vector buffer."""

        self[obs_type] = init_dict.get(obs_type, VectorBuffer)(stats=stats,
                                                               history=True,
                                                               sum=True)

    def add_packet(self, packet):
        """Add a packet to the buffer."""

        # the packet is already in our unit system so as long as we have a
        # timestamp add the fields of interest
        if packet['dateTime'] is not None:
            for obs in [f for f in packet if f in MANIFEST]:
                add_func = add_functions.get(obs, RtcrBuffer.add_value)
                add_func(self, packet, obs, obs in HILO_MANIFEST,
                         obs in HIST_MANIFEST, obs in SUM_MANIFEST)

    def add_value(self, packet, obs_type, hilo, hist, sum):
        """Add a value to the buffer."""

        if obs_type not in self:
            self[obs_type] = init_dict.get(obs_type, ScalarBuffer)(stats=None,
                                                                   history=hist,
                                                                   sum=sum)
        self[obs_type]._add_value(packet[obs_type], packet['dateTime'],
                                  hilo, hist, sum)

    def add_wind_value(self, packet, obs_type, hilo, hist, sum):
        """Add a wind value to the buffer."""

        # first add it as 'windSpeed' the scalar
        self.add_value(packet, obs_type, hilo, hist, sum)
        # then add it as a vector 'wind'
        # have we seen 'wind' before, if not create it as a vector
        if 'wind' not in self:
            self['wind'] = VectorBuffer(stats=None, history=True)
        # and add wind as a vector
        self['wind']._add_value((packet.get('windSpeed'), packet.get('windDir')),
                                packet['dateTime'], False, True, False)

    def clean(self, ts):
        """Clean out any old obs from the buffer history."""

        for obs in HIST_MANIFEST:
            self[obs]['history_full'] = min([a.ts for a in self[obs]['history'] if a.ts is not None])
            # calc ts of oldest sample we want to retain
            oldest_ts = ts - MAX_AGE
            # remove any values older than oldest_ts
            self[obs]['history'] = [s for s in self[obs]['history'] if s.ts > oldest_ts]

    def start_of_day_reset(self):
        """Reset our buffer stats at the end of an archive period.

        Reset our hi/lo data but don't touch the history, it might need to be
        kept longer than the end of the archive period.
        """

        for obs in MANIFEST:
            if obs in self:
                self[obs].day_reset()

    def nineam_reset(self):
        """Reset our buffer stats at the end of an archive period.

        Reset our hi/lo data but don't touch the history, it might need to be
        kept longer than the end of the archive period.
        """

        for obs in SUM_MANIFEST:
            self[obs].nineam_reset()


# ============================================================================
#                            Configuration dictionaries
# ============================================================================

init_dict = ListOfDicts({'wind': VectorBuffer})
add_functions = ListOfDicts({'windSpeed': RtcrBuffer.add_wind_value})
seed_functions = ListOfDicts({'wind': RtcrBuffer.seed_vector})


# ============================================================================
#                              class ObsTuple
# ============================================================================

class ObsTuple(tuple):
    """Class to represent and observation in time.

    An observation can be uniquely represented by the value of the observation
    and the time at which it was observed. This can be represented in a 2 way
    tuple called an obs tuple. An obs tuple is useful because its contents can
    be accessed using named attributes.

        Item   attribute   Meaning
        0      value       The observed value eg 19.5
        1      ts          The epoch timestamp that the value was observed
                           eg 1488245400

    It is valid to have an observed value of None.

    It is also valid to have a ts of None (meaning there is no information
    about the time the observation was observed).
    """

    def __new__(cls, *args):
        return tuple.__new__(cls, args)

    @property
    def value(self):
        return self[0]

    @property
    def ts(self):
        return self[1]


# ============================================================================
#                            Class CachedPacket
# ============================================================================

class CachedPacket(object):
    """Class to cache loop packets.

    The purpose of the cache is to ensure that necessary fields for the
    generation of clientraw.txt are continuously available on systems whose
    station emits partial packets. The key requirement is that the field
    exists, the value (numerical or None) is handled by method calculate().
    Method calculate() could be refactored to deal with missing fields, but
    this would result in overly complex code in method calculate().

    The cache consists of a dictionary of value, timestamp pairs where
    timestamp is the timestamp of the packet when obs was last seen and value
    is the value of the obs at that time. None values may be cached.

    A cached loop packet may be obtained by calling the get_packet() method.
    """

    # These fields must be available in every loop packet read from the
    # cache.
    OBS = ["cloudbase", "windDir", "windrun", "inHumidity", "outHumidity",
           "barometer", "radiation", "rain", "rainRate", "windSpeed",
           "appTemp", "dewpoint", "heatindex", "humidex", "inTemp",
           "outTemp", "windchill", "UV"]

    def __init__(self, rec):
        """Initialise our cache object.

        The cache needs to be initialised to include all the fields required by
        method calculate(). We could initialise all field values to None
        (method calculate() will interpret the None values to be '0' in most
        cases). The results may be misleading. We can get ballpark values for
        all fields by priming them with values from the last archive record.
        As the archive may have many more fields than rtcr requires, only prime
        those fields that rtcr requires.

        This approach does have the drawback that in situations where the
        archive unit system is different to the loop packet unit system the
        entire loop packet will be converted each time the cache is updated.
        This is inefficient.
        """

        self.cache = dict()
        # if we have a dateTime field in our record source use that otherwise
        # use the current system time
        _ts = rec['dateTime'] if 'dateTime' in rec else int(time.time() + 0.5)
        # only prime those fields in CachedPacket.OBS
        for _obs in CachedPacket.OBS:
            if _obs in rec and 'usUnits' in rec:
                # only add a value if it exists and we know what units its in
                self.cache[_obs] = {'value': rec[_obs], 'ts': _ts}
            else:
                # otherwise set it to None
                self.cache[_obs] = {'value': None, 'ts': _ts}
        # set the cache unit system if known
        self.unit_system = rec['usUnits'] if 'usUnits' in rec else None

    def update(self, packet, ts):
        """Update the cache from a loop packet.

        If the loop packet uses a different unit system to that of the cache
        then convert the loop packet before adding it to the cache. Update any
        previously seen cache fields and add any loop fields that have not been
        seen before.
        """

        if self.unit_system is None:
            self.unit_system = packet['usUnits']
        elif self.unit_system != packet['usUnits']:
            packet = weewx.units.to_std_system(packet, self.unit_system)
        for obs in [x for x in packet if x not in ['dateTime', 'usUnits']]:
            if packet[obs] is not None:
                self.cache[obs] = {'value': packet[obs], 'ts': ts}

    def get_value(self, obs, ts, max_age):
        """Get an obs value from the cache.

        Return a value for a given obs from the cache. If the value is older
        than max_age then None is returned.
        """

        if obs in self.cache and ts - self.cache[obs]['ts'] <= max_age:
            return self.cache[obs]['value']
        return None

    def get_packet(self, ts=None, max_age=600):
        """Get a loop packet from the cache.

        Resulting packet may contain None values.
        """

        if ts is None:
            ts = int(time.time() + 0.5)
        packet = {'dateTime': ts, 'usUnits': self.unit_system}
        for obs in self.cache:
            packet[obs] = self.get_value(obs, ts, max_age)
        return packet


# ============================================================================
#                            Utility Functions
# ============================================================================

def calc_trend(obs_type, now_vt, db_manager, then_ts, grace):
    """ Calculate change in an observation over a specified period.

    Inputs:
        obs_type:   database field name of observation concerned
        now_vt:     value of observation now (ie the finishing value)
        db_manager: manager to be used
        then_ts:    timestamp of start of trend period
        grace:      the largest difference in time when finding the then_ts
                    record that is acceptable

    Returns:
        Change in value over trend period. Can be positive, 0, negative or
        None. Result will be in 'group' units.
    """

    result = None
    if now_vt.value is not None:
        then_record = db_manager.getRecord(then_ts, grace)
        if then_record is not None and obs_type in then_record:
            then_vt = weewx.units.as_value_tuple(then_record, obs_type)
            try:
                then = convert(then_vt, now_vt.unit).value
            except KeyError:
                then = None
            if then is not None:
                result = now_vt.value - then
    return result
