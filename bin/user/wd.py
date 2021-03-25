"""
ws.py

Service classes used by WeeWX-WD

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

Version: 2.1.3                                          Date: 15 February 2021

Revision History
    15 February 2021    v2.1.3
        - no change, version number change only
    17 November 2020    v2.1.2
        - no change, version number change only
    11 November 2020    v2.1.1
        - no change, version number change only
    1 November 2020     v2.1.0
        - service WdWXCalculate now adds derived field sunshine to archive
          records, this allows calculation of various 'sunshine hours'
          aggregates
        - added field sunshine to the weewxwd schema
        - fields outTempDay and outTempNight are only added to loop packets and
          archive records if pre-requisite field outTemp exists in the same
          loop packet/archive record
        - removed unused class wdGenerateDerived() from wd.py
        - logging is now WeeWX 3 and 4 compatible
    30 August 2020      v2.0.1
        - no change, version number change only
    20 August 2020      v2.0.0
        - WeeWX 3.2+/4.x python2/3 compatible
        - moved __main__ code to weewxwd_config utility
        - now uses appTemp and humidex as provided by StdWXCalculate
        - simplified WdWXCalculate.new_loop_packet,
          WdWXCalculate.new_archive_record and WdArchive.new_archive_record
          methods
        - simplified outTempDay and outTempNight calculations
        - simplified function toint()
        - added support for a WeeWX-WD supplementary database for recording
          short term information such as theoretical solar max, WU current
          conditions, WU forecast and WU almanac data
        - added WU API language support
        - added ability to exercise WU aspects of wd.py without the
          overheads of running a WeeWX instance
        - added current_label config option to allow a user defined label to be
          prepended to the current conditions text
        - fixed bug that occurred on partial packet stations that occasionally
          omit outTemp from packets/records
        - changed behaviour for calculating derived obs. If any one of the
          pre-requisite obs are missing then the derived obs is not calculated
          and not added to the packet/record. If all of the pre-requisite obs
          exist but one or more is None then the derived obs is set to None. If
          all pre-requisite obs exist and are non-None then the derived obs is
          calculated and added to the packet/record as normal.
        - simplified WdArchive new_archive_record() method
        - renamed from weewxwd3.py to wd.py in line with simplified file naming
          of WeeWX-WD files
Previous Bitbucket revision history
    31 March 2017       v1.0.3
        - no change, version number change only
    14 December 2016    v1.0.2
        - no change, version number change only
    30 November 2016    v1.0.1
        - now uses humidex and appTemp formulae from weewx.wxformulas
        - WeeWX-WD db management functions moved to wd_database utility
        - implemented syslog wrapper functions
        - minor reformatting
        - replaced calls to superseded DBBinder.get_database method with
          DBBinder.get_manager method
        - removed database management utility functions and placed in new
          wd_database utility
    10 January 2015     v1.0.0
        - rewritten for WeeWX v3.0
        - uses separate database for WeeWX-WD specific data, no longer
          recycles existing WeeWX database fields
        - added __main__ to allow command line execution of a number of db
          management actions
        - removed --debug option from main()
        - added --create_archive option to main() to create the weewxwd
          database
        - split --backfill_daily into separate --drop_daily and
          --backfill_daily options
        - added 'user.' to all WeeWX-WD imports
    18 September 2014   v0.9.4 (never released)
        - added GNU license text
    18 May 2014         v0.9.2
        - removed code that set windDir/windGustDir to 0 if windDir/windGustDir
          were None respectively
    30 July 2013        v0.9.1
        - revised version number to align with WeeWX-WD version numbering
    20 July 2013        v0.1
        - initial implementation
"""

# python imports
import socket
import syslog
import threading
import json
import os
import time
from datetime import datetime

# python 2/3 compatibility shims
from six import iteritems
from six.moves import queue
from six.moves import urllib

# WeeWX imports
import weeutil.weeutil
import weewx
import weewx.almanac
import weewx.engine
import weewx.manager
import weewx.units
import weewx.wxformulas

from weewx.units import obs_group_dict
from weeutil.weeutil import accumulateLeaves, to_int, to_bool

# import/setup logging, WeeWX v3 is syslog based but WeeWX v4 is logging based,
# try v4 logging and if it fails use v3 logging
try:
    # WeeWX4 logging
    import logging
    from weeutil.logger import log_traceback

    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

    def logcri(msg):
        log.critical(msg)

    # log_traceback() generates the same output but the signature and code is
    # different between v3 and v4. We only need log_traceback at the log.error
    # level so define a suitable wrapper function.

    def log_traceback_critical(prefix=''):
        log_traceback(log.critical, prefix=prefix)

    def log_traceback_info(prefix=''):
        log_traceback(log.info, prefix=prefix)

except ImportError:
    # WeeWX legacy (v3) logging via syslog
    import syslog
    from weeutil.weeutil import log_traceback

    def logmsg(level, msg):
        syslog.syslog(level, 'wd: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

    def logcri(msg):
        logmsg(syslog.LOG_CRITICAL, msg)

    # log_traceback() generates the same output but the signature and code is
    # different between v3 and v4. We only need log_traceback at the log.error
    # level so define a suitable wrapper function.

    def log_traceback_critical(prefix=''):
        log_traceback(prefix=prefix, loglevel=syslog.LOG_CRIT)

    def log_traceback_info(prefix=''):
        log_traceback(prefix=prefix, loglevel=syslog.LOG_INFO)

WEEWXWD_VERSION = '2.1.3'

# Default radiation threshold value used for calculating sunshine
DEFAULT_SUNSHINE_THRESHOLD = 120

# Define a dictionary to look up Davis forecast rule
# and return forecast text
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
        69: 'Increasing clouds and warmer. Precipitation likley.',
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


# ============================================================================
#                     Exceptions that could get thrown
# ============================================================================


class MissingApiKey(IOError):
    """Raised when an API key cannot be found for an external source/service."""


class MissingFile(IOError):
    """Raised when an API key cannot be found for an external source/service."""


# ==============================================================================
#                              Class WdWXCalculate
# ==============================================================================


class WdWXCalculate(weewx.engine.StdService):
    """Service to calculate WeeWX-WD specific observations."""

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WdWXCalculate, self).__init__(engine, config_dict)

        # determine the radiation threshold value for calculating sunshine, if
        # it is missing use a suitable default
        if 'WeewxWD' in config_dict:
            self.sunshine_threshold = config_dict['WeewxWD'].get('sunshine_threshold',
                                                                 DEFAULT_SUNSHINE_THRESHOLD)
        else:
            self.sunshine_threshold  = DEFAULT_SUNSHINE_THRESHOLD
        loginf("WdWXCalculate sunshine threshold: %s" % self.sunshine_threshold)

        # bind our self to new loop packet and new archive record events
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    @staticmethod
    def new_loop_packet(event):
        """Add outTempDay and outTempNight to the loop packet."""

        _x = dict()
        if 'outTemp' in event.packet:
            _x['outTempDay'], _x['outTempNight'] = calc_day_night(event.packet)
        event.packet.update(_x)

    @staticmethod
    def new_archive_record(event):
        """Add any WeeWX-WD derived fields to the archive record."""

        _x = dict()
        if 'outTemp' in event.record:
            _x['outTempDay'], _x['outTempNight'] = calc_day_night(event.record)
        if 'radiation' in event.record:
            _x['sunshine'] = calc_sunshine(event.record)
        event.record.update(_x)


# ==============================================================================
#                                Class WdArchive
# ==============================================================================


class WdArchive(weewx.engine.StdService):
    """Service to store Weewx-WD specific archive data."""

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WdArchive, self).__init__(engine, config_dict)

        # Extract our binding from the WeeWX-WD section of the config file. If
        # it's missing, fill with a default.
        if 'WeewxWD' in config_dict:
            self.data_binding = config_dict['WeewxWD'].get('data_binding',
                                                           'wd_binding')
        else:
            self.data_binding = 'wd_binding'
        loginf("WdArchive will use data binding %s" % self.data_binding)

        # extract the WeeWX binding for use when we check the need for backfill
        # from the WeeWX archive
        if 'StdArchive' in config_dict:
            self.data_binding_wx = config_dict['StdArchive'].get('data_binding',
                                                                 'wx_binding')
        else:
            self.data_binding_wx = 'wx_binding'

        # setup our database if needed
        self.setup_database()

        # set the unit groups for our obs
        obs_group_dict["humidex"] = "group_temperature"
        obs_group_dict["appTemp"] = "group_temperature"
        obs_group_dict["outTempDay"] = "group_temperature"
        obs_group_dict["outTempNight"] = "group_temperature"
        obs_group_dict["sunshine"] = "group_elapsed"

        # bind ourselves to NEW_ARCHIVE_RECORD event
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        """Save the WeeWX-WD archive record.

           Use our db manager's addRecord method to save the relevant WeeWX-WD
           fields to the WeeWX-WD archive.
        """

        # get our db manager
        dbmanager = self.engine.db_binder.get_manager(self.data_binding)
        # now put the record in the archive
        dbmanager.addRecord(event.record)

    def setup_database(self):
        """Setup the WeeWX-WD database"""

        # create the database if it doesn't exist and a db manager for the
        # opened database
        dbmanager = self.engine.db_binder.get_manager(self.data_binding,
                                                      initialize=True)
        loginf("Using binding '%s' to database '%s'" % (self.data_binding,
                                                        dbmanager.database_name))

        # FIXME. Is this still required
        # Check if we have any historical data to bring in from the WeeWX
        # archive.
        # first get a dbmanager for the WeeWX archive
        dbmanager_wx = self.engine.db_binder.get_manager(self.data_binding_wx,
                                                         initialize=False)

        # then backfill the WeeWX-WD daily summaries
        loginf("Starting backfill of daily summaries")
        t1 = time.time()
        nrecs, ndays = dbmanager_wx.backfill_day_summary()
        tdiff = time.time() - t1
        if nrecs:
            loginf("Processed %d records to backfill %d day summaries in %.2f seconds" % (nrecs,
                                                                                          ndays,
                                                                                          tdiff))
        else:
            loginf("Daily summaries up to date.")


# ==============================================================================
#                              Class WdSuppArchive
# ==============================================================================


