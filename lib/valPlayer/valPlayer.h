#pragma once

#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include <FS.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>

#include "xErrCodes.h"

#define VAL_PIXELS_NUM          8
#define VAL_PATTERN_NAME_SIZE   30
#define VAL_MP3_NAME_SIZE       30
#define VAL_MAX_STRIPS_NUM      30
#define VAL_MAX_PATTERNS_NUM    30
#define VAL_FILE_NAME           "/val.json"
#define VAL_TASK_DELAY_MS       10
#define VAL_PLAYING_NAME        "$$$$PLAY$$$"
#define VAL_NEXT_NAME           "$$$$NEXT$$$$"

struct tLedPixel
{
    uint8_t r = 0;
    uint8_t g = 0;
    uint8_t b = 0;    
    void print(void);
    void set(String hexS);
    void play(uint8_t pxNum);
};

struct tLedStrip
{       
    tLedPixel pixels[VAL_PIXELS_NUM];
    uint16_t  intervalMs;
    bool vibro;
    void print(void);
    unsigned long play(void);
    void loadFromJson(JsonArray strip);
};  

struct tLedPattern
{
    char name[VAL_PATTERN_NAME_SIZE] = "";
    tLedStrip *strips[VAL_MAX_STRIPS_NUM];
    uint16_t stripsCount = 0;
    bool circular = false;
    unsigned long nextStripMs = 0;
    uint16_t stripIdx = 0;
    bool PlaySound = false;
    char SoundFile[VAL_MP3_NAME_SIZE] = "";
    uint8_t SoundLevel = 0;
    bool isPlaying = false;
    void print(void);
    void start(void);
    void loopPlay(void);
    void loadFromJson(JsonObject pattern);
};

struct tValPlayer
{
    bool loaded = false;
    tLedPattern *patterns[VAL_MAX_PATTERNS_NUM];
    uint16_t patternsCount = 0;  
    tLedPattern *currPattern = NULL;  
    int16_t patternIdx = -1;
    void print(void);
    //void init(void);
    static void valTask(void* valPlr);
    void setPatternByName(String patternName);
    void setPatternByIdx(uint16_t idx);
    void updateCurrPattern(void);
    void updateIsPlaying(void);
    void loopPlayer(void);
    bool loadFromJsonFile(void);
    void startTask(void);
};

struct tValStatus
{
    bool isPlaying = false;
    bool error = false;
    String patternName = ""; 
    String nowPlayingName = "";
    int nowPlayingIdx = -1;      
    inline void setPatternName(String s){patternName = s;}
    inline void set(tValStatus *st)
    {
        isPlaying = st->isPlaying; error = st->error; patternName = st->patternName; nowPlayingName = st->nowPlayingName; nowPlayingIdx = st->nowPlayingIdx;
    }
};


bool valPlayerInit(void);
tValStatus *valTakeStatus(void);
bool valGetStatus(tValStatus *newStat);
void valGiveStatus(void);
bool valPlayNext(void);
bool valPlayPattern(String patternName);

extern Adafruit_NeoPixel neoPixels;
// extern tValPlayer valPlayer;

//int i = sizeof(tValPlayer);

void audioLoop(void);
bool audioPlay(const char *fName, int volume);

void valPlayError(uint8_t errB);

void valTest(void);

//void startLedTestTask(void);
