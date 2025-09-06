#include <Arduino.h>
#include <WiFi.h>

#include "__main.h"
#include "serialCommander.h"
#include "xgConfig.h"
#include "gameEngine.h"

#include "valPlayer.h"
#include "tft_utils.h"

// const char *ssid = "tcutestnet";
// const char *password = "tcutestpass";
// static const char *serverAddress = "http://192.168.1.120:5001"; 

bool processErrorRole(String gameRole)
{
    if (gameRole != "roleError")
    {
        return false;
    }
    valPlayError(ERR_VAL_ROLE);
    while(true)
    {
        Serial.println("ERR_VAL_ROLE");
        delay(1000);
    }
    return true;
}

bool processSerialRole(String gameRole)
{
    if (gameRole != "fromSerial")
    {
        return false;
    }        
    while(true)
    {
        String jsonStr = "";
        tftPrintText("SERIAL JSON");
        Serial.println("Enter the game JSON:");
        while(!Serial.available())
        {
            delay(5);
        }
        delay(1);
        while(Serial.available())
        {
            jsonStr += (char) Serial.read();
            if (!Serial.available())
            {
                delay(100);
            }
        }
        Serial.println("=========================");
        Serial.println(jsonStr);
        Serial.println("=========================");
        delay(3000);
        if (startFixedGame("FROM_SERIAL", jsonStr))
        {
            break;
        }
        tftPrintText("JSON ERROR!!!");
        delay(2000);
    }
    return true;
}

bool processFixedRole(String deviceRole)
{
    String fileName = "";
    if (deviceRole == "fixBase")
    {
        fileName = "/xcon_bsettings.json";
    }
    if (deviceRole == "fixZombie")
    {
        fileName = "/xcon_zsettings.json";
    }
    if (deviceRole == "fixHuman")
    {
        fileName = "/xcon_hsettings.json";
    }

    if (deviceRole == "fixRSSI")
    {
        fileName = "/xcon_rsettings.json";
    }

    if (fileName == "")
    {
        return false;
    }

    if (startGameFromFile("FIXED_FROM_FILE", fileName))
    {
        return true;
    }
    else
    {
        tftPrintText("ROLE CONF. ERROR");
        while(true)
        {
            Serial.printf("!!! Role config file error: [%s] !!!\r\n", fileName.c_str());
            delay(10900);
        }
    }
    return false;
}

// bool processRssiMonitor(String deviceRole)
// {
//     if (deviceRole != "fixRSSI")
//     {
//         return false;
//     }
//     testRssiMonitor();
//     return true;
// }

void processGameRole(void)
{
    String deviceName = ConfigAPI::getDeviceName();
    String deviceRole = ConfigAPI::getDeviceRole();
    Serial.printf(">>>> processGameRole [%s] [%s]\r\n", deviceName.c_str(), deviceRole.c_str());

    if (processErrorRole(deviceRole))
    {
        return;
    }

    if (processSerialRole(deviceRole))
    {
        return;
    }

    if (processFixedRole(deviceRole))
    {
        return;
    }

    // if (processRssiMonitor(deviceRole))
    // {
    //     return;
    // }

    if (deviceRole == "gamePlayer")
    {
        gameWait();
        return;
    }    

    tftPrintText("!WRONG ROLE!");
    while(true)
    {
        Serial.println("!WRONG ROLE!");
        delay(1000);
    }
}

void setup()
{    
    if (!initOnBoot())
    {
        while(1)
        {
            checkSleep(false);
            delay(1);
        }
    }    
    processGameRole();    
    //testGameBase();
    //valTest();    
    //testGameHuman();
    //testGameZombie();
    
    
    //serialCommInit();
}

void loop()
{
    serialCommLoop();
    delay(50);
    //Serial.println(millis());
}