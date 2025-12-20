#include "xgConfig.h"

ConfigManager::ConfigManager() : initialized(false)
{
    setDefaults();
}

ConfigManager::~ConfigManager()
{
    if (initialized)
    {
        deinitialize();
    }
}

bool ConfigManager::initialize()
{
    if (initialized)
    {
        return true;
    }

    if (!SPIFFS.begin(false))
    {
        Serial.println("!!! ConfigManager: Failed to initialize SPIFFS");
        return false;
    }

    if (!loadFromFile())
    {
        // Serial.println("!!! ConfigManager: Failed to load config!");
        return false;
    }

    initialized = true;
    Serial.println(">>> ConfigManager: Initialized successfully");

#if (NET_CONFIG_DEINIT_SPIFFS)
    SPIFFS.end();
#endif
    return true;
}

void ConfigManager::deinitialize()
{
    if (!initialized)
    {
        return;
    }

#ifndef USE_PSRAM_FOR_CONFIG
    wifiNetworks.clear();
#endif

    initialized = false;
    Serial.println("ConfigManager: Deinitialized");
}

void ConfigManager::setDefaults()
{
#ifdef USE_PSRAM_FOR_CONFIG
    strncpy(deviceName, "BAZA_GAME", MAX_DEVICE_NAME_LEN - 1);
    deviceName[MAX_DEVICE_NAME_LEN - 1] = '\0';
    strncpy(deviceRole, "roleError", MAX_DEVICE_ROLE_LEN - 1);
    deviceRole[MAX_DEVICE_ROLE_LEN - 1] = '\0';
    isBaseStation = false;
    wifiNetworkCount = 0;
    memset(fileServerUrl, 0, MAX_SERVER_URL_LEN);
    memset(gameServerUrl, 0, MAX_SERVER_URL_LEN);
    memset(otaServerUrl, 0, MAX_SERVER_URL_LEN);
    memset(wifiNetworks, 0, sizeof(wifiNetworks));
    deviceID = 0;
#else
    deviceName = "BAZA_GAME";
    isBaseStation = false;
    wifiNetworks.clear();
    fileServerUrl = "";
    gameServerUrl = "";
    otaServerUrl = "";
#endif
}

void *ConfigManager::allocateMemory(size_t size)
{
#ifdef USE_PSRAM_FOR_CONFIG
    if (ESP.getPsramSize() > 0)
    {
        return ps_malloc(size);
    }
#endif
    return malloc(size);
}

void ConfigManager::deallocateMemory(void *ptr)
{
#ifdef USE_PSRAM_FOR_CONFIG
    if (ESP.getPsramSize() > 0)
    {
        free(ptr); // ps_malloc использует тот же free()
        return;
    }
#endif
    free(ptr);
}

bool ConfigManager::loadFromFile()
{
    if (!SPIFFS.exists(NET_CONFIG_FILE_PATH))
    {
        Serial.println("!!! ConfigManager: Config file not found");
        return false;
    }

    File file = SPIFFS.open(NET_CONFIG_FILE_PATH, "r");
    if (!file)
    {
        Serial.println("!!! ConfigManager: Failed to open config file");
        return false;
    }

    size_t fileSize = file.size();
    if (fileSize == 0)
    {
        Serial.println("!!! ConfigManager: Config file is empty");
        file.close();
        return false;
    }

    char *buffer = static_cast<char *>(allocateMemory(fileSize + 1));
    if (!buffer)
    {
        Serial.println("!!! ConfigManager: Failed to allocate memory for config");
        file.close();
        return false;
    }

    // Читаем файл
    file.readBytes(buffer, fileSize);
    buffer[fileSize] = '\0';
    file.close();

    // Парсим JSON
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, buffer);

    if (error)
    {
        Serial.printf("!!! ConfigManager: JSON parsing failed: %s\n", error.c_str());
        deallocateMemory(buffer);
        return false;
    }

