#include "__main.h"

#include <Wire.h>

#include "PSRamFS.h"
#include "serverSync.h"
#include "board.h"
#include "tft_utils.h"
#include "valPlayer.h"
#include "version.h"
#include "xgConfig.h"
#include "patterns.h"
#include "wifiUtils.h"
#include "gameEngine.h"
#include "statusClient.h"
#include "version.h"

static void boardInit(void)
{
    boardPowerOn();
    delay(10);       
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    if (DEF_USE_TFT)
    {
       setupTFT("BOOT"); 
       tftPrintText("BAZA BOOT");
       delay(300);              
    }
    valPlayError(ERR_VAL_OK);
    //delay(1000);
}

void checkSleep(bool resetTimer)
{
    static uint32_t lastFedMs = 0;
    if (resetTimer)
    {
        lastFedMs = millis();
        return;
    }
    if (millis() - lastFedMs > DEF_SLEEP_AFTER_BOOT_FAIL_MS)    
    {
        statusClientResume();
        statusClientSetGameStatus("SLEEP_ON_FAIL");        
        Serial.println("!!!!!!! AUTO-SLEEP ON BOOT FAIL !!!!!!!!");
        tftPrintText("BOOT FAILED!");
        delay(5000);
        tftPrintText("SLEEP");
        delay(10000);
        boardStartSleep();
    }
}

static bool configInit(void)
{
    if (ConfigAPI::initialize())
    {
        ConfigAPI::printConfig();
        return true;
    }

    return false;
}

static bool psFsInit(void)
{
    Serial.print(">>> PSRAM FS INIT...");
    delay(500);
    if (!PSRamFS.begin())
    {
        Serial.println("ERROR!!!");
        return false;
    }
    Serial.println("DONE");
    Serial.printf("PsRamFS Total: %d bytes\n", PSRamFS.totalBytes());
    Serial.printf("PsRamFS Used: %d bytes\n", PSRamFS.usedBytes());
    Serial.printf("PsRamFS Free: %d bytes\n", PSRamFS.totalBytes() - PSRamFS.usedBytes());    
    return true;
}

static bool accelInitOnBoot(void)
{
    if (accelInit())
    {
        return true;
    }
    return false;
}

static void configBoot(void)
{
    tftPrintText("CONFIG");
    delay(100);
    if (!configInit())
    {
        tftPrintText("!CONFIG ERROR!");
        while(1)
        {
            delay(1);
            checkSleep();
        }
    }
    checkSleep(true);
}

static void accelBoot(void)
{
    tftPrintText("ACCELEROMETER");

    if (!accelInitOnBoot())
    {
        tftPrintText("!ACCEL. ERROR!");
        delay(2500);
        //while(1)
        // {
        //     delay(1);
        //     checkSleep();
        // }
    }
    checkSleep(true);
}

static void netBoot(void)
{    
    int a = 0;
    tftPrintText("NETWORK");
    delay(100);

    if (netConnect(DEF_NET_WAIT_MS))
    {        
        while(!netWait(DEF_NET_WAIT_MS))
        {
            a++;
            Serial.printf("*** Wi-Fi connection attempt #%d\r\n", a);
            tftPrintText("NETWORK " + String(a));
            checkSleep();
        }
    }
    else 
    {
        tftPrintText("!NET. ERROR!");
        while(true)
        {
            checkSleep();
        }
    }
    checkSleep(true);
}

static void discoBoot(void)
{
    IPAddress server;
    int a = 0;
    const int maxAttempts = 10;
    tftPrintText("DISCO");    
    delay(100);
    while(true)
    {
        bool res = wifiGetDisco(server);
        a++;
        if (!res)
        {
            tftPrintText("DISCO ERR " + String(a));
            checkSleep();
        }
        else
        {
            String serverIpStr = server.toString(); 
            Serial.print(">> DISCO COMPLETED: ");
            Serial.println(serverIpStr);
            ConfigAPI::setDiscoServer(serverIpStr);
            break;
        }
        if (a > maxAttempts)
        {
            tftPrintText("DISCO ERROR SLEEP");    
            Serial.println("DISCO ERROR SLEEP");
            delay(3000);
            boardStartSleep();
        }
    }
    checkSleep(true);
}

