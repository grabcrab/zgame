#include "valPlayer.h"
#include "tft_utils.h"

void valTest(void)
{
    if (!valPlayerInit())
    {
        while(1)
        {
            Serial.println("Error VAL init!!!");
            delay(1000);
        }
    }
    while(true)
    {
        if (valPlayNext())
        {
            tValStatus newStat;
            delay(100);
            if (valGetStatus(&newStat))
            {
                Serial.printf("--> Now playing: %s\r\n", newStat.nowPlayingName.c_str());
                tftPrintText(newStat.nowPlayingName);
                unsigned long startMs = millis();
                while(true)
                {
                    if (valGetStatus(&newStat))
                        if(!newStat.isPlaying)
                            break;
                    delay(100);
                    if (millis() - startMs > 10000)
                        break;
                }
                Serial.printf("*** COMPLETED in %d ms\r\n\n", millis() - startMs);
            }
        }
        else
        {
            Serial.println("Error playing next");
        }
    }
}


// void ledTest(void)
// {
//     tLedPattern *pattern;

//     if (valPlayer.loadFromJsonFile())
//     {
//         valPlayer.print();
//     }
//     else 
//     {
//         Serial.println("ledTest: JSON ERROR!!!");
//         return;
//     }

//     Serial.println(">>>TestOne");
//     pattern = valPlayer.findPatternByName("TestOne");
//     if (pattern != NULL)
//     {
//         pattern->print();
//         pattern->start();
//         for(int i = 0; i < 2000; i++)
//         {
//             pattern->loopPlay();
//             delay(1);
//         }
//     }
//     else 
//     {
//         Serial.println("Can't find <TestOne> pattern");
//     }

//     Serial.println(">>>TestTwo");
//     pattern = valPlayer.findPatternByName("TestTwo");
//     if (pattern != NULL)
//     {
//         pattern->print();
//         pattern->start();
//         for(int i = 0; i < 2000; i++)
//         {
//             pattern->loopPlay();
//             delay(1);
//         }
//     }
//     else 
//     {
//         Serial.println("Can't find <TestTwo> pattern");
//     }
//     Serial.println(">>>TestDone");
// }



