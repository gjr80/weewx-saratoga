"""
weatherapi.py

A collection of WeeWX services to obtain data from external Weather APIs.

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

Version: 0.1.0                                      Date: 12 June 2023

Revision History
    12 June 2023        v0.1.0
        - initial implementation
"""

# python imports
import json
import os
import os.path
import queue
import socket
import threading
import time

# python 2/3 compatibility shims
import six
from six.moves import urllib

# WeeWX imports
import weewx
import weeutil.config
import weeutil.weeutil
import weewx.engine

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
    # different between v3 and v4. Define suitable wrapper functions for those
    # levels needed.
    def log_traceback_critical(prefix=''):
        log_traceback(log.critical, prefix=prefix)

    def log_traceback_error(prefix=''):
        log_traceback(log.error, prefix=prefix)

except ImportError:
    # WeeWX legacy (v3) logging via syslog
    import syslog
    from weeutil.weeutil import log_traceback

    def logmsg(level, msg):
        syslog.syslog(level, 'weatherapi: %s' % msg)

    def logcrit(msg):
        logmsg(syslog.LOG_CRIT, msg)

    def logdbg(msg):
        logmsg(syslog.LOG_DEBUG, msg)

    def logerr(msg):
        logmsg(syslog.LOG_ERR, msg)

    def loginf(msg):
        logmsg(syslog.LOG_INFO, msg)

    # log_traceback() generates the same output but the signature and code is
    # different between v3 and v4. Define suitable wrapper functions for those
    # levels needed.
    def log_traceback_critical(prefix=''):
        log_traceback(prefix=prefix, loglevel=syslog.LOG_CRIT)

    def log_traceback_error(prefix=''):
        log_traceback(prefix=prefix, loglevel=syslog.LOG_ERR)

# default API call interval in seconds
DEFAULT_API_CALL_INTERVAL = 3600
# default number of tries to contact the API before giving up
DEFAULT_MAX_TRIES = 3
# default maximum cache age in seconds
DEFAULT_MAX_CACHE_AGE = 7200


# ============================================================================
#                        class OpenWeatherConditions
# ============================================================================

