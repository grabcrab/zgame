#include "deviceRecords.h"

#include <ArduinoJson.h>
#include "utils.h"



static tDeviceDataRecord self;
static tEspPacket selfTxPacket;
static tDeviceDataRecord dRecords[MAX_REC_COUNT];

static int farRSSI   = GAME_START_FAR_RSSI;
static int middlRSSI = GAME_START_MIDDL_RSSI;
static int closeRSSI = GAME_START_CLOSE_RSSI;
static int gameLoopIntMs = GAME_START_LOOP_INT_MS;

//int i = sizeof(dRecords);

uint32_t lastHpUpdatedMs = 0;

void tDeviceDataRecord::print(void)
{
    Serial.printf("[deviceID = %s] [deviceRole = %s] [lastReceivedMs = %lu (%d)] [rssi = %d] [near = %d] [mid = %d] [far = %d] ", 
        utilsGetDeviceID64Hex().c_str(), role2str(deviceRole), lastReceivedMs, lastReceivedMs - millis(), rssi, hitPointsNear, hitPointsMiddle, hitPointsFar);   
}

bool tDeviceDataRecord::setJson(String jsonStr, bool self)
{    
    JsonDocument doc;
 
    DeserializationError error = deserializeJson(doc, jsonStr);
    if (error)
    {
        Serial.print("!!! tDeviceDataRecord::setJson ERROR. deserializeJson() failed: ");
        Serial.println(error.c_str());
        return false;
    }
    
    if (self)
    {
        deviceID = utilsGetDeviceID64();
    }
    else 
    {
        deviceID = doc["deviceID"].as<uint64_t>();
    }

    const char *roleStr = doc["deviceRole"] | "grNone";
    deviceRole = str2role(roleStr);

    hitPointsNear = doc["hitPointsNear"] | 0;
    hitPointsMiddle = doc["hitPointsMiddle"] | 0;
    hitPointsFar = doc["hitPointsFar"] | 0;
    health = doc["health"] | 0;
    return true;
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

void addScannedRecord(tEspPacket *rData, unsigned long lastMs, int rssi)
{    
    uint16_t pos = findPos(rData->deviceID);
    dRecords[pos].processed = false;    
    dRecords[pos].deviceID   = rData->deviceID;
    dRecords[pos].deviceRole = rData->deviceRole;

    dRecords[pos].hitPointsNear     = rData->hitPointsNear; 
    dRecords[pos].hitPointsMiddle   = rData->hitPointsMiddle;
    dRecords[pos].hitPointsFar      = rData->hitPointsFar;     

    dRecords[pos].lastReceivedMs = lastMs;    
    dRecords[pos].rssi = rssi;    
    //dRec.print();    
}

void printScannedRecords(tGameRole filterRole)
{
    Serial.println(">>>>>>>>>>>>>>> RECORDS LIST <<<<<<<<<<<<<<<<<<");
    self.print();
    Serial.println("\r\n----");
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
        Serial.println();
    }    
    Serial.println("===============================================");
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

static void self2tx(void)
{   
    selfTxPacket.deviceID        = self.deviceID;      
    selfTxPacket.deviceRole      = self.deviceRole;
    selfTxPacket.hitPointsNear   = self.hitPointsNear; 
    selfTxPacket.hitPointsMiddle = self.hitPointsMiddle;
    selfTxPacket.hitPointsFar    = self.hitPointsFar;        
}

bool setSelfJson(String jsonS, bool print)
{
    bool res = self.setJson(jsonS, true);
    if (res)
    {
        if (print)
        {
            Serial.println(">>> SELF record is set to:");
            self.print();
            Serial.println("\n=========================");
        }
        self2tx();
    }
    else 
    {
        Serial.println("!!! setSelfJson ERROR!");
    }
    return res;
}

tEspPacket *getSelfTxPacket(void)
{
    return &selfTxPacket;
}

static int rssi2points(tDeviceDataRecord *rec)
{
    if (rec->rssi < farRSSI)
    {
        return rec->hitPointsFar;
    }
    if (rec->rssi < middlRSSI)
    {
        return rec->hitPointsMiddle;
    }
    return rec->hitPointsNear;
}

bool loopScanRecords(tGameRole &deviceRole, int &zCount, int &hCount, int &bCount, int &healPoints, int &hitPoints, int &healthPoints, bool &base)
{
    static uint32_t lastLoopedMs = 0;

    if (millis() - lastLoopedMs < gameLoopIntMs)
    {
        return false;
    }

    lastLoopedMs = millis();
    deviceRole = self.deviceRole;

    if (self.deviceRole == grBase)
    {        
        base = true;
    }
    else 
    {
        base = false;
    }

    zCount = hCount = bCount = healPoints = hitPoints = 0;
    healthPoints = self.health;
    
    for (int i = 0; i < MAX_REC_COUNT; i++)
    {        
        if (!dRecords[i].deviceID)
        {
            continue;
        }     

        if (millis() - dRecords[i].lastReceivedMs > gameLoopIntMs)
        {
            continue;
        }     

        if (dRecords[i].deviceRole == grZombie)
        {
            zCount++;
        }

        if (dRecords[i].deviceRole == grHuman)
        {
            hCount++;
        }

        if (dRecords[i].deviceRole == grBase)
        {
            bCount++;
        }

        if (dRecords[i].isZomboHum())
        {
            if (self.deviceRole != dRecords[i].deviceRole)
            {
                int hp = rssi2points(&dRecords[i]);
                hitPoints += hp;
            }            
        }

        if (dRecords[i].isBase())
        {
            int hp = rssi2points(&dRecords[i]);
            healPoints += hp;
        }
    }  
    self.health += healPoints;
    self.health += hitPoints;
    healthPoints = self.health;
    return true;
}
