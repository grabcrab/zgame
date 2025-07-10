#pragma once

#include <Arduino.h>

#include "espPacket.h"
#include "gameRole.h"

#define GAME_START_FAR_RSSI     -80
#define GAME_START_MIDDL_RSSI   -65
#define GAME_START_CLOSE_RSSI   -50
#define GAME_START_LOOP_INT_MS  2000

struct tDeviceDataRecord
{
    uint64_t deviceID = 0;
    tGameRole deviceRole;   
    uint32_t lastReceivedMs = 0;
    bool     processed = false;    
    int      hitPointsNear; 
    int      hitPointsMiddle;
    int      hitPointsFar;     
    int      health;     
    int  rssi = 0;         
    void print(void);   
    bool setJson(String jsonStr, bool self = true);
    inline bool isZomboHum(void) {if (deviceRole == grZombie || deviceRole == grHuman) return true; return false;}
    inline bool isBase(void) {if (deviceRole == grBase) return true; return false;}
};

bool checkIfApPortal(int rssiLevel);
void printScannedRecords(tGameRole filterRole = grNone);
bool setSelfJson(String jsonS, bool print);
tEspPacket *getSelfTxPacket(void);
bool loopScanRecords(tGameRole &deviceRole, int &zCount, int &hCount, int &bCount, int &healPoints, int &hitPoints, int &healthPoints, bool &base);