class OpenWeatherConditions(weewx.engine.StdService):
    """'Data' service to obtain current conditions data via the OpenWeather API.

    This service collects current conditions description and icon code via the
    OpenWeather API and makes the data available in a WeeWX loop packet. The
    service was designed to collect the current conditions description and icon
    code for use in the generation of clientraw.txt and tag files supporting
    the Saratoga Weather website templates.

    To use this service:

    1. copy this file to /home/weewx/bin/user or /usr/share/weewx/user
    depending on your WeeWX install

    2. add user.weatherapi.OpenWeatherConditions to the [Engine] [[Services]]
    data_services setting in weewx.conf

    3. Add an [[OpenWeather]] stanza to the [WeatherApi] stanza (create stanza
    if required) in weewx.conf as follows:

    [WeatherApi]
        [[OpenWeather]]
            enable = True

            # OpenWeather API key
            api_key = <your API key>

    4. restart WeeWX
    """

    # define the default field map
    default_field_map = {
        'current_text': 'description',
        'current_icon': 'icon'
    }

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(OpenWeatherConditions, self).__init__(engine, config_dict)

        # get our config dict and save for later
        weather_api_config = config_dict.get('WeatherApi', {})
        self.ow_config = weather_api_config.get('OpenWeather', {})
        # add the name of our source to our config dict, but only if it does
        # not exist or is None
        if 'source_name' not in self.ow_config or self.ow_config['source_name'] is None:
            self.ow_config['source_name'] = 'OpenWeather'
        # are we enabled
        if weeutil.weeutil.to_bool(self.ow_config.get('enable', False)):
            # we are enabled, log that we are enabling our thread
            loginf("OpenWeatherConditions: enabling source '%s'" % self.ow_config['source_name'])
            # construct the field map we are to use, first obtain the field map
            # from our config if it exists
            field_map = self.ow_config.get('field_map')
            # obtain any field map extensions from our config
            extensions = self.ow_config.get('field_map_extensions', {})
            # if we have no field map then use the default
            if field_map is None:
                # obtain the default field map
                field_map = dict(OpenWeatherConditions.default_field_map)
            # If a user wishes to map a field differently to that in the
            # default map they can include an entry in field_map_extensions,
            # but if we just update the field map dict with the field map
            # extensions that will leave two entries for that field in the
            # field map; the original field map entry as well as the entry from
            # the extended map. So if we have field_map_extensions we need to
            # first go through the field map and delete any entries that map
            # fields that are included in the field_map_extensions.

            # we only need process the field_map_extensions if we have any
            if len(extensions) > 0:
                # first make a copy of the field map because we will be
                # iterating over it and changing it
                field_map_copy = dict(field_map)
                # iterate over each key, value pair in the copy of the field
                # map
                for k, v in six.iteritems(field_map_copy):
                    # if the source field is in the field map extensions we
                    # will be mapping that field elsewhere, so pop that field
                    # map entry out of the field map so we don't end up with
                    # multiple mappings for the source field
                    if v in extensions.values():
                        # pop the field map entry
                        _dummy = field_map.pop(k)
                # now we can update the field map with the extensions
                field_map.update(extensions)
            # we now have our final field map
            self.field_map = field_map

            # create a dict for our cache
            self.cache = {}
            # set max age for cache entries
            self.max_cache_age = weeutil.weeutil.to_int(self.ow_config.get('max_cache_age',
                                                                           DEFAULT_MAX_CACHE_AGE))
            # set up the control and response queues
            self.control_queue = six.moves.queue.Queue()
            self.response_queue = six.moves.queue.Queue()
            # and get an appropriate threaded source object
            self.thread = OpenWeatherApiThreadedSource(self.ow_config,
                                                       self.control_queue,
                                                       self.response_queue,
                                                       engine)
            # start our thread
            self.thread.start()
            # bind our self to the NEW_LOOP_PACKET event
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
            # get our (not WeeWX) debug level
            self.debug = weeutil.weeutil.to_int(self.ow_config.get('debug', 0))
            # log important config info
            loginf("OpenWeatherConditions: max_cache_age is %d seconds" % self.max_cache_age)
            if weewx.debug >= 1 or self.debug >= 1:
                loginf('OpenWeatherConditions: field map is %s' % natural_sort_dict(self.field_map))
        else:
            # we are not enabled or have no config stanza, but still listed as
            # a service to be run, log the fact and exit
            loginf("OpenWeatherConditions: source '%s' ignored" % self.ow_config['source_name'])

    def shutDown(self):
        """Shut down any threads."""

        # we only need do something if we have a live thread
        if self.thread.is_alive():
            # if we have a control queue put None in the queue to signal the
            # thread to stop
            if self.control_queue:
                self.control_queue.put(None)
            # attempt to terminate the thread with a suitable timeout
            self.thread.join(5.0)
            # if the thread is still alive we timed out and the thread may not
            # have been terminated, either way log the outcome
            if self.thread.is_alive():
                logerr("OpenWeatherConditions: Unable to shut down '%s' thread" % self.ow_config['source_name'])
            else:
                loginf("OpenWeatherConditions: '%s' thread has been terminated" % self.ow_config['source_name'])
        # we are finished with the thread so lose our reference and our queues
        self.thread = None
        self.control_queue = None
        self.response_queue = None

    def new_loop_packet(self, event):
        """Process our thread response queue and augment the loop packet.

        Check if our thread has sent anything via the queue. If it has sent
        None that is the signal the thread needs to close. If it has sent data
        from the API cache the data and augment the loop packet with the cached
        data.

        Augment the loop packet with any data in the cache that is not already
        in the loop packet.
        """

        # Try to get data from the queue but don't block. If nothing is in the
        # queue an empty queue exception will be thrown. If we have already
        # shut our thread we will have no response queue.
        try:
            _package = self.response_queue.get_nowait()
        except (queue.Empty, AttributeError):
            # Nothing in the queue or we were called but our thread has been
            # closed. Either way just continue.
            pass
        else:
            # something was in the queue, what we do depends on what it is

            # most likely we have API data from our thread, is this is the case
            # the package will be a dict with a 'keys' attribute
            if hasattr(_package, 'keys'):
                # it is a dict, if it's data it will have a field 'type' with a
                # value of 'data'
                if _package.get('type') == 'data':
                    # we have a data package, so get the payload
                    _payload = _package.get('payload')
                    # if the payload is not None and it is a dict then we have
                    # some data that we need to add to our loop packets
                    if _payload is not None and hasattr(_payload, 'keys'):
                        # we have data for loop packets, first map our data
                        _mapped_data = self.map_data(_payload)
                        # now update our cache
                        self.update_cache(_mapped_data)
            # if it is not a dict then it may be the shutdown signal (None)
            elif _package is None:
                # we have a shutdown signal so call our shutDown method
                self.shutDown()
            # if it is something else again we can safely ignore it
            else:
                pass
        # now augment the loop packet
        self.augment_loop_packet(event)

    def map_data(self, data_packet):
        """Map any received data as required."""

        # we may be changing our source data so make a copy to work on
        _response = dict(data_packet)
        # iterate over each key map entry
        for dest, source in six.iteritems(self.field_map):
            # we need to do a mapping if the source field is in our data packet
            # and provided it is not the timestamp - we can't mess with that
            if source in data_packet and source != 'datetime':
                # we have a mapping to do, first pop the source field from our
                # working data
                _response.pop(source, None)
                # now add the data from the source field in our data packet to
                # the destination field in our working copy
                _response[dest] = data_packet[source]
        # we have completed any mappings so return the working copy
        return _response

    def update_cache(self, data_packet):
        """Update our cache with data from a dict."""

        # first get the timestamp of our data
        _packet_ts = data_packet.get('timestamp')
        # now iterate over the key, data pairs and update the cache
        for key, data in six.iteritems(data_packet):
            # we can skip the timestamp
            if key == 'timestamp':
                continue
            # update the cache if we have not cached key before or if the
            # cached data for key is stale
            elif key not in self.cache or _packet_ts > self.cache[key]['timestamp']:
                self.cache[key] = {'data': data, 'timestamp': _packet_ts}
        # now remove any stale data from the cache
        now = time.time()
        for key in six.iterkeys(self.cache):
            if self.cache[key]['timestamp'] + self.max_cache_age < now:
                del self.cache[key]

    def augment_loop_packet(self, event):
        """Augment a loop packet from the cache.

        Only fields that do not already exist in the loop packet are added
        from the cache.
        """

        # iterate over the keys in the cache
        for key in six.iterkeys(self.cache):
            # if the key is not in the loop packet add the cached data to
            # the loop packet
            if key not in event.packet:
                event.packet[key] = self.cache[key]['data']


