#include "deviceRecords.h"

#include "gameEngine.h"
#include "utils.h"



tDeviceDataRecord dRecords[MAX_REC_COUNT];
//int i = sizeof(dRecords);

uint32_t lastHpUpdatedMs = 0;

void tDeviceDataRecord::print(void)
{
    Serial.printf("[deviceID = %s] [deviceRole = %s] [lastReceivedMs = %lu (%d)] [rssi = %d]", 
        utilsGetDeviceID64Hex().c_str(), role2str(deviceRole), lastReceivedMs, lastReceivedMs - millis(), rssi);   
}

static uint16_t findPos(uint64_t deviceID)
{
    for (int i = 0; i < MAX_REC_COUNT; i++)
    {
        if (dRecords[i].deviceID == deviceID)
            return i;
    }
    
    for (int i = 0; i < MAX_REC_COUNT; i++)
    {
        if (!dRecords[i].deviceID)
            return i;
    }

    return 0;
}

void addScannedRecord(uint64_t deviceID, tGameRole deviceRole, unsigned long lastMs, int rssi)
{    
    uint16_t pos = findPos(deviceID);
    dRecords[pos].deviceID   = deviceID;
    dRecords[pos].deviceRole = deviceRole;
    dRecords[pos].lastReceivedMs = lastMs;    
    dRecords[pos].rssi = rssi;    
    //dRec.print();    
}

void printScannedRecords(tGameRole filterRole)
{
    for (int i = 0; i < MAX_REC_COUNT; i++)
    {
        bool printIt = true;
        if (!dRecords[i].deviceID)
        {
            continue;
        }

        if ((filterRole != grNone) && (filterRole != dRecords[i].deviceRole))
        {
            continue;
        }
        dRecords[i].print();
    }
}

void updateCurrHitPoints(tGameRecord *gameRec)
{
    uint32_t res = 0;
    
    if (millis() - lastHpUpdatedMs < gameRec->pointsUpdateIntervalMs)
        return;    

    for (int i = 0; i <  MAX_REC_COUNT; i ++)
    {
        if (!dRecords[i].deviceID)
            break;
        
        if (millis() - dRecords[i].lastReceivedMs > gameRec->pointsUpdateIntervalMs)    
            continue;
        
        uint32_t hp = gameRec->rssi2hp(dRecords[i].rssi);
        Serial.printf("%d -> %d\r\n", dRecords[i].rssi, hp);        
    }
    lastHpUpdatedMs = millis();    
    Serial.println("====");
}

bool checkIfApPortal(int rssiLevel)
{
    bool wasPortal = false;
    for (int i = 0; i <  MAX_REC_COUNT; i ++)
    {
        if (!dRecords[i].deviceID)
            break;
        
        if (dRecords[i].deviceRole != grApPortalBeacon)
            break;
        
        //Serial.printf("----->>> AP PORTAL BEACON: %d\r\n", dRecords[i].rssi);
        if (dRecords[i].rssi > rssiLevel)        
            wasPortal = true;

        dRecords[i].deviceID = 0;
    }

    return wasPortal;
}
