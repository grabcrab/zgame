#include <Arduino.h>
#include "deviceRecords.h"
#include "espRadio.h"
#include "gameEngine.h"
#include "tft_utils.h"

const String zomJsonStr = R"({
    "deviceRole": "grZombie",        
    "hitPointsNear": -100,
    "hitPointsMiddle": -50,
    "hitPointsFar": -10,
    "health": 10000    
})";

const String humJsonStr = R"({
    "deviceRole": "grHuman",        
    "hitPointsNear": -100,
    "hitPointsMiddle": -50,
    "hitPointsFar": -10,
    "health": 10000    
})";

const String baseJsonStr = R"({
    "deviceRole": "grBase",        
    "hitPointsNear": 10,
    "hitPointsMiddle": 5,
    "hitPointsFar": 1,
    "health": 10000    
})";

const String rssiJsonStr = R"({
    "deviceRole": "grRssiMonitor",        
    "hitPointsNear": 10,
    "hitPointsMiddle": 5,
    "hitPointsFar": 1,
    "health": 10000    
})";


bool testGameHuman(void)
{    
    return startFixedGame("TEST_HUMAN", humJsonStr);
}

bool testGameZombie(void)
{
    return startFixedGame("TEST_ZOMBIE", zomJsonStr);
}

bool testGameBase(void)
{
    return startFixedGame("TEST_BASE", baseJsonStr);
}

bool testRssiMonitor(void)
{
    tftPrintText("RSSI MONITOR");
    return startFixedGame("TEST_RSSI", rssiJsonStr);
}