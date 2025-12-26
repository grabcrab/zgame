#include "gameComm.h"
#include <ArduinoJson.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>

#include "xgConfig.h"
#include "utils.h"
#include "board.h"
#include "statusClient.h"

static SemaphoreHandle_t gameApiMutex = NULL;
static TaskHandle_t gameApiTaskHandle = NULL;

static tGameApiResponse cachedResponse;
static bool hasNewResult = false;

static String currentRole = "";
static String currentStatus = "";
static int currentHealth = 0;

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
    jsonDoc["id"] = statusClientGetName();//request.id;
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
    statusClientSetGameStatus("GAME WAIT");
    if (serverURL.isEmpty())
    {
        Serial.println("NO GAME SERVER ERROR!");    
        statusClientSetGameStatus("NO SERVER");    
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
        if (!resp.success)
        {
            Serial.println("*** SERVER IS OFFLINE");
            statusClientSetGameStatus("OFFLINE_HAT");    
            delay(5000);
            continue;
        }

        if (resp.role != "neutral")
        {
            res = resp.getRole();
            preTimeoutMs = resp.game_timeout * 1000;
            break;
        }
        delay(R2R_INT_MS);
    }
    
    Serial.print(">>> waitGame ROLE: ");
    
    Serial.println(role2str(res));
    return res;
}

// tGameApiResponse updateGameStep(String role_, String status_, int health_)
// {
//     String serverURL = ConfigAPI::getGameServerUrl();
//     tGameApiRequest req;
//     req.role = role_;
//     req.status = status_;
//     req.health = health_;
//     return sendDeviceData(req, serverURL);    
// }

// Background task
static void gameApiTask(void* pvParameters)
{
    while (true)
    {
        String serverURL = ConfigAPI::getGameServerUrl();
        tGameApiRequest req;
        
        // Get current params
        if (xSemaphoreTake(gameApiMutex, portMAX_DELAY))
        {
            req.role = currentRole;
            req.status = currentStatus;
            req.health = currentHealth;
            xSemaphoreGive(gameApiMutex);
        }
        
        // Send request (blocking, but in separate task)
        tGameApiResponse resp = sendDeviceData(req, serverURL);
        
        // Store result
        if (xSemaphoreTake(gameApiMutex, portMAX_DELAY))
        {
            cachedResponse = resp;
            if (resp.success)
            {
                hasNewResult = true;
            }
            xSemaphoreGive(gameApiMutex);
        }
        
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

// Call once at startup
void gameApiAsyncInit(void)
{
    Serial.println(">>> gameApiAsyncInit");
    if (gameApiMutex == NULL)
    {
        gameApiMutex = xSemaphoreCreateMutex();
    }
    
    if (gameApiTaskHandle == NULL)
    {
        xTaskCreate(
            gameApiTask,
            "GameAPI",
            4096,  // stack size, adjust if needed
            NULL,
            1,     // priority
            &gameApiTaskHandle
        );
    }
}

// Non-blocking call - updates params and returns latest result
tGameApiResponse updateGameStep(String role_, String status_, int health_)
{
    tGameApiResponse result;
    result.success = false;
    
    if (gameApiMutex == NULL)
    {
        Serial.println("!!! updateGameStep: semaphore not created !!!");
        return result;
    }
    
    if (xSemaphoreTake(gameApiMutex, pdMS_TO_TICKS(10)))
    {
        // Update request params for next cycle
        currentRole = role_;
        currentStatus = status_;
        currentHealth = health_;
        
        // Return cached response
        result = cachedResponse;
        
        // success = true only if new data since last call
        result.success = hasNewResult;
        hasNewResult = false;
        
        xSemaphoreGive(gameApiMutex);
    }
    else 
    {
        Serial.println("!!! updateGameStep: semaphore error !!!");
    }
    
    return result;
}

// Optional: stop the task
void gameApiAsyncStop(void)
{
    Serial.println(">>> gameApiAsyncStop");
    if (gameApiTaskHandle != NULL)
    {
        vTaskDelete(gameApiTaskHandle);
        gameApiTaskHandle = NULL;
    }
}