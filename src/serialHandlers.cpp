#include <Arduino.h>

#include "deviceRecords.h"

void onSerialScanList(void)
{
    Serial.println(">>> onSerialScanList");
    printScannedRecords();
}