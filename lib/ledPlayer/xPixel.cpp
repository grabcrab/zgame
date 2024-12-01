#include "ledPlayer.h"
#include "utils.h"

void tLedPixel::print(void)
{
    Serial.printf("[%02X%02X%02X]", r, g, b);
}

void tLedPixel::set(String hexS)
{
    uint32_t uval32 = hexoDecToInt(hexS);
    uint8_t *bytes = (uint8_t*) &uval32;
    r = bytes[2];
    g = bytes[1];
    b = bytes[0];
}

void tLedPixel::play(uint8_t pxNum)
{    
    neoPixels.setPixelColor(pxNum, neoPixels.Color(r, g, b));
}