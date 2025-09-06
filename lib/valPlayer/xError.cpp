#include "valPlayer.h"
#include "tft_utils.h"


void valPrintError(uint8_t errB)
{
    String errS = "ERROR";
    switch(errB)
    {
        case ERR_VAL_FS: errS = "ERR_VAL_FS"; break;
        case ERR_VAL_LOAD:   errS = "ERR_VAL_LOAD"; break;
        case ERR_VAL_JSON:   errS = "ERR_VAL_JSON"; break;
        case ERR_VAL_INIT:   errS = "ERR_VAL_INIT"; break;
        case ERR_VAL_ROLE:   errS = "ERR_VAL_ROLE"; break;
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
    if (errB)
    {        
        valPrintError(errB);
    }
}