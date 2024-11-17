#ifndef __UTILS_H__
#define __UTILS_H__

#include <Arduino.h>

#define RGB_RED_PIN     3
#define RGB_GREEN_PIN   4
#define RGB_BLUE_PIN    5
#define LW_PIN          19
#define LC_PIN          18
#define LED_DONT_CHANGE 100
#define LED_HELLO_DELAY 300


enum tLedState
{
    lsOff = 0,
    lsOn  = 1
};

void ledInit(void);
void ledSet(uint8_t R, uint8_t G, uint8_t B, uint8_t LC = LED_DONT_CHANGE, uint8_t LW = LED_DONT_CHANGE);
void ledHello(void);
void ledRed(tLedState ls);
void ledGreen(tLedState ls);
void ledBlue(tLedState ls);
void ledRgbOff(void);


#endif //__UTILS_H__