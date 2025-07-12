#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>

#include "espRadio.h"
#include "espRx.h"
#include "tcu_board.h"
#include "utils.h"

void beaconJob(void)
{   
    Serial.println(">>> beaconJob");    
    rssiReaderInit();
    #ifndef ESP32_S3
        boardInit();
        boardLedOn();    
    
    for (int i = 0; i < 5; i++)
    {
        boardLedOff();    
        delay(300);
        boardLedOn();    
        delay(300);
    }
    #endif

    //sendEspPacket();
    // testSender(12, 10);
    // testReceiver(12);    
}