# ============================================================================
#                           class AerisWeatherMap
# ============================================================================

class AerisWeatherMap(weewx.engine.StdService):
    """Service to obtain a weather map image from the Aeris Weather map API.

    Obtains a single weather map image file from the Aeris Weather map API
    using the URL produced by the Aeris Weather Map Wizard
    (https://www.aerisweather.com/wizard/product/maps/type). Note, this service
    cannot download interactive maps available through the Interactive Map or
    WeatherBlox Map components of the Map Wizard.

    To use this service:

    1. copy this file to /home/weewx/bin/user or /usr/share/weewx/user
    depending on your WeeWX install

    2. add user.weatherapi.AerisWeatherMap to the [Engine] [[Services]]
    report_services setting in weewx.conf

    3. Add a [WeatherMap] [[Aeris]] stanza to weewx.conf as follows:

    [WeatherMap]
        [[Aeris]]
            enabled = True

            # Aeris Weather client ID
            client_id =

            # Aeris Weather client secret
            client_secret =

            # Extract from the single image URL produced by the Single Image
            # Map Wizard. Consists of all characters after
            # [CLIENT_ID]_[CLIENT_SECRET]/
            # eg: flat,radar,states/600x500/Mytown, state,4/current.png
            url_extract = "flat,radar,states/600x500/Brisbane,qld,4/current.png"

    4. restart WeeWX
    """

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(AerisWeatherMap, self).__init__(engine, config_dict)

        wm_config = config_dict.get('WeatherMap', {})
        aw_config = wm_config.get('Aeris', {})
        # are we enabled
        if weeutil.weeutil.to_bool(aw_config.get('enable', False)):
            # we are enabled, set up the control and data queues
            self.control_queue = six.moves.queue.Queue()
            self.response_queue = six.moves.queue.Queue()
            # and get an appropriate threaded source object
            self.aeris_map_thread = AerisWeatherMapThreadedSource(aw_config,
                                                                  self.control_queue,
                                                                  self.response_queue,
                                                                  engine)
            self.aeris_map_thread.start()
        else:
            # we are not enabled but still listed as a service to be run, log
            # the fact and exit
            loginf("Source '%s' ignored" % aw_config['source_name'])

    def shutDown(self):
        """Shut down any threads."""

        # we only need do something if a thread is alive
        if self.aeris_map_thread.is_alive():
            # if we have a control queue put None in the queue to signal the
            # thread to stop
            if self.control_queue:
                self.control_queue.put(None)
            # attempt to terminate the thread with a suitable timeout
            self.aeris_map_thread.join(5.0)
            # if the thread is still alive we timed out and the thread may not
            # have been terminated, either way log the outcome
            if self.aeris_map_thread.is_alive():
                logerr("Unable to shut down AerisWeatherMap thread")
            else:
                loginf("AerisWeatherMap thread has been terminated")
        # we are finished with the thread so lose our reference and our queues
        self.aeris_map_thread = None
        self.control_queue = None
        self.response_queue = None

    def new_loop_packet(self):
        """Check our thread to see if it needs to close.

        We don't need to process any loop packet data, but we do need to
        regularly check on our thread to see if it needed to close. Checking
        upon arrival of each loop packet is a convenient time."""

        # Try to get data from the queue, block for up to 60
        # seconds. If nothing is there an empty queue exception
        # will be thrown after 60 seconds
        try:
            _package = self.response_queue.get_nowait()
        except (queue.Empty, AttributeError):
            # Nothing in the queue or we were called but our thread has been
            # closed. Either way just continue.
            pass
        else:
            # something was in the queue, if it is the shutdown signal (None)
            # then return otherwise continue
            if _package is None:
                # we have a shutdown signal so call our shutDown method
                self.shutDown()


# ============================================================================
#                           class ThreadedSource
# ============================================================================

