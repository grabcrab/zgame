#include "__main.h"

#include <Wire.h>


#include "PSRamFS.h"
#include "serverSync.h"
#include "board.h"
#include "tft_utils.h"
#include "valPlayer.h"
#include "version.h"

static void boardInit(void)
{
    boardPowerOn();
    delay(10);       
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 4000000);
    if (DEF_USE_TFT)
    {
        setupTFT("BOOT"); 
        tftPrintText("BAZA BOOT");
    }
    valPlayError(ERR_VAL_OK);
    //delay(1000);
}

static bool psFsInit(void)
{
    Serial.print(">>> PSRAM FS INIT...");
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
        return false;
    }

    tftPrintText("NETWORK");

    if (!netConnect(DEF_NET_WAIT_MS))
    {        
        while(!netWait(DEF_NET_WAIT_MS))
        {
            a++;
            Serial.printf("*** Wi-Fi connection attempt #%d\r\n", a);
            tftPrintText("NETWORK " + String(a));
        }
    }

    a = 0;    
    tftPrintText("OTA");
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
    }

    a = 0;    
    tftPrintText("FILE SYNC");
    while (!syncFiles(DEF_FILE_SERVER_ADDR))
    {
        a++;
        Serial.printf("!!! File sync failed, attempt #%d\r\n", a);
        tftPrintText("FILE SYNC " + String(a));
    }
    
    tftPrintText("VAL_PLAYER");

    if (!valPlayerInit())
    {
        while(1)
        {
            delay(1000);
            Serial.println("Error VAL init!!!");
            valPlayError(ERR_VAL_INIT);
        }
    }

    tftPrintText("RADIO");
    radioConnect();
    delay(500);

    valPlayPattern(ON_BOOT_PATTERN);
    tftPrintText("READY!");
    delay(500);

    return true;
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