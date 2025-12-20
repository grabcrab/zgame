#include "serverSync.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <Update.h>
#include <ArduinoJson.h>
#include <MD5Builder.h>
#include <esp_partition.h>
#include <esp_ota_ops.h>
#include "tft_utils.h"


// WiFi settings
// const char *ssid = "tcutestnet";
// const char *password = "tcutestpass";

// OTA server settings
//const char *otaServerURL = "http://192.168.1.120:5005"; // Your server IP
//const unsigned long checkInterval = 5000;               // Check every 30 seconds

// Global variables
//unsigned long lastCheck = 0;

extern void otaProgressCallback(int progress);
String getCurrentFirmwareMD5(void)
{
    // Use built-in ESP32 function to get current sketch MD5
    String md5 = ESP.getSketchMD5();
    Serial.printf("Current firmware MD5: %s\n", md5.c_str());
    return md5;
}

bool syncOTA(const char *otaServerURL, int currentVersion)
{
    bool res;
    if (WiFi.status() != WL_CONNECTED)
    {
        Serial.println("!!! syncOTA ERROR: WiFi not connected");
        return false;
    }

    HTTPClient http;
    http.begin(String(otaServerURL) + "/version");

    int httpCode = http.GET();
    if (httpCode == HTTP_CODE_OK)
    {
        String payload = http.getString();

        // Parse JSON response
        //DynamicJsonDocument doc(1024);
        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, payload);

        if (error)
        {
            Serial.println("!!! syncOTA ERROR: Failed to parse JSON response");
            http.end();
            return false;
        }

        // Get server version number (from versioning file)
        int serverVersion = doc["version"].as<int>();
        // Get server MD5 checksum
        String serverMD5 = doc["md5"].as<String>();
        int firmwareSize = doc["size"];
        String filename = doc["filename"];
        String currentFirmwareMD5 = getCurrentFirmwareMD5();
        
        Serial.println("Server response:");
        Serial.println("  Server Version: " + String(serverVersion));
        Serial.println("  Server MD5: " + serverMD5);
        Serial.println("  Current Version: " + String(currentVersion));
        Serial.println("  Current MD5: " + currentFirmwareMD5);
        Serial.println("  Size: " + String(firmwareSize));
        Serial.println("  Filename: " + filename);

        // Compare versions - update if server version is newer OR if MD5 mismatch
        bool needsUpdate = false;
        
        if (serverVersion > currentVersion)
        {
            Serial.println("Version mismatch detected! Server has newer version.");
            Serial.printf("  Server Version: %d, Current Version: %d\n", serverVersion, currentVersion);
            needsUpdate = true;
        }
        else if (serverVersion == currentVersion && serverMD5 != currentFirmwareMD5)
        {
            // Same version but different MD5 - could be a rebuild/patch
            Serial.println("MD5 mismatch detected at same version! Possible rebuild/patch.");
            Serial.println("  Server MD5:  " + serverMD5);
            Serial.println("  Current MD5: " + currentFirmwareMD5);
            needsUpdate = true;
        }
        
        if (needsUpdate)
        {
            Serial.println("Starting OTA update...");
            res = performOTAUpdate(otaServerURL, firmwareSize);            
        }
        else
        {
            Serial.println("Firmware is up to date");
            Serial.printf("  Version: %d, MD5 match: %s\n", currentVersion, 
                         (serverMD5 == currentFirmwareMD5) ? "yes" : "no");
            return true;
        }
    }
    else
    {        
        Serial.printf("!!!syncOTA HTTP ERROR: %d\n", httpCode);
        return false;
    }
    
    http.end();
    return res;
}

