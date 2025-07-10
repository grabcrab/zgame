#include "espScanRecords.h"

static tRecRec records[MAX_REC_COUNT];

void printRecords(unsigned long dMs)
{    
    for (int i = 0; i < MAX_REC_COUNT; i++)
    {
        if (records[i].dNum == 0xffff) continue; 
        unsigned long dm = millis() - records[i].lastMs;       
        Serial.printf("%02d\t%d\t-%lu\t[%lu]", records[i].dNum, records[i].rssi, dm, records[i].rCount);
        if (dm > dMs) Serial.println(" XXXXX");
            else Serial.println();
        records[i].rCount = 0;
        if (dm > dMs * 10)
            records[i].dNum = 0xffff;
    }
}

void addRecord(uint16_t dNum, unsigned long lastMs, int rssi)
{
    int i;
    for (i = 0; i < MAX_REC_COUNT; i++)
    {
        if (records[i].dNum == dNum) break;        
    }

    if (i == MAX_REC_COUNT)
    {
        for (i = 0; i < MAX_REC_COUNT; i++)
        {
            if (records[i].dNum == 0xffff) break;
        }
    }

    if (i == MAX_REC_COUNT)
        i = 0;
    
    records[i].dNum = dNum;
    records[i].lastMs = lastMs;
    records[i].rssi = rssi;
    records[i].rCount++;
}

void getNearestRecord(uint16_t &dNum, int &rssi, unsigned long lastSeenAgoMs)
{            
    rssi = -1000;
    dNum = 0;
    for (int i = 0; i < MAX_REC_COUNT; i++)
    {
        if (records[i].dNum == 0xffff) continue; 
        unsigned long dm = millis() - records[i].lastMs;  
        if (dm > lastSeenAgoMs) continue;
        if (records[i].rssi > rssi)
        {
            rssi = records[i].rssi;
            dNum = records[i].dNum;
        }
    }    
    if (rssi == -1000)
        rssi = 0;
}