#ifdef USE_PSRAM_FOR_CONFIG
    const char *devName = doc["device_name"] | "BAZA_GAME";
    strncpy(deviceName, devName, MAX_DEVICE_NAME_LEN - 1);
    deviceName[MAX_DEVICE_NAME_LEN - 1] = '\0';

    const char *devRole = doc["deviceRole"] | "roleError";
    strncpy(deviceRole, devRole, MAX_DEVICE_ROLE_LEN - 1);
    deviceRole[MAX_DEVICE_ROLE_LEN - 1] = '\0';

    deviceID = doc["deviceID"] | 1111;

    // isBaseStation = doc["base_station"] | false;

    wifiNetworkCount = 0;
    if (doc.containsKey("wifi_networks"))
    {
        JsonArray networks = doc["wifi_networks"];
        for (JsonObject network : networks)
        {
            if (wifiNetworkCount >= MAX_WIFI_NETWORKS)
                break;

            const char *ssid = network["ssid"] | "";
            const char *password = network["password"] | "";
            if (strlen(ssid) > 0)
            {
                wifiNetworks[wifiNetworkCount] = WifiNetwork(ssid, password);
                wifiNetworkCount++;
            }
        }
    }

    if (doc.containsKey("servers"))
    {
        JsonObject servers = doc["servers"];

        const char *fsUrl = servers["file_server"] | "CONFIG ERROR";
        strncpy(fileServerUrl, fsUrl, MAX_SERVER_URL_LEN - 1);
        fileServerUrl[MAX_SERVER_URL_LEN - 1] = '\0';

        const char *gsUrl = servers["game_server"] | "CONFIG ERROR";
        strncpy(gameServerUrl, gsUrl, MAX_SERVER_URL_LEN - 1);
        gameServerUrl[MAX_SERVER_URL_LEN - 1] = '\0';

        const char *otaUrl = servers["ota_server"] | "CONFIG ERROR";
        strncpy(otaServerUrl, otaUrl, MAX_SERVER_URL_LEN - 1);
        otaServerUrl[MAX_SERVER_URL_LEN - 1] = '\0';

        const char *sysUrl = servers["sys_server"] | "CONFIG ERROR";
        strncpy(sysServerUrl, sysUrl, MAX_SERVER_URL_LEN - 1);
        sysServerUrl[MAX_SERVER_URL_LEN - 1] = '\0';
    }
#else
    deviceName = doc["device_name"] | "BAZA_GAME";
    isBaseStation = doc["base_station"] | false;

    wifiNetworks.clear();
    if (doc.containsKey("wifi_networks"))
    {
        JsonArray networks = doc["wifi_networks"];
        for (JsonObject network : networks)
        {
            const char *ssid = network["ssid"] | "";
            const char *password = network["password"] | "";
            if (strlen(ssid) > 0)
            {
                wifiNetworks.emplace_back(ssid, password);
            }
        }
    }

    if (doc.containsKey("servers"))
    {
        JsonObject servers = doc["servers"];
        fileServerUrl = servers["file_server"] | "";
        gameServerUrl = servers["game_server"] | "";
        otaServerUrl = servers["ota_server"] | "";
    }
#endif

    deallocateMemory(buffer);
    Serial.println("ConfigManager: Config loaded successfully");
    return true;
}

bool ConfigManager::addWifiNetwork(const char *ssid, const char *password)
{
    if (!ssid || strlen(ssid) == 0)
    {
        return false;
    }

#ifdef USE_PSRAM_FOR_CONFIG
    if (wifiNetworkCount >= MAX_WIFI_NETWORKS)
    {
        Serial.println("ConfigManager: Maximum WiFi networks reached");
        return false;
    }

    for (size_t i = 0; i < wifiNetworkCount; i++)
    {
        if (strcmp(wifiNetworks[i].ssid, ssid) == 0)
        {
            strncpy(wifiNetworks[i].password, password ? password : "", MAX_PASS_LEN - 1);
            wifiNetworks[i].password[MAX_PASS_LEN - 1] = '\0';
            return true;
        }
    }

    wifiNetworks[wifiNetworkCount] = WifiNetwork(ssid, password);
    wifiNetworkCount++;
#else
    for (auto &network : wifiNetworks)
    {
        if (network.ssid.equals(ssid))
        {
            network.password = password ? password : "";
            return true;
        }
    }

    wifiNetworks.emplace_back(ssid, password);
#endif

    return true;
}

void ConfigManager::clearWifiNetworks()
{
#ifdef USE_PSRAM_FOR_CONFIG
    wifiNetworkCount = 0;
    memset(wifiNetworks, 0, sizeof(wifiNetworks));
#else
    wifiNetworks.clear();
#endif
}

bool ConfigManager::saveConfig() const
{
    if (!initialized)
    {
        Serial.println("ConfigManager: Not initialized");
        return false;
    }

    JsonDocument doc;

#ifdef USE_PSRAM_FOR_CONFIG
    doc["device_name"] = deviceName;
    doc["deviceRole"] = deviceRole;
    doc["deviceID"] = deviceID;

    JsonArray networks = doc["wifi_networks"].to<JsonArray>();
    for (size_t i = 0; i < wifiNetworkCount; i++)
    {
        JsonObject network = networks.add<JsonObject>();
        network["ssid"] = wifiNetworks[i].ssid;
        network["password"] = wifiNetworks[i].password;
    }

    JsonObject servers = doc["servers"].to<JsonObject>();
    servers["file_server"] = fileServerUrl;
    servers["game_server"] = gameServerUrl;
    servers["ota_server"] = otaServerUrl;
#else
    doc["device_name"] = deviceName;
    doc["base_station"] = isBaseStation;

    JsonArray networks = doc["wifi_networks"].to<JsonArray>();
    for (const auto &wifi : wifiNetworks)
    {
        JsonObject network = networks.add<JsonObject>();
        network["ssid"] = wifi.ssid;
        network["password"] = wifi.password;
    }

    JsonObject servers = doc["servers"].to<JsonObject>();
    servers["file_server"] = fileServerUrl;
    servers["game_server"] = gameServerUrl;
    servers["ota_server"] = otaServerUrl;
#endif

    File file = SPIFFS.open(NET_CONFIG_FILE_PATH, "w");
    if (!file)
    {
        Serial.println("ConfigManager: Failed to open config file for writing");
        return false;
    }

    size_t bytesWritten = serializeJsonPretty(doc, file);
    file.close();

    if (bytesWritten == 0)
    {
        Serial.println("ConfigManager: Failed to write config");
        return false;
    }

    Serial.printf("ConfigManager: Config saved (%d bytes)\n", bytesWritten);
    return true;
}