class WdSuppArchive(weewx.engine.StdService):
    """Service to archive WeeWX-WD supplementary data.


        Collects and archives WU API sourced data, Davis console forecast/storm 
        data and theoretical max solar radiation data in the WeeWX-WD supp
        database. Data is only kept for a limited time before being dropped.
    """

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WdSuppArchive, self).__init__(engine, config_dict)

        # Initialisation is 2 part; 1 part for wdsupp db/loop data, 2nd part for
        # WU API calls. We are only going to invoke our self if we have the
        # necessary config data available in weewx.conf for 1 or both parts. If
        # any essential config data is missing/not set then give a short log
        # message and defer.

        if 'Weewx-WD' in config_dict:
            # we have a [Weewx-WD] stanza
            if 'Supplementary' in config_dict['Weewx-WD']:
                # we have a [[Supplementary]] stanza so we can initialise
                # wdsupp db
                _supp_dict = config_dict['Weewx-WD']['Supplementary']
                
                # setup for archiving of supp data
                # first, get our binding, if it's missing use a default
                self.binding = _supp_dict.get('data_binding',
                                              'wdsupp_binding')
                loginf("WdSuppArchive will use data binding '%s'" % self.binding)
                # how long to keep records in our db (default 8 days)
                self.max_age = _supp_dict.get('max_age', 691200)
                self.max_age = toint(self.max_age, 691200)
                # how often to vacuum the sqlite database (default 24 hours)
                self.vacuum = _supp_dict.get('vacuum', 86400)
                self.vacuum = toint(self.vacuum, 86400)
                # how many times do we retry database failures (default 3)
                self.db_max_tries = _supp_dict.get('database_max_tries', 3)
                self.db_max_tries = int(self.db_max_tries)
                # how long to wait between retries (default 2 sec)
                self.db_retry_wait = _supp_dict.get('database_retry_wait', 2)
                self.db_retry_wait = int(self.db_retry_wait)
                # setup our database if needed
                self.setup_database()
                # ts at which we last vacuumed
                self.last_vacuum = None
                # create holder for Davis Console loop data
                self.loop_packet = {}

                # set the unit groups for our obs
                obs_group_dict["tempRecordHigh"] = "group_temperature"
                obs_group_dict["tempNormalHigh"] = "group_temperature"
                obs_group_dict["tempRecordLow"] = "group_temperature"
                obs_group_dict["tempNormalLow"] = "group_temperature"
                obs_group_dict["tempRecordHighYear"] = "group_count"
                obs_group_dict["tempRecordLowYear"] = "group_count"
                obs_group_dict["stormRain"] = "group_rain"
                obs_group_dict["stormStart"] = "group_time"
                obs_group_dict["maxSolarRad"] = "group_radiation"
                obs_group_dict["forecastIcon"] = "group_count"
                obs_group_dict["currentIcon"] = "group_count"
                obs_group_dict["vantageForecastIcon"] = "group_count"

                # set event bindings
                
                # bind to NEW_LOOP_PACKET so we can capture Davis Vantage forecast
                # data
                self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
                # bind to NEW_ARCHIVE_RECORD to ensure we have a chance to:
                # - update WU data(if necessary)
                # - save our data
                # on each new record
                self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

                # we have everything we need to put a short message re supp 
                # database
                loginf("max_age=%s vacuum=%s" % (self.max_age, self.vacuum))

                # setup up any sources
                self.sources = dict()
                self.queues = dict()
                # iterate over each source definition under [[Supplementary]]
                for source in _supp_dict.sections:
                    # is it a source we know how to handle
                    if source in KNOWN_SOURCES:
                        # get the source config dict
                        _source_dict = _supp_dict[source]
                        # check if the source is enabled, default to False unless
                        # enable = True
                        _enable = to_bool(_source_dict.get('enable', False))
                        if _source_dict is not None and _enable:
                            # we have a source config dict and the source is
                            # enabled so setup the result and control queues
                            self.queues[source] = {'control': queue.Queue(),
                                                   'result': queue.Queue()}
                            # obtain an appropriate source object
                            self.sources[source] = self.source_factory(source,
                                                                       self.queues[source],
                                                                       engine,
                                                                       _source_dict)
                            # start the source object
                            self.sources[source].start()
                        elif not _enable:
                            # the source was explicitly disabled so tell the
                            # user
                            loginf("Source '%s' not enabled." % source)
                        else:
                            # no usable source config dict so log it
                            loginf("Source '%s' will be ignored, incomplete or missing config settings")

                # define some properties for later use
                self.last_ts = None

                self.source_record = {'forecastIcon': None,
                                      'forecastText': None,
                                      'currentIcon': None,
                                      'currentText': None}

    @staticmethod
    def source_factory(source, queues_dict, engine, source_dict):
        """Factory to produce a source object."""

        # get the source class
        source_class = KNOWN_SOURCES.get(source)
        if source_class is not None:
            # get the source object
            source_object = source_class(queues_dict['control'],
                                         queues_dict['result'],
                                         engine,
                                         source_dict)
            return source_object

    def new_archive_record(self, event):
        """Action on a new archive record being created.

        Add anything we have to the archive record and then save to our
        database. Grab any forecast/storm loop data and theoretical max
        solar radiation. Archive our data, delete any stale records and
        'vacuum' the database if required.
        """

        # If we have a result queue check to see if we have received
        # any forecast data. Use get_nowait() so we don't block the
        # control queue. Wrap in a try..except to catch the error
        # if there is nothing in the queue.

        # get time now as a ts
        now = time.time()

        # get any data from the sources
        for source_name, source_object in iteritems(self.sources):
            _result_queue = self.queues[source_name]['result']
            if _result_queue:
                # if packets have backed up in the result queue, trim it until
                # we only have one entry, that will be the latest
                while _result_queue.qsize() > 1:
                    _result_queue.get()
            # now get any data in the queue
            try:
                # use nowait() so we don't block
                _package = _result_queue.get_nowait()
            except queue.Empty:
                # nothing in the queue so continue
                pass
            else:
                # we did get something in the queue but was it a
                # 'forecast' package
                if isinstance(_package, dict):
                    if 'type' in _package and _package['type'] == 'data':
                        # we have forecast text so log and add it to the archive record
                        if weewx.debug >= 2:
                            logdbg("received forecast text: %s" % _package['payload'])
                        self.source_record.update(_package['payload'])

        _record = dict(self.source_record)
        _record['dateTime'] = event.record['dateTime']
        _record['usUnits'] = event.record['usUnits']
        _record['interval'] = event.record['interval']

        # update our data record with any stashed loop data
        _record.update(self.process_loop())

        # get a db manager dict
        dbm_dict = weewx.manager.get_manager_dict_from_config(self.config_dict,
                                                              self.binding)
        # now save the data
        with weewx.manager.open_manager(dbm_dict) as dbm:
            # save the record
            self.save_record(dbm, _record, self.db_max_tries, self.db_retry_wait)
            # set ts of last packet processed
            self.last_ts = _record['dateTime']
            # prune older packets and vacuum if required
            if self.max_age > 0:
                self.prune(dbm,
                           self.last_ts - self.max_age,
                           self.db_max_tries,
                           self.db_retry_wait)
                # vacuum the database
                if self.vacuum > 0:
                    if self.last_vacuum is None or ((now + 1 - self.vacuum) >= self.last_vacuum):
                        self.vacuum_database(dbm)
                        self.last_vacuum = now

    def new_loop_packet(self, event):
        """ Save Davis Console forecast data that arrives in loop packets so
            we can save it to archive later.

            The Davis Console forecast data is published in each loop packet.
            There is little benefit in saving this data to database each loop
            period as the data is slow changing so we will stash the data and
            save to database each archive period along with our WU sourced data.
        """

        # update stashed loop packet data
        self.loop_packet['forecastIcon'] = event.packet.get('forecastIcon')
        self.loop_packet['forecastRule'] = event.packet.get('forecastRule')
        self.loop_packet['stormRain'] = event.packet.get('stormRain')
        self.loop_packet['stormStart'] = event.packet.get('stormStart')
        self.loop_packet['maxSolarRad'] = event.packet.get('maxSolarRad')

    def process_loop(self):
        """ Process stashed loop data and populate fields as appropriate.

            Adds following fields (if available) to data dictionary:
                - forecast icon (Vantage only)
                - forecast rule (Vantage only)(Note returns full text forecast)
                - stormRain (Vantage only)
                - stormStart (Vantage only)
                - current theoretical max solar radiation
        """

        # holder dictionary for our gathered data
        _data = dict()
        # vantage forecast icon
        if self.loop_packet.get('forecastIcon') is not None:
            _data['vantageForecastIcon'] = self.loop_packet['forecastIcon']
        # vantage forecast rule
        if self.loop_packet.get('forecastRule') is not None:
            try:
                _data['vantageForecastRule'] = davis_fr_dict[self.loop_packet['forecastRule']]
            except KeyError:
                if weewx.debug >= 2:
                    logdbg("Could not decode Vantage forecast code")
        # vantage stormRain
        if self.loop_packet.get('stormRain') is not None:
            _data['stormRain'] = self.loop_packet['stormRain']
        # vantage stormStart
        if self.loop_packet.get('stormStart') is not None:
            _data['stormStart'] = self.loop_packet['stormStart']
        # theoretical solar radiation value
        if self.loop_packet.get('maxSolarRad') is not None:
            _data['maxSolarRad'] = self.loop_packet['maxSolarRad']
        return _data

    @staticmethod
    def save_record(dbm, _data_record, max_tries=3, retry_wait=2):
        """Save a data record to our database."""

        for count in range(max_tries):
            try:
                # save our data to the database
                dbm.addRecord(_data_record)
                break
            except Exception as e:
                logerr("save failed (attempt %d of %d): %s" % ((count + 1),
                                                               max_tries, e))
                logerr("waiting %d seconds before retry" % (retry_wait, ))
                time.sleep(retry_wait)
        else:
            raise Exception("save failed after %d attempts" % max_tries)

    @staticmethod
    def prune(dbm, ts, max_tries=3, retry_wait=2):
        """Remove records older than ts from the database."""

        sql = "delete from %s where dateTime < %d" % (dbm.table_name, ts)
        for count in range(max_tries):
            try:
                dbm.getSql(sql)
                break
            except Exception as e:
                logerr("prune failed (attempt %d of %d): %s" % ((count+1),
                                                                max_tries, e))
                logerr("waiting %d seconds before retry" % (retry_wait, ))
                time.sleep(retry_wait)
        else:
            raise Exception("prune failed after %d attempts" % max_tries)
        return

    @staticmethod
    def vacuum_database(dbm):
        """Vacuum our database to save space."""

        # SQLite databases need a little help to prevent them from continually
        # growing in size even though we prune records from the database.
        # Vacuum will only work on SQLite databases.  It will compact the
        # database file. It should be OK to run this on a MySQL database - it
        # will silently fail.

        # Get time now as a ts
        t1 = time.time()
        # do the vacuum, wrap in try..except in case it fails
        try:
            dbm.getSql('vacuum')
        except Exception as e:
            # it could be that we have a MySQL/MariaDB type database that does
            # not support vacuuming, if we do then we can ignore this exception
            if dbm.connection.dbtype != 'mysql':
                logerr("Vacuuming database %s failed: %s" % (dbm.database_name, e))
        t2 = time.time()
        logdbg("vacuum_database executed in %0.9f seconds" % (t2-t1))

    def setup_database(self):
        """Setup the database table we will be using."""

        # This will create the database and/or table if either doesn't exist,
        # then return an opened instance of the database manager.
        dbmanager = self.engine.db_binder.get_database(self.binding,
                                                       initialize=True)
        loginf("Using binding '%s' to database '%s'" % (self.binding,
                                                        dbmanager.database_name))

    def shutDown(self):
        """Shut down any threads.

        Would normally do all of a given threads actions in one go but since
        we may have more than one thread and so that we don't have sequential
        (potential) waits of up to 15 seconds we send each thread a shutdown
        signal and then go and check that each has indeed shutdown.
        """

        for source_name, source_object in iteritems(self.sources):
            if self.queues[source_name]['control'] and source_object.isAlive():
                # put a None in the control queue to signal the thread to
                # shutdown
                self.queues[source_name]['control'].put(None)


# ============================================================================
#                           class ThreadedSource
# ============================================================================


