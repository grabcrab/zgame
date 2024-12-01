#include "ledPlayer.h"

void tLedStrip::print(void)
{
    for (int i = 0; i < LED_PIXELS_NUM; i++)
    {
        pixels[i].print();
    }
    Serial.print(" ");
    Serial.printf("intervalMs = %u\n", intervalMs);
}

unsigned long tLedStrip::play(void)
{    
    for (int i = 0; i < LED_PIXELS_NUM; i++)
    {
        pixels[i].play(i);
    }
    delay(1);
    neoPixels.show();
    return millis() + intervalMs; 
}

void tLedStrip::loadFromJson(JsonArray strip)
{
    int idx = 0;
    for(JsonVariant v : strip) 
    {
        String strVal  = String((const char*) v);                
        if (idx < LED_PIXELS_NUM)
            pixels[idx].set(strVal);
        if (idx == LED_PIXELS_NUM)
            intervalMs = strVal.toInt();            
        if (idx >= LED_PIXELS_NUM)
            break;
        idx++;
        
    }
    if (idx != LED_PIXELS_NUM)
        Serial.printf("tLedStrip::loadFromJson ERROR: bad array size [%u]\r\n", idx);
}