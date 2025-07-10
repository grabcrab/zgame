#include "ledPlayer.h"

void tLedPlayer::print(void)
{
    Serial.println(">>> LED PATTERNS:");
    for (int i = 0; i < patternsCount; i++)
    {
        patterns[i]->print();
    }
    Serial.println("---------------------------");
}

tLedPattern *tLedPlayer::findPatternByName(String patternName)
{    
    for (int i = 0; i < patternsCount; i++)
    {
        if (patternName == patterns[i]->name)
            return patterns[i];
    }
    return NULL;
}

bool tLedPlayer::loadFromJsonFile(void)
{
    JsonDocument doc;   

    if (loaded)
        return true;
        
    loaded = true; 

    if(!SPIFFS.begin(true, "/spiffs", 2))
        if(!SPIFFS.begin(true, "/spiffs", 2))
        {
            Serial.println("!!! tLedPlayer::loadFromJsonFile: ERROR while mounting SPIFFS!");    
            return false;
        }      

    File f = SPIFFS.open(LED_FILE_NAME, "r");
    if (!f)
    {
        Serial.printf("tLedPlayer::loadFromJsonFile: ERROR loading from <%s>\r\n", LED_FILE_NAME);
        return false;
    }
    
    DeserializationError error = deserializeJson(doc, f);
    if (error)
    {
        Serial.printf("JSON deserialize ERROR [%s]\r\n", error.c_str());
        return false;
    }

    for (JsonObject pattern : doc["LedPatterns"].as<JsonArray>()) 
    {    
        patterns[patternsCount] = new tLedPattern;
        patterns[patternsCount]->loadFromJson(pattern);
        patternsCount++;

        if (patternsCount >= LED_MAX_PATTERNS_NUM)
        {
            Serial.println("tLedPlayer::loadFromJsonFile ERROR: too many patterns!!!");
            break;
        }
    }   

    return true;
}