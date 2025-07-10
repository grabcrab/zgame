#include <Arduino.h>

#include "serialCommander.h"

#define SERIAL_COMM_SCAN_LIST           "scan_list"
extern void onSerialScanList(void);
#define SERIAL_COMM_HELP                "help"
void onHelp(void);

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
    
    Serial.printf(">>> Serial command [%s] received\r\n", comS.c_str());

    if (isCommand(comS, SERIAL_COMM_SCAN_LIST))
    {        
        onSerialScanList();
        return;
    }            

    if (isCommand(comS, SERIAL_COMM_HELP))
    {        
        onHelp();
        return;
    }                
    
    Serial.println("!!! WRONG SERIAL COMMAND");
    onHelp();
}

void onHelp(void)
{
    Serial.println(">>>>>>>>>>> SERIAL COMMANDS: <<<<<<<<<<<");
    Serial.printf("%-15s This help\r\n", SERIAL_COMM_HELP);
    Serial.printf("%-15s Print all scanned devices\r\n", SERIAL_COMM_SCAN_LIST);

    Serial.println("=========================================");
}
