#include <Arduino.h>
#include <WiFi.h>

#include "__main.h"
#include "serialCommander.h"
#include "gameEngine.h"

#include "valPlayer.h"

// const char *ssid = "tcutestnet";
// const char *password = "tcutestpass";
// static const char *serverAddress = "http://192.168.1.120:5001"; 


void setup()
{    
    if (!initOnBoot())
    {

    }

    //valTest();

    testGameHuman();
    //testGameZombie();
    //testGameBase();
    
    //serialCommInit();
}

void loop()
{
    serialCommLoop();
    delay(50);
    //Serial.println(millis());
}