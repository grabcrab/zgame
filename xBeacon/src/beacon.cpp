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
}

