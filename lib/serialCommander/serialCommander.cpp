#include <Arduino.h>

#include "serialCommander.h"

#define SERIAL_COMM_SCAN_LIST           "scan_list"
extern void onSerialScanList(void);

static String getSerialCommand(void)
{
    String res = "";
    if (!Serial.available())
        return "";
    delay(30);
    while(Serial.available())
        res += (char) Serial.read();
    return res;
}

bool isCommand(String comTxt, String comS)
{
    if (comTxt.indexOf(comS) >=0) return true;
    return false;
}


void serialCommTask(void*)
{
    Serial.println(">>> serialCommTask: STARTED");
    delay(3000); //wait for scan
    while(true)
    {
        serialCommLoop();
        delay(10);
    }
}

void serialCommInit(void)
{
    xTaskCreatePinnedToCore(serialCommTask, "serialCommTask", 4096, NULL, 5, NULL, APP_CPU_NUM);
}

void serialCommLoop(void)
{    
    String comS = getSerialCommand();
    if (comS == "")
    {
        return;
    }
    
    if (isCommand(comS, SERIAL_COMM_SCAN_LIST))
    {        
        return;
    }            
    
    Serial.println("!!! WRONG SERIAL COMMAND!");
}