class ThreadedSource(threading.Thread):
    """Base class for a threaded HTTP GET based weather API source.

    ThreadedSource constructor parameters:

        source_config_dict:   a ConfigObj config dictionary for the source
        control_queue:        a Queue object used by our parent to control
                              (shutdown) this thread
        response_queue:       a Queue object used to pass results to our parent
        engine:               an instance of weewx.engine.StdEngine (or a
                              reasonable facsimile)

    ThreadedSource methods:

        run():               Thread entry point, controls data fetching,
                             parsing and dispatch. Monitors the control queue.
        setup():             Method to be called after object initialisation
                             but before run() starts proper.
        get_raw_data():      Obtain the raw data. This method must be written
                             for each child class.
        submit_request():    Make a HTTP GET request to the API.
        extended_http_error_logging(): Method to provide optional source
                                       specific HTTP error logging. This method
                                       must be written for each child class.
        parse_raw_data():    Parse the raw data and return the final format
                             data. This method must be written for each child
                             class.
        process_data():      Process the parsed data, this may involve
                             packaging and placing the data in the result queue
                             or saving the data locally.
        time_to_make_call(): Determine whether an API call is due.
        obfuscated_key():    Obfuscate an API key.
    """

    def __init__(self, source_config_dict, control_queue, response_queue, engine):

        # initialize my superclass
        threading.Thread.__init__(self)

        # set up some thread things
        self.setDaemon(True)
        # get an identifying name to use to identify this thread and when
        # logging
        self.name = KNOWN_SOURCES[source_config_dict['source_name']]['long_name']

        # save the queues we will use
        self.control_queue = control_queue
        self.response_queue = response_queue
        # keep a reference to the WeeWX engine
        self.engine = engine
        # get our API call interval using a suitable default
        self.interval = weeutil.weeutil.to_int(source_config_dict.get('interval',
                                                                      DEFAULT_API_CALL_INTERVAL))
        # get the number of attempts to contact the API before giving up
        self.max_tries = weeutil.weeutil.to_int(source_config_dict.get('max_tries',
                                                                       DEFAULT_MAX_TRIES))
        # get our (not WeeWX) debug level
        self.debug = weeutil.weeutil.to_int(source_config_dict.get('debug', 0))

        # keep a track of the time of our last call
        self.last_call_ts = None

    def run(self):
        """Entry point for the thread."""

        # since we are in a thread some additional try..except clauses will
        # help give additional output in case of an error rather than having
        # the thread die silently
        try:
            # first run our setup() method
            self.setup()
            # Run a continuous loop, obtaining data as required and monitoring
            # the control queue for the shutdown signal. Only break out if we
            # receive the shutdown signal (None) from our parent.
            while True:
                if self.time_to_make_call(time.time()):
                    # run an inner loop obtaining, parsing and dispatching the data
                    # and checking for the shutdown signal
                    # first up get the raw data
                    _raw_data = self.get_raw_data()
                    if weewx.debug >= 3 or self.debug >= 3:
                        loginf("%s: raw data: %s" % (self.name, _raw_data))
                    elif weewx.debug >= 2 or self.debug >= 2:
                        loginf("%s: obtained raw data" % self.name)
                    # if we have a non-None response then we have data so parse it,
                    # gather the required data and put it in the result queue
                    if _raw_data is not None:
                        # parse the raw data response and extract the required data
                        _parsed_data = self.parse_data(_raw_data)
                        if weewx.debug >= 3 or self.debug >= 3:
                            loginf("%s: parsed data: %s" % (self.name, _parsed_data))
                        elif weewx.debug >= 2 or self.debug >= 2:
                            loginf("%s: obtained parsed data" % self.name)
                        # now process the parsed data
                        self.process_data(_parsed_data)
                        if weewx.debug >= 2 or self.debug >= 2:
                            loginf("%s: parsed data has been processed" % self.name)
                # now check to see if we have a shutdown signal
                try:
                    # Try to get data from the queue, block for up to 10
                    # seconds. If nothing is there an empty queue exception
                    # will be thrown after 10 seconds
                    _package = self.control_queue.get(block=True, timeout=10)
                except six.moves.queue.Empty:
                    # nothing in the queue so continue
                    pass
                else:
                    # something was in the queue, if it is the shutdown signal
                    # then return otherwise continue
                    if _package is None:
                        # we have a shutdown signal so return to exit
                        if weewx.debug >= 2 or self.debug >= 2:
                            loginf("%s: received shutdown signal in control queue" % self.name)
                        return
                    if weewx.debug >= 2 or self.debug >= 2:
                        loginf("%s: discarded data received in control queue" % self.name)
        except Exception as e:
            # Some unknown exception occurred. This is probably a serious
            # problem. Exit with some notification.
            logcrit("%s: Unexpected exception of type %s" % (self.name, type(e)))
            log_traceback_critical(prefix='%s: **** ' % self.name)
            logcrit("%s: Thread exiting. Reason: %s" % (self.name, e))

    def setup(self):
        """Perform any post post-__init__() setup.

        This method is executed as the very first thing in the thread run()
        method. It must be defined if required for each child class.
        """

        pass

    def get_raw_data(self, **kwargs):
        """Obtain the raw data.

        This method must be defined for each child class.
        """

        return None

    def submit_request(self, **kwargs):
        """Submit a HTTP GET request to the API and return the result.

        Submit a HTTP GET request using the supplied URL and optional header
        dict. If the API does not respond the request will be submitted up to a
        total of max_tries times before giving up. If a response is received it
        is character decoded and returned. If no response is received None is
        returned.
        """

        url = kwargs.get('url')
        headers = kwargs.get('headers')
        if headers is None:
            headers = {}
        # obtain a Request object
        req = six.moves.urllib.request.Request(url=url, headers=headers)
        # we will attempt to obtain a response max_tries times
        for count in range(self.max_tries):
            # attempt to contact the API
            try:
                if weewx.debug >= 2 or self.debug >= 2:
                    loginf("%s: submitting HTTP GET request, attempt %d" % (self.name,
                                                                            count + 1))
                w = six.moves.urllib.request.urlopen(req)
            except six.moves.urllib.error.HTTPError as err:
                log.error("%s: failed to get API response on attempt %d" % (self.name,
                                                                            count + 1))
                log.error("%s:   **** %s" % (self.name, err))
                if self.extended_http_error_logging(err):
                    break
            except (six.moves.urllib.error.URLError, socket.timeout) as err:
                log.error("%s: failed to get API response on attempt %d" % (self.name,
                                                                            count + 1))
                log.error("%s:    **** %s" % (self.name, err))
            else:
                # we have a response, first set the timestamp of the last
                # successful call
                self.last_call_ts = time.time()
                # The response could be character set encoded. Get the charset
                # used so we can decode the stream correctly. Unfortunately the
                # way to get the charset depends on whether we are running
                # under python2 or python3. Assume python3 but be prepared to
                # catch the error if python2.
                try:
                    char_set = w.headers.get_content_charset()
                except AttributeError:
                    # must be python2
                    char_set = w.headers.getparam('charset')
                # now get the response, decoding it appropriately
                response = w.read().decode(char_set)
                # close the API connection
                w.close()
                # log the decoded response if required
                if weewx.debug >= 3 or self.debug >= 3:
                    loginf("%s: API response: %s" % (self.name, response))
                elif weewx.debug >= 1 or self.debug >= 1:
                    loginf("%s: API response received" % self.name)
                # return the decoded response
                return response
        else:
            # no response after max_tries attempts, so log it
            log.error("%s: Failed to get API response" % self.name)
        # if we made it here we have not been able to obtain a response so
        # return None
        return None

    def extended_http_error_logging(self, err):
        """Produce source specific extended HTTP error logging.

        Some APIs provide extended error reporting in any HTTPError exceptions
        raised when a call to the API fails. As this reporting can vary from
        API to API, API specific processing and logging of this error reporting
        by overriding this method.

        One parameter is accepted, err, which is an instance of a HTTPError
        exception. The method should return True if the calling code should
        break from it's current loop or False if it should not.
        """

        return False

    def parse_data(self, response):
        """Parse the block response and return the required data.

        This method must be defined if the raw data from the block must be
        further processed/parsed to extract the data to be used.

        The action of base class version of this method is to return the raw
        data unchanged.
        """

        return response

    def process_data(self, data):
        """Process the parsed data.

        The action of base class version of this method is to package the data
        into a dict and place it in the queue for our parent Service to process
        further. The dict structure is:
        'type': the string 'data'
        'payload': the data to be packaged

        If data is None nothing is queued.

        This method may be overridden if other tasks must be performed with the
        data.
        """

        # if we have some data then place it in the result queue
        if data is not None:
            # construct our data dict for the queue
            _package = {'type': 'data',
                        'payload': data}
            # queue the package
            self.response_queue.put(_package)
            # if required log the package that was queued
            if weewx.debug >= 2 or self.debug >= 2:
                loginf("%s: queued package: %s" % (self.name, _package))

    def time_to_make_call(self, now_ts):
        """Is it time to make another call via the API?

        Given a timestamp is it time to make and API call or not? Look at the
        time of last call and the call interval to decide if a call should be
        made. Return True if:
        - no call has ever been made
        - a previous call has been made and self.interval seconds have elapsed
          since the call
        otherwise returns False

        Returns true or False only.
        """

        # have we ever made a call
        if self.last_call_ts is None:
            # no previous call so return True
            return True
        # has interval seconds passed since the last call
        elif now_ts >= self.last_call_ts + self.interval:
            return True
        # default to False
        else:
            return False

    @staticmethod
    def obfuscated_key(key):
        """Produce an obfuscated copy of a key.

        Obfuscates a number of the leftmost characters in a key leaving a
        number of the rightmost characters as is. For keys of length eight
        characters or fewer at least half of the characters are obfuscated. For
        keys longer than eight characters in length all except the rightmost
        four characters are obfuscated. If the key is None or the length of the
        key is less than 2 then None is returned.
        """

        if key is None or len(key) < 2:
            return None
        elif len(key) < 8:
            clear = len(key) // 2
        else:
            clear = 4
        return '*' * (len(key) - clear) + key[-clear:]


