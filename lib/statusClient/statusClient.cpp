#include "statusClient.h"
#include "board.h"

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>

// ============== Internal State ==============
static char _deviceName[33] = {0};
static char _serverIP[64] = {0};
static char _gameStatus[STATUS_GAME_STATUS_MAX_LEN + 1] = "BOOT";
static DeviceStatus_t _deviceStatus = DEVICE_STATUS_OPERATION;
static volatile bool _running = false;
static TaskHandle_t _taskHandle = NULL;
static SemaphoreHandle_t _mutex = NULL;
static bool doUpdate = false;

// Accelerometer activity tracking
static float _accelSamples[100][3];  // Store last N samples [x,y,z]
static int _accelSampleIndex = 0;
static int _accelSampleCount = 0;
static uint8_t _accelActivity = 1;   // Current activity level 1-100
static unsigned long _lastAccelSample = 0;
static SemaphoreHandle_t _accelMutex = NULL;

//misc
volatile bool statusClientSuspended = false;

// ============== Forward Declarations ==============
static void statusClientTask(void* parameter);
static bool sendStatusUpdate(void);
static DeviceCommand_t checkForCommand(const String& response);
static void processCommand(DeviceCommand_t cmd);
static String getDeviceStatusString(DeviceStatus_t status);
static uint8_t calculateAccelActivity(void);

// ============== Public Functions ==============

bool statusClientInit(const char* deviceName, const char* serverIP)
{
    if (deviceName == NULL || serverIP == NULL)
    {
        Serial.println("!!! statusClientInit: NULL parameters");
        return false;
    }
    
    // Create mutexes
    if (_mutex == NULL)
    {
        _mutex = xSemaphoreCreateMutex();
        if (_mutex == NULL)
        {
            Serial.println("!!! statusClientInit: Failed to create mutex");
            return false;
        }
    }
    
    if (_accelMutex == NULL)
    {
        _accelMutex = xSemaphoreCreateMutex();
        if (_accelMutex == NULL)
        {
            Serial.println("!!! statusClientInit: Failed to create accel mutex");
            return false;
        }
    }
    
    // Copy device name (truncate if needed)
    strncpy(_deviceName, deviceName, 32);
    _deviceName[32] = '\0';
    
    // Copy server IP
    strncpy(_serverIP, serverIP, 63);
    _serverIP[63] = '\0';
    
    Serial.printf(">>> statusClientInit: device=<%s> server=<%s>\n", _deviceName, _serverIP);
    return statusClientStart();
}

bool statusClientStart(void)
{
    if (_running)
    {
        Serial.println(">>> statusClientStart: Already running");
        return true;
    }
    
    if (WiFi.status() != WL_CONNECTED)
    {
        Serial.println("!!! statusClientStart: WiFi not connected");
        return false;
    }
    
    if (strlen(_serverIP) == 0)
    {
        Serial.println("!!! statusClientStart: Not initialized");
        return false;
    }
    
    _running = true;
    
    // Create the status client task
    BaseType_t result = xTaskCreatePinnedToCore(
        statusClientTask,       // Task function
        "StatusClient",         // Task name
        4096,                   // Stack size
        NULL,                   // Parameters
        1,                      // Priority (low)
        &_taskHandle,           // Task handle
        0                       // Core 0 (leave core 1 for main app)
    );
    
    if (result != pdPASS)
    {
        Serial.println("!!! statusClientStart: Failed to create task");
        _running = false;
        return false;
    }
    
    Serial.println(">>> statusClientStart: Task started");
    return true;
}

void statusClientStop(void)
{
    if (!_running)
    {
        return;
    }
    
    _running = false;
    
    // Wait for task to finish
    if (_taskHandle != NULL)
    {
        vTaskDelay(pdMS_TO_TICKS(100));
        vTaskDelete(_taskHandle);
        _taskHandle = NULL;
    }
    
    Serial.println(">>> statusClientStop: Stopped");
}

void statusClientSetGameStatus(const char* status)
{
    if (status == NULL || _mutex == NULL)
    {
        return;
    }
    
    if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(100)) == pdTRUE)
    {
        strncpy(_gameStatus, status, STATUS_GAME_STATUS_MAX_LEN);
        _gameStatus[STATUS_GAME_STATUS_MAX_LEN] = '\0';
        doUpdate = true;
        xSemaphoreGive(_mutex);
        delay(250);
    }
}

