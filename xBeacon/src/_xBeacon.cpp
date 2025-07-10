#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include "OneButton.h"

// #include "soc/soc.h"
// #include "soc/rtc_cntl_reg.h"

#include "espRadio.h"
#include "kxtj3-1057.h"

#include "valPlayer.h"
#include "tft_utils.h"
#include "zgConfig.h"

extern void beaconJob(void);
extern void gameJob(void*);

extern void setupTFT(String textS);
extern void loopTFT(void);
extern void jobNone(void);
extern void jobServer(void);
extern void startPlayerJob(void);


void onTouchBtn(void)
{
    Serial.println("--> BUTTON");
}

void initDevice(void)
{
    zgConfigInit();
    switch(zgConfig()->DeviceRole)
    {
        case drServer:
            Serial.println(">>> SERVER ROLE");
            jobServer();
        break;

        case drPlayer:
            Serial.println(">>> PLAYER ROLE");
            startPlayerJob();
        break;

        case drNone:
            Serial.println(">>> NO ROLE");
            jobNone();
        break;
    }
}

void setup(void)
{
    Serial.begin(115200);
    //waitG0();
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, HIGH);
    setupTFT("PORTAL BEACON");
    SPIFFS.begin();
    Serial.println(">>> BOOT");

    Serial.printf("FLASH: %lu\r\n", ESP.getFlashChipSize());
    Serial.printf("PSRAM: %lu\r\n", ESP.getPsramSize());

    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 4000000);

    prepareWiFi();
    espInitRxTx(grApPortalBeacon, false);

    Serial.println(">>>>>>>>>");
    tftPrintThreeLines("AP", "PORTAL", "BEACON", TFT_BLACK, TFT_GREEN);    
}

static uint32_t lastTxMs = 0;
uint32_t packCount = 0;

void loopTx(void)
{
    if (millis() - lastTxMs < 50)
        return;
    lastTxMs = millis();
    espProcessTx();
    packCount++;
}

void loopStatus(void)
{
    static uint32_t lastPrintedMs = 0;
    if (millis() - lastPrintedMs < 5000)
        return;
    lastPrintedMs = millis();
    Serial.println(packCount);
}

void loop(void)
{
    delay(1);    
    loopStatus();
    loopTx();
}