# ============================================================================
#                     class OpenWeatherApiThreadedSource
# ============================================================================

class OpenWeatherApiThreadedSource(ThreadedSource):
    """Query the OpenWeather API and return the API response.

    OpenWeatherAPI constructor parameters:

        ow_config_dict: ConfigObj object with (at least) the following keys:
                        api_key:   OpenWeather API key to be used
                        latitude:  Latitude of the location concerned
                        longitude: Longitude of the location concerned
        control_queue:  a Queue object used by our parent to control
                        (shutdown) this thread
        response_queue: a Queue object used to pass results to our parent
        engine:         an instance of weewx.engine.StdEngine (or a reasonable
                        facsimile)

    OpenWeather API data is accessed by calling the get_raw_data() method. The
    get_raw_data() method expects the following parameters:
        data_type: The data type being sought, supported options are 'weather',
                   'forecast', 'air_pollution'. String, default is 'weather'
        language: The language to be used in any API response text. Refer to
                  the optional parameter 'lang' at
                  https://openweathermap.org/current#multi. String, default
                  is 'en'.
        units: The units to be used in the API response. Refer to the optional
               parameter 'units' at
               https://openweathermap.org/current#data. String, default
               is 'metric'.
        max_tries: Maximum number of attempts to obtain an API response.
                   Integer, default is 3.
    The get_raw_data() method returns a JSON format object or None if no response was
    obtained.
    """

    # OpenWeather API end point
    END_POINT = 'https://api.openweathermap.org'
    # OpenWeather endpoint qualifier
    QUALIFIER = 'data/2.5'
    # available data 'blocks' we may obtain from the API
    DATA_TYPES = ('weather', 'forecast', 'air_pollution')
    # map OpenWeather icon codes to clientraw icon codes
    ICON_MAP = {'1d': 0,
                '1n': 1,
                '2d': 2,
                '2n': 4,
                '3d': 0,
                '3n': 0,
                '4d': 18,
                '4n': 13,
                '9d': 22,
                '9n': 15,
                '10d': 20,
                '10n': 14,
                '11d': 31,
                '11n': 17,
                '13d': 25,
                '13n': 16,
                '50d': 10,
                '50n': 10
                }

    def __init__(self, ow_config_dict, control_queue, response_queue, engine):
        # initialise a OpenWeatherAPI object

        # initialize my base class
        super(OpenWeatherApiThreadedSource, self).__init__(ow_config_dict,
                                                           control_queue,
                                                           response_queue,
                                                           engine)

        # obtain various config items from our config dict
        # first we cannot do anything without an API key, if we have no key
        # then notify the user and return
        try:
            self.api_key = ow_config_dict['api_key']
        except KeyError:
            # we have no API key, we cannot continue
            # first log the error
            log.error('%s: OpenWeather API key not found, %s will close' % (self.name,
                                                                            self.name))
            # now put None in the result queue to indicate to our service that
            # we need to close
            self.response_queue.put(None)
            return
        else:
            # we have an API key so continue
            self.latitude = weeutil.weeutil.to_float(ow_config_dict.get('latitude',
                                                                        self.engine.stn_info.latitude_f))
            self.longitude = weeutil.weeutil.to_float(ow_config_dict.get('longitude',
                                                                         self.engine.stn_info.longitude_f))
            self.language = ow_config_dict.get('language', 'en').lower()
            self.units = ow_config_dict.get('units', 'metric').lower()
            self.map_icon_code = weeutil.weeutil.to_bool(ow_config_dict.get('map_icon_code',
                                                                            True))
            self.max_tries = weeutil.weeutil.to_int(ow_config_dict.get('max_tries',
                                                                       3))
        # now log some key config info
        loginf("OpenWeatherConditions source '%s' enabled" % ow_config_dict['source_name'])
        loginf("     api_key=%s interval=%d" % (self.obfuscated_key(self.api_key),
                                                self.interval))
        loginf("     language=%s units=%s max_tries=%d" % (self.language,
                                                           self.units,
                                                           self.max_tries))
        if self.map_icon_code:
            loginf("     OpenWeather icon codes will be mapped to clientraw.txt icon codes")

    def get_raw_data(self):
        """Make a data request via the API and return the response.

        Construct the URL used to contact the API, contact the API and return
        the decoded response as a JSON formatted object.

        Returns the OpenWeather API response in JSON format or None is no
        response was received.
        """

        # construct the URL to be used to contact the API, for a HTTP GET
        # request this is a combination of the base URL and the url-encoded
        # parameters start constructing the base URL to be used to contact the
        # API
        # first construct the base URL
        base_url = '/'.join([self.END_POINT,
                             self.QUALIFIER,
                             'weather'])
        # now construct the parameters dict
        param_dict = {'lat': self.latitude,
                      'lon': self.longitude,
                      'lang': self.language,
                      'units': self.units,
                      'appid': self.api_key
                      }
        # obtain the params as a URL encoded string
        params = urllib.parse.urlencode(param_dict)
        # construct the URL, it is a concatenation of the base URL and the
        # url-encoded parameters using a '?' as the joining character
        url = '?'.join([base_url, params])
        # if debug >= 1 log the URL used but obfuscate the API key
        if weewx.debug >= 2 or self.debug >= 2:
            _obfuscated_url = url.replace(self.api_key, self.obfuscated_key(self.api_key))
            loginf("%s: submitting API call using URL: %s" % (self.name, _obfuscated_url))
        # make the API call and obtain the response
        _response = self.submit_request(url=url)
        # if we have a response we need to de-serialise it
        json_response = json.loads(_response) if _response is not None else None
        # return the response
        return json_response

    def parse_data(self, response):
        """Parse our raw data."""

        # obtain an empty dict for the parsed data
        _parsed_data = {}
        # get the timestamp of the raw data
        _ts = response.get('dt')
        # if we have a timestamp proceed to parse the data
        if _ts is not None:
            # save our timestamp
            _parsed_data['timestamp'] = _ts
            # obtain the weather element
            _weather = response.get('weather', [])
            # The weather element will be a list, we want the first element of
            # the list. Also, the list could be empty.
            if len(_weather) > 0:
                # get the description
                _desc = _weather[0].get('description')
                # capitalise the first character and only the first character
                # of the description
                try:
                    _description = _desc[0].capitalize() + _desc[1:]
                except (IndexError, TypeError):
                    _description = _desc
                # if description is not None save to our parsed data
                if _description is not None:
                    _parsed_data['description'] = _description
                # get the icon, mapping to clientraw/Saratoga icon codes if
                # required
                if self.map_icon_code:
                    _icon = self.ICON_MAP.get(_weather[0].get('icon', 0), 0)
                else:
                    _icon = _weather[0].get('icon', '1d')
                # if icon is not None save to our parsed data
                if _icon is not None:
                    _parsed_data['icon'] = _icon
        # return the parsed data
        return _parsed_data

    def extended_http_error_logging(self, err):
        """Produce source specific extended HTTP error logging.

        The OpenWeather API supports a number of different HTTP error codes
        that indicate the source of the error:
        401: some sort of API key error, eg: incorrect key, no key or key not
             yet activated. Can also occur if using a free subscription and
             attempting to access another subscription
        404: error in specifying location in the API request or an error in
             the API request format
        429: exceeding the rate limit of a free subscription
        500, 502, 503, 504: refer to OpenWeather help desk for assistance

        For 401, 404 and 429 errors there is no point in further requests so
        True is returned so the current loop will be broken.
        """

        if err.code == 401:
            log.error("   **** Possible incorrect API key or user credentials")
            return True
        if err.code == 404:
            log.error("   **** Possible incorrect location specified or "
                      "API request format error")
            return True
        elif err.code == 429:
            log.error("   **** Possible too many API calls per minute")
            return True
        elif err.code in (500, 502, 503, 504):
            log.error("   **** Unknown error, seek support")
        return False