void ConfigManager::printConfig() const
{
    Serial.println("=== Configuration ===");
#ifdef USE_PSRAM_FOR_CONFIG
    Serial.printf("Device Name: %s\n", deviceName);
    Serial.printf("Device Role: %s\n", deviceRole);
    // Serial.printf("Base Station: %s\n", isBaseStation ? "Yes" : "No");

    Serial.printf("WiFi Networks (%d):\n", wifiNetworkCount);
    for (size_t i = 0; i < wifiNetworkCount; i++)
    {
        Serial.printf("  %d. SSID: %s, Pass: %s\n",
                      i + 1,
                      wifiNetworks[i].ssid,
                      strlen(wifiNetworks[i].password) == 0 ? "[empty]" : "[hidden]");
    }

    Serial.println("Servers:");
    Serial.printf("  File Server: %s\n",
                  strlen(fileServerUrl) == 0 ? "[not set]" : fileServerUrl);
    Serial.printf("  Game Server: %s\n",
                  strlen(gameServerUrl) == 0 ? "[not set]" : gameServerUrl);
    Serial.printf("  OTA Server: %s\n",
                  strlen(otaServerUrl) == 0 ? "[not set]" : otaServerUrl);
#else
    Serial.printf("Device Name: %s\n", deviceName.c_str());
    Serial.printf("Base Station: %s\n", isBaseStation ? "Yes" : "No");

    Serial.printf("WiFi Networks (%d):\n", wifiNetworks.size());
    for (size_t i = 0; i < wifiNetworks.size(); i++)
    {
        Serial.printf("  %d. SSID: %s, Pass: %s\n",
                      i + 1,
                      wifiNetworks[i].ssid.c_str(),
                      wifiNetworks[i].password.isEmpty() ? "[empty]" : "[hidden]");
    }

    Serial.println("Servers:");
    Serial.printf("  File Server: %s\n",
                  fileServerUrl.isEmpty() ? "[not set]" : fileServerUrl.c_str());
    Serial.printf("  Game Server: %s\n",
                  gameServerUrl.isEmpty() ? "[not set]" : gameServerUrl.c_str());
    Serial.printf("  OTA Server: %s\n",
                  otaServerUrl.isEmpty() ? "[not set]" : otaServerUrl.c_str());
#endif
    Serial.println("====================");
}

#ifdef USE_PSRAM_FOR_CONFIG
ConfigManager *ConfigManager::createInPSRAM()
{
    if (ESP.getPsramSize() == 0)
    {
        Serial.println("ConfigManager: PSRAM not available, using heap");
        return new ConfigManager();
    }

    void *ptr = ps_malloc(sizeof(ConfigManager));
    if (!ptr)
    {
        Serial.println("ConfigManager: Failed to allocate PSRAM, using heap");
        return new ConfigManager();
    }

    ConfigManager *instance = new (ptr) ConfigManager();
    Serial.println("ConfigManager: Instance created in PSRAM");
    return instance;
}

void ConfigManager::destroyFromPSRAM(ConfigManager *instance)
{
    if (!instance)
        return;

    instance->~ConfigManager();

    void *psramStart = (void *)0x3F800000; // Примерный адрес начала PSRAM
    void *psramEnd = (void *)((uint8_t *)psramStart + ESP.getPsramSize());

    if (instance >= psramStart && instance < psramEnd)
    {
        free(instance); // ps_malloc использует тот же free()
        Serial.println("ConfigManager: Instance destroyed from PSRAM");
    }
    else
    {
        delete instance;
        Serial.println("ConfigManager: Instance destroyed from heap");
    }
}
#endif

namespace
{
#ifdef USE_PSRAM_FOR_CONFIG
    ConfigManager *g_configInstance = nullptr;
#else
    ConfigManager *g_configInstance = nullptr;
    ConfigManager g_configObject;
#endif
    bool g_instanceCreated = false;
}

