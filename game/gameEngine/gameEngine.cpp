#include "gameEngine.h"

static uint32_t gameStartedMs = 0;
static uint32_t gameCompletedMs = 0;
static uint32_t gameStep = 0;
// uint32_t tGameRecord::rssi2hp(int rssi)
// {
//     if (rssi > closeRssi)
//         return closePs;

//     if (rssi > middleRssi)
//         return middlePs;

//     if (rssi > farRssi)
//         return farHitPs;
    

//     return 0;
// }

void gamePrintStep(tGameRole deviceRole, int zCount, int hCount, int bCount, int healPoints, int hitPoints, int healthPoints, bool isBase)
{
    if (isBase)
    {
        healthPoints = 0;
    }
    Serial.printf(">>> STEP #%05lu [%s] [%d] [Z: %d] [H: %d] [B: %d] [HEAL: %d] [HIT: %d] \r\n", 
                            gameStep, role2str(deviceRole), healthPoints, zCount, hCount, bCount, healPoints, hitPoints);
}

void doGameStep(void)
{
    int zCount, hCount, bCount, healPoints, hitPoints, healthPoints;
    bool isBase;
    tGameRole deviceRole;
    bool doStep = loopScanRecords(deviceRole, zCount, hCount, bCount, healPoints, hitPoints, healthPoints, isBase);
    if (!doStep)
    {
        return;
    }
    gameStep++;
    gamePrintStep(deviceRole, zCount, hCount, bCount, healPoints, hitPoints, healthPoints, isBase);
}