class ThreadedSource(threading.Thread):
    """Base class for a threaded external source.

    ThreadedSource constructor parameters:

        control_queue:       A Queue object used by our parent to control
                             (shutdown) this thread.
        result_queue:        A Queue object used to pass data to our parent
        engine:              an instance of weewx.engine.StdEngine
        source_config_dict:  A weeWX config dictionary.

    ThreadedSource methods:

        run.            Thread entry point, controls data fetching, parsing and
                        dispatch. Monitors the control queue.
        get_raw_data.       Obtain the raw data. This method must be written for
                        each child class.
        parse_data.     Parse the raw data and return the final  format data.
                        This method must be written for each child class.
    """

    def __init__(self, control_queue, result_queue, engine, source_config_dict):

        # initialize my superclass
        threading.Thread.__init__(self)

        # setup a some thread things
        self.setDaemon(True)
        # thread name needs to be set in the child class __init__() eg:
        #   self.setName('WdWuThread')

        # save the queues we will use
        self.control_queue = control_queue
        self.result_queue = result_queue

    def run(self):
        """Entry point for the thread."""

        self.setup()
        # since we are in a thread some additional try..except clauses will
        # help give additional output in case of an error rather than having
        # the thread die silently
        try:
            # Run a continuous loop, obtaining data as required and monitoring
            # the control queue for the shutdown signal. Only break out if we
            # receive the shutdown signal (None) from our parent.
            while True:
                # run an inner loop obtaining, parsing and dispatching the data
                # and checking for the shutdown signal
                # first up get the raw data
                _raw_data = self.get_raw_data()
                # if we have a non-None response then we have data so parse it,
                # gather the required data and put it in the result queue
                if _raw_data is not None:
                    # parse the raw data response and extract the required data
                    _data = self.parse_raw_data(_raw_data)
                    if self.debug > 0:
                        loginf("Parsed data=%s" % _data)
                    # if we have some data then place it in the result queue
                    if _data is not None:
                        # construct our data dict for the queue
                        _package = {'type': 'data',
                                    'payload': _data}
                        self.result_queue.put(_package)
                # now check to see if we have a shutdown signal
                try:
                    # Try to get data from the queue, block for up to 60
                    # seconds. If nothing is there an empty queue exception
                    # will be thrown after 60 seconds
                    _package = self.control_queue.get(block=True, timeout=60)
                except queue.Empty:
                    # nothing in the queue so continue
                    pass
                else:
                    # something was in the queue, if it is the shutdown signal
                    # then return otherwise continue
                    if _package is None:
                        # we have a shutdown signal so return to exit
                        return
        except Exception as e:
            # Some unknown exception occurred. This is probably a serious
            # problem. Exit with some notification.
            logcri("Unexpected exception of type %s" % (type(e),))
            log_traceback_critical(prefix='wdthreadedsource: **** ')
            logcri("Thread exiting. Reason: %s" % (e,))

    def setup(self):
        """Perform any post post-__init__() setup.

        This method is executed as the very first thing in the thread run()
        method. It must be defined if required for each child class.
        """

        pass

    def get_raw_data(self):
        """Obtain the raw block data.

        This method must be defined for each child class.
        """

        return None

    def parse_raw_data(self, response):
        """Parse the block response and return the required data.

        This method must be defined if the raw data from the block must be
        further processed to extract the final scroller text.
        """

        return response


# ============================================================================
#                              class WuSource
# ============================================================================


