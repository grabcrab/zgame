#include "__main.h"
#include "wifiUtils.h"
#include "espRadio.h"

uint8_t wifiChannel = DEF_WIFI_CHANNEL;

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
    wifiInit(DEF_SSID, DEF_PASS, wifiChannel);
    wifiMaxPower();
    return netWait(toMs);
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
        if (wifiIsConnected())
        {
            Serial.println(">>> netWait: CONNECTED");
            return true;
        }
    }
    return false;
}