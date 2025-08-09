#pragma once
#include <Arduino.h>

#define BUTTON_PIN    0
#define ACCEL_INT_PIN 13

#define KXTJ3_ADDR 0x0F


void boardPowerOn(void);
void boardPowerOff(void);
uint16_t boardGetVcc(void);
uint8_t boardGetVccPercent(void);

bool accelInit(void);
bool accelWakeOnShake(void);

void boardStartSleep(bool btnWake = true, bool accelWake = true);