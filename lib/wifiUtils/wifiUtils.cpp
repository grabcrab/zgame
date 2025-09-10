#include "wifiUtils.h"

#include <HTTPClient.h>
#include <Preferences.h>
#include <esp_wifi.h>

////////////////////////////////
String wifiSsid = "";
String wifiPass = "";
bool wifiConnected = false;
bool wifiInternetConnected = false;

unsigned long lastPingedGoogleMs = 0;
unsigned long lastSyncTimeMs = 0;
////////////////////////////////
bool wifiIsConnected(void)
{
    return WiFi.isConnected();
}
////////////////////////////////
void wifiUnhandled_evt(WiFiEvent_t event)
{
    // Serial.printf("[WiFi-event] event: %d\n", event);

    switch (event)
    {
    case SYSTEM_EVENT_STA_CONNECTED:
        wifiStationConnected_evt(event);
        break;

    case SYSTEM_EVENT_WIFI_READY:
        Serial.println("WiFi interface ready");
        break;
    case SYSTEM_EVENT_SCAN_DONE:
        Serial.println("Completed scan for access points");
        break;
    case SYSTEM_EVENT_STA_START:
        Serial.println("WiFi client started");
        break;
    case SYSTEM_EVENT_STA_STOP:
        Serial.println("WiFi clients stopped");
        wifiConnected = false;
        wifiInternetConnected = false;
        break;
    case SYSTEM_EVENT_STA_AUTHMODE_CHANGE:
        Serial.println("Authentication mode of access point has changed");
        break;
    case SYSTEM_EVENT_STA_GOT_IP:
        wifiGotIP_evt(event);
        break;
    case SYSTEM_EVENT_STA_LOST_IP:
        Serial.println("Lost IP address and IP address is reset to 0");
        wifiConnected = false;
        wifiInternetConnected = false;
        break;
    case SYSTEM_EVENT_STA_WPS_ER_SUCCESS:
        Serial.println("WiFi Protected Setup (WPS): succeeded in enrollee mode");
        break;
    case SYSTEM_EVENT_STA_WPS_ER_FAILED:
        Serial.println("WiFi Protected Setup (WPS): failed in enrollee mode");
        break;
    case SYSTEM_EVENT_STA_WPS_ER_TIMEOUT:
        Serial.println("WiFi Protected Setup (WPS): timeout in enrollee mode");
        break;
    case SYSTEM_EVENT_STA_WPS_ER_PIN:
        Serial.println("WiFi Protected Setup (WPS): pin code in enrollee mode");
        break;
    case SYSTEM_EVENT_AP_START:
        Serial.println("WiFi access point started");
        break;
    case SYSTEM_EVENT_AP_STOP:
        Serial.println("WiFi access point  stopped");
        break;
    case SYSTEM_EVENT_AP_STACONNECTED:
        Serial.println("Client connected");
        break;
    case SYSTEM_EVENT_AP_STADISCONNECTED:
        Serial.println("Client disconnected");
        break;
    case SYSTEM_EVENT_AP_STAIPASSIGNED:
        Serial.println("Assigned IP address to client");
        break;
    case SYSTEM_EVENT_AP_PROBEREQRECVED:
        Serial.println("Received probe request");
        break;
    case SYSTEM_EVENT_GOT_IP6:
        Serial.println("IPv6 is preferred");
        break;
    case SYSTEM_EVENT_STA_DISCONNECTED:
        wifiStationDisconnected_evt(event);
        break;

    } // switch
} // void wifiUnhandled_evt(WiFiEvent_t event)
////////////////////////////////////////////
void wifiStationConnected_evt(WiFiEvent_t event)
{
    Serial.println("Connected to AP successfully!");
} // void wifiStationConnected(WiFiEvent_t event, WiFiEventInfo_t info)
////////////////////////////////////////////
void wifiGotIP_evt(WiFiEvent_t event)
{
    Serial.print("WiFi connected. IP address: ");
    Serial.print(WiFi.localIP().toString().c_str());
    Serial.print(" SSID: ");
    Serial.print(WiFi.SSID());
    Serial.print(" RSSI: ");
    Serial.println(WiFi.RSSI());
    delay(50);
    wifiConnected = true;
    // wifiInternetConnected =

    //  CURRENT_WIFI_SSID = WiFi.SSID();
    //  CURRENT_WIFI_PASS = WiFi.psk();

} // void wifiGotIP(WiFiEvent_t event, WiFiEventInfo_t info)
////////////////////////////////////////////
void wifiStationDisconnected_evt(WiFiEvent_t event)
{
    Serial.println("Disconnected from WiFi access point");
    Serial.println(String("WiFi lost connection. Trying to Reconnect: ") + wifiSsid + " " + wifiPass);
    wifiConnected = false;
    wifiInternetConnected = false;

    WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
} // void wifiStationDisconnected(WiFiEvent_t event, WiFiEventInfo_t info)
////////////////////////////////////////////////////////////
void wifiInit(String ssid, String pass, uint8_t wifiChannel)
{
    wifiSsid = ssid;
    wifiPass = pass;

    // WiFi.disconnect(true);

    delay(100);

    WiFi.onEvent(wifiUnhandled_evt);
    // WiFi.onEvent(wifiStationConnected_evt,  SYSTEM_EVENT_STA_CONNECTED);
    // WiFi.onEvent(wifiGotIP_evt, SYSTEM_EVENT_STA_GOT_IP);
    // WiFi.onEvent(wifiStationDisconnected_evt, SYSTEM_EVENT_STA_DISCONNECTED);
    // WiFi.channel(wifiChannel);
    // esp_wifi_set_channel(wifiChannel, WIFI_SECOND_CHAN_NONE);
    WiFi.begin(wifiSsid.c_str(), wifiSsid.c_str()); //, wifiChannel

} // bool wifiInit(void)
////////////////////////////////////////////
String wifiGetString(String fileLink)
{
    HTTPClient http;

    String payload = "0";

    http.begin(fileLink);
    int httpCode = http.GET();
    if (httpCode > 0)
    {
        if (httpCode == HTTP_CODE_OK)
        {
            payload = http.getString();
            return payload;
        }
        else
        {
            Serial.println(String("wifiGetString failed[1], error code = ") + httpCode + " URL = " + fileLink);
            return "";
        }
    }
    Serial.println(String("wifiGetString failed[2], error code = ") + httpCode + " URL = " + fileLink);
    return "";
}
///////////////////////////////////////
// time_t wifiSyncTimeBase(String sNtp)
// {
//   WiFiUDP ntpUDP;
//   NTPClient timeClient(ntpUDP, sNtp.c_str(), 0);