class WuSource(ThreadedSource):
    """Thread that obtains WU API forecast text and places it in a queue.

    The WuSource class queries the WU API and places selected forecast text in
    JSON format in a queue used by the data consumer. The WU API is called at a
    user selectable frequency. The thread listens for a shutdown signal from
    its parent.

    WuSource constructor parameters:

        control_queue:      A Queue object used by our parent to control
                            (shutdown) this thread.
        result_queue:       A Queue object used to pass forecast data to the
                            destination
        engine:             An instance of class weewx.weewx.Engine
        source_config_dict: A weeWX config dictionary.

    WuSource methods:

        run.               Control querying of the API and monitor the control
                           queue.
        query_wu.          Query the API and put selected forecast data in the
                           result queue.
        parse_wu_response. Parse a WU API response and return selected data.
    """

    VALID_FORECASTS = ('3day', '5day', '7day', '10day', '15day')
    VALID_NARRATIVES = ('day', 'day-night')
    VALID_LOCATORS = ('geocode', 'iataCode', 'icaoCode', 'placeid', 'postalKey')
    VALID_UNITS = {'e': 'English units',
                   'm': 'Metric units',
                   's': 'Metric SI units',
                   'h': 'Hybrid units (UK)'}
    VALID_LANGUAGES = {'ar-AE': 'Arabic - (United Arab Emirates)',
                       'az-AZ': 'Azerbaijani - (Azerbaijan)',
                       'bg-BG': 'Bulgarian - (Bulgaria)',
                       'bn-BD': 'Bengali, Bangla - (Bangladesh)',
                       'bn-IN': 'Bengali, Bangla - (India)',
                       'bs-BA': 'Bosnian - (Bosnia and Herzegovina)',
                       'ca-ES': 'Catalan - (Spain)',
                       'cs-CZ': 'Czech - (Czechia)',
                       'da-DK': 'Danish - (Denmark)',
                       'de-DE': 'German - (Germany)',
                       'el-GR': 'Greek (modern) - (Greece)',
                       'en-GB': 'English - (Great Britain)',
                       'en-IN': 'English (India)',
                       'en-US': 'English - (United States of America)',
                       'es-AR': 'Spanish - (Argentina)',
                       'es-ES': 'Spanish - (Spain)',
                       'es-LA': 'Spanish - (Latin America)',
                       'es-MX': 'Spanish - (Mexico)',
                       'es-UN': 'Spanish - (International)',
                       'es-US': 'Spanish - (United States of America)',
                       'et-EE': 'Estonian - (Estonia)',
                       'fa-IR': 'Persian (Farsi) - (Iran)',
                       'fi-FI': 'Finnish - (Finland)',
                       'fr-CA': 'French - (Canada)',
                       'fr-FR': 'French - (France',
                       'gu-IN': 'Gujarati - (India)',
                       'he-IL': 'Hebrew (modern) - (Israel)',
                       'hi-IN': 'Hindi - (India)',
                       'hr-HR': 'Croatian - (Croatia)',
                       'hu-HU': 'Hungarian - (Hungary)',
                       'in-ID': 'Indonesian - (Indonesia)',
                       'is-IS': 'Icelandic - (Iceland)',
                       'it-IT': 'Italian - (Italy)',
                       'iw-IL': 'Hebrew - (Israel)',
                       'ja-JP': 'Japanese - (Japan)',
                       'jv-ID': 'Javanese - (Indonesia)',
                       'ka-GE': 'Georgian - (Georgia',
                       'kk-KZ': 'Kazakh - (Kazakhstan)',
                       'km-KH': 'Khmer - (Cambodia)',
                       'kn-IN': 'Kannada - (India)',
                       'ko-KR': 'Korean - (South Korea)',
                       'lo-LA': 'Lao - (Laos)',
                       'lt-LT': 'Lithuanian - (Lithuania)',
                       'lv-LV': 'Latvian - (Latvia)',
                       'mk-MK': 'Macedonian - (Macedonia)',
                       'mn-MN': 'Mongolian - (Mongolia)',
                       'mr-IN': 'Marathi - (India)',
                       'ms-MY': 'Malay - (Malaysia)',
                       'my-NM': 'Burmese - (Myanmar)',
                       'ne-IN': 'Nepali - (India)',
                       'ne-NP': 'Nepali - (Nepal)',
                       'nl-NL': 'Dutch - (Netherlands)',
                       'no-NO': 'Norwegian - (Norway)',
                       'pa-PL': 'Panjabi - (Pakistan)',
                       'pl-PL': 'Polish - (Poland)',
                       'pt-BR': 'Portuguese - (Brazil)',
                       'pt-PT': 'Portuguese - (Portugal)',
                       'ro-RO': 'Romanian - (Romania)',
                       'ru-RU': 'Russian - (Russia)',
                       'si-LK': 'Sinhalese, Sinhala - (Sri Lanka)',
                       'sk-SK': 'Slovak - (Slovakia)',
                       'sl-SI': 'Slovenian - (Slovenia)',
                       'sq-AL': 'Albanian - (Albania)',
                       'sr-BA': 'Serbian - (Bosnia and Herzegovina)',
                       'sr-ME': 'Serbian - (Montenegro)',
                       'sr-RS': 'Serbian - (Serbia)',
                       'sv-SE': 'Swedish - (Sweden)',
                       'sw-KE': 'Swahili - (Kenya)',
                       'ta-IN': 'Tamil - (India)',
                       'ta-LK': 'Tamil - (Sri Lanka)',
                       'te-IN': 'Telugu - (India)',
                       'ti-ER': 'Tigrinya - (Eritrea)',
                       'ti-ET': 'Trigrinya - (Eritrea)',
                       'tg-TJ': 'Tajik - (Tajikistan)',
                       'th-TH': 'Thai - (Thailand)',
                       'tk-TM': 'Turkmen - (Turkmenistan)',
                       'tl-PH': 'Tagalog - (Philippines)',
                       'tr-TR': 'Turkish - (Turkey)',
                       'uk-UA': 'Ukrainian - (Ukraine)',
                       'ur-PK': 'Urdu - (Pakistan)',
                       'uz-UZ': 'Uzbek - (Uzbekistan)',
                       'vi-VN': 'Vietnamese - (Viet Nam)',
                       'zh-CN': 'Chinese - (China)',
                       'zh-HK': 'Chinese - (Hong Kong)',
                       'zh-TW': 'Chinese - (Taiwan)'}

    ICON_MAP = {0: 32,   # Tornado (Night and Day) --> Tornado
                1: 31,   # Tropical Storm (Night and Day) --> Thunderstorms
                2: 32,   # Hurricane (Night and Day) --> Tornado
                3: 31,   # Strong Storms (Night and Day) --> Thunderstorms
                4: 8,    # Thunder and Hail (Night and Day) --> Heavy Rain
                5: 27,   # Rain to Snow Showers (Night and Day) --> Snow Showers2
                6: 24,   # Rain/Sleet (Night and Day) --> Sleet Showers
                7: 27,   # Wintry Mix Snow/Sleet (Night and Day) --> Snow Showers2
                8: 24,   # Freezing Drizzle (Night and Day) --> Sleet Showers
                9: 22,   # Drizzle (Night and Day) --> Showers2
                10: 23,  # Freezing Rain (Night and Day) --> Sleet
                11: 22,  # Light Rain (Night and Day) --> Showers2
                12: 20,  # Rain (Night and Day) --> Rain
                13: 25,  # Scattered Flurries (Night and Day) --> Snow
                14: 25,  # Light Snow (Night and Day) --> Snow
                15: 25,  # Blowing/Drifting Snow (Night and Day) --> Snow
                16: 25,  # Snow (Night and Day) --> Snow
                17: 8,   # Hail (Night and Day) --> Heavy Rain
                18: 23,  # Sleet (Night and Day) --> Sleet
                19: 33,  # Blowing Dust/Sandstorm (Night and Day) --> Windy
                20: 6,   # Foggy (Night and Day) --> Fog
                21: 7,   # Haze/Windy (Night and Day) --> Haze
                22: 33,  # Smoke/Windy (Night and Day) --> Windy
                23: 33,  # Breezy (Night and Day) --> Windy
                24: 33,  # Blowing Spray/Windy (Night and Day) --> Windy
                25: 25,  # Frigid/Ice Crystals (Night and Day) --> Snow
                26: 2,   # Cloudy (Night and Day) --> Cloudy
                27: 19,  # Mostly Cloudy (Night and Day) --> Partly Cloudy
                28: 2,   # Mostly Cloudy (Day) --> Cloudy
                29: 4,   # Partly Cloudy (Night) --> Cloudy (Night)
                30: 19,  # Partly Cloudy (Day) --> Partly Cloudy
                31: 1,   # Clear (Night) --> Clear (Night)
                32: 0,   # Sunny (Day) --> Sunny
                33: 1,   # Fair/Mostly Clear (Night) --> Clear (Night)
                34: 9,   # Fair/Mostly Sunny (Day) --> Mainly Fine
                35: 8,   # Mixed Rain & Hail (Day) --> Heavy Rain
                36: 5,   # Hot (Day) --> Dry
                37: 31,  # Isolated Thunderstorms (Day) --> Thunderstorms
                38: 31,  # Thunderstorms (Night and Day) --> Thunderstorms
                39: 22,  # Scattered Showers (Day) --> Showers2
                40: 8,   # Heavy Rain (Night and Day) --> Heavy Rain
                41: 27,  # Scattered Snow Showers (Day) --> Snow Showers2
                42: 25,  # Heavy Snow (Night and Day) --> Snow
                43: 25,  # Blizzard (Night and Day) --> Snow
                44: None,  # Not Available (N/A) (Night and Day) --> None
                45: 15,  # Scattered Showers (Night) --> Showers (Night)
                46: 16,  # Scattered Snow Showers (Night) --> Snow (Night)
                47: 31,  # Scattered Thunderstorms (Night and Day) -->  Thunderstorms
                }
    
    def __init__(self, control_queue, result_queue, engine, source_config_dict):

        # initialize my superclass
        super(WuSource, self).__init__(control_queue, result_queue,
                                       engine, source_config_dict)

        # set thread name
        self.setName('WdWuThread')

        # WuSource debug level
        self.debug = to_int(source_config_dict.get('debug', 0))

        # interval between API calls
        self.interval = to_int(source_config_dict.get('interval', 1800))
        # max no of tries we will make in any one attempt to contact WU via API
        self.max_tries = to_int(source_config_dict.get('max_tries', 3))
        # Get API call lockout period. This is the minimum period between API
        # calls for the same feature. This prevents an error condition making
        # multiple rapid API calls and thus breach the API usage conditions.
        self.lockout_period = to_int(source_config_dict.get('api_lockout_period',
                                                            60))
        # initialise container for timestamp of last WU api call
        self.last_call_ts = None

        # get our API key from weewx.conf
        api_key = source_config_dict.get('api_key')
        if api_key is None:
            raise MissingApiKey("Cannot find valid Weather Underground API key")

        # get the forecast type
        _forecast = source_config_dict.get('forecast_type', '5day').lower()
        # validate forecast type
        self.forecast = _forecast if _forecast in self.VALID_FORECASTS else '5day'

        # get the forecast text to display
        _narrative = source_config_dict.get('forecast_text', 'day-night').lower()
        self.forecast_text = _narrative if _narrative in self.VALID_NARRATIVES else 'day-night'

        # FIXME, Not sure the logic is correct should we get a delinquent location setting
        # get the locator type and location argument to use for the forecast
        # first get the
        _location = source_config_dict.get('location', 'geocode').split(',', 1)
        _location_list = [a.strip() for a in _location]
        # validate the locator type
        self.locator = _location_list[0] if _location_list[0] in self.VALID_LOCATORS else 'geocode'
        if len(_location_list) == 2:
            self.location = _location_list[1]
        else:
            self.locator = 'geocode'
            self.location = '%s,%s' % (engine.stn_info.latitude_f,
                                       engine.stn_info.longitude_f)

        # get units to be used in forecast text
        _units = source_config_dict.get('units', 'm').lower()
        # validate units
        self.units = _units if _units in self.VALID_UNITS else 'm'

        # get language to be used in forecast text
        _language = source_config_dict.get('language', 'en-GB')
        # validate language
        self.language = _language if _language in self.VALID_LANGUAGES else 'en-GB'

        # set format of the API response
        self.format = 'json'

        # get a WeatherUndergroundAPI object to handle the API calls
        self.api = WeatherUndergroundAPIForecast(api_key, debug=self.debug)
        
        # do we map WU icons numbers to clientraw.txt icon numbers
        self.map_icons = source_config_dict.get("map_to_clientraw_icons", True)

        # log what we will do
        loginf("Weather Underground API will be used for forecast data")
        if self.debug > 0:
            loginf("interval=%s lockout period=%s max tries=%s" % (self.interval,
                                                                   self.lockout_period,
                                                                   self.max_tries))
            loginf("forecast=%s units=%s language=%s" % (self.forecast,
                                                         self.units,
                                                         self.language))
            loginf("locator=%s location=%s" % (self.locator,
                                               self.location))
            loginf("Weather Underground debug=%s" % self.debug)

    def get_raw_data(self):
        """If required query the WU API and return the response.

        Checks to see if it is time to query the API, if so queries the API
        and returns the raw response in JSON format. To prevent the user
        exceeding their API call limit the query is only made if at least
        self.lockout_period seconds have elapsed since the last call.

        Inputs:
            None.

        Returns:
            The raw WU API response in JSON format.
        """

        # get the current time
        now = time.time()
        if self.debug > 0:
            loginf("Last Weather Underground API call at %s" % weeutil.weeutil.timestamp_to_string(self.last_call_ts))

        # has the lockout period passed since the last call
        if self.last_call_ts is None or ((now + 1 - self.lockout_period) >= self.last_call_ts):
            # If we haven't made an API call previously or if its been too long
            # since the last call then make the call
            if (self.last_call_ts is None) or ((now + 1 - self.interval) >= self.last_call_ts):
                # Make the call, wrap in a try..except just in case
                try:
                    _response = self.api.forecast_request(forecast=self.forecast,
                                                          locator=self.locator,
                                                          location=self.location,
                                                          units=self.units,
                                                          language=self.language,
                                                          format=self.format,
                                                          max_tries=self.max_tries)
                    if self.debug > 0:
                        if _response is not None:
                            loginf("Downloaded updated Weather Underground forecast")
                        else:
                            loginf("Failed to download updated Weather Underground forecast")

                except Exception as e:
                    # Some unknown exception occurred. Set _response to None,
                    # log it and continue.
                    _response = None
                    loginf("Unexpected exception of type %s" % (type(e),))
                    log_traceback_info(prefix='WUThread: **** ')
                    loginf("Unexpected exception of type %s" % (type(e),))
                    loginf("Weather Underground API forecast query failed")
                # if we got something back then reset our last call timestamp
                if _response is not None:
                    self.last_call_ts = now
                return _response
        else:
            # API call limiter kicked in so say so
            loginf("Tried to make a WU API call within %d sec of the previous call." % (self.lockout_period,))
            loginf("WU API call limit reached. API call skipped.")
        return None

    def parse_raw_data(self, response):
        """ Parse a WU API forecast response and return the forecast text.

        The WU API forecast response contains a number of forecast texts, the
        three main ones are:

        - the full day narrative
        - the day time narrative, and
        - the night time narrative.

        WU claims that night time is for 7pm to 7am and day time is for 7am to
        7pm though anecdotally it appears that the day time forecast disappears
        late afternoon and reappears early morning. If day-night forecast text
        is selected we will look for a day time forecast up until 7pm with a
        fallback to the night time forecast. From 7pm to midnight the nighttime
        forecast will be used. If day forecast text is selected then we will
        use the higher level full day forecast text.

        Input:
            response: A WU API response in JSON format.

        Returns:
            The selected forecast text if it exists otherwise None.
        """

        _text = None
        _icon = None
        # deserialize the response but be prepared to catch an exception if the
        # response can't be deserialized
        try:
            _response_json = json.loads(response)
        except ValueError:
            # can't deserialize the response so log it and return None
            loginf("Unable to deserialise Weather Underground forecast response")

        # forecast data has been deserialized so check which forecast narrative
        # we are after and locate the appropriate field.
        if self.forecast_text == 'day':
            # we want the full day narrative, use a try..except in case the
            # response is malformed
            try:
                _text = _response_json['narrative'][0]
            except KeyError:
                # could not find the narrative so log and return None
                if self.debug > 0:
                    loginf("Unable to locate 'narrative' field for "
                           "'%s' forecast narrative" % self.forecast_text)
        else:
            # we want the day time or night time narrative, but which, WU
            # starts dropping the day narrative late in the afternoon and it
            # does not return until the early hours of the morning. If possible
            # use day time up until 7pm but be prepared to fall back to night
            # if the day narrative has disappeared. Use night narrative for 7pm
            # to 7am but start looking for day again after midnight.
            # get the current local hour
            _hour = datetime.now().hour
            # helper string for later logging
            if 7 <= _hour < 19:
                _period_str = 'daytime'
            else:
                _period_str = 'nighttime'
            # day_index is the index of the day time forecast for today, it
            # will either be 0 (ie the first entry) or None if today's day
            # forecast is not present. If it is None then the night time
            # forecast is used. Start by assuming there is no day forecast.
            day_index = None
            if _hour < 19:
                # it's before 7pm so use day time, first check if it exists
                try:
                    day_index = _response_json['daypart'][0]['dayOrNight'].index('D')
                except KeyError:
                    # couldn't find a key for one of the fields, log it and
                    # force use of night index
                    if self.debug > 0:
                        loginf("Unable to locate 'dayOrNight' field for %s "
                               "'%s' forecast narrative" % (_period_str,
                                                            self.forecast_text))
                    day_index = None
                except ValueError:
                    # could not get an index for 'D', log it and force use of
                    # night index
                    if self.debug > 0:
                        loginf("Unable to locate 'D' index for %s "
                               "'%s' forecast narrative" % (_period_str,
                                                            self.forecast_text))
                    day_index = None
            # we have a day_index but is it for today or some later day
            if day_index is not None and day_index <= 1:
                # we have a suitable day index so use it
                _index = day_index
            else:
                # no day index for today so try the night index
                try:
                    _index = _response_json['daypart'][0]['dayOrNight'].index('N')
                except KeyError:
                    # couldn't find a key for one of the fields, log it and
                    # return None
                    if self.debug > 0:
                        loginf("Unable to locate 'dayOrNight' field for %s "
                               "'%s' forecast narrative" % (_period_str,
                                                            self.forecast_text))
                except ValueError:
                    # could not get an index for 'N', log it and return None
                    if self.debug > 0:
                        loginf("Unable to locate 'N' index for %s "
                               "'%s' forecast narrative" % (_period_str,
                                                            self.forecast_text))
            # if we made it here we have an index to use so get the required
            # narrative
            try:
                _text = _response_json['daypart'][0]['narrative'][_index]
                _icon = _response_json['daypart'][0]['iconCode'][_index]
            except KeyError:
                # if we can'f find a field log the error and return None
                if self.debug > 0:
                    loginf("Unable to locate 'narrative' field for "
                           "'%s' forecast narrative" % self.forecast_text)
            except ValueError:
                # if we can'f find an index log the error and return None
                if self.debug > 0:
                    loginf("Unable to locate 'narrative' index for "
                           "'%s' forecast narrative" % self.forecast_text)

            if _icon is not None and self.map_icons:
                _raw_icon = _icon
                _icon = self.ICON_MAP.get(_icon)
                if self.debug or weewx.debug > 0:
                    loginf("Forecast icon mapped from '%d' to '%d'" % (_raw_icon,
                                                                       _icon))
            if _text is not None or _icon is not None:
                return {'forecastIcon': _icon,
                        'forecastText': _text}
            else:
                return None