void statusClientSetDeviceStatus(DeviceStatus_t status)
{
    if (_mutex == NULL)
    {
        return;
    }
    
    if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(100)) == pdTRUE)
    {
        _deviceStatus = status;
        xSemaphoreGive(_mutex);
    }
}

bool statusClientIsRunning(void)
{
    return _running;
}

uint8_t statusClientGetAccelActivity(void)
{
    return _accelActivity;
}

void statusClientFeedAccelData(float x, float y, float z)
{
    if (_accelMutex == NULL)
    {
        return;
    }
    
    if (xSemaphoreTake(_accelMutex, pdMS_TO_TICKS(10)) == pdTRUE)
    {
        // Store sample in circular buffer
        _accelSamples[_accelSampleIndex][0] = x;
        _accelSamples[_accelSampleIndex][1] = y;
        _accelSamples[_accelSampleIndex][2] = z;
        
        _accelSampleIndex = (_accelSampleIndex + 1) % 100;
        if (_accelSampleCount < 100)
        {
            _accelSampleCount++;
        }
        
        _lastAccelSample = millis();
        xSemaphoreGive(_accelMutex);
    }
}

// ============== Internal Functions ==============

static void statusClientTask(void* parameter)
{
    Serial.println(">>> StatusClient task running");
    
    unsigned long lastUpdate = 0;
    
    while (_running)
    {
        // Check WiFi connection
        if (WiFi.status() != WL_CONNECTED)
        {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }
        
        // Update accelerometer activity level
        _accelActivity = calculateAccelActivity();
        
        // Time to send status update?
        unsigned long now = millis();
        if ((now - lastUpdate >= STATUS_UPDATE_INTERVAL_MS) || (doUpdate))
        {
            lastUpdate = now;
            if (doUpdate) doUpdate = false;
            if (!sendStatusUpdate())
            {
                Serial.println("!!! StatusClient: Failed to send update");
            }
        }
        
        vTaskDelay(pdMS_TO_TICKS(100));  // Small delay to prevent tight loop
        while (statusClientSuspended)
        {
            delay(100);
        }
    }
    
    Serial.println(">>> StatusClient task exiting");
    vTaskDelete(NULL);
}

static bool sendStatusUpdate(void)
{
    HTTPClient http;
    
    // Build URL
    String url = "http://";
    url += _serverIP;
    url += ":";
    url += STATUS_SERVER_PORT;
    url += "/status";
    
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(5000);  // 5 second timeout
    
    // Build JSON payload
    StaticJsonDocument<512> doc;
    
    // Get MAC address
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char macStr[18];
    snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    
    // Thread-safe read of status values
    char gameStatusCopy[STATUS_GAME_STATUS_MAX_LEN + 1];
    DeviceStatus_t deviceStatusCopy;
    
    if (xSemaphoreTake(_mutex, pdMS_TO_TICKS(100)) == pdTRUE)
    {
        strcpy(gameStatusCopy, _gameStatus);
        deviceStatusCopy = _deviceStatus;
        xSemaphoreGive(_mutex);
    }
    else
    {
        strcpy(gameStatusCopy, "UNKNOWN");
        deviceStatusCopy = DEVICE_STATUS_OPERATION;
    }
    
    // Populate JSON
    doc["mac"] = macStr;
    doc["name"] = _deviceName;
    doc["ip"] = WiFi.localIP().toString();
    doc["ssid"] = WiFi.SSID();
    doc["rssi"] = WiFi.RSSI();
    doc["uptime"] = millis() / 1000;
    doc["battery_mv"] = boardGetVcc();
    doc["battery_pct"] = boardGetVccPercent();
    doc["accel_activity"] = _accelActivity;
    doc["device_status"] = getDeviceStatusString(deviceStatusCopy);
    doc["game_status"] = gameStatusCopy;
    doc["free_heap"] = ESP.getFreeHeap();
    doc["max_alloc_heap"] = ESP.getMaxAllocHeap();
    
    String payload;
    serializeJson(doc, payload);
    
    // Send POST request
    int httpCode = http.POST(payload);
    
    if (httpCode > 0)
    {
        if (httpCode == HTTP_CODE_OK)
        {
            String response = http.getString();
            
            // Check for command in response
            DeviceCommand_t cmd = checkForCommand(response);
            if (cmd != CMD_NONE)
            {
                processCommand(cmd);
            }
            
            http.end();
            return true;
        }
        else
        {
            Serial.printf("!!! StatusClient: HTTP error %d\n", httpCode);
        }
    }
    else
    {
        Serial.printf("!!! StatusClient: Connection failed: %s\n", http.errorToString(httpCode).c_str());
    }
    
    http.end();
    return false;
}

