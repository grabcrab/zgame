#include "ledPlayer.h"

void tLedPattern::print(void)
{
    Serial.printf("\t<%s>\r\n", name);
    for (int i = 0; i < stripsCount; i++)
    {
        Serial.print("\t\t");
        strips[i]->print();
        Serial.println();
    }
}

void tLedPattern::start(void)
{
    stripIdx = 0;
    nextStripMs = 0;
    loopPlay();
}

void tLedPattern::loopPlay(void)
{    
    if (!stripsCount)
        return;

    if ((millis() > nextStripMs) || (!nextStripMs))
    {
        nextStripMs = strips[stripIdx]->play();
        stripIdx++;
        if (stripIdx >= stripsCount) 
        {
            if (circular)
                stripIdx = 0;
            else 
                stripIdx--;
        }
    }
    
}

void tLedPattern::loadFromJson(JsonObject pattern)
{
    strncpy(name, pattern["PatternName"] | "NO_NAME", LED_PATTERN_NAME_SIZE - 1);
    circular = pattern["Circular"] | false;

    for (JsonArray strip : pattern["Strips"].as<JsonArray>()) 
    {    
        //loraPackets[loraPacketsCount].loadPacketParams(LoRaPackets);    
        strips[stripsCount] = new tLedStrip;
        strips[stripsCount]->loadFromJson(strip);
        stripsCount++;
        if (stripsCount >= LED_MAX_PATTERNS_NUM)
        {
            Serial.println("tLedPattern::loadFromJson ERROR: too many strips!!!");
            break;
        }
    }

}
    