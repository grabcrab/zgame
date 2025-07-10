#include <Arduino.h>
#include "deviceRecords.h"
#include "espRadio.h"
#include "gameEngine.h"

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


static bool startTestGame(String captS, String jsonS)
{    
    Serial.print(">>> ");
    Serial.println(captS);
    if (setSelfJson(jsonS, true))
    {
        espInitRxTx(getSelfTxPacket(), true);
        startCommunicator();
        return true;
    }
    return false;
}

bool testGameHuman(void)
{    
    return startTestGame("", humJsonStr);
}

bool testGameZombie(void)
{
    return startTestGame("", zomJsonStr);
}

bool testGameBase(void)
{
    return startTestGame("", baseJsonStr);
}