#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_adc_cal.h>

#include "espRadio.h"
#include "espRx.h"
#include "espScanRecords.h"
#include "tcu_board.h"
#include "utils.h"
#include "tft_utils.h"
#include "../pin_config.h"

#include "gameEngine.h"
#include "deviceRecords.h"
#include "webPortalBase.h"

RTC_DATA_ATTR bool inDeepSleep = false;

tGameRecord gameRecord;

extern void updateCurrHitPoints(tGameRecord *gameRec);

uint16_t getVcc(void)
{
    esp_adc_cal_characteristics_t adc_chars;

    // Get the internal calibration value of the chip
    esp_adc_cal_value_t val_type = esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_11, ADC_WIDTH_BIT_12, 1100, &adc_chars);
    uint32_t raw = analogRead(PIN_BAT_VOLT);
    uint32_t v1 = esp_adc_cal_raw_to_voltage(raw, &adc_chars) * 2; 
    return v1;
}

void toSleep(void)
{
    inDeepSleep = true;
    uint64_t sleepTime_us = (uint64_t)1000000 * 10;//(uint64_t)24 * (uint64_t)60 * (uint64_t)60 * (uint64_t)1000000;
    tftSleep();
    delay(3000);
    //esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0);
    delay(1);
    esp_deep_sleep(sleepTime_us);
}

unsigned long buttonPressedMs = 0;
void checkBtn(void)
{
    return;
    pinMode(0, INPUT_PULLUP);
    delay(10);
    if (digitalRead(0) == LOW)
    {
        if (buttonPressedMs)
        {
            if (millis() - buttonPressedMs > 5000)
            {
                tftSleepScreen();
                while(digitalRead(0) == LOW) delay(1);                
                delay(500);
                toSleep();
            }
        }
        else 
            buttonPressedMs = millis();
    }
    else 
        buttonPressedMs = 0;
}

void onBoot(void)
{
    return;
    //if (!inDeepSleep) return;
    pinMode(0, INPUT_PULLUP);
    delay(10);
    //if (digitalRead(0) == LOW)
    {
        //tftInit();
        // tftBootScreen();
        // delay(1000);
        unsigned long ms = millis();
        while(millis() - ms < 2500)
        {
            delay(1);
            if (digitalRead(0) != LOW)
                break;
        }

        // if (digitalRead(0) != LOW)
        // {
        //     toSleep();
        // }
    }
    // else 
    //     toSleep();
    inDeepSleep = false;
}
extern void testRgb(void);

void gameJob(void*)
{   
    unsigned long lastBeaconMs = 0;
    unsigned long lastPrintedMs = 0;
    const int beaconRssi = -40;
    Serial.println(">>> gameJob");    
    //onBoot();
    //tftInit();
    //testRgb();
    tTftMainScreenRecord dRec;    
    //BEACON_INTERVAL_MS
    delay(10);
    while(true)
    {
        espProcessRx(RECEIVER_INTERVAL_MS);
        checkBtn();
        if (millis() - lastBeaconMs > BEACON_INTERVAL_MS)
        {
            espProcessTx();
            lastBeaconMs = millis();
        }

        if (millis() - lastPrintedMs > 1000)
        {
            // printRecords(1500);
            // Serial.println("----------\n\n");
            lastPrintedMs = millis();
        }        
        dRec.vcc = getVcc();
        //getNearestRecord(dRec.dNum, dRec.rssi, 500);
        //tftProcessMainScreen(&dRec);
        updateCurrHitPoints(&gameRecord);
        if (checkIfApPortal(beaconRssi))
        {
            Serial.println("----> AP PORTAL");
            tftPrintThreeLines("AP PORTAL", "BEACON", "DETECTED", TFT_BLACK, TFT_BLUE);
            delay(3000);
            startSelfPortal();
        }
        delay(5);
    }    
}

void startPlayerJob(void)
{
    prepareWiFi();
    espInitRxTx((tGameRole)DEF_DEVICE_ROLE);
           //gameJob();
    //xTaskCreatePinnedToCore(gameJob, "gameJob", 25000, NULL, 7 | portPRIVILEGE_BIT, NULL, APP_CPU_NUM);
    gameJob(NULL);
}

void portalTft(String s1, String s2, String s3)
{
    tftPrintThreeLines(s1, s2, s3, TFT_BLACK, TFT_BLUE);
}

