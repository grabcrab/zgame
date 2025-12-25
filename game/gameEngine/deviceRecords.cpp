#include "deviceRecords.h"

#include <ArduinoJson.h>
#include "utils.h"
#include "PSRamFS.h"
#include "tft_utils.h"
#include "xgConfig.h"

static tDeviceDataRecord self;
static tEspPacket selfTxPacket;
static tDeviceDataRecord dRecords[MAX_REC_COUNT];

// static int farRSSI   = GAME_START_FAR_RSSI;
// static int middlRSSI = GAME_START_MIDDL_RSSI;
// static int closeRSSI = GAME_START_CLOSE_RSSI;
static int gameLoopIntMs = GAME_START_LOOP_INT_MS;

// int i = sizeof(dRecords);

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

    // if (self)
    // {
    //     deviceID = utilsGetDeviceID64();
    // }
    // else
    // {
    //     deviceID = doc["deviceID"].as<uint64_t>();
    // }

    deviceID = ConfigAPI::getDeviceID();

    const char *roleStr = doc["deviceRole"] | "grNone";
    deviceRole = str2role(roleStr);

    hitPointsNear = doc["hitPointsNear"] | 0;
    hitPointsMiddle = doc["hitPointsMiddle"] | 0;
    hitPointsFar = doc["hitPointsFar"] | 0;
    health = doc["health"] | 0;
    beginHealth = health;
    maxHealth = doc["maxHealth"] | 0;
    return true;
}

bool tDeviceDataRecord::setJsonFromFile(String filename, bool self)
{

    // // Check if file exists
    // if (!PSRamFS.exists(filename)) {
    //     Serial.print("!!! tDeviceDataRecord::setJsonFromFile ERROR. File does not exist: ");
    //     Serial.println(filename);
    //     return false;
    // }

    // Open file for reading
    File file = PSRamFS.open(filename, "r");
    if (!file)
    {
        Serial.print("!!! tDeviceDataRecord::setJsonFromFile ERROR. Failed to open file: ");
        Serial.println(filename);
        return false;
    }

    // Read file content
    String jsonStr = file.readString();
    file.close();

    // Check if file was empty
    if (jsonStr.length() == 0)
    {
        Serial.print("!!! tDeviceDataRecord::setJsonFromFile ERROR. File is empty: ");
        Serial.println(filename);
        return false;
    }

    // Parse JSON
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, jsonStr);
    if (error)
    {
        Serial.print("!!! tDeviceDataRecord::setJsonFromFile ERROR. deserializeJson() failed: ");
        Serial.println(error.c_str());
        return false;
    }

    // Set device data from JSON
    // if (self) {
    //     deviceID = utilsGetDeviceID64();
    // }
    // else {
    //     deviceID = doc["deviceID"].as<uint64_t>();
    // }
    deviceID = ConfigAPI::getDeviceID();

    const char *roleStr = doc["deviceRole"] | "grNone";
    deviceRole = str2role(roleStr);

    hitPointsNear = doc["hitPointsNear"] | 0;
    hitPointsMiddle = doc["hitPointsMiddle"] | 0;
    hitPointsFar = doc["hitPointsFar"] | 0;
    health = doc["health"] | 0;
    maxHealth = doc["maxHealth"] | 0;
    beginHealth = health;

    rssiFar = doc["rssiFar"] | 0;
    rssiMiddle = doc["rssiMiddle"] | 0;
    rssiClose = doc["rssiClose"] | 0;

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
    dRecords[pos].deviceID = rData->deviceID;
    dRecords[pos].deviceRole = rData->deviceRole;

    dRecords[pos].hitPointsNear = rData->hitPointsNear;
    dRecords[pos].hitPointsMiddle = rData->hitPointsMiddle;
    dRecords[pos].hitPointsFar = rData->hitPointsFar;

    dRecords[pos].lastReceivedMs = lastMs;
    dRecords[pos].rssi = rssi;
    // dRec.print();
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
    for (int i = 0; i < MAX_REC_COUNT; i++)
    {
        if (!dRecords[i].deviceID)
            break;

        if (dRecords[i].deviceRole != grApPortalBeacon)
            break;

        // Serial.printf("----->>> AP PORTAL BEACON: %d\r\n", dRecords[i].rssi);
        if (dRecords[i].rssi > rssiLevel)
            wasPortal = true;

        dRecords[i].deviceID = 0;
    }

    return wasPortal;
}