# ============================================================================
#                    class WeatherUndergroundAPIForecast
# ============================================================================


class WeatherUndergroundAPIForecast(object):
    """Obtain a forecast from the Weather Underground API.

    The WU API is accessed by calling one or more features. These features can
    be grouped into two groups, WunderMap layers and data features. This class
    supports access to the API data features only.

    WeatherUndergroundAPI constructor parameters:

        api_key: WeatherUnderground API key to be used.

    WeatherUndergroundAPI methods:

        data_request. Submit a data feature request to the WeatherUnderground
                      API and return the response.
    """

    BASE_URL = 'https://api.weather.com/v3/wx/forecast/daily'

    def __init__(self, api_key, debug=0):
        # initialise a WeatherUndergroundAPIForecast object

        # save the API key to be used
        self.api_key = api_key
        # save debug level
        self.debug = debug

    def forecast_request(self, locator, location, forecast='5day', units='m',
                         language='en-GB', format='json', max_tries=3):
        """Make a forecast request via the API and return the results.

        Construct an API forecast call URL, make the call and return the
        response.

        Parameters:
            forecast:  The type of forecast required. String, must be one of
                       '3day', '5day', '7day', '10day' or '15day'.
            locator:   Type of location used. String. Must be a WU API supported
                       location type.
                       Refer https://docs.google.com/document/d/1RY44O8ujbIA_tjlC4vYKHKzwSwEmNxuGw5sEJ9dYjG4/edit#
            location:  Location argument. String.
            units:     Units to use in the returned data. String, must be one
                       of 'e', 'm', 's' or'h'.
                       Refer https://docs.google.com/document/d/13HTLgJDpsb39deFzk_YCQ5GoGoZCO_cRYzIxbwvgJLI/edit#heading=h.k9ghwen9fj7l
            language:  Language to return the response in. String, must be one
                       of the WU API supported language_setting codes
                       (eg 'en-US', 'es-MX', 'fr-FR').
                       Refer https://docs.google.com/document/d/13HTLgJDpsb39deFzk_YCQ5GoGoZCO_cRYzIxbwvgJLI/edit#heading=h.9ph8uehobq12
            format:    The output format_setting of the data returned by the WU
                       API. String, must be 'json' (based on WU API
                       documentation JSON is the only confirmed supported
                       format_setting.
            max_tries: The maximum number of attempts to be made to obtain a
                       response from the WU API. Default is 3.

        Returns:
            The WU API forecast response in JSON format_setting.
        """

        # construct the locator setting
        location_setting = '='.join([locator, location])
        # construct the units_setting string
        units_setting = '='.join(['units', units])
        # construct the language_setting string
        language_setting = '='.join(['language', language])
        # construct the format_setting string
        format_setting = '='.join(['format', format])
        # construct API key string
        api_key = '='.join(['apiKey', self.api_key])
        # construct the parameter string
        parameters = '&'.join([location_setting, units_setting,
                               language_setting, format_setting, api_key])

        # construct the base forecast url
        f_url = '/'.join([self.BASE_URL, forecast])

        # finally construct the full URL to use
        url = '?'.join([f_url, parameters])

        # if debug >=1 log the URL used but obfuscate the API key
        if weewx.debug > 0 or self.debug > 0:
            _obf_api_key = '='.join(['apiKey',
                                     '*'*(len(self.api_key) - 4) + self.api_key[-4:]])
            _obf_parameters = '&'.join([location_setting, units_setting,
                                        language_setting, format_setting,
                                        _obf_api_key])
            _obf_url = '?'.join([f_url, _obf_parameters])
            loginf("Submitting Weather Underground API call using URL: %s" % (_obf_url, ))
        # we will attempt the call max_tries times
        for count in range(max_tries):
            # attempt the call
            try:
                w = urllib.request.urlopen(url)
                # Get charset used so we can decode the stream correctly.
                # Unfortunately the way to get the charset depends on whether
                # we are running under python2 or python3. Assume python3 but be
                # prepared to catch the error if python2.
                try:
                    char_set = w.headers.get_content_charset()
                except AttributeError:
                    # must be python2
                    char_set = w.headers.getparam('charset')
                # now get the response decoding it appropriately
                response = w.read().decode(char_set)
                w.close()
                return response
            except (urllib.error.URLError, socket.timeout) as e:
                logerr("Failed to get Weather Underground forecast on attempt %d" % (count+1, ))
                logerr("   **** %s" % e)
        else:
            logerr("Failed to get Weather Underground forecast")
        return None


# ============================================================================
#                           class DarkSkySource
# ============================================================================


