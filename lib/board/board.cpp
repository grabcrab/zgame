#include <board.h>

void boardPowerOn(void)
{
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, HIGH);
}

void boardPowerOff(void)
{
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, LOW);
}