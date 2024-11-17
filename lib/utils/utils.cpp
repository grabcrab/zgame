#include "utils.h"


void ledSet(uint8_t R, uint8_t G, uint8_t B, uint8_t LC, uint8_t LW)
{
    digitalWrite(RGB_RED_PIN, R);
    digitalWrite(RGB_GREEN_PIN, G);
    digitalWrite(RGB_BLUE_PIN, B);    
    if (LC != LED_DONT_CHANGE)
        digitalWrite(LC_PIN, LC);        
    if (LC != LED_DONT_CHANGE)
    digitalWrite(LW_PIN, LW);            
}

void ledInit(void)
{
    pinMode(RGB_RED_PIN, OUTPUT);
    digitalWrite(RGB_RED_PIN, LOW);     

    pinMode(RGB_GREEN_PIN ,OUTPUT);
    digitalWrite(RGB_GREEN_PIN, LOW);     

    pinMode(RGB_BLUE_PIN ,OUTPUT);
    digitalWrite(RGB_BLUE_PIN, LOW);     
        
    pinMode(LC_PIN, OUTPUT);
    digitalWrite(LC_PIN, LOW);     
    
    pinMode(LW_PIN, OUTPUT);
    digitalWrite(LW_PIN, LOW);        
}

void ledHello(void)
{
    ledSet(1, 0, 0, 0, 0);
    delay(LED_HELLO_DELAY);
    ledSet(0, 1, 0, 0, 0);
    delay(LED_HELLO_DELAY);
    ledSet(0, 0, 1, 0, 0);
    delay(LED_HELLO_DELAY);
    ledSet(0, 0, 0, 1, 0);
    delay(LED_HELLO_DELAY);    
    ledSet(0, 0, 0, 0, 1);
    delay(LED_HELLO_DELAY);    
    ledSet(0, 0, 0, 0, 0);
}

void ledRed(tLedState ls)
{
    uint8_t ledState = uint8_t (ls);
    ledSet(ledState, 0, 0, digitalRead(LC_PIN), digitalRead(LW_PIN));
}

void ledGreen(tLedState ls)
{
    uint8_t ledState = uint8_t (ls);
    ledSet(0, ledState, 0, digitalRead(LC_PIN), digitalRead(LW_PIN));
}

void ledBlue(tLedState ls)
{
    uint8_t ledState = uint8_t (ls);
    ledSet(0, 0, ledState, digitalRead(LC_PIN), digitalRead(LW_PIN));
}

void ledRgbOff(void)
{
    ledSet(0, 0, 0, 0, 0);
}