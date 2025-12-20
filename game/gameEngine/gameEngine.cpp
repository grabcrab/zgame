#include "gameEngine.h"
#include "gameComm.h"
#include "valPlayer.h"
#include "patterns.h"
#include "tft_utils.h"
#include "espRadio.h"
static uint32_t gameStartedMs = 0;

static uint32_t gameCompletedMs = 0;
static uint32_t gameStep = 0;
static uint32_t lastBaseStartedMs = 0;
static uint32_t gameDurationS = 180;
static bool inTheBase = 0;

void gameOnCritical(String errS, bool noVal)
{
    //SLEEP HANDLING!!!
    int waitSec = 5;
    if (!noVal)
    {
        valPlayPattern(ERROR_PATTERN);    
    }
    gameCriticalErrorPicture(errS);
    while(waitSec)
    {
        Serial.printf("!!! GAME ERROR: [%s] [%d sec to reboot]\r\n", errS.c_str(), waitSec);        
        delay(1000);
        waitSec--;
    }
    Serial.println("!!!! REBOOTING !!!!");
    delay(1000);
    ESP.restart();
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
    valPlayPattern(GAME_ZOMBIE_NEUTRAL);
}

void basePreGame(void)
{    
    //CHANGE!!!
    int lastDrawMs = 0;
    uint32_t startMs = millis();    
    basePreWaitPicture();
    valPlayPattern(BASE_ROLE_PATTERN);    
}

void rssiMonitorPreGame(void)
{
    tftPrintText("RSSI MONITOR");
}

static void preGame(tGameRole role, uint16_t preTimeoutMs)
{
    switch(role)
    {
        case grZombie:
            zombiePreGame(preTimeoutMs);
        return;        
        case grHuman:
            humanPreGame(preTimeoutMs);
        return;        
        case grBase:
            basePreGame();
        return;
        case grRssiMonitor:
            rssiMonitorPreGame();
        return;
        default:
            gameOnCritical("ERR_ROLE", false);
        break;
    }
}

