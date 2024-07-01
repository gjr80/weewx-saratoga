"""
ws.py

Service classes used by WeeWX-Saratoga

Copyright (C) 2021-2023 Gary Roderick                gjroderick<at>gmail.com

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

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
        - version number change only
    7 February 2022     v0.1.3
        - version number change only
    25 November 2021    v0.1.2
        - WsWXCalculate now logs pyephem installation status on startup
    21 May 2021         v0.1.1
        - version number change only
    13 May 2021         v0.1.0
        - initial release
"""

# python imports
import sys
import time
from datetime import datetime

# WeeWX imports
import weewx
import weewx.almanac
import weewx.engine
import weewx.manager
import weewx.units
import weewx.wxformulas

from weewx.units import obs_group_dict

# import/setup logging, WeeWX v3 is syslog based but WeeWX v4 is logging based,
# try v4 logging and if it fails use v3 logging
try:
    # WeeWX4 logging
    import logging

    log = logging.getLogger(__name__)

    def logdbg(msg):
        log.debug(msg)

    def loginf(msg):
        log.info(msg)

    def logerr(msg):
        log.error(msg)

    def logcri(msg):
        log.critical(msg)

except ImportError:
    # WeeWX legacy (v3) logging via syslog
    import syslog

    def logmsg(level, msg):
        syslog.syslog(level, 'ws: %s' % msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

    def logcri(msg):
        logmsg(syslog.LOG_CRIT, msg)

WS_VERSION = '0.1.10'

# Default radiation threshold value used for calculating sunshine
DEFAULT_SUNSHINE_THRESHOLD = 120


# ==============================================================================
#                              Class WsWXCalculate
# ==============================================================================

class WsWXCalculate(weewx.engine.StdService):
    """Service to calculate WeeWX-Saratoga specific observations."""

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WsWXCalculate, self).__init__(engine, config_dict)

        # determine the radiation threshold value for calculating sunshine, if
        # it is missing use a suitable default
        if 'WeewxSaratoga' in config_dict:
            self.sunshine_threshold = config_dict['WeewxSaratoga'].get('sunshine_threshold',
                                                                       DEFAULT_SUNSHINE_THRESHOLD)
        else:
            self.sunshine_threshold = DEFAULT_SUNSHINE_THRESHOLD
        # bind our self to new loop packet and new archive record events
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        # log our version and config
        loginf("WsWXCalculate version %s" % WS_VERSION)
        loginf("WsWXCalculate sunshine threshold: %s" % self.sunshine_threshold)
        # not really our place to say since we don't use extended Almanac
        # capabilities, but since some of our supported templates/SLEs do we
        # will log pyephem's availability
        if 'ephem' in sys.modules:
            loginf('pyephem was detected')
        else:
            loginf('pyephem was not detected')

    @staticmethod
    def new_loop_packet(event):
        """Add outTempDay and outTempNight to the loop packet."""

        _x = dict()
        if 'outTemp' in event.packet:
            _x['outTempDay'], _x['outTempNight'] = calc_day_night(event.packet)
        event.packet.update(_x)

    @staticmethod
    def new_archive_record(event):
        """Add any WeeWX-Saratoga derived fields to the archive record."""

        _x = dict()
        if 'outTemp' in event.record:
            _x['outTempDay'], _x['outTempNight'] = calc_day_night(event.record)
        if 'radiation' in event.record:
            _x['sunshine'] = calc_sunshine(event.record)
        event.record.update(_x)


# ==============================================================================
#                                Class WsArchive
# ==============================================================================

class WsArchive(weewx.engine.StdService):
    """Service to store Weewx-Saratoga specific archive data."""

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WsArchive, self).__init__(engine, config_dict)

        # log our version
        loginf("WsArchive version %s" % WS_VERSION)
        # Extract our binding from the WeeWX-Saratoga section of the config file. If
        # it's missing, fill with a default.
        if 'WeewxSaratoga' in config_dict:
            self.data_binding = config_dict['WeewxSaratoga'].get('data_binding',
                                                                 'ws_binding')
        else:
            self.data_binding = 'ws_binding'

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
        obs_group_dict["outTempDay"] = "group_temperature"
        obs_group_dict["outTempNight"] = "group_temperature"
        obs_group_dict["sunshine"] = "group_elapsed"

        # bind ourselves to NEW_ARCHIVE_RECORD event
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    def new_archive_record(self, event):
        """Save the WeeWX-Saratoga archive record.

           Use our db manager's addRecord method to save the relevant
           WeeWX-Saratoga fields to the WeeWX-Saratoga archive.
        """

        # get our db manager
        dbmanager = self.engine.db_binder.get_manager(self.data_binding)
        # now put the record in the archive
        dbmanager.addRecord(event.record)

    def setup_database(self):
        """Setup the WeeWX-Saratoga database"""

        # create the database if it doesn't exist and a db manager for the
        # opened database
        dbmanager = self.engine.db_binder.get_manager(self.data_binding,
                                                      initialize=True)
        loginf("Using binding '%s' to database '%s'" % (self.data_binding,
                                                        dbmanager.database_name))

        # Check if we have any historical data to bring in from the WeeWX
        # archive.
        # first get a dbmanager for the WeeWX archive
        dbmanager_wx = self.engine.db_binder.get_manager(self.data_binding_wx,
                                                         initialize=False)

        # then backfill the WeeWX-Saratoga daily summaries
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
#                                   Utilities
# ==============================================================================

def toint(string, default=None):
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