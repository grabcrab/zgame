#include <Arduino.h>
#include "gameRole.h"
#include "gameComm.h"
#include "deviceRecords.h"

#define GAME_START_LIFE_POINT 10000
#define GAME_MAX_TIME_MS      10 * 60 * 1000;  

#define GAME_START_FAR_HIT_PS   100

#define GAME_START_MIDDL_HIT_PS 250

#define GAME_START_CLOSE_HIT_PS 500

#define GAME_START_PS_UPD_INT_MS 1000

struct tGameRecord
{
    tGameRole gameRole = (tGameRole) DEF_DEVICE_ROLE;
    uint32_t startLifePoints = GAME_START_LIFE_POINT;    
    uint32_t gameTimeMs      = GAME_MAX_TIME_MS;

    uint32_t currentLifePoints = GAME_START_LIFE_POINT;    
    uint32_t gameStartedMs     = 0;

    int      farRssi    = GAME_START_FAR_RSSI;
    int      farHitPs   = GAME_START_FAR_HIT_PS;
    
    int      middleRssi = GAME_START_MIDDL_RSSI;
    int      middlePs   = GAME_START_MIDDL_HIT_PS;

    int     closeRssi   = GAME_START_CLOSE_RSSI;
    int     closePs     = GAME_START_CLOSE_HIT_PS;    

    uint32_t pointsUpdateIntervalMs = GAME_START_PS_UPD_INT_MS;

    uint32_t rssi2hp(int rssi);

};

bool testGameHuman(void);
bool testGameZombie(void);
bool testGameBase(void);
bool testRssiMonitor(void);

void gameOnCritical(String errS);
void gameWait(void);
void startCommunicator(void);
void doGameStep(void);
bool startFixedGame(String captS, String jsonS);
bool startGameFromFile(String captS, String fileName);