"""
weatherapi.py

A WeeWX service to augment loop packets and archive records with data from an
external weather API.

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation; either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

Version: 0.1.0                                      Date: 2 April 2023

Revision History
    2 April 2023        v0.1.0
        - initial implementation
"""

# python imports
import json
import socket
import threading
# import urllib.error
# import urllib.parse
# import urllib.request

# python 2/3 compatibility shims
import six

# WeeWX imports
import weewx
import weeutil.config

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


# ==============================================================================
#                          class CurrentConditions
# ==============================================================================

class WeatherAPIData(weewx.engine.StdService):
    """Service to obtain data from an external weather API.

    [WeatherApiData]
        [[SomeName]]
            source = OW
            enabled = True
            block = current
            key = abcdefg
            [[[field_map]]]
                current_conditions = current
                current_icon = icon
    """

    def __init__(self, engine, config_dict):
        # initialise our superclass
        super(WeatherAPIData, self).__init__(engine, config_dict)

        wad_config = config_dict.get('WeatherApiData')
        self.sources = dict()
        self.queues = dict()
        for section in wad_config.sections:
            # get the section config dict
            section_config = weeutil.config.accumulateLeaves(wad_config[section])
            log.info("section_config=%s" % (section_config,))
            # is it enabled
            _enable = weeutil.weeutil.to_bool(section_config.get('enable', False))
#            log.info("source=%s source in KNOWN=%s _enable=%s" % (section_config.get("source"),
#                                                                  section_config['source'] in KNOWN_SOURCES.keys(),
#                                                                  _enable))
            if 'source' in section_config and section_config['source'] in KNOWN_SOURCES.keys() and _enable:
                # we have a source config dict and the source is enabled
                # set up the control and data queues
                self.queues[section] = {'control': six.moves.queue.Queue(),
                                        'data': six.moves.queue.Queue()}
                # and get an appropriate threaded source object
                self.sources[section] = self.source_factory(section_config,
                                                            self.queues[section],
                                                            engine)
                # then start the thread
                self.sources[section].start()
                # finally, let the user know what we did
            elif 'source' not in section_config:
                # no source was specified
                loginf("No source specified in section [[%s]]" % section)
            elif section_config['source'] not in KNOWN_SOURCES.keys():
                # an invalid source was specified
                loginf("Invalid source '%s' specified" % section_config['source'])
            else:
                # the source was not enabled
                loginf("Source '%s' ignored, not enabled" % section_config['source'])
        # set event bindings
        # bind to NEW_LOOP_PACKET
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        # bind to NEW_ARCHIVE_RECORD
        self.bind(weewx.NEW_ARCHIVE_RECORD, self
                  .new_archive_record)

    @staticmethod
    def source_factory(source_config, queues, engine):
        """Factory to produce a weather data source object."""

        # get the source class
        source_class = KNOWN_SOURCES.get(source_config['source'])
        if source_class is not None:
            # get the source object
            source_object = source_class(source_config,
                                         queues['control'],
                                         queues['data'],
                                         engine)
            return source_object
        else:
            return None

    def new_archive_record(self, event):
        """Action on a new archive record being created."""

        pass

    def new_loop_packet(self, event):
        """Action on a new loop packet being created."""

        pass

    def shutDown(self):
        """Shut down any threads.

        Would normally do all of a given thread's actions in one go but since
        we may have more than one thread, and so that we don't have sequential
        (potential) waits of up to 15 seconds, we send each thread a shutdown
        signal and then go and check that each has indeed shutdown.
        """

        # TODO. There may be better/alternate ways to do this
        for source_name, source_object in six.iteritems(self.sources):
            if self.queues[source_name]['control'] and source_object.isAlive():
                # put a None in the control queue to signal the thread to
                # shutdown
                self.queues[source_name]['control'].put(None)
        # TODO. Do we need to check for thread shutdown


# ============================================================================
#                           class ThreadedSource
# ============================================================================


