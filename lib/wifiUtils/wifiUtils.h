#ifndef __WIFI_UTILS__
#define __WIFI_UTILS__

#include <Arduino.h>
#include <WiFi.h>

#define WIFI_GOOGLE_PING_INTERVAL_MS    30000
#define WIFI_TIME_SYNC_INTERVAL_MS      120000
#define WIFI_MAX_TIME_SYNC_ATTEMPTS     3

void wifiStationConnected_evt(WiFiEvent_t event);
void wifiGotIP_evt(WiFiEvent_t event);
void wifiStationDisconnected_evt(WiFiEvent_t event);

void wifiInit(String ssid, String pass, uint8_t wifiChannel);
bool wifiIsConnected(void);
String wifiGetString(String fileLink);

//bool wifiSyncTime(String sNtp1 = WIFI_DEF_NTP1_ADDR, String sNtp2 = WIFI_DEF_NTP2_ADDR, String sNtp3 = WIFI_DEF_NTP3_ADDR);

int8_t  wifiGetRSSI(void);
uint8_t wifiGetSSPercents(void);
String  wifiGetIP(void);
void wifiDisconnect(void);
bool wifiWaitConnection(uint32_t timeoutMs = 30000);

String wifiGetTimeString(String url);
void getWiFiCredentials(String &ssid, String &pass, bool &localNet);
void setWiFiCredentials(String ssid, String pass, bool localNet);
void setWiFiToLocal(bool localNet);
void wifiMaxPower(void);
bool wifiGetDisco(IPAddress &server);


#endif