# ============================================================================
#                     class AerisWeatherMapThreadedSource
# ============================================================================

class AerisWeatherMapThreadedSource(ThreadedSource):
    """Class that obtains weather map images via the Aeris Weather API."""

    # Aeris Weather map API end point
    END_POINT = 'https://maps.aerisapi.com'

    def __init__(self, config_dict, control_queue, response_queue, engine, **kwargs):

        # get the Aeris Weather config
        wm_config = config_dict.get('WeatherMap')
        aw_config = wm_config.get('Aeris')
        # initialize my base class
        super(AerisWeatherMapThreadedSource, self).__init__(aw_config,
                                                            control_queue,
                                                            response_queue,
                                                            engine)

        # obtain our client ID and secret, wrap in try..except so we can catch
        # the exception raised if oe or the other does not exist
        try:
            self.client_id = aw_config['client_id']
            self.client_secret = aw_config['client_secret']
        except KeyError:
            log.error('%s: client ID and/or client secret not specified. '
                      'Exiting.' % self.name)
            # we cannot continue, place None in the result queue to signal we
            # need to close then return
            self.response_queue.put(None)
            return
        else:
            # we have a client ID and secret, continue with the rest of our
            # initialisation
            # construct the client ID and secret string to be used in our URL
            id_secret = '_'.join([self.client_id, self.client_secret])
            # obtain the URL stem
            url_stem = aw_config.get('url_extract')
            # now construct the URL
            self.url = '/'.join([self.END_POINT, id_secret, url_stem])
            # obtain the HTML_ROOT setting from StdReport
            HTML_ROOT = os.path.join(config_dict['WEEWX_ROOT'],
                                     config_dict['StdReport']['HTML_ROOT'])
            # obtain the destination for the retrieved file
            _path = aw_config.get('destination', HTML_ROOT).strip()
            _file = os.path.basename(url_stem)
            # now we can construct the destination path and file name
            self.destination = os.path.join(HTML_ROOT, _path, _file)
            _path, _file = os.path.split(self.destination)
            if not os.path.exists(_path):
                os.makedirs(_path)
            # interval between API calls, default to 30 minutes
            self.interval = weeutil.weeutil.to_int(aw_config.get('interval',
                                                                 1800))
            # Get API call lockout period. This is the minimum period between API
            # calls. This prevents an error condition making multiple rapid API
            # calls and thus potentially breaching the API usage conditions.
            # The Aeris Weather API does specify a plan dependent figure for
            # the maximum API calls per minute, we will be conservative and
            # default limit our calls to no more often than once every 10
            # seconds. The user can increase or decrease this value.
            self.lockout_period = weeutil.weeutil.to_int(aw_config.get('api_lockout_period',
                                                                       10))
            # maximum number of attempts to obtain a response from the API
            # before giving up
            self.max_tries = weeutil.weeutil.to_int(aw_config.get('max_tries',
                                                                  3))
            # initialise a property to hold the timestamp the API was last called
            self.last_call_ts = None

            # inform the user what we are doing, what we log depends on the
            # WeeWX debug level or our debug level
            # basic infor is logged everytime
            loginf("'%s' will obtain Aeris Weather map image data" % self.name)
            loginf("    destination=%s interval=%d" % (self.destination,
                                                       self.interval))
            # more detail when debug >= 1
            if weewx.debug >= 1 or self.debug >= 1:
                loginf("    Aeris debug=%d lockout period=%s max tries=%s" % (self.debug,
                                                                              self.lockout_period,
                                                                              self.max_tries))
            # detailed client and URL info when debug >= 2
            if weewx.debug >= 2 or self.debug >= 2:
                loginf("    client ID=%s" % self.obfuscated_key(self.client_id))
                loginf("    client secret=%s" % self.obfuscated_key(self.client_secret))
                loginf("    URL extract=%s" % url_stem)

    def get_raw_data(self):
        """Make a data request via the API.

        Submit an API request observing both lock periods and the API call
        interval.

        For an Aeris Weather map API call the resulting map image file is saved
        as part of the API call HTTP request and as such no API response data
        is returned that requires further processing by our parent. To this end
        all processing and logging is carried out in this or subordinate
        methods, and we return the value None in all cases.
        """

        # get the current time
        now = time.time()
        # log the time of last call if debug >= 2
        if weewx.debug >= 2 or self.debug >= 2:
            log.debug("Last %s API call at %s" % (self.name, self.last_call_ts))
        # has the lockout period passed since the last call
        if self.last_call_ts is None or ((now + 1 - self.lockout_period) > self.last_call_ts):
            # If we haven't made an API call previously, or if it's been too
            # long since the last call then make the call
            if (self.last_call_ts is None) or ((now + 1 - self.interval) >= self.last_call_ts):
                # if debug >= 2 log the URL used, but obfuscate the client
                # credentials
                if weewx.debug >= 2 or self.debug >= 2:
                    _obfuscated = self.url.replace(self.client_id,
                                                   self.obfuscated_key(self.client_id))
                    _obfuscated_url = _obfuscated.replace(self.client_secret,
                                                          self.obfuscated_key(self.client_secret))
                    log.info("Submitting %s API call using URL: %s" % (self.name,
                                                                       _obfuscated_url))
                # make the API call and return the response, we will discard the
                # response after some response based logging
                _result = self.submit_request()
                # log the result
                if weewx.debug >= 1 or self.debug >= 1:
                    if _result is not None:
                        loginf("%s: successfully downloaded '%s'" % (self.name, _result))
                    else:
                        loginf("%s: failed to obtain API response" % self.name)
        # we have nothing to return, so return None
        return None

    def submit_request(self, **kwargs):
        """Submit a HTTP GET request to the API.

        Submit a HTTP GET request using the url property and any optional
        headers in the headers property. If the API does not respond the
        request will be submitted up to a total of self.max_tries times
        before giving up.

        Unlike the standard Aeris Weather API the Aeris Weather map API returns
        an image file. If this file is downloaded and saved successfully the
        file name and path is returned. If a HTTP error code is raised, or if no
        response is received, None is returned.
        """

        for count in range(self.max_tries):
            # attempt to contact the API
            try:
                # make the call, urlretrieve returns the file name and headers
                (file_name, headers) = six.moves.urllib.request.urlretrieve(self.url,
                                                                            self.destination)
            except six.moves.urllib.error.HTTPError as err:
                log.error("Failed to get %s API response on attempt %d" % (self.name,
                                                                           count + 1))
                log.error("   **** %s" % err)
                if err.code == 403:
                    # Aeris Weather has not listed specific HTTP response error
                    # codes, but we know an incorrect client ID or secret results
                    # in a 403 error as does an invalid URL stem
                    log.error("   **** Possible incorrect client credentials or URL stem")
                    # we cannot continue with these errors so return
                    break
            except (six.moves.urllib.error.URLError, socket.timeout) as e:
                log.error("Failed to get %s API response on attempt %d" % (self.name,
                                                                           count + 1))
                log.error("   **** %s" % e)
            else:
                # we had a successful retrieval, first update the time of last call
                self.last_call_ts = time.time()
                # indicate success to our caller by returning the file name
                return file_name
        else:
            # no response after max_tries attempts, so log it
            log.error("Failed to get %s API response after %d attempts" % (self.name,
                                                                           self.max_tries))
        # if we made it here we have nothing so return None
        return None


