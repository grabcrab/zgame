#include <FS.h>
#include <SPIFFS.h>
#include "TFT_eSPI.h"
#include "rm67162.h"
#include "PSRamFS.h"

extern TFT_eSprite spr;

uint16_t read16(fs::File &f)
{
    uint16_t result;
    ((uint8_t *)&result)[0] = f.read(); // LSB
    ((uint8_t *)&result)[1] = f.read(); // MSB
    return result;
}

uint32_t read32(fs::File &f)
{
    uint32_t result;
    ((uint8_t *)&result)[0] = f.read(); // LSB
    ((uint8_t *)&result)[1] = f.read();
    ((uint8_t *)&result)[2] = f.read();
    ((uint8_t *)&result)[3] = f.read(); // MSB
    return result;
}
#include "true_color.h"
void tftDrawBmp(const char *filename, int16_t x, int16_t y, uint16_t wLimit, uint16_t hLimit)
{

    if ((x >= spr.width()) || (y >= spr.height()))
    {
        Serial.println("*** tftDrawBmp WARNING! Out of screen");
        return;
    }

    fs::File bmpFS;

    // Open requested file on SD card
    bmpFS = PSRamFS.open(filename, "r");

    if (!bmpFS)
    {
        Serial.print("!!!tftDrawBmp ERROR. File not found: ");
        Serial.println(filename);
        return;
    }

    uint32_t seekOffset;
    uint16_t w, h, row, col;
    uint8_t r, g, b;
    int16_t maxY;

    uint32_t startTime = millis();

    if (read16(bmpFS) == 0x4D42)
    {
        read32(bmpFS);
        read32(bmpFS);
        seekOffset = read32(bmpFS);
        read32(bmpFS);
        w = read32(bmpFS);
        h = read32(bmpFS);

        
       // if ((wLimit > w) || (!wLimit))
            wLimit = w;
        
        if ((hLimit > h) || (!hLimit))
            hLimit = h;

        maxY = y + hLimit;
        

        if ((read16(bmpFS) == 1) && (read16(bmpFS) == 24) && (read32(bmpFS) == 0))
        {
            y += h - 1;            

            bool oldSwapBytes = spr.getSwapBytes();
            spr.setSwapBytes(true);
            bmpFS.seek(seekOffset);

            uint16_t padding = (4 - ((w * 3) & 3)) & 3;
            uint8_t lineBuffer[w * 3 + padding];

            for (row = 0; row < h; row++)
            {

                bmpFS.read(lineBuffer, sizeof(lineBuffer));
                uint8_t *bptr = lineBuffer;
                uint16_t *tptr = (uint16_t *)lineBuffer;
                // Convert 24 to 16-bit colours
                for (uint16_t col = 0; col < w; col++)
                {
                    b = *bptr++;
                    g = *bptr++;
                    r = *bptr++;
                    *tptr++ = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
                }

                // Push the pixel row to screen, pushImage will crop the line if needed
                // y is decremented as the BMP image is drawn bottom up
                //Serial.printf("%d %d\r\n", y, maxY);
                //if (y < maxY)
                    spr.pushImage(x, y--, wLimit, 1, (uint16_t*)lineBuffer, 16);                
                //spr.pushImage(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)gImage_true_color);
            }
            //lcd_PushColors(x, y, w, h, (uint16_t *)spr.getPointer());
            lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
            spr.setSwapBytes(oldSwapBytes);
            Serial.printf(">>> <%s> Loaded in ", filename);
            Serial.print(millis() - startTime);
            Serial.println(" ms");
        }
        else
            Serial.println("BMP format not recognized.");
    }
    bmpFS.close();
}

