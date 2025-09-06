#include "valPlayer.h"
Adafruit_NeoPixel neoPixels(VAL_PIXELS_NUM, PIN_LED_MATRIX, NEO_GRB + NEO_KHZ800);
static SemaphoreHandle_t statusMutex;
static tValStatus valStatus;
static tValPlayer valPlayer;

tValStatus *valTakeStatus(void)
{
    tValStatus *resPtr = NULL;
    if (xSemaphoreTake(statusMutex, 30 ) == pdTRUE)
    {
        resPtr = &valStatus;
    }
    return resPtr;
}

void valGiveStatus(void)
{
    xSemaphoreGive(statusMutex);
}

bool valGetStatus(tValStatus *newStat)
{
    tValStatus *statusPtr = valTakeStatus();
    if (statusPtr != NULL)
    {
        newStat->set(statusPtr);
        valGiveStatus();
        return true;  
    }
    else
    {
        
    }
    return false;
}

void tValPlayer::updateCurrPattern(void)
{
    tValStatus *statusPtr = valTakeStatus();
    String nameToPlay = "";
    if (statusPtr != NULL)
    {       
        String newPatternS = statusPtr->patternName;     
        if ((newPatternS != "") && (newPatternS != VAL_PLAYING_NAME))                
        {   
            if (newPatternS == VAL_NEXT_NAME)
            {
                if (patternsCount)
                {
                    patternIdx++;
                    if (patternIdx >= patternsCount)
                        patternIdx = 0;                    
                    setPatternByIdx(patternIdx);
                }
            }
            else
            {
                setPatternByName(statusPtr->patternName);
            }                    
        
            if (currPattern != NULL)
            {
                statusPtr->error = false;
                statusPtr->isPlaying = true;
                statusPtr->nowPlayingName = currPattern->name;
                statusPtr->nowPlayingIdx = patternIdx;
                currPattern->start();
                Serial.printf(">>> New pattern playing: %s\r\n", currPattern->name);
            }
            else
            {
                statusPtr->error = true;
                statusPtr->isPlaying = false;  
                statusPtr->nowPlayingName = "ERROR";  
                statusPtr->nowPlayingIdx = -1;            
            }
        }
        statusPtr->setPatternName(VAL_PLAYING_NAME);
        valGiveStatus();
    }
}

void tValPlayer::updateIsPlaying(void)
{
    tValStatus *statusPtr = valTakeStatus();
    if (statusPtr != NULL)
    {
        if (currPattern == NULL)
        {
            statusPtr->isPlaying = false;
        }
        else
        {
            statusPtr->isPlaying = currPattern->isPlaying;
        }
        valGiveStatus();     
    }
}

void tValPlayer::loopPlayer(void)
{
    if (currPattern != NULL)
    {
        currPattern->loopPlay();
    }
}

void tValPlayer::valTask(void* valPlr)
{
    tValPlayer *valPlayer = (tValPlayer *) valPlr;       

    while(true)
    {    
        valPlayer->updateCurrPattern();
        valPlayer->loopPlayer();
        valPlayer->updateIsPlaying();
        delay(VAL_TASK_DELAY_MS );
    }
}

void tValPlayer::startTask(void)
{
    xTaskCreatePinnedToCore(
    valTask,             /* Function to implement the task */
    "valTask",           /* Name of the task */
    10000,                  /* Stack size in words */
    this,                  /* Task input parameter */
    3, /* Priority of the task */
    NULL,                  /* Task handle. */
    1                      /* Core where the task should run */
);
}

#include "valPlayer.h"

void tValPlayer::print(void)
{
    Serial.println(">>> LED PATTERNS:");
    for (int i = 0; i < patternsCount; i++)
    {
        patterns[i]->print();
    }
    Serial.println("---------------------------");
}

void tValPlayer::setPatternByName(String patternName)
{            
    for (int i = 0; i < patternsCount; i++)
    {
        patternIdx = i;
        if (patternName == patterns[i]->name)
        {
            currPattern = patterns[i];
            return;
        }
    }   
    Serial.printf("!!! tValPlayer::setPatternByName ERROR: can't find pattern!!!");         
}

void tValPlayer::setPatternByIdx(uint16_t idx)
{
    if (idx >= patternsCount)
    {
        Serial.println("!!! tValPlayer::getPatternByIdx ERROR: the idx is too big");        
    }
    else
    {
        currPattern = patterns[idx];
    }
}

bool tValPlayer::loadFromJsonFile(void)
{
    JsonDocument doc;   

    if (loaded)
        return true;
        
    loaded = true;    

    File f = PSRamFS.open(VAL_FILE_NAME, "r");
    if (!f)
    {
        Serial.printf("tValPlayer::loadFromJsonFile: ERROR loading from <%s>\r\n", VAL_FILE_NAME);
        valPlayError(ERR_VAL_LOAD);
        return false;
    }
    
    DeserializationError error = deserializeJson(doc, f);
    if (error)
    {
        Serial.printf("JSON deserialize ERROR [%s]\r\n", error.c_str());
        valPlayError(ERR_VAL_JSON);
        f.close();
        return false;
    }

    for (JsonObject pattern : doc["PlayPatterns"].as<JsonArray>()) 
    {    
        patterns[patternsCount] = new tLedPattern;
        patterns[patternsCount]->loadFromJson(pattern);
        patternsCount++;

        if (patternsCount >= VAL_MAX_PATTERNS_NUM)
        {
            Serial.println("tValPlayer::loadFromJsonFile ERROR: too many patterns!!!");
            break;
        }
    }   
    f.close();
    return true;
}

bool valPlayerInit(void)
{
    if (valPlayer.loadFromJsonFile())
    {
        valPlayer.print();
        statusMutex = xSemaphoreCreateMutex(); 
        valPlayer.startTask();
        return true;
    }
    Serial.println("valPlayerInit: JSON ERROR!!!");
    return false;
}

bool valPlayNext(void)
{
    String resS = "";
    tValStatus *valStatus = valTakeStatus();
    if (valStatus == NULL)
    {
        Serial.println("!!! valPlayNext ERROR. Can't get mutex");
        return false;
    }
    valStatus->setPatternName(VAL_NEXT_NAME);
    valGiveStatus();
    return true;
}

bool valPlayPattern(String patternName)
{
    String resS = "";
    tValStatus *valStatus = valTakeStatus();
    if (valStatus == NULL)
    {
        Serial.println("!!! valPlayPattern ERROR. Can't get mutex");
        return false;
    }
    valStatus->setPatternName(patternName);
    valGiveStatus();
    return true;
}