static void otaBoot(void)
{
    int a = 0;    
    int fwVer = String(BUILD_NUMBER).toInt();
    statusClientSetGameStatus("OTA_CHECK");
    statusClientPause();
    tftPrintText("OTA");
    delay(100);    
    while (!syncOTA(ConfigAPI::getOTAServerUrl().c_str(), fwVer))
    {        
        if (DEF_CAN_SKIP_OTA)
        {
            Serial.println("*** WARNING: OTA SKIPPED!");
            break;
        }
        else 
        {
            a++;
            Serial.printf("!!! OTA sync failed, attempt #%d\r\n", a);
            tftPrintText("OTA " + String(a));
        }
        checkSleep();
    }
    checkSleep(true);
    statusClientResume();
}

static void statusBoot(void)
{
    int a = 0;    
    tftPrintText("STATUS CLIENT");
    delay(100);    

    while (!statusClientInit(ConfigAPI::getDeviceName().c_str(), ConfigAPI::getDiscoServer().c_str()))
    {                
        checkSleep();
        a++;
        tftPrintText("STATUS CLIENT ERR " + String(a));
    }
    checkSleep(true);
}

static bool checkFsInit(void)
{
    File f = PSRamFS.open(VAL_FILE_NAME, "r");
    if (!f)
    {        
        return false;
    }
    f.close();
    return true;
}

bool fsProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
{
    String legendS = "FILE SYNC " + String(percentage) + "%";
    Serial.printf("Progress: %d/%d bytes (%d%%) downloaded\n", downloaded, total, percentage);
    tftPrintText(legendS);

    // Add your custom logic here
    // Return false to cancel sync, true to continue
    return true;
}


static void fileSyncBoot(void)
{
    int a = 0;    
    statusClientSetGameStatus("FILE SYNC");
    statusClientPause();
    tftPrintText("FILE SYNC");
    delay(100);

    if (!checkFsInit())
    {
        while (!syncFiles(ConfigAPI::getFileServerUrl().c_str(), fsProgressCallback))
        {
            a++;
            Serial.printf("!!! File sync failed, attempt #%d\r\n", a);
            tftPrintText("FILE SYNC ERR " + String(a));
            checkSleep();
        }
        checkSleep(true);    
    }
    else 
    {
        tftPrintText("FILE SYNC READY");
        delay(500);
    }
    statusClientResume();
}

static void valPlayerBoot(void)
{
    tftPrintText("VAL_PLAYER");
    delay(500);
    if (!valPlayerInit())
    {
        while(1)
        {
            delay(1000);
            Serial.println("Error VAL init!!!");
            valPlayError(ERR_VAL_INIT);
            checkSleep();
        }
    }
}

static void radioBoot(void)
{
    checkSleep(true);
    tftPrintText("RADIO");
    radioConnect();
    delay(100);
}

bool initOnBoot(void)
{
    bool wasError = false;    

    Serial.begin(115200);

    if (!psFsInit())
    {
        wasError = true;
    }    

    boardInit();          

    delay(1500);
    Serial.println(">>> BOOT");
    Serial.print(">>> BAZA GAME TERMINAL ");
    Serial.println(VERSION_STR);
    delay(10);

    if (wasError)
    {
        tftPrintText("!FS ERROR!");
        while(1)
        {
            delay(1);
            checkSleep();
        }
        return false;
    }
    else 
    {
    
    }
    checkSleep(true);
    accelBoot();    
    configBoot();
    netBoot();    
    discoBoot();
    statusBoot();        
    otaBoot();       
    fileSyncBoot();                
    radioBoot();
    valPlayerBoot();  
    valPlayPattern(ON_BOOT_PATTERN);
    statusClientSetGameStatus("READY");
    bazaLogo();    
    //tftPrintText("READY!");    
    statusClientSetGameStatus("STARTED");

    return true;
}

void otaProgressCallback(int progress)
{
    Serial.printf("OTA Progress: %d%%\n", progress);
    tftPrintText("OTA  " + String(progress) + "%");
}