# ============================================================================
#                             Utility functions
# ============================================================================

def natural_sort_keys(source_dict):
    """Return a naturally sorted list of keys for a dict."""

    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(text):
        """Natural key sort.

        Allows use of key=natural_keys to sort a list in human order, eg:
            alist.sort(key=natural_keys)

        https://nedbatchelder.com/blog/200712/human_sorting.html (See
        Toothy's implementation in the comments)
        """

        return [atoi(c) for c in re.split(r'(\d+)', text.lower())]

    # create a list of keys in the dict
    keys_list = list(source_dict.keys())
    # naturally sort the list of keys where, for example, xxxxx16 appears in the
    # correct order
    keys_list.sort(key=natural_keys)
    # return the sorted list
    return keys_list


def natural_sort_dict(source_dict):
    """Return a string representation of a dict sorted naturally by key.

    When represented as a string a dict is displayed in the format:
        {key a:value a, key b: value b ... key z: value z}
    but the order of the key:value pairs is unlikely to be alphabetical.
    Displaying dicts of key:value pairs in logs or on the console in
    alphabetical order by key assists in the analysis of the dict data.
    Where keys are strings with leading digits a natural sort is useful.
    """

    # first obtain a list of key:value pairs as string sorted naturally by key
    sorted_dict_fields = ["'%s': '%s'" % (k, source_dict[k]) for k in natural_sort_keys(source_dict)]
    # return as a string of comma separated key:value pairs in braces
    return "{%s}" % ", ".join(sorted_dict_fields)


KNOWN_SOURCES = {'AerisWeatherMap': {'long_name': 'AerisWeatherMapSource',
                                     'short_name': 'AerisWeatherMap',
                                     'class': AerisWeatherMapThreadedSource
                                     },
                 'OpenWeather': {'long_name': 'OpenWeatherAPISource',
                                 'short_name': 'OpenWeather',
                                 'class': OpenWeatherApiThreadedSource
                                 }
                 }
