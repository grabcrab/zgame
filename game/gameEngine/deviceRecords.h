#pragma once

#include <Arduino.h>

#include "gameRole.h"

struct tDeviceDataRecord
{
    uint64_t deviceID = 0;
    uint32_t lastReceivedMs = 0;
    //uint32_t lastProcessedMs = 0;
    int  rssi = 0;    
    tGameRole deviceRole;    
    void print(void);    
};

bool checkIfApPortal(int rssiLevel);
void printScannedRecords(tGameRole filterRole = grNone);
