#include <Arduino.h>
#include "valPlayer.h"
#include "tft_utils.h"

void jobNone(void)
{
    if (!valPlayerInit())
    {
        while(1)
        {
            Serial.println("Error VAL init!!!");
            delay(1000);
        }
    }
    tftPrintText("NO ROLE", TFT_BLACK, TFT_RED);
    valPlayPattern("NoneJob");

    while(true)
    {
        Serial.println("!!! NOT CONFIGURED !!!");
        delay(1000);
    }
}