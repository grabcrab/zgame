#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <Update.h>
#include <Adafruit_NeoPixel.h>

// Variables for LED blinking and OTA progress
bool otaInProgress = false;
unsigned long previousMillis = 0;
const long blinkInterval = 100; // 100ms interval for blinking
size_t otaTotalSize = 0;
size_t otaCurrentSize = 0;

const char ota_html[] PROGMEM = R"rawliteral(
    <!DOCTYPE HTML><html>
    <head>
      <title>OTA Update</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
      <h1>Firmware Update</h1>
      <form id="uploadForm" method="POST" action="/update" enctype="multipart/form-data">
        <input type="file" name="update" accept=".bin">
        <input type="submit" value="Upload Firmware">
      </form>
      <div id="progressSection" style="display:none;">
        <p>Uploading...</p>
        <progress id="progressBar" value="0" max="100"></progress>
        <p id="progressText">0%</p>
      </div>
    
      <script>
        document.getElementById('uploadForm').onsubmit = function(e) {
          e.preventDefault();
          document.getElementById('progressSection').style.display = 'block';
          let formData = new FormData(this);
          let xhr = new XMLHttpRequest();
          xhr.upload.onprogress = function(event) {
            if (event.lengthComputable) {
              let percent = Math.round((event.loaded / event.total) * 100);
              document.getElementById('progressBar').value = percent;
              document.getElementById('progressText').innerText = percent + '%';
            }
          };
          xhr.onload = function() {
            if (xhr.status === 200 && xhr.responseText === 'OK') {
              window.location.href = '/ota_complete'; // Redirect to completion page
            } else {
              alert('Update failed!');
              document.getElementById('progressSection').style.display = 'none';
              document.getElementById('progressBar').value = 0;
              document.getElementById('progressText').innerText = '0%';
            }
          };
          xhr.open('POST', '/update', true);
          xhr.send(formData);
        };
      </script>
    </body>
    </html>
    )rawliteral";

// HTML for the OTA completion page
const char ota_complete_html[] PROGMEM = R"rawliteral(
    <!DOCTYPE HTML><html>
    <head>
      <title>OTA Complete</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body>
      <h1>OTA completed, rebooting. <a href="/doReset">Click to restart</a></h1>
    </body>
    </html>
    )rawliteral";


// const char ota_html[] PROGMEM = R"rawliteral(
// <!DOCTYPE HTML><html>
// <head>
//   <title>OTA Update</title>
//   <meta name="viewport" content="width=device-width, initial-scale=1">
// </head>
// <body>
//   <h1>Firmware Update</h1>
//   <form id="uploadForm" method="POST" action="/update" enctype="multipart/form-data">
//     <input type="file" name="update" accept=".bin">
//     <input type="submit" value="Upload Firmware">
//   </form>
//   <div id="progressSection" style="display:none;">
//     <p>Uploading...</p>
//     <progress id="progressBar" value="0" max="100"></progress>
//     <p id="progressText">0%</p>
//   </div>

//   <script>
//     document.getElementById('uploadForm').onsubmit = function(e) {
//       e.preventDefault();
//       document.getElementById('progressSection').style.display = 'block';
//       let formData = new FormData(this);
//       let xhr = new XMLHttpRequest();
//       xhr.upload.onprogress = function(event) {
//         if (event.lengthComputable) {
//           let percent = Math.round((event.loaded / event.total) * 100);
//           document.getElementById('progressBar').value = percent;
//           document.getElementById('progressText').innerText = percent + '%';
//         }
//       };
//       xhr.onload = function() {
//         if (xhr.status === 200 && xhr.responseText === 'OK') {
//           alert('Update successful! Device will reboot.');
//         } else {
//           alert('Update failed!');
//         }
//         document.getElementById('progressSection').style.display = 'none';
//         document.getElementById('progressBar').value = 0;
//         document.getElementById('progressText').innerText = '0%';
//       };
//       xhr.open('POST', '/update', true);
//       xhr.send(formData);
//     };
//   </script>
// </body>
// </html>
// )rawliteral";

void handleOtaPage(AsyncWebServerRequest *request)
{
    request->send_P(200, "text/html", ota_html);
}

void handleOtaComplete(AsyncWebServerRequest *request) 
{
    request->send_P(200, "text/html", ota_complete_html);
    delay(100);
}

void handleOtaUpdateResponse(AsyncWebServerRequest *request)
{
    bool shouldReboot = !Update.hasError();
    AsyncWebServerResponse *response = request->beginResponse(200, "text/plain", shouldReboot ? "OK" : "FAIL");
    response->addHeader("Connection", "close");
    request->send(response);
    delay(1000);
    if (shouldReboot)
    {        
        //ESP.restart();
    }
    else
    {        
        delay(1000);
    }
}

void handleOtaUpdateUpload(AsyncWebServerRequest *request, String filename, size_t index, uint8_t *data, size_t len, bool final)
{
    if (!index)
    {
        Serial.println("Starting OTA update...");
        otaInProgress = true;                    // Start blinking
        otaTotalSize = request->contentLength(); // Get total size of the upload
        otaCurrentSize = 0;
        if (!Update.begin(UPDATE_SIZE_UNKNOWN))
        {
            Update.printError(Serial);
        }
    }
    if (Update.write(data, len) != len)
    {
        Update.printError(Serial);
    }
    otaCurrentSize += len; // Update current size
    if (final)
    {
        if (Update.end(true))
        {
            Serial.println(">>> OTA update successful!!!");
            //request->send_P(200, "text/html", ota_complete_html);
            delay(1000);
        }
        else
        {
            Update.printError(Serial);
            //String errHtml = ota_error_html;
            //errHtml.replace("__ERR_MESS__", Update.errorString());
            //request->send_P(200, "text/html", errHtml.c_str());                     
            //delay(3000);
        }
        otaInProgress = false; // Stop blinking        
    }
}

bool loopOTA(void)
{
    // LED blinking during OTA
    if (otaInProgress)
    {
        unsigned long currentMillis = millis();
        if (currentMillis - previousMillis >= blinkInterval)
        {
            previousMillis = currentMillis;
            static bool ledState = false;
            ledState = !ledState;            
        }
        return true;
    }
    return false;
}