class ThreadedSource(threading.Thread):
    """Base class for a threaded HTTP GET based weather API source.

    ThreadedSource constructor parameters:

        source_config_dict: a ConfigObj config dictionary for the source
        control_queue:      a Queue object used by our parent to control
                            (shutdown) this thread
        data_queue:         a Queue object used to pass data to our parent
        engine:             an instance of weewx.engine.StdEngine (or a
                            reasonable facsimile)

    ThreadedSource methods:

        run():          Thread entry point, controls data fetching, parsing and
                        dispatch. Monitors the control queue.
        get_raw_data(): Obtain the raw data. This method must be written for
                        each child class.
        parse_data():   Parse the raw data and return the final format data.
                        This method must be written for each child class.
    """

    def __init__(self, source_config_dict, control_queue, data_queue, engine):

        # initialize my superclass
        threading.Thread.__init__(self)

        # set up some thread things
        self.setDaemon(True)
        # get an identifying prefix to use to identify this thread and when
        # logging
        self.name = KNOWN_SOURCES[source_config_dict['source']]

        # save the queues we will use
        self.control_queue = control_queue
        self.result_queue = data_queue
        # keep a reference to the WeeWX engine
        self.engine = engine
        # set our (not WeeWX) debug level
        self.debug = weeutil.weeutil.to_int(source_config_dict.get('debug', 0))

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
                    _package = self.control_queue.get(block=True, timeout=10)
                except six.moves.queue.Empty:
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
            logcrit("Unexpected exception of type %s" % (type(e),))
            log_traceback_critical(prefix='%s: **** ' % self.name)
            logcrit("Thread exiting. Reason: %s" % (e,))

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

    def submit_request(self, url, headers=None):
        """Submit a HTTP GET request to the API and return the result.

        Submit a HTTP GET request using the supplied URL and optional header
        dict. If the API does not respond the request will be submitted up to a
        total of max_tries times before giving up. If a response is received it
        is character decoded and returned. If no response is received None is
        returned.
        """

        if headers is None:
            headers = {}
        # obtain a Request object
        req = six.moves.urllib.request.Request(url=url, headers=headers)
        # we will attempt to obtain a response max_tries times
        for count in range(self.max_tries):
            # attempt to contact the API
            try:
                w = six.moves.urllib.request.urlopen(req)
            except six.moves.urllib.error.HTTPError as err:
                log.error("Failed to get API response on attempt %d" % (count + 1,))
                log.error("   **** %s" % err)
                if err.code == 401:
                    log.error("   **** Possible incorrect API key or user credentials")
                    break
                elif err.code == 429:
                    log.error("   **** Possible too many API calls per minute")
                    break
            except (six.moves.urllib.error.URLError, socket.timeout) as e:
                log.error("Failed to get API response on attempt %d" % (count + 1,))
                log.error("   **** %s" % e)
            else:
                # We have a response, but it could be character set encoded.
                # Get the charset used so we can decode the stream correctly.
                # Unfortunately the way to get the charset depends on whether
                # we are running under python2 or python3. Assume python3 but
                # be prepared to catch the error if python2.
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
                if self.debug > 1:
                    log.info("API response=%s" % (response, ))
                # return the decoded response
                return response
        else:
            # no response after max_tries attempts, so log it
            log.error("Failed to get API response")
        # if we made it here we have not been able to obtain a response so
        # return None
        return None

    @staticmethod
    def obfuscated_key(key):
        """Produce and obfuscated copy of a key.

        Obfuscates a number of the leftmost characters in a key leaving a
        number of the rightmost characters as is. For keys of length eight
        characters or fewer at least half of the characters are obfuscated. For
        keys longer than eight characters in length all except the rightmost
        four characters are obfuscated. If key is None or the length of the key
        is less than 2 then None is returned.
        """

        if key is None or len(key) < 2:
            return None
        elif len(key) < 8:
            clear = len(key) // 2
        else:
            clear = 4
        return '*' * (len(key) - clear) + key[-clear:]


class OpenWeatherSource(ThreadedSource):
    """Class that obtains OpenWeather API data."""

    # OpenWeather API end point
    END_POINT = 'https://api.openweathermap.org'
    # OpenWeather endpoint qualifier
    QUALIFIER = 'data/2.5'
    # available data 'blocks' we may obtain from the API
    DATA_TYPES = ('weather', 'forecast', 'air_pollution')

    def __init__(self, ow_config, control_queue, data_queue, engine):

        # initialize my base class:
        super(OpenWeatherSource, self).__init__(ow_config, control_queue, data_queue, engine)

        log.info("self.debug=%s" % self.debug)
        try:
            self.key = ow_config['key']
        except KeyError:
            log.error('no key')
            # TODO. Should we send None to request closure?
        else:
            self.latitude = ow_config.get('latitude',
                                          self.engine.stn_info.latitude_f)
            self.longitude = ow_config.get('longitude',
                                           self.engine.stn_info.longitude_f)
            self.language = ow_config.get('language', 'en').lower()
            self.units = ow_config.get('units', 'metric').lower()
            self.max_tries = weeutil.weeutil.to_int(ow_config.get('max_tries',
                                                                  3))
            self.block = ow_config['block'].lower()

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
                             self.block])
        # now construct the parameters dict
        param_dict = {'lat': self.latitude,
                      'lon': self.longitude,
                      'lang': self.language,
                      'units': self.units,
                      'appid': self.key
                      }
        # obtain the params as a URL encoded string
        params = six.moves.urllib.parse.urlencode(param_dict)
        # construct the URL, it is a concatenation of the base URL and the
        # url-encoded parameters using a '?' as the joining character
        url = '?'.join([base_url, params])
        # if debug >= 1 log the URL used but obfuscate the key
        if weewx.debug > 0 or self.debug > 0:
            _obfuscated_url = url.replace(self.key, self.obfuscated_key(self.key))
            log.info("Submitting API call using URL: %s" % (_obfuscated_url,))
        # make the API call and obtain the response
        _response = self.submit_request(url)
        # if we have a response we need to de-serialise it
        json_response = json.loads(_response) if _response is not None else None
        # return the response
        return json_response


KNOWN_SOURCES = {'OW': OpenWeatherSource}
