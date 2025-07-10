#pragma once
//const char device_html[] PROGMEM = R"rawliteral(
  const char device_html[] = R"rawliteral(
<!DOCTYPE HTML><html>
<head>
  <title>DEVICE</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {margin: 10px; background: white;}
    label,
      input,
      button {
          width: 100px;
          padding: 2px;
          box-sizing: border-box;
          font-family: Arial;
          font-size: 18.67 px;
          margin-left: 40px;
      }
    select {font-family: Arial; font-size: 18.67 px; background: white; border-style: solid; border-color: grey; border-radius: 5px; margin-left: 20px; position:absolute; left:300px}
    h4 {font-family: Arial; font-size: 18.67 px; margin-left: 20px;}
    textarea {font-family: Arial; font-size: 18.67 px; background: white; border-style: solid; border-color: grey; border-radius: 5px; margin-left: 40px;}
    .input_submit:active  { background-color:orange;}
    .input_submit {font-family: Arial; font-weight: bold; background: #FB9871; border-style: solid; border-color: #FB9871; border-radius: 5px;width:140px; padding-top: 5px; padding-bottom: 5px;}

    .group_label {font-family: Arial; font-size: 18.67 px; font-weight: bold; margin-left: 40px; color: #46B4E7;}
    .back_button {font-family: Arial; font-weight: bold; background: #AAAAAA; border-style: solid; border-color: #AAAAAA; border-radius: 5px; width:140px; padding-top: 5px; padding-bottom: 5px;}
    .back_button:active {background-color: #0077b6;}
    .table_label {font-family: Arial; font-size: 18.67 px; font-weight: bold; margin-left: 40px;}
    table {border: 1px solid grey; border-collapse: collapse; margin-left: 40px;}
    th {border: 0px solid grey; padding: 10px; font-family: Arial; font-size: 18.67 px; color: #46B4E7;} 
    td {border: 1px solid grey;  padding: 10px; font-family: Arial; font-size: 18.67 px;} 
    .tdl {text-align: left;}
    .tdr {text-align: left;}
    .longtext {width : 200px;font-family: Arial; font-size: 18.67 px; background: white; border-style: solid; border-color: grey; border-radius: 5px; margin-left: 40px; position:absolute; left:200px}
  </style>


  <script>  
 
    function doResetRequest () 
    {
      var xhttp = new XMLHttpRequest();
      xhttp.open("GET", "/doReset", true);
      xhttp.send();
    }

    function goHomeRequest() {
      setTimeout(function() {
          document.location.href="/";
      }, 500);
    }

  </script>
</head>
<body>
  <button class="back_button" type="button" onclick="goHomeRequest();" class="button">BACK TO HOME</button>
  <br>
  <br>
  <br>
  <label class="group_label">Device Actions</label><br><br>
  
  <br>
  <label class="table_label">Device Info Table</label><br><br>
  <table>
    <tr><th class="tdl">NAME</th><th class="tdr">VALUE</th></tr>
    <tr><td class="tdl">HEAP, bytes</td><td class="tdr">%HEAP_CURR_VAL_PLACEHOLDER%</td></tr> 
    <tr><td class="tdl">Firmware Version</td><td class="tdr">%FIRMWARE_VERSION_PLACEHOLDER%</td></tr> 
    <tr><td class="tdl">ESP32 Dev ID</td><td class="tdr">%ESP32_DEV_ID_PLACEHOLDER%</td></tr>     
    <tr><td class="tdl">Temperature</td><td class="tdr">%ESP32_TEMPERATURE_PLACEHOLDER%</td></tr> 
    <tr><td class="tdl">Battery Voltage, mV</td><td class="tdr">%VCC_PLACEHOLDER%</td></tr> 
    <tr><td class="tdl">Power consumption, mAh</td><td class="tdr">%MAH_PLACEHOLDER%</td></tr> 
    <tr><td class="tdl">SPIFFS Used Bytes</td><td class="tdr">%SPIFFS_USED_PLACEHOLDER%</td></tr> 
    <tr><td class="tdl">SPIFFS Total Bytes</td><td class="tdr">%SPIFFS_TOTAL_PLACEHOLDER%</td></tr> 
  </table> <br><br>
  
</form>

)rawliteral";

 //<button type="button" onclick="doResetRequest();" class="input_submit">REBOOT</button> 
  // <div style="text-align:center">
  //   <p><h4 style="text-align:left">Device Portal</h4></p>
  // </div>



  // <form action="/doOTA" target="hidden-form">
  //   <label for="otaSSID">SSID:</label>
  //   <input class="longtext" type="text" name="otaSSID"><br><br>
  //   <label for="otaPASS">Password:</label>
  //   <input class="longtext" type="text" name="otaPASS"><br><br>
  //   <label for="otaLINK">Firmware binary URL:</label>
  //   <input class="longtext" type="text" name="otaLINK"><br><br>  
 
  //   <datalist id="otaList">

// Note: between device_html and otaLinkListTail_html function createOtaLinkList() add OTA link list and save into SPIFFS file
// const char otaLinkListTail_html[] = R"rawliteral(
//     </datalist><br>

//     <button class="input_submit" type="submit" onclick="submitMessage();" class="button">Make Firmware OTA</button>
//   </form><br><br>

//   <button class="back_button" type="button" onclick="goHomeRequest();" class="button">BACK TO HOME</button>

// </body>
// </html>
// )rawliteral";

//<input class="longtext" type="text" name="otaFileLink" list="otaList"  placeholder="Choose in drop down menu or type own link">