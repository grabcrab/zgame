#include "gameComm.h"
#include <ArduinoJson.h>
#include <WiFi.h>
#include <HTTPClient.h>

#include "xgConfig.h"
#include "utils.h"
#include "board.h"

tGameApiRequest::tGameApiRequest()
{
    id = utilsGetDeviceID64Hex();
    role = "neutral";
    status = "wait";
}

tGameApiResponse sendDeviceData(tGameApiRequest request, String serverURL)
{
    tGameApiResponse response;
    response.success = false;
    
    if (WiFi.status() != WL_CONNECTED)
    {
        Serial.println("WiFi not connected");
        return response;
    }
    
    // Get WiFi info automatically
    String deviceIP = WiFi.localIP().toString();
    int rssi = WiFi.RSSI();
    
    // Create JSON data string
    JsonDocument jsonDoc;
    jsonDoc["id"] = request.id;
    jsonDoc["ip"] = deviceIP;
    jsonDoc["rssi"] = rssi;
    jsonDoc["role"] = request.role;
    jsonDoc["status"] = request.status;
    jsonDoc["health"] = request.health;
    jsonDoc["battery"] =  boardGetVccPercent();//request.battery;
    jsonDoc["comment"] = request.comment;
    
    String jsonString;
    serializeJson(jsonDoc, jsonString);
    
    // URL encode the JSON string for GET parameter
    String encodedJson = "";
    for (int i = 0; i < jsonString.length(); i++) {
        char c = jsonString.charAt(i);
        if (c == ' ') {
            encodedJson += "%20";
        } else if (c == '"') {
            encodedJson += "%22";
        } else if (c == '{') {
            encodedJson += "%7B";
        } else if (c == '}') {
            encodedJson += "%7D";
        } else if (c == ':') {
            encodedJson += "%3A";
        } else if (c == ',') {
            encodedJson += "%2C";
        } else {
            encodedJson += c;
        }
    }
    
    // Build complete URL with data parameter
    String fullURL = serverURL + "/api/device?data=" + encodedJson;
    
    //Serial.println("Sending GET request to: " + fullURL);
    
    HTTPClient http;
    http.begin(fullURL);
    uint32_t startMs = millis();
    int httpResponseCode = http.GET();
    response.respTimeMs = millis() - startMs;

    
    if (httpResponseCode > 0)
    {
        String responsePayload = http.getString();
        // Serial.println("HTTP Response Code: " + String(httpResponseCode));
        // Serial.println("Response: " + responsePayload);
        
        // Parse JSON response
        DynamicJsonDocument responseDoc(1024);
        DeserializationError error = deserializeJson(responseDoc, responsePayload);
        
        if (!error)
        {
            response.game_duration = responseDoc["game_duration"];
            response.game_timeout = responseDoc["game_timeout"];
            response.role = responseDoc["role"].as<String>();
            response.status = responseDoc["status"].as<String>();
            response.success = true;
        }
        else
        {
            Serial.println("Failed to parse JSON response");
        }
    }
    else
    {
        Serial.println("HTTP request failed with code: " + String(httpResponseCode));
    }
    
    http.end();
    return response;
}

tGameRole waitGame(uint16_t &preTimeoutMs, uint32_t toMs)
{
    String serverURL = ConfigAPI::getGameServerUrl();
    uint32_t startMs = millis();
    tGameApiRequest req;
    tGameRole res;
    Serial.print(">>> waitGame: ");
    if (serverURL.isEmpty())
    {
        Serial.println("NO GAME SERVER ERROR!");
        return grNone;
    }
    else 
    {
        req.print(serverURL);
    }
    while(millis() - startMs < toMs)
    {
        tGameApiResponse resp = sendDeviceData(req, serverURL);
        resp.print();
        if (resp.role != "neutral")
        {
            res = resp.getRole();
            preTimeoutMs = resp.game_timeout * 1000;
            break;
        }
        delay(R2R_INT_MS);
    }
    
    Serial.print(">>> waitGame ROLE ");
    
    Serial.println(role2str(res));
    return res;
}

// // Example usage function
// void setup() {
//   Serial.begin(115200);

//   // Connect to WiFi (replace with your credentials)
//   WiFi.begin("YOUR_SSID", "YOUR_PASSWORD");
//   while (WiFi.status() != WL_CONNECTED) {
//     delay(1000);
//     Serial.println("Connecting to WiFi...");
//   }
//   Serial.println("WiFi connected!");
//   Serial.println("IP address: " + WiFi.localIP().toString());
// }

// void loop() {
//   // Create device request structure
//   tGameApiRequest deviceData;
//   deviceData.id = "device123";
//   deviceData.role = "neutral";
//   deviceData.status = "sleep";
//   deviceData.health = 100;
//   deviceData.battery = 85;
//   deviceData.comment = "Device operational";

//   // Send request
//   String serverURL = "http://192.168.1.120:5000/api/device";
//   tGameApiResponse result = sendDeviceData(deviceData, serverURL);

//   if (result.success) {
//     Serial.println("API call successful!");
//     // Use the response data as needed
//     if (result.status == "game") {
//       Serial.println("Device is now in game mode");
//     }
//   } else {
//     Serial.println("API call failed");
//   }

//   delay(30000); // Wait 30 seconds before next call
// }