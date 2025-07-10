#include <Arduino.h>
#include <FreeRTOS.h>
#include "webPortalBase.h"
#include "../../include/version.h"

#define  PORTAL_BUTTON_PIN      0 
#define  PORTAL_BUTTON_DB_MS    200

volatile uint32_t lastButtonPressTime = 0;  
volatile bool buttonPressed = false;        
static bool wasBtnMonitorInit = false;

RTC_DATA_ATTR bool runPortal = false;
static bool inPortal = false;
static unsigned long lastStatusPrintedMs = 0;
static unsigned long lastPortalActivity = 0;

static String getDeviceMac(void)
{
    char buf[100];
    uint64_t mac64 = ESP.getEfuseMac();
    byte *macPtr = (byte*) &mac64;
    sprintf(buf, "%02X:%02X:%02X:%02X:%02X:%02X", macPtr[0], macPtr[1], macPtr[2], macPtr[3], macPtr[4], macPtr[5]);
    String res = buf;
    return res;
}


void IRAM_ATTR buttonISR() {
    static uint32_t lastInterruptTime = 0;
    uint32_t currentTime = millis();
    
    if (currentTime - lastInterruptTime > PORTAL_BUTTON_DB_MS) 
    {  
        buttonPressed = !digitalRead(PORTAL_BUTTON_PIN); 
        if (buttonPressed) 
        {
            lastButtonPressTime = currentTime;
        }
    }
    lastInterruptTime = currentTime;
}

uint32_t getTimeSinceLastPress() 
{
    if (!lastButtonPressTime) 
    {
        return UINT32_MAX;  
    }
    return millis() - lastButtonPressTime;
}

bool isButtonPressed() 
{
    return buttonPressed;
}

void startSelfPortal(void)
{
    Serial.println(">>>>>>>> STARTING SELF PORTAL");
    runPortal = true;
    ESP.deepSleep(1);
}

void buttonMonitorTask(void *pvParameters) 
{
    while (true) 
    {
        if (millis() < 1000)
        {
            delay(1000);
            continue;
        }
        if (isButtonPressed()) 
        {
            if (inPortal)
            {
                Serial.println(">>>>>>>> SELF PORTAL RESTARTED BY BUTTON");    
                delay(1000);
                ESP.restart();
            }
            uint32_t timeSincePress = getTimeSinceLastPress();
            #if (LOCAL_PORTAL_BY_BTN)
                startSelfPortal();
            #endif
        }
        vTaskDelay(pdMS_TO_TICKS(100));  
    }
}

void initButtonMonitor()
{
    if (wasBtnMonitorInit)
        return;
    wasBtnMonitorInit = true;
    pinMode(PORTAL_BUTTON_PIN, INPUT_PULLUP);  
    xTaskCreate(buttonMonitorTask, "ButtonMonitor", 2048, NULL, 10, NULL);
    attachInterrupt(digitalPinToInterrupt(PORTAL_BUTTON_PIN), buttonISR, FALLING);
}

void checkLastPortalActivity(void)
{
    if (millis() - lastPortalActivity > AUTO_OFF_TIMEOUT_S * 1000)
    {
        Serial.printf("Web portal is not active last %d seconds, restarting\r\n", AUTO_OFF_TIMEOUT_S);
        delay(3000);
        ESP.restart();
    }

    if (millis() - lastStatusPrintedMs > 10000)
    {
        uint16_t secondsToReboot = AUTO_OFF_TIMEOUT_S - (millis() - lastPortalActivity)/1000;
        lastStatusPrintedMs = millis();
        Serial.printf("Web portal job, %d seconds to reboot\r\n", secondsToReboot);
    }
}

void selfPortalOnBoot(uint32_t fwVersion, String portalName)
{
    Serial.println(">>> SELF WEB PORTAL MODE: btn. monitor started");
    initButtonMonitor();     

    if (!runPortal)
    {          
        return;
    }
    runPortal = false;
    inPortal = true;
    Serial.println("<<<< SELF WEB PORTAL MODE >>>>");    
    tWebPortalBase *wp = new tWebPortalBase(DEFAULT_HTPP_PORT, fwVersion,  portalName, getDeviceMac() + "<br>" + String(VERSION_STR));
    wp->serverOnSetup();
    wp->wifiAPSetup();
    wp->begin();
    Serial.println("Preparing WEB portal: DONE");
    
    while(true)
    {        
        checkLastPortalActivity();
        wp->server_loop();
        lastPortalActivity = wp->activityTimeMs;
        delay(1); 
    }
}



