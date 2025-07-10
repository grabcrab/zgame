#include "valPlayer.h"

void tLedStrip::print(void)
{
    for (int i = 0; i < VAL_PIXELS_NUM; i++)
    {
        pixels[i].print();
    }
    Serial.print(" ");
    Serial.printf("intervalMs = %u", intervalMs);
    if (vibro)
        Serial.print(" VIBRO");
    Serial.println();
}

unsigned long tLedStrip::play(void)
{    
    for (int i = 0; i < VAL_PIXELS_NUM; i++)
    {
        pixels[i].play(i);
    }
    delay(1);
    neoPixels.show();
    if (vibro)
    {
        pinMode(PIN_VIBRO, OUTPUT);
        digitalWrite(PIN_VIBRO, HIGH);
    }
    else 
    {
        pinMode(PIN_VIBRO, OUTPUT);
        digitalWrite(PIN_VIBRO, LOW);       
    }
    
    return millis() + intervalMs; 
}

void tLedStrip::loadFromJson(JsonArray strip)
{
    int idx = 0;
    for(JsonVariant v : strip) 
    {
        String strVal  = String((const char*) v);                
        if (idx < VAL_PIXELS_NUM)
            pixels[idx].set(strVal);
        if (idx == VAL_PIXELS_NUM)
            intervalMs = strVal.toInt();            
        
        if (idx == VAL_PIXELS_NUM + 1)
            vibro = (strVal.toInt() > 0);            
        
        if (idx >= VAL_PIXELS_NUM + 1)
            break;
        idx++;
        
    }
    if (idx != VAL_PIXELS_NUM +1)
        Serial.printf("tLedStrip::loadFromJson ERROR: bad array size [%u]\r\n", idx);
}