void gameWait(void)
{
    uint16_t preTimeoutMs;
    valPlayPattern(GAME_WAIT_PATTERN);
    gameWaitLogo();
    tGameRole role = waitGame(preTimeoutMs);
    preGame(role, preTimeoutMs);
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

void gameVisualizeStep(tGameRole deviceRole, int zCount, int hCount, int bCount, int healPoints, int hitPoints, int healthPoints, bool isBase, int secLeft)
{
    int lifePoint = healPoints + hitPoints;
    if (inTheBase)
    {
        tftGameScreenBase(healthPoints, lifePoint, secLeft);        
    }
    
    if (deviceRole == grZombie)    
    {
        
        //tftPrintText(String(healthPoints));
        if (lifePoint == 0)
        {
            valPlayPattern(GAME_ZOMBIE_NEUTRAL);           
        }
        
        if (lifePoint > 0)
        {
            valPlayPattern(GAME_ZOMBIE_HEALING);           
        }

        if (lifePoint < 0)
        {
            valPlayPattern(GAME_ZOMBIE_KILLING);           
        }
        
        if (!inTheBase)
        {
            tftGameScreenZombie(healthPoints, lifePoint, secLeft);
        }
    }
    
    if (deviceRole == grHuman)    
    {
        
        //tftPrintText(String(healthPoints), TFT_BLACK, TFT_RED);
        if (lifePoint == 0)
        {
            valPlayPattern(GAME_HUMAN_NEUTRAL);           
        }
        
        if (lifePoint > 0)
        {
            valPlayPattern(GAME_HUMAN_HEALING);           
        }

        if (lifePoint < 0)
        {
            valPlayPattern(GAME_HUMAN_KILLING);           
        }

        if (!inTheBase)
        {
            tftGameScreenHuman(healthPoints, lifePoint, secLeft);
        }
    }
}

bool isInTheBase(int healPoints)
{
    if (!healPoints)
    {
        inTheBase = false;
        if (lastBaseStartedMs)
        {
            if (millis() - lastBaseStartedMs > 15000) //BaseRestoredAfterMs 
            {
                lastBaseStartedMs = 0;
                Serial.println(">>> Base restored!");
            }            
        }
        return false;
    }
    
    if (!lastBaseStartedMs)
    {
        lastBaseStartedMs = millis();
        inTheBase = true;
        Serial.println(">>> Base started!");
        return true;
    }
    
    if ((lastBaseStartedMs) && (millis() - lastBaseStartedMs > 5000)) // BaseProtectionMs
    {
        #warning CONFIGURE THE BASE!!!
        inTheBase = false;        
    }
    return inTheBase;
}

static void processGameOver(void)
{
    Serial.println(">>>>>>>>>> GAME OVER <<<<<<<<<<<");
    gameOverPicture();
    while(true)
    {

    }
}

static int32_t getGameDurationLeftS(void)
{
    int32_t res;
    if (!gameStartedMs)
    {
        gameStartedMs = millis();
    }

    res = gameDurationS - ((millis() - gameStartedMs) / 1000);

    if (res < 0)
    {
        res = 0;
    }

    return res;
}

bool doGameStep(void)
{
    int zCount, hCount, bCount, healPoints, hitPoints, healthPoints;
    bool isBase;
    tGameRole deviceRole;
    int secLeft = 300;
    bool doStep = loopScanRecords(deviceRole, zCount, hCount, bCount, healPoints, hitPoints, healthPoints, isBase);
    if (!doStep)
    {
        return true;
    }
    gameStep++;
    if (healthPoints > getSelfDataRecord()->maxHealth)
    {
        healthPoints = getSelfDataRecord()->maxHealth;
    }

    if (inTheBase)
    {
        hitPoints = 0;
    }

    if (healthPoints < 0)
    {
        Serial.println("***** UNDER ZERO HEALTH *****");
        tGameRole newRole = revertGameRole();   
        // preGame(newRole, 10000); 
        // healthPoints = getSelfDataRecord()->beginHealth;
        if (newRole == grHuman)
        {         
            Serial.println("***** TO HUMAN *****");
            startZombieGame(GAME_SWAPROLE_PRE_MS);
        }

        if (newRole == grZombie)
        {        
            Serial.println("***** TO ZOMBIE *****");
            startZombieGame(GAME_SWAPROLE_PRE_MS);
        }
        
        lastBaseStartedMs = 0;
        inTheBase = 0;         
        return true;
    }

    secLeft =  getGameDurationLeftS();

    if (deviceRole == grBase)
    {
        secLeft = 3000;
    }

    if (secLeft <= 0) 
    {
        processGameOver();        
        return false;
    }

    isInTheBase(healPoints);
    gamePrintStep(deviceRole, zCount, hCount, bCount, healPoints, hitPoints, healthPoints, isBase);
    gameVisualizeStep(deviceRole, zCount, hCount, bCount, healPoints, hitPoints, healthPoints, isBase, secLeft);
    return true;
}

bool startFixedGame(String captS, String jsonS)
{    
    const uint16_t fixedGameToMs = 10000;
    Serial.print(">>> ");
    Serial.println(captS);

    if (setSelfJson(jsonS, true))
    {
        preGame(getSelfDataRecord()->deviceRole, fixedGameToMs);
        espInitRxTx(getSelfTxPacket(), true);
        startCommunicator();
        return true;
    }
    return false;
}

bool startGameFromFile(String captS, String fileName, uint16_t gameToMs)
{        
    Serial.print(">>> ");
    Serial.println(captS);

    if (setSelfJsonFromFile(fileName))
    {
        preGame(getSelfDataRecord()->deviceRole, gameToMs);
        espInitRxTx(getSelfTxPacket(), true);
        startCommunicator();
        return true;
    }
    return false;
}

bool startZombieGame(uint16_t gameToMs)
{
    return startGameFromFile("startZombieGame", GAME_ZOMB_FNAME, gameToMs);
}

bool startHumanGame(uint16_t gameToMs)
{
    return startGameFromFile("startHumanGame", GAME_HUMB_FNANE, gameToMs);
}

bool startBaseGame(void)
{
    return startGameFromFile("startBaseGame", GAME_BASE_FNAME, 0);
}

bool startRssiReader(void)
{
    return startGameFromFile("startGameFromFile", GAME_RSSI_FNAME, 0);
}

