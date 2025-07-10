#pragma once

#include <Arduino.h>

struct tRecRec
{
    uint16_t        dNum = 0xffff;
    unsigned long   lastMs;
    int             rssi;
    uint32_t        rCount;
};

void addRecord(uint16_t dNum, unsigned long lastMs, int rssi);
void printRecords(unsigned long dMs);
void getNearestRecord(uint16_t &dNum, int &rssi, unsigned long lastSeenAgoMs);