static void self2tx(void)
{
    selfTxPacket.deviceID = self.deviceID;
    selfTxPacket.deviceRole = self.deviceRole;
    selfTxPacket.hitPointsNear = self.hitPointsNear;
    selfTxPacket.hitPointsMiddle = self.hitPointsMiddle;
    selfTxPacket.hitPointsFar = self.hitPointsFar;
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

bool setSelfJsonFromFile(String fName)
{
    Serial.println(">>> setSelfJsonFromFile: START");
    bool res = self.setJsonFromFile(fName, true);
    if (res)
    {
        Serial.println(">>> setSelfJsonFromFile: OK");
        self.print();
        self2tx();
    }
    else
    {
        Serial.println("!!! setSelfJsonFromFile ERROR!");
    }
    return res;
}

tEspPacket *getSelfTxPacket(void)
{
    return &selfTxPacket;
}

tDeviceDataRecord *getSelfDataRecord(void)
{
    return &self;
}

static int rssi2points(tDeviceDataRecord *rec, String &rangeName)
{
    if (rec->rssi < self.rssiFar)
    {
        rangeName = " (OUT:0)";
        return 0;
    }

    if (rec->rssi > self.rssiClose)
    {
        rangeName = " (CLOSE:" + String(rec->hitPointsNear) + ")";
        return rec->hitPointsNear;
    }

    if (rec->rssi > self.rssiMiddle)
    {
        rangeName = " (MIDDLE:" + String(rec->hitPointsMiddle) + ")";
        return rec->hitPointsMiddle;
    }

    rangeName = " (FAR:" + String(rec->hitPointsFar) + ")";
    return rec->hitPointsFar;
}

static bool loopRssiMonitor(void)
{
    String deviceS, roleS, rssiS, rangeS;
    int maxRssi = -1000;
    int maxPos = -1;
    if (self.deviceRole != grRssiMonitor)
    {
        return false;
    }
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

        if (dRecords[i].rssi > maxRssi)
        {
            maxRssi = dRecords[i].rssi;
            maxPos = i;
        }
    }

    if (maxPos >= 0)
    {
        deviceS = dRecords[maxPos].deviceID;
        roleS = role2str(dRecords[maxPos].deviceRole);
        rssi2points(&dRecords[maxPos], rangeS);
        rssiS = String(dRecords[maxPos].rssi) + rangeS;
    }
    else
    {
        deviceS = "No devices";
        roleS = "";
        rssiS = "";
    }
    Serial.printf("[RSSI MONITOR] [%s] [%s] [%s]\r\n", deviceS.c_str(), roleS.c_str(), rssiS.c_str());
    tftPrintThreeLines(deviceS, roleS, rssiS, TFT_BLACK, TFT_GREEN);
    return true;
}

bool loopScanRecords(tGameRole &deviceRole, int &zCount, int &hCount, int &bCount, int &healPoints, int &hitPoints, int &healthPoints, bool &base)
{
    static uint32_t lastLoopedMs = 0;
    String tmpS;

    if (loopRssiMonitor())
    {
        return true;
    }

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
                int hp = rssi2points(&dRecords[i], tmpS);
                hitPoints += hp;
            }
        }

        if (dRecords[i].isBase())
        {
            int hp = rssi2points(&dRecords[i], tmpS);
            healPoints += hp;
        }
    }
    self.health += healPoints;
    self.health += hitPoints;
    healthPoints = self.health;
    return true;
}

tGameRole revertGameRole(void)
{
    if (self.deviceRole == grZombie)
    {
        self.deviceRole = grHuman;
        Serial.println("--->>> Converted to HUMAN");
        return self.deviceRole;
    }

    if (self.deviceRole == grHuman)
    {
        self.deviceRole = grZombie;
        Serial.println("--->>> Converted to ZOMBIE");
        return self.deviceRole;
    }
    return grNone;
}
