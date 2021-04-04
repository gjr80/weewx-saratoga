# WeeWX-Saratoga #

A WeeWX extension to support the Saratoga Weather Website Templates.

The *WeeWX-Saratoga* extension consists of a number of WeeWX services, Search List Extensions (SLE) and skins that produce the following data files:

-   clientraw.txt
-   clientrawextra.txt
-   clientrawdaily.txt
-   clientrawhour.txt
-   daywindrose.png
-   WEEWXtags.php

The above files are produced during each WeeWX report cycle with the exception of clientraw.txt which is generated upon receipt of loop packets.

The *WeeWX-Saratoga* extension is based on the WeeWD-WD (https://bitbucket.org/ozgreg/weewx-wd and https://github.com/gjr80/weewx-weewx-wd).


## Pre-Requisites ##

The *WeeWX-Saratoga* extension requires WeeWX v4.0.0 or later and operates under both Python 2 and Python 3.

Pyephem is required to support advanced ephemeris tags. 

## File Locations ##

As WeeWX file locations vary by system and installation method, the following symbolic names, as per the WeeWX User's Guide - Installing WeeWX, are used in these instructions:

- $BIN_ROOT (Executables)
- $SKIN_ROOT (Skins and templates)
- $SQLITE_ROOT (SQLite databases)
- $HTML_ROOT (Web pages and images)

Where applicable the nominal location for your system and installation type should be used in place of the symbolic name.

## Installation Instructions ##

**Note:** If installing *WeeWX-Saratoga* in place of a previous *WeeWX-WD* installation you should uninstall the *WeeWX-WD* installation before installing the *WeeWX-Saratoga* extension. You may wish to make a backup copy of weewx.conf before please uninstalling *WeeWX-WD* to aid in configuring the subsequent *WeeWX-Saratoga* extension installation.

**Note:** In the following code snippets the symbolic name *$DOWNLOAD_ROOT* is the path to the directory containing the downloaded *WeeWX-Saratoga* extension.

### Installation using the wee_extension utility ###

1.  Download the *WeeWX-Saratoga* extension from the *WeeWX-Saratoga* extension [releases page](https://github.com/gjr80/weewx-saratoga/releases) into a directory accessible from the WeeWX machine.

        $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-saratoga/releases/download/v0.1.0/ws-0.1.0.tar.gz

	replacing the symbolic name *$DOWNLOAD_ROOT* with the path to the directory where the *WeeWX-Saratoga* extension is to be downloaded (eg, */var/tmp*).

1.  Stop WeeWX:

        $ sudo /etc/init.d/weewx stop

	or

        $ sudo service weewx stop

    or

        $ sudo systemctl stop weewx

1.  Install the *WeeWX-Saratoga* extension downloaded at step 1 using the WeeWX *wee_extension* utility:

        $ wee_extension --install=$DOWNLOAD_ROOT/ws-0.1.0.tar.gz

    **Note:** Depending on your system/installation the above command may need to be prefixed with *sudo*.

    **Note:** Depending on your WeeWX installation the path to *wee_extension* may need to be provided, eg: `$ /home/weewx/bin/wee_extension --install...`.
    
    This will result in output similar to the following:

		Request to install '/var/tmp/ws-0.1.0.tar.gz'
		Extracting from tar archive /var/tmp/ws-0.1.0.tar.gz
		Saving installer file to /home/weewx/bin/user/installer/WeeWX-Saratoga
		Saved configuration dictionary. Backup copy at /home/weewx/weewx.conf.20210403130000
		Finished installing extension '/var/tmp/ws-0.1.0.tar.gz'

1. Start WeeWX:

        $ sudo /etc/init.d/weewx start

	or

        $ sudo service weewx start

    or

        $ sudo systemctl start weewx

1.  This will result in the WeeWX-Saratoga data files being generated as outlined above. The *WeeWX-Saratoga* extension installation can be further customized (eg units of measure, file locations etc) by referring to the WeeWX-Saratoga wiki.

### Manual installation ###

1.  Download the *WeeWX-Saratoga* extension from the *WeeWX-Saratoga* extension [releases page](https://github.com/gjr80/weewx-saratoga/releases) into a directory accessible from the WeeWX machine.

        $ wget -P $DOWNLOAD_ROOT https://github.com/gjr80/weewx-saratoga/releases/download/v0.1.0/ws-0.1.0.tar.gz

	where *$DOWNLOAD_ROOT* is the path to the directory where the *WeeWX-Saratoga* extension is to be downloaded.

1.  Unpack the extension as follows:

        $ tar xvfz ws-0.1.0.tar.gz

1.  Copy files from within the resulting directory as follows:

        $ cp ws/bin/user/*.py $BIN_ROOT/user
        $ cp -R ws/skins/* $SKIN_ROOT

	replacing the symbolic names *$BIN_ROOT* and *$SKIN_ROOT* with the nominal locations for your installation.

1.  Edit weewx.conf:

        $ vi weewx.conf

1.  In weewx.conf, modify the *[StdReport]* section by adding the following sub-sections:

        [[WEEWXtagsReport]]
            skin = WEEWXtags
            enable = True
            [[[Units]]]
                [[[[TimeFormats]]]]
                    date_f = %d/%m/%Y,
                    date_time_f = %d/%m/%Y %H:%M
        [[ClientrawReport]]
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

1.  In weewx.conf, add the following section:

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
                # URL to use if transferring clientraw.txt to web server via HTTP POST 
                # using post_clientraw.php. Supports both http and https. Must end with 
                # post_clientraw.php. To enable uncomment line and enter web server 
                # address to be used.
                # remote_server_url = http://web.server.address/post_clientraw.php
        
                # How often to generate clientraw.txt. clientraw.txt is only generated 
                # on receipt of a loop packet and then only after at least min_interval 
                # seconds have elapsed since the last generation time. Default is 10, 
                # use 0 to generate on every loop packet.
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

1.  In weewx.conf, add the following sub-section to *[Databases]*:

        [[ws_sqlite]]
            database_type = SQLite
            database_name = weewxwd.sdb
        [[ws_supp_sqlite]]
            database_type = SQLite
            database_name = wdsupp.sdb

    if using MySQL instead add something like (with settings for your MySQL setup):

        [[ws_mysql]]
            database_type = MySQL
            database_name = weewxwd
        [[ws_supp_mysql]]
            database_type = MySQL
            database_name = wdsupp

1.  In weewx.conf, add the following sub-section to the *[DataBindings]* section:

        [[ws_binding]]
            database = ws_sqlite
            table_name = archive
            manager = weewx.manager.DaySummaryManager
            schema = user.wsschema.ws_schema
        [[ws_supp_binding]]
            database = ws_supp_sqlite
            table_name = supp
            manager = weewx.manager.Manager
            schema = user.wsschema.ws_supp_schema

    if using MySQL instead, add something like (with settings for your MySQL
    setup):

        [[wd_binding]]
            database = weewxwd_mysql
            table_name = archive
            manager = weewx.manager.DaySummaryManager
            schema = user.wdschema.weewxwd_schema
    
        [[wdsupp_binding]]
            database = wd_supp_mysql
            table_name = supp
            manager = weewx.manager.Manager
            schema = user.wdschema.wdsupp_schema

1.  In weewx.conf, modify the services lists in *[Engine]* as indicated:

	*   process_services. Add user.ws.WsWXCalculate eg:

            process_services = weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC, weewx.wxservices.StdWXCalculate, user.ws.WsWXCalculate

	*   archive_services. Add user.ws.WsArchive AND user.ws.WsSuppArchive eg:

            archive_services = weewx.engine.StdArchive, user.ws.WsArchive, user.ws.WsSuppArchive

1. Start WeeWX:

        $ sudo /etc/init.d/weewx start

	or

        $ sudo service weewx start

    or

        $ sudo systemctl start weewx

1.  This will result in the WeeWX-Saratoga data files being generated as outlined above. The *WeeWX-Saratoga* extension installation can be further customized (eg units of measure, file locations etc) by referring to the WeeWX-Saratoga wiki.


## Support ##

General support issues may be raised in the Google Groups [weewx-user forum](https://groups.google.com/group/weewx-user "Google Groups weewx-user forum"). Specific bugs in the *WeeWX-Saratoga* extension code should be the subject of a new issue raised via the [Issues Page](https://github.com/gjr80/weewx-weewx-wd/issues "WeeWX-Saratoga extension Issues").

## Licensing ##

The *WeeWX-Saratoga* extension is licensed under the [GNU Public License v3](https://github.com/gjr80/weewx-saratoga/blob/master/LICENSE "*WeeWX-Saratoga* extension License").
