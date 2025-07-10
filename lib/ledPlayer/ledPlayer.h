#pragma once

#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include <FS.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>

#define LED_PIXELS_NUM 8
#define LED_PATTERN_NAME_SIZE 30
#define LED_MAX_STRIPS_NUM  30
#define LED_MAX_PATTERNS_NUM  30
#define LED_FILE_NAME   "/led.json"

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
    tLedPixel pixels[LED_PIXELS_NUM];
    uint16_t  intervalMs;
    void print(void);
    unsigned long play(void);
    void loadFromJson(JsonArray strip);
};  

struct tLedPattern
{
    char name[LED_PATTERN_NAME_SIZE] = "";
    tLedStrip *strips[LED_MAX_STRIPS_NUM];
    uint16_t stripsCount = 0;
    bool circular = false;
    unsigned long nextStripMs = 0;
    uint16_t stripIdx = 0;
    void print(void);
    void start(void);
    void loopPlay(void);
    void loadFromJson(JsonObject pattern);
};

struct tLedPlayer
{
    bool loaded = false;
    tLedPattern *patterns[LED_MAX_PATTERNS_NUM];
    uint16_t patternsCount = 0;
    void print(void);
    //void init(void);
    tLedPattern *findPatternByName(String patternName);
    bool loadFromJsonFile(void);
};

extern Adafruit_NeoPixel neoPixels;
extern tLedPlayer ledPlayer;

//int i = sizeof(tLedPlayer);

void ledTest(void);
void startLedTestTask(void);