static DeviceCommand_t checkForCommand(const String& response)
{
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, response);
    
    if (error)
    {
        return CMD_NONE;
    }
    
    if (!doc.containsKey("command"))
    {
        return CMD_NONE;
    }
    
    const char* cmd = doc["command"];
    
    if (strcmp(cmd, "reboot") == 0)
    {
        return CMD_REBOOT;
    }
    else if (strcmp(cmd, "sleep") == 0)
    {
        return CMD_SLEEP;
    }
    
    return CMD_NONE;
}

static void processCommand(DeviceCommand_t cmd)
{
    Serial.printf(">>> StatusClient: Processing command %d\n", cmd);
    
    switch (cmd)
    {
        case CMD_REBOOT:
        {
            Serial.println(">>> StatusClient: REBOOT command received");
            
            // Update status on server first
            statusClientSetDeviceStatus(DEVICE_STATUS_REBOOT);
            sendStatusUpdate();
            
            delay(500);
            ESP.restart();
            break;
        }
        
        case CMD_SLEEP:
        {
            Serial.println(">>> StatusClient: SLEEP command received");
            
            // Update status on server first
            statusClientSetDeviceStatus(DEVICE_STATUS_SLEEP);
            sendStatusUpdate();
            
            delay(500);
            
            // Stop the status client
            _running = false;
            
            // Start sleep (using existing board function)
            boardStartSleep(true, true);
            break;
        }
        
        default:
            break;
    }
}

static String getDeviceStatusString(DeviceStatus_t status)
{
    switch (status)
    {
        case DEVICE_STATUS_OPERATION:
            return "OPERATION";
        case DEVICE_STATUS_SLEEP:
            return "SLEEP";
        case DEVICE_STATUS_REBOOT:
            return "REBOOT";
        default:
            return "UNKNOWN";
    }
}

static uint8_t calculateAccelActivity(void)
{
    if (_accelMutex == NULL || _accelSampleCount < 2)
    {
        return 1;  // Minimum activity if no data
    }
    
    if (xSemaphoreTake(_accelMutex, pdMS_TO_TICKS(50)) != pdTRUE)
    {
        return _accelActivity;  // Return last known value
    }
    
    // Calculate activity based on variance/movement in samples
    float sumDelta = 0.0f;
    
    for (int i = 1; i < _accelSampleCount; i++)
    {
        int prevIdx = (i - 1) % 100;
        int currIdx = i % 100;
        
        float dx = _accelSamples[currIdx][0] - _accelSamples[prevIdx][0];
        float dy = _accelSamples[currIdx][1] - _accelSamples[prevIdx][1];
        float dz = _accelSamples[currIdx][2] - _accelSamples[prevIdx][2];
        
        // Sum of absolute deltas
        sumDelta += fabsf(dx) + fabsf(dy) + fabsf(dz);
    }
    
    // Normalize to 1-100 range
    // Assuming typical movement produces delta sum of 0-10g cumulative
    float avgDelta = sumDelta / (_accelSampleCount - 1);
    
    // Scale: 0g = 1, 1g average delta = 100
    int activity = (int)(avgDelta * 100.0f) + 1;
    
    // Clamp to 1-100
    if (activity < 1) activity = 1;
    if (activity > 100) activity = 100;
    
    xSemaphoreGive(_accelMutex);
    
    return (uint8_t)activity;
}

void statusClientPause(void)
{
    delay(500); //to let the next activity start
    statusClientSuspended = true;
}

void statusClientResume(void)
{
    statusClientSuspended = false;    
    delay(150);
}
