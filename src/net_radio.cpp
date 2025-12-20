#include "__main.h"
#include "wifiUtils.h"
#include "espRadio.h"
#include "wifiAuto.h"

uint8_t wifiChannel = ESP_WIFI_CHANNEL;

static void netPrint(void)
{
    Serial.print(">>> netConnect: ");
    Serial.println(DEF_SSID);
}

bool netConnect(uint16_t toMs)
{
    netPrint();
    delay(10);
    prepareWiFi();
    /// wifiInit(DEF_SSID, DEF_PASS, wifiChannel);
    if (!WiFiAutoConnect::begin(toMs))
    {
        Serial.println("WiFi start failed");
        return false;
    }
    else
    {
        Serial.printf("Started, current AP: %s\n",
                      WiFiAutoConnect::currentSSID().c_str());        
    }
    wifiMaxPower();
    netWait(toMs);
    return true;
}
void radioConnect(void)
{
    prepareWiFi();
    rssiReaderInit();
    wifiMaxPower();
    initRadio();
}

bool netWait(uint16_t toMs)
{
    uint32_t startMs = millis();
    while (millis() - startMs < toMs)
    {
        if (WiFiAutoConnect::maintain(toMs+1))
        {
            Serial.println(">>> netWait: CONNECTED");
            return true;
        }
        delay(10);
    }
    return false;
}