bool performOTAUpdate(const char *otaServerURL, int firmwareSize)
{
    bool res = false;
    HTTPClient http;
    http.begin(String(otaServerURL) + "/update");

    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK)
    {
        Serial.printf("!!! performOTAUpdate ERROR: Failed to start download: %d\n", httpCode);
        http.end();
        return false;
    }

    int contentLength = http.getSize();
    if (contentLength != firmwareSize)
    {
        Serial.println("!!! performOTAUpdate ERROR: Content length mismatch");
        http.end();
        return false;
    }

    // Start OTA update
    if (!Update.begin(contentLength))
    {
        Serial.println("!!! performOTAUpdate ERROR: Not enough space for update");
        http.end();
        return false;
    }

    Serial.println("Starting OTA update...");
    Serial.printf("Firmware size: %d bytes\n", contentLength);

    WiFiClient *client = http.getStreamPtr();
    int written = 0;
    int progress = 0;
    int lastProgress = -1;

    uint8_t buffer[128];

    while (http.connected() && (written < contentLength))
    {
        size_t available = client->available();
        if (available)
        {
            int readBytes = client->readBytes(buffer, min(available, sizeof(buffer)));

            if (readBytes > 0)
            {
                if (Update.write(buffer, readBytes) != readBytes)
                {
                    Serial.println("!!! performOTAUpdate ERROR: write failed");
                    res = false;
                    break;
                }
                written += readBytes;

                // Calculate and display progress
                progress = (written * 100) / contentLength;
                if (progress != lastProgress && progress % 5 == 0)
                {
                    otaProgressCallback(progress);
                    lastProgress = progress;
                }
            }
        }
        delay(1);
    }

    if (written == contentLength)
    {
        Serial.println(">>> performOTAUpdate: Update completed successfully");
        otaProgressCallback(100);
        res = true;
    }
    else
    {
        Serial.printf("!!! performOTAUpdate ERROR:  Update failed. Written: %d, Expected: %d\n", written, contentLength);
        res = false;
    }

    if (Update.end())
    {
        if (Update.isFinished())
        {
            Serial.println(">>> performOTAUpdate: Update successfully finished. Rebooting...");
            tftPrintText("OTA DONE");
            delay(2000);
            ESP.restart();
        }
        else
        {
            Serial.println("!!! performOTAUpdate ERROR: Update failed to finish");
            tftPrintText("OTA ERROR[1]");
            delay(5000);
            res = false;
        }
    }
    else
    {
        Serial.printf("!!! performOTAUpdate ERROR: %d\n", Update.getError());
        tftPrintText("OTA ERROR[2]");
        delay(5000);
        res = false;
    }

    http.end();
    return res;
}

// #include "serverSync.h"
// #include <WiFi.h>
// #include <HTTPClient.h>
// #include <Update.h>
// #include <ArduinoJson.h>
// #include <MD5Builder.h>
// #include <esp_partition.h>
// #include <esp_ota_ops.h>
// #include "tft_utils.h"


// // WiFi settings
// // const char *ssid = "tcutestnet";
// // const char *password = "tcutestpass";

// // OTA server settings
// //const char *otaServerURL = "http://192.168.1.120:5005"; // Your server IP
// //const unsigned long checkInterval = 5000;               // Check every 30 seconds

// // Global variables
// //unsigned long lastCheck = 0;

// extern void otaProgressCallback(int progress);
// String getCurrentFirmwareMD5(void)
// {
//     // Use built-in ESP32 function to get current sketch MD5
//     String md5 = ESP.getSketchMD5();
//     Serial.printf("Current firmware MD5: %s\n", md5.c_str());
//     return md5;
// }

// bool syncOTA(const char *otaServerURL)
// {
//     bool res;
//     if (WiFi.status() != WL_CONNECTED)
//     {
//         Serial.println("!!! syncOTA ERROR: WiFi not connected");
//         return false;
//     }

//     HTTPClient http;
//     http.begin(String(otaServerURL) + "/version");

//     int httpCode = http.GET();
//     if (httpCode == HTTP_CODE_OK)
//     {
//         String payload = http.getString();

//         // Parse JSON response
//         //DynamicJsonDocument doc(1024);
//         JsonDocument doc;
//         DeserializationError error = deserializeJson(doc, payload);

//         if (error)
//         {
//             Serial.println("!!! syncOTA ERROR: Failed to parse JSON response");
//             http.end();
//             return false;
//         }

