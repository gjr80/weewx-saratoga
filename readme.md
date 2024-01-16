# WeeWX-Saratoga #

The *WeeWX-Saratoga extension* is a *WeeWX* extension that supports the [*Saratoga Weather Website Templates*](https://saratoga-weather.org/wxtemplates/index.php) using the *WEEWX-plugin*. The extension also supports the *Saratoga Weather Website templates* [Alternative dashboard](https://saratoga-weather.org/scripts-legacy.php#scott) and can be further used to support any scripts that rely on one or more of the [Weather-Display](https://www.weather-display.com/index.php) *clientraw* family of files for operation.

The *WeeWX-Saratoga extension* consists of a number of [*WeeWX* services](https://weewx.com/docs/5.0/custom/introduction/#overall-system-architecture), [Search List Extensions (SLE)](https://weewx.com/docs/5.0/custom/sle/), [XTypes](https://weewx.com/docs/5.0/custom/derived/) and [reports/skins](https://weewx.com/docs/5.0/custom/custom-reports/) that produce the following data files:

-   clientraw.txt
-   clientrawextra.txt
-   clientrawdaily.txt
-   clientrawhour.txt
-   daywindrose.png
-   WEEWXtags.php
-   various observation plots

The above files are produced during each *WeeWX* report cycle with the exception of *clientraw.txt* which is generated upon receipt of loop packets and (by default) updated at 10 second intervals.

The *WeeWX-Saratoga extension* is based on the original [*weewx-WD extension*](https://bitbucket.org/ozgreg/weewx-wd) and the later forked [*WeeWX-WD extension*](https://github.com/gjr80/weewx-weewx-wd).


## Pre-Requisites ##

The *WeeWX-Saratoga extension* requires:

- *WeeWX* v4.5.0 or later, and

- the *Pyephem* Python library for extended almanac information.

**Note**: Both Python 2 and Python 3 are supported when the *WeeWX-Saratoga extension* is run under *WeeWX* v4. When run under *WeeWX* v5 only Python 3 is supported.

**Note**: The *Pyephem* Python library is automatically installed under *WeeWX* v5, but may or may not be installed under *WeeWX* v4. *WeeWX* v4.6.0 and later log the availability of the *Pyephem* Python library during *WeeWX* startup. Refer to [WeeWX: Installation using setup.py](https://weewx.com/docs/4.10/setup.htm) for the commands to install the *Pyephem* Python library under *WeeWX* v4.


## Installation and Upgrade Instructions ##

The preferred method of installing or upgrading the *WeeWX-Saratoga extension* is through use of the applicable *WeeWX* extension utility. The *WeeWX-Saratoga extension* can also be installed manually.

**Note**: If installing the *WeeWX-Saratoga extension* in place of *WeeWX-WD* please refer to the [Migrating from *WeeWX-WD*](https://github.com/gjr80/weewx-saratoga/wiki/Migrating-from-WeeWX‐WD) wiki page.


### Installing or upgrading using the *WeeWX* extension utility ###

1.  Download the *WeeWX-Saratoga extension* from the *WeeWX-Saratoga extension* [releases page](https://github.com/gjr80/weewx-saratoga/releases) into a directory accessible from the *WeeWX* machine:

        wget -P /var/tmp https://github.com/gjr80/weewx-saratoga/releases/download/v0.1.8/ws-0.1.8.tar.gz

	in this case the extension will be downloaded to the directory */var/tmp*.

1.  Install the *WeeWX-Saratoga extension* downloaded at step 1 using the applicable *WeeWX* extension utility:

- for *WeeWX* v5:

      weectl extension install /var/tmp/ws-0.1.8.tar.gz

    **Note:** Depending on your *WeeWX* installation the path to *weectl* may need to be provided.

- for *WeeWX* v4:

      wee_extension --install /var/tmp/ws-0.1.8.tar.gz

    **Note:** Depending on your system/installation the above command may need to be prefixed with *sudo*.

    **Note:** Depending on your *WeeWX* installation the path to *wee_extension* may need to be provided.

    This will result in output similar to the following:

      Using configuration file /home/username/weewx-data/weewx.conf
      Install extension '/var/tmp/ws-0.1.8b1.tar.gz' (y/n)? y
      Extracting from tar archive /var/tmp/ws-0.1.8b1.tar.gz
      Saving installer file to /home/username/weewx-data/bin/user/installer/WeeWX-Saratoga.
      Saved configuration dictionary. Backup copy at /home/username/weewx-data/weewx.conf.20240116142114.
      Finished installing extension WeeWX-Saratoga from /var/tmp/ws-0.1.8b1.tar.gz.

    **Note:** If upgrading an existing *WeeWX-Saratoga extension* installation any previous *WeeWX-Saratoga extension* configuration information in *weewx.conf* will have been retained and upgraded as required. The *WeeWX* extension utility will save a timestamped backup copy of the pre-upgrade *weewx.conf* as detailed in the extension utility output, eg:
    
      Saved configuration dictionary. Backup copy at /home/username/weewx-data/weewx.conf.20240116142114.
    
1.  Restart *WeeWX*:

        sudo /etc/init.d/weewx restart

	or

        sudo service weewx restart

    or

        sudo systemctl restart weewx

1.  This will result in the WeeWX-Saratoga data files being generated as outlined above. The generated files should be located in the *public_html/saratoga* directory.

1. The *WeeWX-Saratoga extension* installation can be further customized (eg remote file transfer, units of measure etc) by referring to the [WeeWX-Saratoga wiki](https://github.com/gjr80/weewx-saratoga/wiki).


### Installing or upgrading manually ###

1.  Download the *WeeWX-Saratoga extension* from the *WeeWX-Saratoga extension* [releases page](https://github.com/gjr80/weewx-saratoga/releases) into a directory accessible from the *WeeWX* machine.

        wget -P /var/tmp https://github.com/gjr80/weewx-saratoga/releases/download/v0.1.8/ws-0.1.8.tar.gz

	in this case the extension will be downloaded to the directory */var/tmp*.

1.  Unpack the extension as follows:

        tar xvfz /var/tmp/ws-0.1.8.tar.gz

1.  Copy files from within the resulting *ws* directory as follows:

-   *WeeWX* v5:

        cp ws/bin/user/*.py USER_ROOT/user
        cp -R ws/skins/* SKIN_ROOT

    Where *USER_ROOT* is the *User directory* and *SKIN_ROOT* is the *Skins and templates* directory as detailed in the [*WeeWX* v5 *where to find things*](https://weewx.com/docs/5.0/usersguide/where/) section of the [WeeWX User's Guide](https://weewx.com/docs/5.0/usersguide/introduction/).

-   *WeeWX* v4:

        cp ws/bin/user/*.py BIN_ROOT/user
        cp -R ws/skins/* SKIN_ROOT

       Where *BIN_ROOT* is the *Executables* directory and *SKIN_ROOT* is the *Skins and templates* directory as detailed in the [*WeeWX* v4 *where to find things*](https://weewx.com/docs/4.10/usersguide.htm#Where_to_find_things) section of the [WeeWX User's Guide](http://weewx.com/docs/4.10/usersguide.htm).

1.  Edit *weewx.conf*:

        vi weewx.conf
    
    **Note:** If manually upgrading an existing *WeeWX-Saratoga extension* installation it is the user's responsibility to retain any previous *WeeWX-Saratoga extension* configuration information in *weewx.conf*. It is strongly recommended that a backup copy of *weewx.conf* be made before any upgrade changes are made to *weewx.conf*.

1.  In *weewx.conf*, modify the *[StdReport]* section by adding the following sub-sections:

        [[WEEWXtagsReport]]
            HTML_ROOT = public_html/saratoga
            skin = WEEWXtags
            enable = True
            [[[Units]]]
                [[[[TimeFormats]]]]
                    date_f = %d/%m/%Y,
                    date_time_f = %d/%m/%Y %H:%M
        [[ClientrawReport]]
            HTML_ROOT = public_html/saratoga
            skin = Clientraw
            enable = True
            [[[Units]]]
                [[[[StringFormats]]]]
                    degree_C = %.1f
                    degree_compass = %.0f
                    foot = %.0f
                    hPa = %.1f
                    km = %.1f
                    knot = %.1f
                    mm = %.1f
                    percent = %.0f
                    uv_index = %.1f
                    watt_per_meter_squared = %.0f
                    NONE = --          

1.  In *weewx.conf*, add the following section:

        [WeewxSaratoga]
            # WeewxSaratoga database binding
            data_binding = ws_binding

            # radiation (solar insolation) level above which the sun is considered
            # shining
            sunshine_threshold = 120

            [[Supplementary]]
                # WeewxSaratoga supplementary database binding
                data_binding = ws_supp_binding
                [[[WU]]]
                    api_key = replace_me
                    enable = False
                [[[DS]]]
                    api_key = replace_me
                    enable = False
                [[[File]]]
                    file = /path/and/filename
                    enable = False

            [[RealtimeClientraw]]

                # If using an external website, configure remote_server_url to point to
                # the post_clientraw.php script on your website like:
                #   remote_server_url = http://your.website.com/post_clientraw.php
                #
                # To disable or use the webserver on this system, leave the entry
                # commented out or blank.
                # remote_server_url = http://your.website.com/post_clientraw.php

                # min_interval sets the minimum clientraw.txt generation interval.
                # Default is 10 seconds.
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

1.  In *weewx.conf*, add the following sub-section to *[Databases]*:

        [[ws_sqlite]]
            database_type = SQLite
            database_name = weewxwd.sdb

    if using MySQL instead add something like (with settings for your MySQL setup):

        [[ws_mysql]]
            database_type = MySQL
            database_name = weewxwd

1.  In *weewx.conf*, add the following sub-section to the *[DataBindings]* section:

        [[ws_binding]]
            database = ws_sqlite
            table_name = archive
            manager = weewx.manager.DaySummaryManager
            schema = user.wsschema.ws_schema

    if using MySQL instead, add something like (with settings for your MySQL
    setup):

        [[ws_binding]]
            database = ws_mysql
            table_name = archive
            manager = weewx.manager.DaySummaryManager
            schema = user.wdschema.weewxwd_schema

1.  In *weewx.conf*, modify the services lists in *[Engine]* as indicated:

	*   process_services. Add user.ws.WsWXCalculate eg:

            process_services = weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC, weewx.wxservices.StdWXCalculate, user.ws.WsWXCalculate

	*   archive_services. Add user.ws.WsArchive AND user.ws.WsSuppArchive eg:

            archive_services = weewx.engine.StdArchive, user.ws.WsArchive, user.ws.WsSuppArchive

1. restart *WeeWX*:

        sudo /etc/init.d/weewx restart

	or

        sudo service weewx restart

    or

        sudo systemctl restart weewx

1.  This will result in the WeeWX-Saratoga data files being generated as outlined above. The generated files should be located in the *public_html/saratoga* directory.

1. The *WeeWX-Saratoga extension* installation can be further customized (eg remote file transfer, units of measure etc) by referring to the [WeeWX-Saratoga wiki](https://github.com/gjr80/weewx-saratoga/wiki).


## Support ##

General support issues for the *WeeWX-Saratoga extension* may be raised in the Google Groups [weewx-user forum](https://groups.google.com/g/weewx-user "Google Groups weewx-user forum"). The *WeeWX-Saratoga extension* [Issues Page](https://github.com/gjr80/weewx-saratoga/issues "WeeWX-Saratoga extension Issues") should only be used for specific bugs in the *WeeWX-Saratoga extension* code. It is recommended that even if a *WeeWX-Saratoga extension* bug is suspected users first post to the Google Groups [weewx-user forum](https://groups.google.com/g/weewx-user "Google Groups weewx-user forum"). Support for the [_WEEWX-plugin_](https://saratoga-weather.org/wxtemplates/install.php) for the *Saratoga Weather Website templates* should be via posts on [WXForum.net, Custom Templates/Scripts board](https://www.wxforum.net/index.php?board=102.0).

## Licensing ##

The *WeeWX-Saratoga extension* is licensed under the [GNU Public License v3](https://github.com/gjr80/weewx-saratoga/blob/master/LICENSE "*WeeWX-Saratoga extension* License").