namespace ConfigAPI
{
    String discoServer = "";
    bool initialize()
    {
        if (g_instanceCreated)
        {
            Serial.println("ConfigAPI: Already initialized");
            return true;
        }

#ifdef USE_PSRAM_FOR_CONFIG
        g_configInstance = ConfigManager::createInPSRAM();
        if (!g_configInstance)
        {
            Serial.println("ConfigAPI: Failed to create instance");
            return false;
        }

        if (!g_configInstance->initialize())
        {
            ConfigManager::destroyFromPSRAM(g_configInstance);
            g_configInstance = nullptr;
            return false;
        }
#else
        g_configInstance = &g_configObject;
        if (!g_configInstance->initialize())
        {
            g_configInstance = nullptr;
            return false;
        }
#endif

        g_instanceCreated = true;
        Serial.println("ConfigAPI: Initialized successfully");
        return true;
    }

    void deinitialize()
    {
        if (!g_instanceCreated || !g_configInstance)
        {
            return;
        }

        g_configInstance->deinitialize();

#ifdef USE_PSRAM_FOR_CONFIG
        ConfigManager::destroyFromPSRAM(g_configInstance);
#endif

        g_configInstance = nullptr;
        g_instanceCreated = false;
        Serial.println("ConfigAPI: Deinitialized");
    }

    bool isInitialized()
    {
        return g_instanceCreated && g_configInstance && g_configInstance->isInitialized();
    }

    void setDiscoServer(String dS)
    {
        discoServer = dS;
    }

    String getDiscoServer(void)
    {
        return discoServer;
    }

    String replaceUrlAddress(String fullAddress)
    {
        String newAddress = discoServer;
        if (newAddress.length() == 0)
        {
            return fullAddress;
        }
        
        int protocolEndIndex = fullAddress.indexOf("://");
        if (protocolEndIndex == -1)
        {
            return fullAddress;
        }

        String protocol = fullAddress.substring(0, protocolEndIndex + 3); // Include "://"

        String remainingUrl = fullAddress.substring(protocolEndIndex + 3);
        int pathStartIndex = remainingUrl.indexOf('/');
        int portStartIndex = remainingUrl.indexOf(':');

        String pathAndQuery = "";
        
        if (portStartIndex != -1 && (pathStartIndex == -1 || portStartIndex < pathStartIndex))
        {         
            String portAndPath = remainingUrl.substring(portStartIndex);
            pathAndQuery = portAndPath;
        }
        else if (pathStartIndex != -1)
        { 
            pathAndQuery = remainingUrl.substring(pathStartIndex);
        }
        return protocol + newAddress + pathAndQuery;
    }

    String getDeviceName()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return String("BAZA_GAME");
        }
        return g_configInstance->getDeviceName();
    }

    String getDeviceRole()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return String("gamePlayer");
        }
        return g_configInstance->getDeviceRole();
    }

    uint16_t getDeviceID()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return 2222;
        }
        return g_configInstance->getDeviceID();
    }

    bool getIsBaseStation()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return false;
        }
        return g_configInstance->getIsBaseStation();
    }

    String getFileServerUrl()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return String("");
        }
        return replaceUrlAddress(g_configInstance->getFileServerUrl());
    }

    String getGameServerUrl()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return String("");
        }
        return replaceUrlAddress(g_configInstance->getGameServerUrl());
    }

    String getOTAServerUrl()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return String("");
        }
        return replaceUrlAddress(g_configInstance->getOTAServerUrl());
    }

    String getSysServerUrl()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return String("");
        }
        return replaceUrlAddress(g_configInstance->getSysServerUrl());
    }

    size_t getWifiNetworkCount()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return 0;
        }
        return g_configInstance->getWifiNetworkCount();
    }

    bool getWifiNetwork(size_t index, String &ssid, String &password)
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            ssid = "";
            password = "";
            return false;
        }
        return g_configInstance->getWifiNetwork(index, ssid, password);
    }

    bool addWifiNetwork(const char *ssid, const char *password)
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return false;
        }
        return g_configInstance->addWifiNetwork(ssid, password);
    }

    void clearWifiNetworks()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return;
        }
        g_configInstance->clearWifiNetworks();
    }

    void printConfig()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return;
        }
        g_configInstance->printConfig();
    }

    bool saveConfig()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return false;
        }
        return g_configInstance->saveConfig();
    }

    bool loadConfig()
    {
        if (!isInitialized())
        {
            Serial.println("ConfigAPI: Not initialized");
            return false;
        }
        g_configInstance->deinitialize();
        return g_configInstance->initialize();
    }

    bool isInstanceCreated()
    {
        return g_instanceCreated;
    }

    void forceCleanup()
    {
        if (g_instanceCreated)
        {
            Serial.println("ConfigAPI: Force cleanup requested");
            deinitialize();
        }
    }
}