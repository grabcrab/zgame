#pragma once
const char index_html_tmp[]  = R"rawliteral(
<!DOCTYPE html>
<html>

<head>
	<title>
		javaScript | Detecting a mobile browser
	</title>

</head>

<body style="text-align:center;">

	<h1 style="color:green;">
			GeeksForGeeks
		</h1>

	<button id="GFG_Button"
			onclick="detec()">
	detect
</button>
	<p id="GFG_P"
	style="color:green;
			font-size: 20px;">
	</p>
	<script>
		var a = '';
		var up = document.getElementById("GFG_P");

		function detec() {

			if (navigator.userAgent.match(/Android/i)
				|| navigator.userAgent.match(/webOS/i)
				|| navigator.userAgent.match(/iPhone/i)
				|| navigator.userAgent.match(/iPad/i)
				|| navigator.userAgent.match(/iPod/i)
				|| navigator.userAgent.match(/BlackBerry/i)
				|| navigator.userAgent.match(/Windows Phone/i)) {
				a = true;
			} else {
				a = false;
			}
			up.innerHTML = a;
		}
	</script>
</body>

</html>

)rawliteral";


const char index_html[]  = R"rawliteral(
<!DOCTYPE HTML><html>
<head>
  <title>%WEB_PORTAL_NAME_PLACEHOLDER%</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
	h1  {font-family: Arial; color:rgb(25, 114, 248); margin-bottom: 10px;}
	h11 {font-family: Arial; color:rgb(239, 0, 0); margin-bottom: 10px;}
	h2 {font-family: Arial; color: #474747; margin-bottom: 10px;}	
	.pages_links {font-family: Arial; color: #474747; margin: 10px}
	.pages_links_1 {font-family: Arial; color:rgb(245, 115, 2); margin: 10px}
	.input_submit {font-family: Arial; font-weight: bold; background:rgb(113, 228, 251); border-style: solid; border-color:rgb(47, 25, 248); border-radius: 5px;width:140px; padding-top: 5px; padding-bottom: 5px;}
    .input_submit:active  { background-color:#F85919;}
  </style>
</head>
<body>
  <script>  
 
    function doResetRequest () 
    {
      var xhttp = new XMLHttpRequest();
      xhttp.open("GET", "/doReset", true);
      xhttp.send();
    }
  </script>

  <div style="text-align:center">
  	<img src="logo">
  </div>	

  <div style="text-align:center">
    <p><h1>%HEADERLINE1_PLACEHOLDER%</h1></p>
  </div>

  <div style="text-align:center">
    <p><h2>%HEADERLINE2_PLACEHOLDER%</h2></p>
  </div>
  <div style="text-align:center">
    <h1 style="display: inline-block"><a class = "pages_links" href="/device">STATUS</a></h1><br>
    <h1 style="display: inline-block"><a class = "pages_links" href="/editor">CONFIGURATION</a></h1><br>
	<h1 style="display: inline-block"><a class = "pages_links" href="/files">FILES</a></h1><br>
	<h1 style="display: inline-block"><a class = "pages_links" href="/ota">OTA</a></h1><br>	  
	<h1 style="display: inline-block"><a class = "pages_links_1" href="/doReset">REBOOT</a></h1><br>	  
  </div>

</body>
</html>
)rawliteral";


//<h1 style="display: inline-block"><a class = "pages_links" href="/wifiOta">WI-FI OTA</a></h1>
//<h1 style="display: inline-block"><a class = "pages_links" href="/configuration_files_portal">EDIT CONFIGURATION</a></h1>

/*
  <div style="text-align:center">
    <p><h1><a href="/configuration">CONFIGURATION</a></h1></p>
  </div>
  <div style="text-align:center">
    <p><h1><a href="/monitoring" >MONITORING</a></h1></p>
  </div>

*/

/*
  	<br>
  	<div style="text-align:center">
	<b>DEVICE SETTINGS</b><br>
	<form action="/doRole"   target="hidden-form">
	<b><label for="devRole">Device role:</label><b>	
  	%ROLE_PLACEHOLDER%	
	<br>
	<input type="submit" class = "input_submit" value="SAVE" />
	</form>
	</div>
	<br>
	<div style="text-align:center">
	<a href="/doReset" class="input_submit">REBOOT</a><br>
	
	</div>
*/