class DarkSkySource(ThreadedSource):
    """Thread that obtains Dark Sky data and places it in a queue.

    The DarkskyThread class queries the Darksky API and places selected data in
    JSON format in a queue used by the data consumer. The Dark Sky API is
    called at a user selectable rate. The thread listens for a shutdown signal
    from its parent.

    DarkskyThread constructor parameters:

        control_queue:       A Queue object used by our parent to control
                             (shutdown) this thread.
        result_queue:        A Queue object used to pass forecast data to the
                             destination
        engine:              A weewx.engine.StdEngine object
        source_config_dict:  A source config dictionary.

    DarkskyThread methods:

        run:            Control querying of the API and monitor the control
                        queue.
        get_raw_data:   Query the API and put selected forecast data in the
                        result queue.
        parse_raw_data: Parse a Darksky API response and return selected data.
    """

    # list of valid unit codes
    VALID_UNITS = {'auto': 'Automatic based on geolocation',
                   'ca': 'SI units but with kilometres per hour',
                   'uk2': 'SI units but with mile/miles per hour',
                   'us': 'Imperial units',
                   'si': 'SI units'}

    # list of valid language codes

    VALID_LANGUAGES = {'ar': 'Arabic',
                       'az': 'Azerbaijani',
                       'be': 'Belarusian',
                       'bg': 'Bulgarian',
                       'bn': 'Bengali',
                       'bs': 'Bosnian',
                       'ca': 'Catalan',
                       'cs': 'Czech',
                       'da': 'Danish',
                       'de': 'German',
                       'el': 'Greek',
                       'en': 'English',
                       'eo': 'Esperanto',
                       'es': 'Spanish',
                       'et': 'Estonian',
                       'fi': 'Finnish',
                       'fr': 'French',
                       'he': 'Hebrew',
                       'hi': 'Hindi',
                       'hr': 'Croatian',
                       'hu': 'Hungarian',
                       'id': 'Indonesian',
                       'is': 'Icelandic',
                       'it': 'Italian',
                       'ja': 'Japanese',
                       'ka': 'Georgian',
                       'kn': 'Kannada',
                       'ko': 'Korean',
                       'kw': 'Cornish',
                       'lv': 'Latvian',
                       'ml': 'Malayam',
                       'mr': 'Marathi',
                       'nb': 'Norwegian Bokmal',
                       'nl': 'Dutch',
                       'no': 'Norwegian Bokmal',
                       'pa': 'Punjabi',
                       'pl': 'Polish',
                       'pt': 'Portuguese',
                       'ro': 'Romanian',
                       'ru': 'Russian',
                       'sk': 'Slovak',
                       'sl': 'Slovenian',
                       'sr': 'Serbian',
                       'sv': 'Swedish',
                       'ta': 'Tamil',
                       'te': 'Telugu',
                       'tet': 'Tetum',
                       'tr': 'Turkish',
                       'uk': 'Ukrainian',
                       'ur': 'Urdu',
                       'x-pig-latin': 'Igpay Atinlay',
                       'zh': 'simplified Chinese',
                       'zh-tw': 'traditional Chinese'}

    # default forecast block to be used
    DEFAULT_BLOCK = 'daily'

    ICON_DICT = {'clear-day': (0, 1),
                 'clear-night': (0, 1),
                 'rain': (20, 14),
                 'snow': (25, 16),
                 'sleet': (23, 23),
                 'wind': (33, 33),
                 'fog': (6, 11),
                 'cloudy': (18, 13),
                 'partly-cloudy-day': (2, 4),
                 'partly-cloudy-night': (2, 4),
                 'hail': (23, 23),
                 'thunderstorm': (31, 17),
                 'tornado': (32, 32)}

    def __init__(self, control_queue, result_queue, engine, source_config_dict):

        # initialize my base class:
        super(DarkSkySource, self).__init__(control_queue, result_queue,
                                            engine, source_config_dict)

        # set thread name
        self.setName('WdDarkSkyThread')

        # DarkSkySource debug level
        self.debug = to_int(source_config_dict.get('debug', 0))

        # are we providing forecast data as well as current conditions data
        self.do_forecast = to_bool(source_config_dict.get('forecast', True))

        # Dark Sky uses lat, long to 'locate' the forecast. Check if lat and
        # long are specified in the source_config_dict, if not use station lat
        # and long.
        latitude = source_config_dict.get("latitude", engine.stn_info.latitude_f)
        longitude = source_config_dict.get("longitude", engine.stn_info.longitude_f)

        # interval between API calls
        self.interval = to_int(source_config_dict.get('interval', 1800))
        # max no of tries we will make in any one attempt to contact the API
        self.max_tries = to_int(source_config_dict.get('max_tries', 3))
        # Get API call lockout period. This is the minimum period between API
        # calls for the same feature. This prevents an error condition making
        # multiple rapid API calls and thus breach the API usage conditions.
        self.lockout_period = to_int(source_config_dict.get('api_lockout_period',
                                                            60))
        # Dark Sky can provide both forecast and current conditions data. Some
        # users may choose to use the forecast from another source (eg WU) but
        # still use the Dark Sky current conditions (WU does not provide
        # current conditions). So check what source data Dark Sky is to provide.
        _s_data = source_config_dict.get('source_data', 'both').lower()
        # do forecast if source_data contains 'both' or 'forecast'
        self.do_forecast = 'both' in _s_data or 'forecast' in _s_data
        # do current if source_data contains 'both' or 'current'
        self.do_current = 'both' in _s_data or 'current' in _s_data
        # if we have neither (ie source_data is nonsense) then do both
        if not (self.do_forecast or self.do_current):
            self.do_forecast = self.do_current = True
        # initialise container for timestamp of last API call
        self.last_call_ts = None
        # Get our API key from weewx.conf, first look in [RealtimeGaugeData]
        # [[WU]] and if no luck try [Forecast] if it exists. Wrap in a
        # try..except loop to catch exceptions (ie one or both don't exist.
        key = source_config_dict.get('api_key', None)
        if key is None:
            raise MissingApiKey("Cannot find valid Dark Sky key")
        # get a DarkskyForecastAPI object to handle the API calls
        self.api = DarkskyForecastAPI(key, latitude, longitude, self.debug)
        # get units to be used in forecast text
        _units = source_config_dict.get('units', 'ca').lower()
        # validate units
        self.units = _units if _units in self.VALID_UNITS else 'ca'
        # get language to be used in forecast text
        _language = source_config_dict.get('language', 'en').lower()
        # validate language
        self.language = _language if _language in self.VALID_LANGUAGES else 'en'
        # get the Darksky block to be used, default to our default
        self.block = source_config_dict.get('block', self.DEFAULT_BLOCK).lower()

        # log what we will do
        if self.do_forecast and self.do_current:
            loginf("Dark Sky API will be used for forecast and current conditions data")
        elif self.do_forecast:
            loginf("Dark Sky API will be used for forecast data only")
        elif self.do_current:
            loginf("Dark Sky API will be used for current conditions data only")
        if self.debug > 0:
            loginf("interval=%s lockout period=%s max tries=%s" % (self.interval,
                                                                   self.lockout_period,
                                                                   self.max_tries))
            loginf("units=%s language=%s block=%s" % (self.units,
                                                      self.language,
                                                      self.block))
            loginf("Dark Sky debug=%s" % self.debug)

    def get_raw_data(self):
        """If required query the Darksky API and return the JSON response.

        Checks to see if it is time to query the API, if so queries the API
        and returns the raw response in JSON format. To prevent the user
        exceeding their API call limit the query is only made if at least
        self.lockout_period seconds have elapsed since the last call.

        Inputs:
            None.

        Returns:
            The Darksky API response in JSON format or None if no/invalid
            response was obtained.
        """

        # get the current time
        now = time.time()
        if self.debug > 0:
            loginf("Last Dark Sky API call at %s" % weeutil.weeutil.timestamp_to_string(self.last_call_ts))
        # has the lockout period passed since the last call
        if self.last_call_ts is None or ((now + 1 - self.lockout_period) >= self.last_call_ts):
            # If we haven't made an API call previously or if its been too long
            # since the last call then make the call
            if (self.last_call_ts is None) or ((now + 1 - self.interval) >= self.last_call_ts):
                # Make the call, wrap in a try..except just in case
                try:
                    _response = self.api.get_data(block=self.block,
                                                  language=self.language,
                                                  units=self.units,
                                                  max_tries=self.max_tries)
                    if self.debug > 0:
                        if _response is not None:
                            loginf("Downloaded Dark Sky API response")
                        else:
                            loginf("Failed downloading Dark Sky API response")

                except Exception as e:
                    # Some unknown exception occurred. Set _response to None,
                    # log it and continue.
                    _response = None
                    loginf("Unexpected exception of type %s" % (type(e),))
                    log_traceback_info(prefix='wddarkskysource: **** ')
                    loginf("Unexpected exception of type %s" % (type(e),))
                    loginf("Dark Sky API call failed")
                # if we got something back then reset our last call timestamp
                if _response is not None:
                    self.last_call_ts = now
                return _response
        else:
            # API call limiter kicked in so say so
            loginf("Tried to make an Dark Sky API call within %d sec of the previous call." % (self.lockout_period,))
            loginf("Dark Sky API call limit reached. API call skipped.")
        return None

    def parse_raw_data(self, raw_data):
        """Parse a Darksky raw data.

        Take a Darksky raw data, check for (Darksky defined) errors then
        extract and return the required data.

        Input:
            raw_data: Darksky API response raw data in JSON format.

        Returns:
            Summary text or None.
        """

        _forecast = None
        _forecast_icon = None
        _current = None
        _current_icon = None
        # There is not too much validation of the data we can do other than
        # looking at the 'flags' object
        if 'flags' in raw_data:
            if 'darksky-unavailable' in raw_data['flags']:
                loginf("Dark Sky data for this location temporarily unavailable")
        else:
            loginf("No flag object in Dark Sky API raw data.")

        # get the summary data to be used
        # is our block available, can't assume it is
        if self.block in raw_data:
            if self.do_forecast:
                # we have our block and we are to provide forecast data but is
                # the summary there
                if 'summary' in raw_data[self.block]:
                    # we have a summary field
                    _forecast = raw_data[self.block]['summary']
                    # can we extract an icon number
                    if 'icon' in raw_data[self.block]:
                        # assume we will use a 'day' icon
                        day = True
                        # but let's see if we have a time to refute our assumption
                        if 'time' in raw_data[self.block]:
                            try:
                                # get a datetime object, wrap in a try..except in
                                # case 'time' is not a valid epoch timestamp
                                _dt = datetime.fromtimestamp(raw_data[self.block]['time'])
                            except TypeError:
                                # can't convert the timestamp so stick with our
                                # assumption
                                pass
                            else:
                                # use a day from 6am to 6pm
                                day = 6 <= _dt.hour < 18
                        # get the appropriate icon tuple from our dict, default to
                        # 'clear-day' if the icon does not exist
                        icons = self.ICON_DICT.get(raw_data[self.block]['icon'].lower(),
                                                   self.ICON_DICT['clear-day'])
                        # choose either the day or night icon
                        _forecast_icon = icons[0] if day else icons[1]
                else:
                    # we have no summary field, so log it and return None
                    if self.debug > 0:
                        loginf("Summary data not available for '%s' forecast" % (self.block,))
        else:
            if self.debug > 0:
                loginf("Dark Sky %s block not available" % self.block)
        # get the current data and icon
        # is the 'currently' block available, can't assume it is
        if 'currently' in raw_data:
            if self.do_current:
                # we have our block and we are to provide current conditions
                # data but is the summary there
                if 'summary' in raw_data['currently']:
                    # we have a summary field
                    _current = raw_data['currently']['summary']
                    # can we extract an icon number
                    if 'icon' in raw_data['currently']:
                        # assume we will use a 'day' icon
                        day = True
                        # but let's see if we have a time to refute our assumption
                        if 'time' in raw_data['currently']:
                            try:
                                # get a datetime object, wrap in a try..except in
                                # case 'time' is not a valid epoch timestamp
                                _dt = datetime.fromtimestamp(raw_data['currently']['time'])
                            except TypeError:
                                # can't convert the timestamp so stick with our
                                # assumption
                                pass
                            else:
                                # use a day from 6am to 6pm
                                day = 6 <= _dt.hour < 18
                        # get the appropriate icon tuple from our dict, default to
                        # 'clear-day' if the icon does not exist
                        icons = self.ICON_DICT.get(raw_data['currently']['icon'].lower(),
                                                   self.ICON_DICT['clear-day'])
                        # choose either the day or night icon
                        _current_icon = icons[0] if day else icons[1]
                else:
                    # we have no summary field, so log it and return None
                    if self.debug > 0:
                        loginf("Summary data not available for 'currently' block")
        else:
            if self.debug > 0:
                loginf("Dark Sky 'currently' block not available")

        # if we have at least one non-None value then return a dict, else
        # return None
        if any(a is not None for a in (_forecast_icon, _forecast, _current_icon, _current)):
            # we have something to return but only return what we were asked
            _dict = dict()
            # do we need to return forecast data
            if self.do_forecast:
                _dict.update({'forecastIcon': _forecast_icon,
                              'forecastText': _forecast})
            # do we need to return current data
            if self.do_current:
                _dict.update({'currentIcon': _current_icon,
                              'currentText': _current})
            return _dict
        else:
            # we have no data so return None
            return None


# ==============================================================================
#                           class DarkskyForecastAPI
# ==============================================================================


class DarkskyForecastAPI(object):
    """Query the Darksky API and return the API response.

    DarkskyForecastAPI constructor parameters:

        darksky_config_dict: Dictionary keyed as follows:
            key:       Darksky secret key to be used
            latitude:  Latitude of the location concerned
            longitude: Longitude of the location concerned

    DarkskyForecastAPI methods:

        get_data. Submit a data request to the Darksky API and return the
                  response.

        _build_optional: Build a string containing the optional parameters to
                         submitted as part of the API request URL.

        _hit_api: Submit the API request and capture the response.

        obfuscated_key: Property to return an obfuscated secret key.
    """

    # base URL from which to construct an API call URL
    BASE_URL = 'https://api.darksky.net/forecast'
    # blocks we may want to exclude, note we need 'currently' for current
    # conditions
    BLOCKS = ('minutely', 'hourly', 'daily', 'alerts')

    def __init__(self, key, latitude, longitude, debug=0):
        # initialise a DarkskyForecastAPI object

        # save the secret key to be used
        self.key = key
        # save lat and long
        self.latitude = latitude
        self.longitude = longitude
        # save DS debug level
        self.debug = debug

    def get_data(self, block='hourly', language='en', units='auto',
                 max_tries=3):
        """Make a data request via the API and return the response.

        Construct an API call URL, make the call and return the response.

        Parameters:
            block:     Darksky block to be used. None or list of strings, default is None.
            language:  The language to be used in any response text. Refer to
                       the optional parameter 'language' at
                       https://darksky.net/dev/docs. String, default is 'en'.
            units:     The units to be used in the response. Refer to the
                       optional parameter 'units' at https://darksky.net/dev/docs.
                       String, default is 'auto'.
            max_tries: The maximum number of attempts to be made to obtain a
                       response from the API. Number, default is 3.

        Returns:
            The Darksky API response in JSON format.
        """

        # start constructing the API call URL to be used
        url = '/'.join([self.BASE_URL,
                        self.key,
                        '%s,%s' % (self.latitude, self.longitude)])

        # now build the optional parameters string
        optional_string = self._build_optional(block=block,
                                               language=language,
                                               units=units)
        # if it has any content then add it to the URL
        if len(optional_string) > 0:
            url = '?'.join([url, optional_string])

        # if debug >= 1 log the URL used but obfuscate the key
        if weewx.debug > 0 or self.debug > 0:
            _obfuscated_url = '/'.join([self.BASE_URL,
                                        self.obfuscated_key,
                                        '%s,%s' % (self.latitude, self.longitude)])
            _obfuscated_url = '?'.join([_obfuscated_url, optional_string])
            loginf("Submitting API call using URL: %s" % (_obfuscated_url,))
        # make the API call
        _response = self._hit_api(url, max_tries)
        # if we have a response we need to deserialise it
        json_response = json.loads(_response) if _response is not None else None
        # return the response
        return json_response

    def _build_optional(self, block='hourly', language='en', units='auto'):
        """Build the optional parameters string."""

        # initialise a list of non-None optional parameters and their values
        opt_params_list = []
        # exclude all but our block
        _blocks = [b for b in self.BLOCKS if b != block]
        opt_params_list.append('exclude=%s' % ','.join(_blocks))
        # language
        if language is not None:
            opt_params_list.append('lang=%s' % language)
        # units
        if units is not None:
            opt_params_list.append('units=%s' % units)
        # now if we have any parameters concatenate them separating each with
        # an ampersand
        opt_params = "&".join(opt_params_list)
        # return the resulting string
        return opt_params

    def _hit_api(self, url, max_tries=3):
        """Make the API call and return the result."""

        # we will attempt the call max_tries times
        for count in range(max_tries):
            # attempt the call
            try:
                w = urllib.request.urlopen(url)
                # Get charset used so we can decode the stream correctly.
                # Unfortunately the way to get the charset depends on whether
                # we are running under python2 or python3. Assume python3 but be
                # prepared to catch the error if python2.
                try:
                    char_set = w.headers.get_content_charset()
                except AttributeError:
                    # must be python2
                    char_set = w.headers.getparam('charset')
                # now get the response decoding it appropriately
                response = w.read().decode(char_set)
                w.close()
                if self.debug > 1:
                    logdbg("Dark Sky API response=%s" % (response, ))
                return response
            except (urllib.error.URLError, socket.timeout) as e:
                logerr("Failed to get API response on attempt %d" % (count + 1,))
                logerr("   **** %s" % e)
        else:
            logerr("Failed to get API response")
        return None

    @property
    def obfuscated_key(self):
        """Produce and obfuscated copy of the key."""

        # replace all characters in the key with an asterisk except for the
        # last 4
        return '*' * (len(self.key) - 4) + self.key[-4:]


