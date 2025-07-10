#pragma once
#include <Arduino.h>

void serialCommInit(void);
void serialCommLoop(void);
bool isCommand(String comTxt, String comS);