#include <Arduino.h>
#include <WiFi.h>

#include "espRadio.h"
#include "serialCommander.h"
#include "gameEngine.h"


void setup()
{
    Serial.begin(115200);
    delay(500);
    Serial.println(">>> BOOT");
    delay(10);
    prepareWiFi();
    rssiReaderInit();
    initRadio();
    testGameHuman();        
    //testGameZombie();
    //testGameBase();    
    serialCommInit();    
}

void loop()
{
    serialCommLoop();
    delay(50);    
}