# ==============================================================================
#                               class FileSource
# ==============================================================================


class FileSource(ThreadedSource):
    """Class to obtain forecast and current conditions from a formatted text
       file.

    FileSource constructor parameters:

        control_queue:      A Queue object used by our parent to control
                            (shutdown) this thread.
        result_queue:       A Queue object used to pass forecast data to the
                            destination
        engine:             An instance of class weewx.weewx.Engine
        source_config_dict: source config dictionary.

    FileSource methods:

        run: Control fetching the text and monitor the control queue.
    """

    # structure of the text file, one entry per line
    FORECAST_STRUCT = ('forecastText', 'forecastIcon')
    CURRENT_STRUCT = ('currentText', 'currentIcon')

    def __init__(self, control_queue, result_queue, engine, source_config_dict):

        # initialize my base class
        super(FileSource, self).__init__(control_queue,
                                         result_queue,
                                         engine,
                                         source_config_dict)

        # set thread name
        self.setName('WdFileThread')

        # FileSource debug level
        self.debug = to_int(source_config_dict.get('debug', 0))

        # interval between file reads
        self.interval = to_int(source_config_dict.get('interval', 1800))
        # get the file to be read, check it refers to a file
        self.file = source_config_dict.get('file')
        if self.file is None or not os.path.isfile(self.file):
            raise MissingFile("Source file not specified or not a valid path/file")

        # Text file source can provide both forecast and current conditions
        # data. Some users may choose to use the forecast from another source
        # (eg WU) but still use the file source for current conditions (WU does
        # not provide current conditions). So check what source data the file
        # source is to provide.
        _s_data = source_config_dict.get('source_data', 'both').lower()
        # do forecast if source_data contains 'both' or 'forecast'
        self.do_forecast = 'both' in _s_data or 'forecast' in _s_data
        # do current if source_data contains 'both' or 'current'
        self.do_current = 'both' in _s_data or 'current' in _s_data
        # if we have neither (ie source_data is nonsense) then do both
        if not (self.do_forecast or self.do_current):
            self.do_forecast = self.do_current = True

        # initialise the time of last file read
        self.last_read_ts = None

        # log what we will do
        if self.do_forecast and self.do_current:
            loginf("Formatted text file will be used for forecast and current conditions data")
        elif self.do_forecast:
            loginf("Formatted text file will be used for forecast data only")
        elif self.do_current:
            loginf("Formatted text file will be used for current conditions data only")
        if self.debug > 0:
            loginf("file=%s interval=%s" % (self.file, self.interval))
            loginf("File debug=%s" % self.debug)

    def get_raw_data(self):
        """Get forecast and current conditions data from a formatted text file.

        Checks to see if it is time to read the file, if so the file is read
        and the stripped raw text returned.

        Inputs:
            None.

        Returns:
            The first line of text from the file.
        """

        # get the current time
        now = time.time()
        if self.debug > 0:
            if self.last_read_ts is not None:
                loginf("Last file read attempted at %s" % weeutil.weeutil.timestamp_to_string(self.last_read_ts))
        if self.last_read_ts is None or (now + 1 - self.interval) >= self.last_read_ts:
            # read the file, wrap in a try..except just in case
            _data = None
            try:
                if self.file is not None:
                    with open(self.file) as f:
                        _data = f.readlines()
                if self.debug > 0:
                    loginf("File '%s' read" % self.file)
            except Exception as e:
                # Some unknown exception occurred, likely IOError. Set _data to
                # None, log it and continue.
                _data = None
                loginf("Unexpected exception of type %s" % (type(e),))
                log_traceback_info(prefix='wdfilesource: **** ')
                loginf("Unexpected exception of type %s" % (type(e),))
                loginf("Read of file '%s' failed" % self.file)
            # we got something so reset our last read timestamp
            if _data is not None:
                self.last_read_ts = now
            # and finally return the read data
            return _data
        return None

    def parse_raw_data(self, raw_data):
        """Parse raw file data.

        Take the raw file data, extract and return the required data.

        Input:
            raw_data: List of lines of data read from a formatted text file.

        Returns:
            dict of data.
        """

        # do we have any data
        if raw_data is not None:
            # work out what our data file structure was, it will depend on
            # whether we had forecast and current data or just forecast or just
            # current
            if self.do_forecast and self.do_current:
                _file_structure = self.FORECAST_STRUCT + self.CURRENT_STRUCT
            elif self.do_forecast:
                _file_structure = self.FORECAST_STRUCT
            else:
                _file_structure = self.CURRENT_STRUCT
            # initialise holder dict for our parsed data
            _parsed = dict()
            # iterate over each field we are looking for
            for index, key in enumerate(_file_structure):
                # assign the relevant data to the relevant key in the dict,
                # wrap in a try..except in case something is missing or
                # otherwise wrong
                try:
                    # icon numbers need to be integers
                    if 'Icon' in key:
                        # it's an icon so convert to an integer
                        _parsed[key] = int(raw_data[index].strip())
                    else:
                        # it's text so leave as it
                        _parsed[key] = raw_data[index].strip()
                except (IndexError, ValueError):
                    # could find the entry in our raw data so set to None
                    _parsed[key] = None
            # return the dict of data
            return _parsed
        else:
            # there was no raw data so return None
            return None


# ==============================================================================
#                                   Utilities
# ==============================================================================


def toint(string, default):
    """Convert a string to an integer whilst handling None and a default.

        If string cannot be converted to an integer default is returned.

        Input:
            string:  The value to be converted to an integer
            default: The value to be returned if value cannot be converted to
                     an integer
    """

    # is string None or do we have a string and is it some variation of 'None'
    if string is None or (isinstance(string, str) and string.lower() == 'none'):
        # we do so our result will be None
        return None
    # otherwise try to convert it
    else:
        try:
            return int(string)
        except ValueError:
            # we can't convert it so our result will be the default
            return default


def calc_day_night(data_dict):
    """ 'Calculate' value for outTempDay and outTempNight.

        outTempDay and outTempNight are used to determine warmest night
        and coldest day stats. This is done by using two derived
        observations; outTempDay and outTempNight. These observations
        are defined as follows:

        outTempDay:   equals outTemp if time of day is > 06:00 and <= 18:00
                      otherwise it is None
        outTempNight: equals outTemp if time of day is > 18:00 or <= 06:00
                      otherwise it is None

        By adding these derived obs to the schema and loop packet the daily
        summaries for these obs are populated and aggregate stats can be
        accessed as per normal (eg $month.outTempDay.minmax to give the
        coldest max daytime temp in the month). Note that any aggregates that
        rely on the number of records (eg avg) will be meaningless due to
        the way outTempxxxx is calculated.
    """

    if 'outTemp' in data_dict:
        # check if record covers daytime (6AM to 6PM) and if so make field
        # 'outTempDay' = field 'outTemp' otherwise make field 'outTempNight' =
        # field 'outTemp', remember record timestamped 6AM belongs in the night
        # time
        _hour = datetime.fromtimestamp(data_dict['dateTime'] - 1).hour
        if _hour < 6 or _hour > 17:
            # ie the data packet is from before 6am or after 6pm
            return None, data_dict['outTemp']
        else:
            # ie the data packet is from after 6am and before or including 6pm
            return data_dict['outTemp'], None
    else:
        return None, None


def calc_sunshine(data_dict, threshold=120):
    """ 'Calculate' value for sunshine.

        'sunshine' is a measure of duration the sun shining during the day and
        is normally measured using a sunshine recorder. It can be approximated
        by calculating the time the solar irradiance is greater than a given
        threshold value.
    """

    # we know we have a radiation field but is it non-None and do we have
    # field interval
    if data_dict['radiation'] is not None and 'interval' in data_dict:
        # We have the pre-requisites. sunshine is simply the interval (in
        # seconds) if radiation >= the threshold value or 0 if radiation is
        # below the threshold value.
        if data_dict['radiation'] >= threshold:
            return data_dict['interval'] * 60
        else:
            return 0
    # we can' calculate sunshine so return None
    return None


def check_enable(cfg_dict, service, *args):

    try:
        wdsupp_dict = accumulateLeaves(cfg_dict[service], max_level=1)
    except KeyError:
        if weewx.debug >= 2:
            logdbg("%s: No config info. Skipped." % service)
        return None

    # check to see whether all the needed options exist, and none of them have
    # been set to 'replace_me'
    try:
        for option in args:
            if wdsupp_dict[option] == 'replace_me':
                raise KeyError(option)
    except KeyError as e:
        if weewx.debug >= 2:
            logdbg("%s: Missing option %s" % (service, e))
        return None

    return wdsupp_dict

# ============================================================================
#                            class SimpleWuSource
# ============================================================================


class SimpleWuSource(WuSource):
    """Simplified version of WuSource object for testing.

    A simplified version of the WuSource object for use in testing. Has all the
    same properties and methods of a WuSource object but instead on
    continuously polling the WU API it polls once only. The source is still
    closed by placing the value None in the control queue.
    """

    def __init__(self, control_queue, result_queue, engine,
                 source_config_dict=None):

        # initialize my superclass
        super(SimpleWuSource, self).__init__(control_queue, result_queue,
                                             engine, source_config_dict)

    def run(self):
        _package = None
        # get the raw data
        _raw_data = self.get_raw_data()
        # if we have a non-None response then we have data so parse it,
        # gather the required data and put it in the result queue
        if _raw_data is not None:
            # parse the raw data response and extract the required data
            _data = self.parse_raw_data(_raw_data)
            # if we have some data then place it in the result queue
            if _data is not None:
                # construct our data dict for the queue
                _package = {'type': 'data',
                            'payload': _data}
        self.result_queue.put(_package)


# ============================================================================
#                         class SimpleDarkSkySource
# ============================================================================


class SimpleDarkSkySource(DarkSkySource):
    """Simplified version of DarkSkySource object for testing.

    A simplified version of the DarkSkySource object for use in testing. Has
    all the same properties and methods of a DarkSkySource object but instead on
    continuously polling the WU API it polls once only. The source is still
    closed by placing the value None in the control queue.
    """

    def __init__(self, control_queue, result_queue, engine,
                 source_config_dict=None):

        # initialize my superclass
        super(SimpleDarkSkySource, self).__init__(control_queue, result_queue,
                                                  engine, source_config_dict)

    def run(self):
        _package = None
        # get the raw data
        _raw_data = self.get_raw_data()
        # if we have a non-None response then we have data so parse it,
        # gather the required data and put it in the result queue
        if _raw_data is not None:
            # parse the raw data response and extract the required data
            _data = self.parse_raw_data(_raw_data)
            # if we have some data then place it in the result queue
            if _data is not None:
                # construct our data dict for the queue
                _package = {'type': 'data',
                            'payload': _data}
        self.result_queue.put(_package)


# ============================================================================
#                           class SimpleFileSource
# ============================================================================


