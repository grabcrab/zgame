#include <Arduino.h>
#include <WiFi.h>

#include "espRadio.h"
#include "serialCommander.h"
#include "gameEngine.h"
#include "tft_utils.h"

#define COM_LOOP_DELAY 2

static bool commStarted = false;
static TaskHandle_t taskHandle = NULL;

static void waitForTheNextGame(String gRes)
{    
    if (gRes == "zwin")
    {
        zombieWinPicture();
    } 
    
    if (gRes == "hwin")
    {
        humanWinPicture();
    }
    
    if (gRes == "draw")
    {
        drawPicture();
    }

    while(true)
    {
        delay(1000);
        Serial.println("!!! waitForTheNextGame: FIX ME !!! ");
    }
}

static String communicatorJob(void)
{   
    unsigned long lastBeaconMs = 0;
    unsigned long lastPrintedMs = 0;
    const int beaconRssi = -40;   
    int secondsLeft_ = 10;  
    String globalResult = "";
    //commStarted = true;
    delay(10);
    gameApiAsyncInit();
    Serial.println(">>> communicatorJob: LOOP STARTED");   
    while(true)
    {
        espProcessRx(RECEIVER_INTERVAL_MS);        
        if (millis() - lastBeaconMs > BEACON_INTERVAL_MS)
        {
            espProcessTx();
            lastBeaconMs = millis();
        }  
        String role_;
        int health_;
        doGameStep(role_, health_, secondsLeft_);
        tGameApiResponse updRes = updateGameStep(role_, "GAME_LOOP", health_);
        if (updRes.success)
        {
            updRes.print();
            secondsLeft_ = updRes.game_duration;            
            if ((updRes.role == "zwin") || (updRes.role == "hwin") || (updRes.role == "draw"))
            {
                globalResult = updRes.role;
                break;
            }
        }        
        delay(COM_LOOP_DELAY);      
    }    
    Serial.printf(">>> communicatorJob: LOOP COMPLETED <%s>\r\n", globalResult.c_str());   
    gameApiAsyncStop();
    waitForTheNextGame(globalResult);
    return globalResult;
}

String startGameCommunicator(void)
{
    if (commStarted)
    {
        Serial.println("!!! startCommunicator: ALREADY STARTED !!!");
        return "error";
    }
    //xTaskCreatePinnedToCore(communicatorJob, "communicatorJob", 25000, NULL, 7 | portPRIVILEGE_BIT, &taskHandle, APP_CPU_NUM);
    return communicatorJob();
}

void stopCommunicator(void)
{
    if (!commStarted)
    {
        return;
    }
    // vTaskDelete(taskHandle);
    // delay(200);
}