//   timeClient.begin();
//   if (!timeClient.update()) return 0;

//   Serial.printf("Time sync over Wi-Fi [%s]. %s\n", sNtp.c_str(), timeClient.getFormattedTime().c_str());

//   return timeClient.getEpochTime();

// }
///////////////////////////////////////
// bool wifiSyncTime(String sNtp1, String sNtp2, String sNtp3)
// {
//   time_t epochTime = 0;

//   Serial.print("wifiSyncTime: ");

//   if (!wifiIsConnected())
//     {
//       Serial.println("connect to Wi-Fi firstr!!!");
//       return false;
//     }

//   Serial.print("[1]");
//   epochTime =  wifiSyncTimeBase(sNtp1);

//   if (!epochTime)
//     {
//       Serial.print("[2]");
//       epochTime =  wifiSyncTimeBase(sNtp2);
//     }

//   if (!epochTime)
//     {
//       Serial.print("[3]");
//       epochTime =  wifiSyncTimeBase(sNtp2);
//     }

//   if (!epochTime)
//    {
//       Serial.println(" error!!!");
//       return false;
//    }

//   tRtcSyncResult res = extRtcSyncTimeFromSource(epochTime, rtcSyncSourceFromNTP);
//   if (res == rtcSyncResUpdated)
//    {
//     Serial.println("Internal RTC updated.");
//    }
//   else
//    extRtcSyncTimeIfValid();
//   return true;
// }
///////////////////////////////////////
int8_t wifiGetRSSI(void)
{
    return WiFi.RSSI();
}
///////////////////////////////////////
uint8_t wifiGetSSPercents(void)
{
    int8_t dBm = wifiGetRSSI();

    if (!dBm)
        return 0;

    if (dBm <= -100)
        return 0;
    else if (dBm >= -50)
        return 100;

    return 2 * (dBm + 100);
}
///////////////////////////////////////
String wifiGetIP(void)
{
    return WiFi.localIP().toString();
}
///////////////////////////////////////
void wifiDisconnect(void)
{
    WiFi.disconnect(true);
}
///////////////////////////////////////
bool wifiWaitConnection(uint32_t timeoutMs)
{
    unsigned long m = millis();

    while (millis() - m < timeoutMs)
        if (wifiIsConnected())
        {
            return true;
        }
        else
            delay(50);
    return false;
}
/////////////////////
String wifiGetTimeString(String url)
{
    String res = wifiGetString(url);
    return res;
}
/////////////////////
void getWiFiCredentials(String &ssid, String &pass, bool &localNet)
{
    Preferences prefs;
    prefs.begin("wifi");
    ssid = prefs.getString("ssid", "spollardemo");
    pass = prefs.getString("pass", "spollardpro");
    localNet = prefs.getBool("local", true);
    prefs.end();
}

void setWiFiCredentials(String ssid, String pass, bool localNet)
{
    Preferences prefs;
    prefs.begin("wifi");
    prefs.putString("ssid", ssid);
    prefs.putString("pass", pass);
    prefs.putBool("local", localNet);
    prefs.end();
}

void setWiFiToLocal(bool localNet)
{
    Preferences prefs;
    prefs.begin("wifi");
    prefs.putBool("local", localNet);
    prefs.end();
}

void wifiMaxPower(void)
{
    WiFi.setTxPower(WIFI_POWER_19_5dBm);
    int8_t power;
    esp_wifi_get_max_tx_power(&power);
    Serial.println(">>> wifiMaxPower: " + String(power / 4.0) + " dBm");
}

bool wifiGetDisco(IPAddress &server)
{
    WiFiUDP udp;    
    const uint16_t DISCO_PORT = 4210; // arbitrary free port
    const char DISCO_MAGIC[] = "ESP32-LOOK";
    udp.begin(DISCO_PORT);

    IPAddress broadcast(255, 255, 255, 255);
    udp.beginPacket(broadcast, DISCO_PORT);
    udp.write((uint8_t *)DISCO_MAGIC, strlen(DISCO_MAGIC));
    udp.endPacket();

    uint32_t start = millis();
    while (millis() - start < 300)
    { 
        int len = udp.parsePacket();
        if (len >= 7)
        { // expect “192.x.x.x”
            char buf[16] = {0};
            udp.read(buf, sizeof(buf) - 1);            
            if (server.fromString(buf))
            {
                Serial.print(">>> wifiGetDisco: server found at ");
                Serial.println(server);
                return true;
            }
        }
    }
    Serial.println(">>> wifiGetDisco: NO SERVER FOUND");
    return false;
}