class SimpleFileSource(FileSource):
    """Simplified version of FileSource object for testing.

    A simplified version of the FileSource object for use in testing. Has all
    the same properties and methods of a FileSource object but instead on
    continuously polling the WU API it polls once only. The source is still
    closed by placing the value None in the control queue.
    """

    def __init__(self, control_queue, result_queue, engine,
                 source_config_dict=None):

        # initialize my superclass
        super(SimpleFileSource, self).__init__(control_queue, result_queue,
                                               engine, source_config_dict)

    def run(self):
        _package = None
        # get the raw data
        _raw_data = self.get_raw_data()
        # if we have a non-None response then we have data so parse it,
        # gather the required data and put it in the result queue
        if _raw_data is not None:
            # parse the raw data response and extract the required data
            _data = self.parse_raw_data(_raw_data)
            # if we have some data then place it in the result queue
            if _data is not None:
                # construct our data dict for the queue
                _package = {'type': 'data',
                            'payload': _data}
        self.result_queue.put(_package)


# ============================================================================
#                             class SimpleEngine
# ============================================================================


class SimpleEngine(object):
    """Simplified version of a WeeWX engine object.

    Used to simulate a WeeWX engine object that only provides station latitude
    and longitude.
    """

    def __init__(self, config_dict):
        # create our stn_info property
        self.stn_info = self.SimpleStationInfo(**config_dict['Station'])

    class SimpleStationInfo(object):
        """Simplified version of a Station object.

        Used to provide latitude_f and longitude_f properties to a SimpleEngine
        object.
        """

        def __init__(self, **stn_dict):
            # create latitude_f and longitude_f properties
            self.latitude_f = float(stn_dict['latitude'])
            self.longitude_f = float(stn_dict['longitude'])


# ============================================================================
#                          Main Entry for Testing
# ============================================================================


"""
Define a main entry point for basic testing without the WeeWX engine and 
services overhead. To invoke this module without WeeWX:

    $ PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/wd.py --option

    where option is one of the following options:
        --help            - display command line help
        --version         - display version
        --get-wu-data     - display WU API data
        --get-wu-config   - display WU API config parameters to be used 
        --get-ds-data     - display Dark Sky API data
        --get-ds-config   - display Dark Sky API config parameters to be used 
        --get-file-data   - display Dark Sky API data
        --get-file-config - display Dark Sky API config parameters to be used 
"""

if __name__ == '__main__':

    # python imports
    import optparse
    import pprint
    import sys

    # WeeWX imports
    import weecfg

    usage = """PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/%prog [--option]"""

    syslog.openlog('weewxwd', syslog.LOG_PID | syslog.LOG_CONS)
    syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_DEBUG))
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--config', dest='config_path', type=str,
                      metavar="CONFIG_FILE",
                      help="Use configuration file CONFIG_FILE.")
    parser.add_option('--version', dest='version', action='store_true',
                      help='Display module version.')
    parser.add_option('--get-wu-data', dest='wu_data',
                      action='store_true',
                      help='Query WU API and display results.')
    parser.add_option('--get-wu-config', dest='wu_config',
                      action='store_true',
                      help='Display config data used to access the WU API.')
    parser.add_option('--get-ds-data', dest='ds_data',
                      action='store_true',
                      help='Query Dark Sky API and display results.')
    parser.add_option('--get-ds-config', dest='ds_config',
                      action='store_true',
                      help='Display config data used to access the Dark Sky API.')
    parser.add_option('--get-file-data', dest='file_data',
                      action='store_true',
                      help='Display data from a file source.')
    parser.add_option('--get-file-config', dest='file_config',
                      action='store_true',
                      help='Display config data used to access the a file source.')
    (options, args) = parser.parse_args()

    if options.version:
        print("weewxwd version %s" % WEEWXWD_VERSION)
        exit(0)

    # get config_dict to use
    config_path, config_dict = weecfg.read_config(options.config_path, args)
    print("Using configuration file %s" % config_path)

    # get a WeeWX-WD config dict
    weewxwd_dict = config_dict.get('Weewx-WD', None)
    
    # get a WuData object
    if weewxwd_dict is not None:
        # get result and control queues for our source
        result_queue = queue.Queue()
        control_queue = queue.Queue()
        if options.wu_data or options.wu_config:
            # get a simplified engine to feed to our source object
            _engine = SimpleEngine(config_dict)
            # get the WU source config dict
            source_config_dict = weewxwd_dict['Supplementary'].get('WU')
            # now get a modified WU source object
            source = SimpleWuSource(control_queue,
                                    result_queue,
                                    _engine,
                                    source_config_dict)
        elif options.ds_data or options.ds_config:
            # get a simplified engine to feed to our source object
            _engine = SimpleEngine(config_dict)
            # get the WU source config dict
            source_config_dict = weewxwd_dict['Supplementary'].get('DS')
            # now get a modified WU source object
            source = SimpleDarkSkySource(control_queue,
                                         result_queue,
                                         _engine,
                                         source_config_dict)
        elif options.file_data or options.file_config:
            # get a simplified engine to feed to our source object
            _engine = SimpleEngine(config_dict)
            # get the WU source config dict
            source_config_dict = weewxwd_dict['Supplementary'].get('File')
            # now get a modified WU source object
            source = SimpleFileSource(control_queue,
                                      result_queue,
                                      _engine,
                                      source_config_dict)
        # finally start the simplified source object
        source.start()
    else:
        exit_str = "'Weewx-WD' stanza not found in config file '%s'. Exiting." % config_path
        sys.exit(exit_str)
    
    if options.wu_data:
        # now get any data in the queue
        try:
            # use nowait() so we don't block
            _package = result_queue.get(True, 15)
        except queue.Empty:
            # nothing in the queue so exit with appropriate message
            print("No data obtained from Weather Underground API")
            print("Suggest Weather Underground config data be checked")
        else:
            # we did get something in the queue but was it a data package
            if isinstance(_package, dict):
                if 'type' in _package and _package['type'] == 'data':
                    # we have forecast text so print it
                    print()
                    print("The following data was extracted from the Weather Underground API:")
                    pprint.pprint(_package['payload'])
                else:
                    # received an invalid data package
                    print("Invalid data obtained from Weather Underground API:")
                    print(pprint.pprint(_package))
            else:
                # received an invalid data package
                print("Invalid data obtained from Weather Underground API:")
                print(pprint.pprint(_package))
        # sent the shutdown signal to our source thread
        control_queue.put(None)
        sys.exit(0)

    if options.wu_config:
        print()
        print("The following config data will be used to access the Weather Underground API:")
        print()
        if source.api.api_key is not None:
            _len = len(source.api.api_key)
            print("%24s: %s%s" % ('API key',
                                  (_len - 4) * 'x',
                                  source.api.api_key[-4:]))
        else:
            print("Cannot find valid Weather Underground API key.")
        print("%24s: %s" % ('Forecast type', source.forecast))
        print("%24s: %s" % ('Forecast text to display', source.forecast_text))
        print("%24s: %s" % ('Locator', source.locator))
        print("%24s: %s" % ('Location', source.location))
        print("%24s: %s (%s)" % ('Units',
                                 source.units,
                                 source.VALID_UNITS[source.units]))
        print("%24s: %s (%s)" % ('Language',
                                 source.language,
                                 source.VALID_LANGUAGES[source.language]))
        if source.api.api_key is None:
            print("Weather Underground API will not be accessed.")
        control_queue.put(None)
        sys.exit(0)

    if options.ds_data:
        # now get any data in the queue
        try:
            # use nowait() so we don't block
            _package = result_queue.get(True, 15)
        except queue.Empty:
            # nothing in the queue so exit with appropriate message
            print("No data obtained from Dark Sky API")
            print("Suggest Dark Sky config data be checked")
        else:
            # we did get something in the queue but was it a data package
            if isinstance(_package, dict):
                if 'type' in _package and _package['type'] == 'data':
                    # we have something so print it
                    print()
                    print("The following data was extracted from the Dark Sky API:")
                    pprint.pprint(_package['payload'])
                else:
                    # received an invalid data package
                    print("Invalid data obtained from Dark Sky API:")
                    print(pprint.pprint(_package))
            else:
                # received an invalid data package
                print("Invalid data obtained from Dark Sky API:")
                print(pprint.pprint(_package))
        # sent the shutdown signal to our source thread
        control_queue.put(None)
        sys.exit(0)

    if options.ds_config:
        print()
        print("The following config data will be used to access the Dark Sky API:")
        if source.api.key is not None:
            _len = len(source.api.key)
            print("%18s: %s%s" % ('API key',
                                  (_len - 4) * 'x',
                                  source.api.key[-4:]))
        else:
            print("Cannot find valid Dark Sky API key.")
        print("%18s: %s" % ('Block', source.block))
        if source.do_forecast and source.do_current:
            print("%18s: %s" % ('Data to be sourced',
                                'Forecast and current conditions'))
        elif source.do_forecast:
            print("%18s: %s" % ('Data to be sourced', 'Forecast only'))
        elif source.do_current:
            print("%18s: %s" % ('Data to be sourced', 'Current conditions only'))
        else:
            print("%18s: %s" % ('Data to be sourced', 'Nothing selected'))
        print("%18s: %s,%s" % ('Location', _engine.stn_info.latitude_f, _engine.stn_info.longitude_f))
        print("%18s: %s (%s)" % ('Units',
                                 source.units,
                                 source.VALID_UNITS[source.units]))
        print("%18s: %s (%s)" % ('Language',
                                 source.language,
                                 source.VALID_LANGUAGES[source.language]))
        if source.api.key is None:
            print("Dark Sky API will not be accessed.")
        control_queue.put(None)
        sys.exit(0)

    if options.file_data:
        # now get any data in the queue
        try:
            # use nowait() so we don't block
            _package = result_queue.get(True, 15)
        except queue.Empty:
            # nothing in the queue so exit with appropriate message
            print("No data obtained from file source")
            print("Suggest file source config data be checked")
        else:
            # we did get something in the queue but was it a data package
            if isinstance(_package, dict):
                if 'type' in _package and _package['type'] == 'data':
                    # we have something so print it
                    print()
                    print("The following data was extracted from the file source:")
                    pprint.pprint(_package['payload'])
                else:
                    # received an invalid data package
                    print("Invalid data obtained from the file source:")
                    print(pprint.pprint(_package))
            else:
                # received an invalid data package
                print("Invalid data obtained from the file source:")
                print(pprint.pprint(_package))
        # sent the shutdown signal to our source thread
        control_queue.put(None)
        sys.exit(0)

    if options.file_config:
        print()
        print("The following config data will be used to access a file source:")
        print("%18s: %s" % ('File', source.file))
        if source.do_forecast and source.do_current:
            print("%18s: %s" % ('Data to be sourced',
                                'Forecast and current conditions'))
        elif source.do_forecast:
            print("%18s: %s" % ('Data to be sourced', 'Forecast only'))
        elif source.do_current:
            print("%18s: %s" % ('Data to be sourced', 'Current conditions only'))
        else:
            print("%18s: %s" % ('Data to be sourced', 'Nothing selected'))
        control_queue.put(None)
        sys.exit(0)

    # if we made it here display our help message
    parser.print_help()

KNOWN_SOURCES = {'WU': WuSource,
                 'DS': DarkSkySource,
                 'File': FileSource}
