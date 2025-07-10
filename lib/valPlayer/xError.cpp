#include "valPlayer.h"
#include "tft_utils.h"


void valPrintError(uint8_t errB)
{
    String errS = "ERROR";
    switch(errB)
    {
        case ERR_VAL_SPIFFS: errS = "ERR_VAL_SPIFFS"; break;
        case ERR_VAL_LOAD:   errS = "ERR_VAL_LOAD"; break;
        case ERR_VAL_JSON:   errS = "ERR_VAL_JSON"; break;
    }
    tftPrintText(errS);
}

void valPlayError(uint8_t errB)
{
    neoPixels.setPixelColor(0, neoPixels.Color(0, 0, 20));
    
    for (int i = 0; i < 7; i++)
    {
        if (bitRead(errB, 6 - i))
            neoPixels.setPixelColor(i + 1, neoPixels.Color(20, 0, 0));
        else 
            neoPixels.setPixelColor(i + 1, neoPixels.Color(0, 0, 0));
    }
    delay(1);
    neoPixels.show();
    valPrintError(errB);
}