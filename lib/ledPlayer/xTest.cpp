#include "ledPlayer.h"

void ledTest(void)
{
    tLedPattern *pattern;

    if (ledPlayer.loadFromJsonFile())
    {
        ledPlayer.print();
    }
    else 
    {
        Serial.println("ledTest: JSON ERROR!!!");
        return;
    }

    Serial.println(">>>TestOne");
    pattern = ledPlayer.findPatternByName("TestOne");
    if (pattern != NULL)
    {
        pattern->print();
        pattern->start();
        for(int i = 0; i < 2000; i++)
        {
            pattern->loopPlay();
            delay(1);
        }
    }
    else 
    {
        Serial.println("Can't find <TestOne> pattern");
    }

    Serial.println(">>>TestTwo");
    pattern = ledPlayer.findPatternByName("TestTwo");
    if (pattern != NULL)
    {
        pattern->print();
        pattern->start();
        for(int i = 0; i < 2000; i++)
        {
            pattern->loopPlay();
            delay(1);
        }
    }
    else 
    {
        Serial.println("Can't find <TestTwo> pattern");
    }
    Serial.println(">>>TestDone");
}

void ledTestTask(void*)
{
    while(true)
    {
        ledTest();
    }
}

void startLedTestTask(void)
{
    xTaskCreatePinnedToCore(
    ledTestTask,             /* Function to implement the task */
    "edTestTask",           /* Name of the task */
    10000,                  /* Stack size in words */
    NULL,                  /* Task input parameter */
    3, /* Priority of the task */
    NULL,                  /* Task handle. */
    1                      /* Core where the task should run */
);
}