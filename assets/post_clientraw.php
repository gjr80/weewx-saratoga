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
  11 April 2021         v0.1.1   K. True mods
      - added return codes for results
        200 - OK for proper operation
        400 - Bad Request for malformed POST request (clientraw missing/malformed)
        405 - Method Not Allowed for GET or HEAD requests
        507 - Insufficient Storage if writing clientraw.txt to disk fails


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
      $CRrec = urldecode($param[1]);
      $CRarray = explode(' ',$CRrec);
      // make sure it's a clientraw.txt record we've got
      if(isset($CRarray[0]) and isset($CRarray[177]) and
         $CRarray[0] == '12345' and preg_match('/^!!\S+!!/',$CRarray[177]) ) {
       // save the decoded data to file
       $flag = file_put_contents($cr_file, $CRrec);
       if($flag !== false) {
         // we have our data so exit the loop
         header('HTTP/1.0 200 OK');
         exit('<h1>200 OK</h1>');
        } else {
         header('HTTP/1.0 507 Insufficient Storage');
         exit('<h1>507 Insufficient Storage</h1>');
       }
      }
    }
  }
} else { // GET or HEAD requests are rejected
  header('HTTP/1.0 405 Method Not Allowed');
  exit('<h1>405 Method Not Allowed</h1>');  
}

// oops.. malformed POST request.. let'em know
header('HTTP/1.0 400 Bad Request');
exit('<h1>400 Bad Request</h1>');  

