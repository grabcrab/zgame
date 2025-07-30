#include "wifiAuto.h"
#include <esp_event.h>

static WiFiMulti wifiMulti;
static bool wasAdded = false;
static bool isConnected = false;
static bool wasConnected = false;
static bool wasIP = false;

static void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info)
{
    switch (event)
    {
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
        if (isConnected)
        {
            Serial.println("!!! WiFiAuto: Lost connection!");
            isConnected = false;
            wasIP = false;
        }
        if (WIFI_AUTO_RECONNECT)
        {
            WiFi.reconnect();
        }
        break;

    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
        if (!isConnected)
        {
            Serial.printf(">>> WiFiAuto: Connected to %s (ch=%d, rssi=%d)\n",
                      info.wifi_sta_connected.ssid,
                      info.wifi_sta_connected.channel,
                      WiFi.RSSI());
            isConnected = true;
            wasConnected = true;    
        }
        
        break;

    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
        if (!wasIP)
        {
            wasIP = true;
            Serial.printf(">>> WiFiAuto: Got IP: %s\n", WiFi.localIP().toString().c_str());
            break;
        }

    default:
        break;
    }
}

bool WiFiAutoConnect::begin(uint32_t toMs)
{
    if (ConfigAPI::isInitialized() == false)
    {
        Serial.println("!!! WiFiAuto: Config not ready");
        return false;
    }

    WiFi.disconnect(true);
    WiFi.onEvent(onWiFiEvent);    

    size_t netCnt = ConfigAPI::getWifiNetworkCount();
    if (netCnt == 0)
    {
        Serial.println("!!! WiFiAuto: No WiFi networks in config");
        return false;
    }

    if (!wasAdded)
    {
        Serial.printf(">>> WiFiAuto: Adding %d networks:\r\n", netCnt);
        for (size_t i = 0; i < netCnt; ++i)
        {
            String ssid, pass;
            if (ConfigAPI::getWifiNetwork(i, ssid, pass))
            {
                wifiMulti.addAP(ssid.c_str(), pass.c_str());
                Serial.printf("\t#%d: %s\n", i, ssid.c_str());
            }
        }
        wasAdded = true;
    }

    Serial.printf(">>> WiFiAuto: (Re) Starting WiFiMulti, %d ms\r\n", toMs);
    return wifiMulti.run(toMs) == WL_CONNECTED;
}

bool WiFiAutoConnect::isConnected(void)
{
    return WiFi.isConnected();
}

String WiFiAutoConnect::currentSSID(void)
{
    return WiFi.isConnected() ? WiFi.SSID() : String();
}

void WiFiAutoConnect::disconnect(void)
{
    WiFi.disconnect(true);
}

bool WiFiAutoConnect::maintain(uint32_t toMs)
{
    if (isConnected())
    {
        return true;
    }
    if (WIFI_AUTO_RECONNECT)
    {
        if (!wasConnected)
        {
            return begin(toMs);
        }
        return false;
    }
    return begin(toMs);
}
