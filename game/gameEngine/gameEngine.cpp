#include "gameEngine.h"
#include "gameComm.h"
#include "valPlayer.h"
#include "patterns.h"
#include "tft_utils.h"

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

void gameOnCritical(String errS)
{
    //SLEEP HANDLING!!!
    valPlayPattern(ERROR_PATTERN);
    while(true)
    {
        Serial.print("!!! GAME ERROR: ");
        Serial.println(errS);
        delay(1000);
    }
}

void humanPreGame(uint16_t preTimeoutMs)
{    
    //CHANGE!!!
    int lastDrawMs = 0;
    uint32_t startMs = millis();    
    valPlayPattern(ROLE_ZOMBI_PATTERN);
    while(millis() - startMs < preTimeoutMs)
    {        
        if (millis() - lastDrawMs < 1000)       
        {
            delay(10);
            continue;
        }
        lastDrawMs = millis();
        int secLeft = (preTimeoutMs - (millis() - startMs))/1000;
        humanPreWaitPicture();
        tftPrintTextBig(String(secLeft), TFT_BLACK, TFT_GREEN, true);
    }
}

void zombiePreGame(uint16_t preTimeoutMs)
{
    int lastDrawMs = 0;
    uint32_t startMs = millis();    
    valPlayPattern(ROLE_ZOMBI_PATTERN);
    while(millis() - startMs < preTimeoutMs)
    {        
        if (millis() - lastDrawMs < 1000)       
        {
            delay(50);
            continue;
        }
        lastDrawMs = millis();
        int secLeft = (preTimeoutMs - (millis() - startMs))/1000;
        zombiPreWaitPicture();
        tftPrintTextBig(String(secLeft), TFT_BLACK, TFT_GREEN, true);
        lastDrawMs = millis();
    }
}

void gameWait(void)
{
    uint16_t preTimeoutMs;
    valPlayPattern(GAME_WAIT_PATTERN);
    gameWaitLogo();
    tGameRole role = waitGame(preTimeoutMs);
    switch(role)
    {
        case grZombie:
            zombiePreGame(preTimeoutMs);
        return;        
        case grHuman:
            humanPreGame(preTimeoutMs);
        return;        
        default:
            gameOnCritical("ERR_ROLE");
        break;
    }

}

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

