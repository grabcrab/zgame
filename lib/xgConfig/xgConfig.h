#ifndef CONFIG_MANAGER_H
#define CONFIG_MANAGER_H

#include <Arduino.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <vector>


#ifdef USE_PSRAM_FOR_CONFIG
#define MAX_DEVICE_NAME_LEN 64
#define MAX_DEVICE_ROLE_LEN 32
#define MAX_SERVER_URL_LEN 128
#define MAX_SSID_LEN 32
#define MAX_PASS_LEN 64
#define MAX_WIFI_NETWORKS 50
#endif

#define NET_CONFIG_FILE_PATH        "/nconf.json"
#define NET_CONFIG_DEINIT_SPIFFS    (true)

struct WifiNetwork
{
#ifdef USE_PSRAM_FOR_CONFIG
    char ssid[MAX_SSID_LEN];
    char password[MAX_PASS_LEN];

    WifiNetwork()
    {
        memset(ssid, 0, MAX_SSID_LEN);
        memset(password, 0, MAX_PASS_LEN);
    }

    WifiNetwork(const char *s, const char *p)
    {
        strncpy(ssid, s ? s : "", MAX_SSID_LEN - 1);
        strncpy(password, p ? p : "", MAX_PASS_LEN - 1);
        ssid[MAX_SSID_LEN - 1] = '\0';
        password[MAX_PASS_LEN - 1] = '\0';
    }

    String getSSID() const { return String(ssid); }
    String getPassword() const { return String(password); }
#else
    String ssid;
    String password;

    WifiNetwork() = default;
    WifiNetwork(const char *s, const char *p) : ssid(s ? s : ""), password(p ? p : "") {}

    String getSSID() const { return ssid; }
    String getPassword() const { return password; }
#endif
};

class ConfigManager
{
private:
#ifdef USE_PSRAM_FOR_CONFIG
    char deviceName[MAX_DEVICE_NAME_LEN];
    char deviceRole[MAX_DEVICE_ROLE_LEN];
    bool isBaseStation;
    uint16_t deviceID;
    WifiNetwork wifiNetworks[MAX_WIFI_NETWORKS];
    size_t wifiNetworkCount;
    char fileServerUrl[MAX_SERVER_URL_LEN];
    char gameServerUrl[MAX_SERVER_URL_LEN];
    char otaServerUrl[MAX_SERVER_URL_LEN];
#else
    String deviceName;
    bool isBaseStation;
    std::vector<WifiNetwork> wifiNetworks;
    String fileServerUrl;
    String gameServerUrl;
    String otaServerUrl;
#endif

    bool initialized;
    //static const char *NET_CONFIG_FILE_PATH;
    
    bool loadFromFile();
    void setDefaults();
    void *allocateMemory(size_t size);
    void deallocateMemory(void *ptr);

public:
    ConfigManager();
    ~ConfigManager();

    bool initialize();
    void deinitialize();
    
#ifdef USE_PSRAM_FOR_CONFIG
    String getDeviceName() const { return String(deviceName); }
    String getDeviceRole() const { return String(deviceRole); }
    uint16_t getDeviceID() const { return deviceID; }
    String getFileServerUrl() const { return String(fileServerUrl); }
    String getGameServerUrl() const { return String(gameServerUrl); }
    String getOTAServerUrl() const { return String(otaServerUrl); }
    size_t getWifiNetworkCount() const { return wifiNetworkCount; }
    bool getWifiNetwork(size_t index, String &ssid, String &password) const
    {
        if (index >= wifiNetworkCount)
            return false;
        ssid = wifiNetworks[index].getSSID();
        password = wifiNetworks[index].getPassword();
        return true;
    }
#else
    const String &getDeviceName() const { return deviceName; }
    const String &getFileServerUrl() const { return fileServerUrl; }
    const String &getGameServerUrl() const { return gameServerUrl; }
    const String &getOTAServerUrl() const { return otaServerUrl; }
    size_t getWifiNetworkCount() const { return wifiNetworks.size(); }
    bool getWifiNetwork(size_t index, String &ssid, String &password) const
    {
        if (index >= wifiNetworks.size())
            return false;
        ssid = wifiNetworks[index].getSSID();
        password = wifiNetworks[index].getPassword();
        return true;
    }
#endif

    bool getIsBaseStation() const { return isBaseStation; }
    bool isInitialized() const { return initialized; }

    bool addWifiNetwork(const char *ssid, const char *password);
    void clearWifiNetworks();
    
    void printConfig() const;
    bool saveConfig() const;

#ifdef USE_PSRAM_FOR_CONFIG
    static ConfigManager *createInPSRAM();
    static void destroyFromPSRAM(ConfigManager *instance);
#endif
};

namespace ConfigAPI
{
    bool initialize();
    void deinitialize();
    bool isInitialized();

    String getDeviceName();
    String getDeviceRole();
    uint16_t getDeviceID();
    bool getIsBaseStation();
    String getFileServerUrl();
    String getGameServerUrl();
    String getOTAServerUrl();

    size_t getWifiNetworkCount();
    bool getWifiNetwork(size_t index, String &ssid, String &password);
    bool addWifiNetwork(const char *ssid, const char *password);
    void clearWifiNetworks();

    void printConfig();
    bool saveConfig();
    bool loadConfig();

    bool isInstanceCreated();
    void forceCleanup();
}

#endif // CONFIG_MANAGER_H