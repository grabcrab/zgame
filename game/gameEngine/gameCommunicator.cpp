#include <Arduino.h>
#include <WiFi.h>

#include "espRadio.h"
#include "serialCommander.h"
#include "gameEngine.h"

#define COM_LOOP_DELAY 2

void communicatorJob(void*)
{   
    unsigned long lastBeaconMs = 0;
    unsigned long lastPrintedMs = 0;
    const int beaconRssi = -40;
    Serial.println(">>> communicatorJob started");    
    delay(10);
    while(true)
    {
        espProcessRx(RECEIVER_INTERVAL_MS);        
        if (millis() - lastBeaconMs > BEACON_INTERVAL_MS)
        {
            espProcessTx();
            lastBeaconMs = millis();
        }  
        doGameStep();
        delay(COM_LOOP_DELAY);      
    }    
}

void startCommunicator(void)
{
    xTaskCreatePinnedToCore(communicatorJob, "communicatorJob", 25000, NULL, 7 | portPRIVILEGE_BIT, NULL, APP_CPU_NUM);
}