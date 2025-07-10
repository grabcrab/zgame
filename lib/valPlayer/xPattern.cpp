#include "valPlayer.h"

void tLedPattern::print(void)
{
    Serial.printf("\t<%s>", name);
    if (circular) 
        Serial.print(" <CIRC>");

    if (PlaySound)
    {
        Serial.printf(" <SoundFile = %s : %d>", SoundFile, SoundLevel);
    }
    
    Serial.println();
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
    isPlaying = true;
    if (PlaySound)
    {
        audioPlay(SoundFile, SoundLevel);
    }
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
            {
                stripIdx = 0;
                if (PlaySound)
                {
                    audioPlay(SoundFile, SoundLevel);
                }
            }
            else
            {
                isPlaying = false; 
                stripIdx--;
            }
        }
    }
    if (PlaySound)
        audioLoop();
}

void tLedPattern::loadFromJson(JsonObject pattern)
{
    strncpy(name, pattern["PatternName"] | "NO_NAME", VAL_PATTERN_NAME_SIZE - 1);
    circular   = pattern["Circular"] | false;
    strncpy(SoundFile, pattern["SoundFile"] | "NA", VAL_MP3_NAME_SIZE - 1);
    SoundLevel = pattern["SoundLevel"];
    PlaySound  = pattern["PlaySound"];
    for (JsonArray strip : pattern["Strips"].as<JsonArray>()) 
    {    
        //loraPackets[loraPacketsCount].loadPacketParams(LoRaPackets);    
        strips[stripsCount] = new tLedStrip;
        strips[stripsCount]->loadFromJson(strip);
        stripsCount++;
        if (stripsCount >= VAL_MAX_PATTERNS_NUM)
        {
            Serial.println("tLedPattern::loadFromJson ERROR: too many strips!!!");
            break;
        }
    }

}
    