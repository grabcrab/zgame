#include "__main.h"

#include <Wire.h>


#include "PSRamFS.h"
#include "serverSync.h"
#include "board.h"
#include "tft_utils.h"
#include "valPlayer.h"
#include "version.h"
#include "xgConfig.h"

static void boardInit(void)
{
    boardPowerOn();
    delay(10);       
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    if (DEF_USE_TFT)
    {
        setupTFT("BOOT"); 
        tftPrintText("BAZA BOOT");
        delay(500);
    }
    valPlayError(ERR_VAL_OK);
    //delay(1000);
}

static void checkSleep(bool resetTimer = false)
{
    static uint32_t lastFedMs = 0;
    if (resetTimer)
    {
        lastFedMs = millis();
        return;
    }
    if (millis() - lastFedMs > DEF_SLEEP_AFTER_BOOT_FAIL_MS)    
    {
        Serial.println("!!!!!!! AUTO-SLEEP ON BOOT FAIL !!!!!!!!");
        tftPrintText("BOOT FAILED!");
        delay(5000);
        tftPrintText("SLEEP");
        delay(2000);
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

bool initOnBoot(void)
{
    bool wasError = false;
    int a = 0;

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
    checkSleep(true);

    tftPrintText("CONFIG");
    delay(500);

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

    tftPrintText("ACCELEROMETER");

    if (!accelInitOnBoot())
    {
        tftPrintText("!ACCEL. ERROR!");
        while(1)
        {
            delay(1);
            checkSleep();
        }
    }
    checkSleep(true);

    tftPrintText("NETWORK");
    delay(500);

    if (!netConnect(DEF_NET_WAIT_MS))
    {        
        while(!netWait(DEF_NET_WAIT_MS))
        {
            a++;
            Serial.printf("*** Wi-Fi connection attempt #%d\r\n", a);
            tftPrintText("NETWORK " + String(a));
            checkSleep();
        }
    }
    checkSleep(true);

    a = 0;    
    tftPrintText("OTA");
    delay(500);    
    while (!syncOTA(DEF_OTA_SERVER_ADDR))
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

    a = 0;    
    tftPrintText("FILE SYNC");
    delay(500);
    while (!syncFiles(DEF_FILE_SERVER_ADDR))
    {
        a++;
        Serial.printf("!!! File sync failed, attempt #%d\r\n", a);
        tftPrintText("FILE SYNC " + String(a));
        checkSleep();
    }
    checkSleep(true);

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

    checkSleep(true);
    tftPrintText("RADIO");
    radioConnect();
    delay(500);

    valPlayPattern(ON_BOOT_PATTERN);
    tftPrintText("READY!");
    delay(500);

    return true;


    //  bool wasError = false;
    // int a = 0;

    // Serial.begin(115200);


    // if (!psFsInit())
    // {
    //     wasError = true;
    // }    

    // boardInit();      

    // delay(1500);
    // Serial.println(">>> BOOT");
    // Serial.print(">>> BAZA GAME TERMINAL ");
    // Serial.println(VERSION_STR);
    // delay(10);


    // if (wasError)
    // {
    //     return false;
    // }

    // tftPrintText("NETWORK");

    // if (!netConnect(DEF_NET_WAIT_MS))
    // {        
    //     while(!netWait(DEF_NET_WAIT_MS))
    //     {
    //         a++;
    //         Serial.printf("*** Wi-Fi connection attempt #%d\r\n", a);
    //         tftPrintText("NETWORK " + String(a));
    //     }
    // }

    // a = 0;    
    // tftPrintText("OTA");
    // while (!syncOTA(DEF_OTA_SERVER_ADDR))
    // {        
    //     if (DEF_CAN_SKIP_OTA)
    //     {
    //         Serial.println("*** WARNING: OTA SKIPPED!");
    //         break;
    //     }
    //     else 
    //     {
    //         a++;
    //         Serial.printf("!!! OTA sync failed, attempt #%d\r\n", a);
    //         tftPrintText("OTA " + String(a));
    //     }
    // }

    // a = 0;    
    // tftPrintText("FILE SYNC");
    // while (!syncFiles(DEF_FILE_SERVER_ADDR))
    // {
    //     a++;
    //     Serial.printf("!!! File sync failed, attempt #%d\r\n", a);
    //     tftPrintText("FILE SYNC " + String(a));
    // }
    
    // tftPrintText("VAL_PLAYER");

    // if (!valPlayerInit())
    // {
    //     while(1)
    //     {
    //         delay(1000);
    //         Serial.println("Error VAL init!!!");
    //         valPlayError(ERR_VAL_INIT);
    //     }
    // }

    // tftPrintText("RADIO");
    // radioConnect();
    // delay(500);

    // valPlayPattern(ON_BOOT_PATTERN);
    // tftPrintText("READY!");
    // delay(500);

    // return true;
}

void otaProgressCallback(int progress)
{
     Serial.printf("OTA Progress: %d%%\n", progress);

    // Example: blink built-in LED
    if (progress % 10 == 0)
    {
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }

    // Example: send progress via Serial in JSON format
    Serial.printf("{\"ota_progress\": %d}\n", progress);
}