/**
 * @file      TFT_eSPI_Sprite.ino
 * @author    Lewis He (lewishe@outlook.com)
 * @license   MIT
 * @copyright Copyright (c) 2023  Shenzhen Xin Yuan Electronic Technology Co., Ltd
 * @date      2023-06-14
 *
 */

#include "rm67162.h"
#include <TFT_eSPI.h>   //https://github.com/Bodmer/TFT_eSPI
#include "true_color.h"
#include "tft_utils.h"

unsigned int rainbow(uint8_t value);
void drawRainbow();

#if ARDUINO_USB_CDC_ON_BOOT != 1
#warning "If you need to monitor printed data, be sure to set USB CDC On boot to ENABLE, otherwise you will not see any data in the serial monitor"
#endif

#ifndef BOARD_HAS_PSRAM
#error "Detected that PSRAM is not turned on. Please set PSRAM to OPI PSRAM in ArduinoIDE"
#endif

TFT_eSPI tft = TFT_eSPI();
TFT_eSprite spr = TFT_eSprite(&tft);



unsigned long targetTime = 0;
byte red = 31;
byte green = 0;
byte blue = 0;
byte state = 0;
unsigned int colour = red << 11;

//extern void tftDrawBmp(const char *filename, int16_t x, int16_t y);

void setupTFT(String textS = "BOOT")
{
    // Use TFT_eSPI Sprite made by framebuffer , unnecessary calling during use tft.xxxx function
    Serial.begin(115200);
    /*
    * Compatible with touch version
    * Touch version, IO38 is the screen power enable
    * Non-touch version, IO38 is an onboard LED light
    * * */
    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, HIGH);

    rm67162_init();
    //lcd_setRotation(3);
    lcd_setRotation(X_TFT_ROTATION);

    //tft.begin();
    // tft.setRotation(TFT_ROTATION);  // 0 & 2 Portrait. 1 & 3 landscape
    // tft.fillScreen(TFT_BLACK);



    spr.createSprite(X_TFT_WIDTH, X_TFT_HEIGHT);
    spr.setSwapBytes(1);
    
    // spr.pushImage(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)gImage_true_color);
    // lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
    // delay(2000);

    // spr.fillSprite(TFT_BLACK);
    // spr.fillRect(0, 0, 67, 120, TFT_RED);
    // spr.fillRect(67 * 1,  0, 67, 120, TFT_GREEN);
    // spr.fillRect(67 * 2,  0, 67, 120, TFT_BLUE);
    // spr.fillRect(67 * 3,  0, 67, 120, TFT_RED);
    // spr.fillRect(67 * 4,  0, 67, 120, TFT_GREEN);
    // spr.fillRect(67 * 5,  0, 67, 120, TFT_BLUE);
    // spr.fillRect(67 * 6,  0, 67, 120, TFT_RED);
    // spr.fillRect(67 * 7,  0, 67, 120, TFT_GREEN);
    // delay(3990);

    spr.fillSprite(TFT_BLACK);
    spr.setTextColor(TFT_GREEN, TFT_BLACK);
    spr.setTextDatum(MC_DATUM);
    spr.setTextSize(2);
    spr.drawString(textS, X_TFT_WIDTH/2, X_TFT_HEIGHT/2, 4);
    lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
    delay(500);
    spr.fillSprite(TFT_BLACK);
    lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
}


void tftPrintText(String txt, uint16_t bgColor, uint16_t txtColor)
{
    spr.fillSprite(bgColor);
    spr.setTextColor(txtColor, bgColor);
    spr.setTextDatum(MC_DATUM);
    spr.setTextSize(2);
    spr.drawString(txt, X_TFT_WIDTH/2, X_TFT_HEIGHT/2, 4);
    lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
}

void tftPrintThreeLines(String txt1, String txt2, String txt3, uint16_t bgColor, uint16_t txtColor)
{
    spr.fillSprite(bgColor);
    spr.setTextColor(txtColor, bgColor);
    spr.setTextSize(2);
    spr.setTextDatum(TC_DATUM);    
    spr.drawString(txt1, X_TFT_WIDTH/2, 5, 4);
    spr.setTextDatum(MC_DATUM);    
    spr.drawString(txt2, X_TFT_WIDTH/2, X_TFT_HEIGHT/2, 4);
    spr.setTextDatum(BC_DATUM);    
    spr.drawString(txt3, X_TFT_WIDTH/2, X_TFT_HEIGHT - 5, 4);    
    lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
}


void tSprite::init(TFT_eSPI *tft, int xx, int yy, int ww, int hh)
{
    spr = new TFT_eSprite(tft);
    sX = xx; sY = yy; sW = ww; sH = hh;
    spr->createSprite(sW, sH);
    spr->setSwapBytes(1);
}

tSprite::~tSprite()
{
    if (spr != NULL)
        delete spr;
}

extern uint16_t read16(fs::File &f);
extern uint32_t read32(fs::File &f);

void tSprite::drawBmp(const char *filename, int16_t x, int16_t y)
{

    if ((x >= spr->width()) || (y >= spr->height()))
    {
        Serial.println("***  tSprite::tftDrawBmp WARNING! Out of screen");
        return;
    }

    fs::File bmpFS;
    
    bmpFS = SPIFFS.open(filename, "r");

    if (!bmpFS)
    {
        Serial.println("!!! tSprite::tftDrawBmp: File not found");
        return;
    }

    uint32_t seekOffset;
    uint16_t w, h, row, col;
    uint8_t r, g, b;    

    uint32_t startTime = millis();

    if (read16(bmpFS) == 0x4D42)
    {
        read32(bmpFS);
        read32(bmpFS);
        seekOffset = read32(bmpFS);
        read32(bmpFS);
        w = read32(bmpFS);
        h = read32(bmpFS);

        if ((read16(bmpFS) == 1) && (read16(bmpFS) == 24) && (read32(bmpFS) == 0))
        {
            y += h - 1;            

            bool oldSwapBytes = spr->getSwapBytes();
            spr->setSwapBytes(true);
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

                spr->pushImage(x, y--, w, 1, (uint16_t*)lineBuffer, 16);                
                //spr.pushImage(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)gImage_true_color);
            }
            //lcd_PushColors(x, y, w, h, (uint16_t *)spr.getPointer());
            //lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr->getPointer());
            pushColors();
            spr->setSwapBytes(oldSwapBytes);
            Serial.print("Loaded in ");
            Serial.print(millis() - startTime);
            Serial.println(" ms");
        }
        else
            Serial.println("BMP format not recognized.");
    }
    bmpFS.close();
}

void tSprite::pushColors(void)
{
    lcd_PushColors(sX, sY, sW, sH, (uint16_t *)spr->getPointer());
}

void tSprite::clear(uint16_t bgColor)
{
    spr->fillSprite(bgColor);
    pushColors();
}

void tftTestBmp(void)
{
    // int w = 10;
    // int h = 10;
    tSprite spr;
    spr.init(&tft, 10, 10, 150, 150);

    spr.drawBmp("/bmp/parrot.bmp");
    while(true)
    {        
        //spr.clear(TFT_BLACK);
        //spr.drawBmp("/parrot.bmp");
        
        // int x = 5;
        // int y = 5;
        // tftDrawBmp("/parrot.bmp", x, y, w, h);
        // w += 3;
        // h += 3;    
        delay(100);
    }
}