//         String serverVersion = doc["version"];
//         int firmwareSize = doc["size"];
//         String filename = doc["filename"];
//         String currentFirmwareVersion = getCurrentFirmwareMD5();
//         Serial.println("Server response:");
//         Serial.println("  Server MD5: " + serverVersion);
//         Serial.println("  Current MD5: " + currentFirmwareVersion);
//         Serial.println("  Size: " + String(firmwareSize));
//         Serial.println("  Filename: " + filename);

//         // Compare versions
//         if (serverVersion != currentFirmwareVersion)
//         {
//             Serial.println("MD5 mismatch detected! Starting update...");
//             Serial.println("  Server:  " + serverVersion);
//             Serial.println("  Current: " + currentFirmwareVersion);
//             res = performOTAUpdate(otaServerURL, firmwareSize);            
//         }
//         else
//         {
//             Serial.println("Firmware is up to date - MD5 match");
//             return true;
//         }
//     }
//     else
//     {        
//         Serial.printf("!!!syncOTA HTTP ERROR: %d\n", httpCode);
//         return false;
//     }
    
//     http.end();
//     return res;
// }

// bool performOTAUpdate(const char *otaServerURL, int firmwareSize)
// {
//     bool res = false;
//     HTTPClient http;
//     http.begin(String(otaServerURL) + "/update");

//     int httpCode = http.GET();
//     if (httpCode != HTTP_CODE_OK)
//     {
//         Serial.printf("!!! performOTAUpdate ERROR: Failed to start download: %d\n", httpCode);
//         http.end();
//         return false;
//     }

//     int contentLength = http.getSize();
//     if (contentLength != firmwareSize)
//     {
//         Serial.println("!!! performOTAUpdate ERROR: Content length mismatch");
//         http.end();
//         return false;
//     }

//     // Start OTA update
//     if (!Update.begin(contentLength))
//     {
//         Serial.println("!!! performOTAUpdate ERROR: Not enough space for update");
//         http.end();
//         return false;
//     }

//     Serial.println("Starting OTA update...");
//     Serial.printf("Firmware size: %d bytes\n", contentLength);

//     WiFiClient *client = http.getStreamPtr();
//     int written = 0;
//     int progress = 0;
//     int lastProgress = -1;

//     uint8_t buffer[128];

//     while (http.connected() && (written < contentLength))
//     {
//         size_t available = client->available();
//         if (available)
//         {
//             int readBytes = client->readBytes(buffer, min(available, sizeof(buffer)));

//             if (readBytes > 0)
//             {
//                 if (Update.write(buffer, readBytes) != readBytes)
//                 {
//                     Serial.println("!!! performOTAUpdate ERROR: write failed");
//                     res = false;
//                     break;
//                 }
//                 written += readBytes;

//                 // Calculate and display progress
//                 progress = (written * 100) / contentLength;
//                 if (progress != lastProgress && progress % 5 == 0)
//                 {
//                     otaProgressCallback(progress);
//                     lastProgress = progress;
//                 }
//             }
//         }
//         delay(1);
//     }

//     if (written == contentLength)
//     {
//         Serial.println(">>> performOTAUpdate: Update completed successfully");
//         otaProgressCallback(100);
//         res = true;
//     }
//     else
//     {
//         Serial.printf("!!! performOTAUpdate ERROR:  Update failed. Written: %d, Expected: %d\n", written, contentLength);
//         res = false;
//     }

//     if (Update.end())
//     {
//         if (Update.isFinished())
//         {
//             Serial.println(">>> performOTAUpdate: Update successfully finished. Rebooting...");
//             tftPrintText("OTA DONE");
//             delay(2000);
//             ESP.restart();
//         }
//         else
//         {
//             Serial.println("!!! performOTAUpdate ERROR: Update failed to finish");
//             tftPrintText("OTA ERROR[1]");
//             delay(5000);
//             res = false;
//         }
//     }
//     else
//     {
//         Serial.printf("!!! performOTAUpdate ERROR: %d\n", Update.getError());
//         tftPrintText("OTA ERROR[2]");
//         delay(5000);
//         res = false;
//     }

//     http.end();
//     return res;
// }

