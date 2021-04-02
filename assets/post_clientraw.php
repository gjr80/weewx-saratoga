<?php
/*
post_clientraw.php

Accept a string via HTTP POST and then save the string as clientraw.txt.

Copyright (C) 2021 Gary Roderick                    gjroderick<at>gmail.com

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program.  If not, see http://www.gnu.org/licenses/.

Version: 0.1.0                                        Date: 2 April 2021

Revision History
  2 April 2021         v0.1.0
      - initial release

Instructions for use:

1.  Copy this file to an appropriate directory in the web server document tree

2.  Change $cr_file variable if required. Absolute paths with be relative to
    the web server document root, relative paths will be relative to the
    location of this file. The file name can be changed as well but should be
    left as clientraw.txt if using the received file with the Saratoga Weather
    Web Site templates or the Alternative dashboard.
*/

// define our destination path and file name
$cr_file = "./clientraw.txt";
// we are only interested in HTTP POST
if($_SERVER['REQUEST_METHOD'] == 'POST') {
    // get the data
    $data = file_get_contents("php://input");
    // the data should be urlencoded in key=value pairs, we want the pair whose
    // key=='clientraw'

    // iterate over each of the key=value pairs
    foreach (explode('&', $data) as $chunk) {
        // split the pair into key and value
        $param = explode("=", $chunk);
        // we are interested in the 'clientraw' data
        if (urldecode($param[0]) == 'clientraw') {
            // save the decoded data to file
            file_put_contents($cr_file, urldecode($param[1]));
            // we have our data so exit the loop
            break;
        }
    }
}
?>