void tftDrawBmpToSprite(const char *filename, int16_t x, int16_t y, uint16_t wLimit, uint16_t hLimit, TFT_eSprite &spr)
{

    if ((x >= spr.width()) || (y >= spr.height()))
    {
        Serial.println("*** tftDrawBmp WARNING! Out of screen");
        return;
    }

    fs::File bmpFS;

    // Open requested file on SD card
    bmpFS = PSRamFS.open(filename, "r");

    if (!bmpFS)
    {
        Serial.print("!!!tftDrawBmp ERROR. File not found: ");
        Serial.println(filename);
        return;
    }

    uint32_t seekOffset;
    uint16_t w, h, row, col;
    uint8_t r, g, b;
    int16_t maxY;

    uint32_t startTime = millis();

    if (read16(bmpFS) == 0x4D42)
    {
        read32(bmpFS);
        read32(bmpFS);
        seekOffset = read32(bmpFS);
        read32(bmpFS);
        w = read32(bmpFS);
        h = read32(bmpFS);

        
       // if ((wLimit > w) || (!wLimit))
            wLimit = w;
        
        if ((hLimit > h) || (!hLimit))
            hLimit = h;

        maxY = y + hLimit;
        

        if ((read16(bmpFS) == 1) && (read16(bmpFS) == 24) && (read32(bmpFS) == 0))
        {
            y += h - 1;            

            bool oldSwapBytes = spr.getSwapBytes();
            spr.setSwapBytes(true);
            bmpFS.seek(seekOffset);

            uint16_t padding = (4 - ((w * 3) & 3)) & 3;
            uint8_t lineBuffer[w * 3 + padding];

            for (row = 0; row < h; row++)
            {

                bmpFS.read(lineBuffer, sizeof(lineBuffer));
                uint8_t *bptr = lineBuffer;
                uint16_t *tptr = (uint16_t *)lineBuffer;
                // Convert 24 to 16-bit colours
                for (uint16_t col = 0; col < w; col++)
                {
                    b = *bptr++;
                    g = *bptr++;
                    r = *bptr++;
                    *tptr++ = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
                }

                // Push the pixel row to screen, pushImage will crop the line if needed
                // y is decremented as the BMP image is drawn bottom up
                //Serial.printf("%d %d\r\n", y, maxY);
                //if (y < maxY)
                    spr.pushImage(x, y--, wLimit, 1, (uint16_t*)lineBuffer, 16);                
                //spr.pushImage(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)gImage_true_color);
            }
            //lcd_PushColors(x, y, w, h, (uint16_t *)spr.getPointer());
            lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
            spr.setSwapBytes(oldSwapBytes);
            Serial.printf(">>> <%s> Loaded in ", filename);
            Serial.print(millis() - startTime);
            Serial.println(" ms");
        }
        else
            Serial.println("BMP format not recognized.");
    }
    bmpFS.close();
}


// void tftDrawBmp(const char *filename, int16_t x, int16_t y)
// {

//     if ((x >= spr.width()) || (y >= spr.height()))
//     {
//         Serial.println("*** tftDrawBmp WARNING! Out of screen");
//         return;
//     }

//     fs::File bmpFS;

//     // Open requested file on SD card
//     bmpFS = SPIFFS.open(filename, "r");

//     if (!bmpFS)
//     {
//         Serial.print("File not found");
//         return;
//     }

//     uint32_t seekOffset;
//     uint16_t w, h, row, col;
//     uint8_t r, g, b;

//     uint32_t startTime = millis();

//     if (read16(bmpFS) == 0x4D42)
//     {
//         read32(bmpFS);
//         read32(bmpFS);
//         seekOffset = read32(bmpFS);
//         read32(bmpFS);
//         w = read32(bmpFS);
//         h = read32(bmpFS);

//         if ((read16(bmpFS) == 1) && (read16(bmpFS) == 24) && (read32(bmpFS) == 0))
//         {
//             y += h - 1;

//             bool oldSwapBytes = spr.getSwapBytes();
//             spr.setSwapBytes(false);
//             bmpFS.seek(seekOffset);

//             uint16_t padding = (4 - ((w * 3) & 3)) & 3;
//             uint8_t lineBuffer[w * 3 + padding];

//             for (row = 0; row < h; row++)
//             {

//                 bmpFS.read(lineBuffer, sizeof(lineBuffer));
//                 uint8_t *bptr = lineBuffer;
//                 uint16_t *tptr = (uint16_t *)lineBuffer;
//                 // Convert 24 to 16-bit colours
//                 for (uint16_t col = 0; col < w; col++)
//                 {
//                     b = *bptr++;
//                     g = *bptr++;
//                     r = *bptr++;
//                     *tptr++ = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
//                 }

//                 // Push the pixel row to screen, pushImage will crop the line if needed
//                 // y is decremented as the BMP image is drawn bottom up
//                 spr.pushImage(x, y--, w, 1, (uint16_t *)lineBuffer);                
//             }
//             lcd_PushColors(x, y, w, h, (uint16_t *)spr.getPointer());
//             spr.setSwapBytes(oldSwapBytes);
//             Serial.print("Loaded in ");
//             Serial.print(millis() - startTime);
//             Serial.println(" ms");
//         }
//         else
//             Serial.println("BMP format not recognized.");
//     }
//     bmpFS.close();
// }

