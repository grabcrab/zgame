#pragma once
#include <Arduino.h>

enum tButtonResult 
{
    brNone,   // Кнопка не нажата
    brShort,  // Короткое нажатие (до 1 секунды)
    brLong    // Длинное нажатие (1-5 секунд)
};
