#include "tft_utils.h"
#include "rm67162.h"

#define TFT_GAME_ICO_X  50
#define TFT_GAME_ICO_Y  (240 - 160) / 2
#define TFT_GAME_ICO_W  160
#define TFT_GAME_ICO_H  160
#define TFT_GAME_TOP_FONT   4
#define TFT_GAME_BOT_FONT   4

#define TFT_GAME_BASE_ICO_FNAME "/base_ico.bmp"
#define TFT_GAME_ZOMB_ICO_FNAME "/zomb_ico.bmp"
#define TFT_GAME_HUMN_ICO_FNAME "/hum_ico.bmp"

#define TFT_GAME_B_COLOR       TFT_YELLOW
#define TFT_GAME_H_COLOR       TFT_RED
#define TFT_GAME_Z_COLOR       TFT_GREEN


extern TFT_eSPI tft;
extern TFT_eSprite spr;
static bool bmpUpdated = false;

static void drawBitmap(String fName)
{
    static bool wasInit;
    static String fName__ = "";    
    if (fName == fName__)
    {
        bmpUpdated = false;
        return;
    }
    bmpUpdated = true;
    fName__ = fName;
    spr.fillSprite(TFT_BLACK);
    tftDrawBmp(fName.c_str(), TFT_GAME_ICO_X, TFT_GAME_ICO_Y, TFT_GAME_ICO_W, TFT_GAME_ICO_H);   
    lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
}

static void drawStr1(uint16_t txtColor, String str1)
{
    static TFT_eSprite sprStr1= TFT_eSprite(&tft);
    const uint16_t sprWidth = X_TFT_WIDTH - TFT_GAME_ICO_X - TFT_GAME_ICO_W;
    const uint16_t sprHeight = 100;
    const uint16_t sprX = TFT_GAME_ICO_X + TFT_GAME_ICO_W;
    const uint16_t sprY = X_TFT_HEIGHT / 2 - (sprHeight/2);
    static bool wasInit;
    static String str1__ = "";
    if (!wasInit)
    {
        sprStr1.createSprite(sprWidth, sprHeight);
        sprStr1.setSwapBytes(1);
        wasInit = true;
    }
    if ((str1 == str1__) && (!bmpUpdated))
    {
        return;
    }
    str1__ = str1;
    sprStr1.fillSprite(TFT_BLACK);
    sprStr1.setTextColor(txtColor, TFT_BLACK);
    sprStr1.setTextSize(8);    
    sprStr1.setTextDatum(MC_DATUM);    
    sprStr1.drawString(str1, sprWidth/2, sprHeight/2, 1);    
    lcd_PushColors(sprX, sprY, sprWidth, sprHeight, (uint16_t *)sprStr1.getPointer());
}

static void drawStr2(uint16_t txtColor, String str2)
{
    static TFT_eSprite sprStr2 = TFT_eSprite(&tft);
    const uint16_t sprWidth = X_TFT_WIDTH - TFT_GAME_ICO_X - TFT_GAME_ICO_W;
    const uint16_t sprHeight = 90;
    const uint16_t sprX = TFT_GAME_ICO_X + TFT_GAME_ICO_W;
    const uint16_t sprY = X_TFT_HEIGHT - sprHeight;
    static bool wasInit;
    static String str2__ = "";
    if (!wasInit)
    {
        sprStr2.createSprite(sprWidth, sprHeight);
        sprStr2.setSwapBytes(1);
        wasInit = true;
    }
    if ((str2 == str2__) && (!bmpUpdated))
    {
        return;
    }
    str2__ = str2;
    sprStr2.fillSprite(TFT_BLACK);
    sprStr2.setTextColor(txtColor, TFT_BLACK);
    sprStr2.setTextSize(4);    
    sprStr2.setTextDatum(MC_DATUM);        
    sprStr2.drawString(str2, sprWidth/2, sprHeight/2, 1);    
    lcd_PushColors(sprX, sprY, sprWidth, sprHeight, (uint16_t *)sprStr2.getPointer());
}

static void drawSecStr(uint16_t txtColor, String secS)
{
    static TFT_eSprite sprSec = TFT_eSprite(&tft);
    const uint16_t sprWidth = X_TFT_WIDTH - TFT_GAME_ICO_X - TFT_GAME_ICO_W;
    const uint16_t sprHeight = 60;
    const uint16_t sprX = TFT_GAME_ICO_X + TFT_GAME_ICO_W;
    const uint16_t sprY = 0;
    static bool wasInit;
    static String secS__ = "";
    if (!wasInit)
    {
        sprSec.createSprite(sprWidth, sprHeight);
        sprSec.setSwapBytes(1);
        wasInit = true;
    }
    if ((secS == secS__) && (!bmpUpdated))
    {
        return;
    }
    secS__ = secS;
    sprSec.fillSprite(TFT_BLACK);
    sprSec.setTextColor(txtColor, TFT_BLACK);
    sprSec.setTextSize(4);    
    sprSec.setTextDatum(MC_DATUM);        
    sprSec.drawString(secS, sprWidth/2, sprHeight/2, 1);    
    lcd_PushColors(sprX, sprY, sprWidth, sprHeight, (uint16_t *)sprSec.getPointer());
}

void tftGameScreenRaw(String fName, uint16_t txtColor, String str1, String str2, String secStr)
{
    drawBitmap(fName);
    drawStr1(txtColor, str1);
    drawStr2(txtColor, str2);
    drawSecStr(txtColor, secStr);
    // spr.fillSprite(TFT_BLACK);
    // tftDrawBmp(fName.c_str(), TFT_GAME_ICO_X, TFT_GAME_ICO_Y, TFT_GAME_ICO_W, TFT_GAME_ICO_H);
    // spr.setTextColor(txtColor, TFT_BLACK);
    // spr.setTextSize(8);    
    // spr.setTextDatum(TC_DATUM);    
    // spr.drawString(str1, (X_TFT_WIDTH - TFT_GAME_ICO_W - TFT_GAME_ICO_X)/2 + 200, 90, 1);
    // spr.setTextSize(2);    
    // spr.setTextDatum(TC_DATUM);    
    // spr.drawString(str2, (X_TFT_WIDTH - TFT_GAME_ICO_W - TFT_GAME_ICO_X)/2 + 190, 170, 4);    
    // spr.setTextDatum(TC_DATUM);    
    // spr.drawString(secStr, (X_TFT_WIDTH - TFT_GAME_ICO_W - TFT_GAME_ICO_X)/2 + 190, 10, 4);    

    // lcd_PushColors(0, 0, X_TFT_WIDTH, X_TFT_HEIGHT, (uint16_t *)spr.getPointer());
}

static String botVal2Str(int32_t botVal)
{
    String botStr = String(botVal);
    if (botVal > 0)
    {
        botStr = "+ " + botStr;
    }

    if (botVal < 0)
    {
        botStr = "- " + String(-botVal);
    }

    if (botVal == 0)
    {
        botStr = "0";
    }
    return botStr;
}

static String mmss(int totalSeconds)
{
  int m = abs(totalSeconds) / 60;
  int s = abs(totalSeconds) % 60;

  char buf[6];                // "mm:ss\0"
  sprintf(buf, "%02d:%02d", m, s);
  return String(buf);
}

void tftGameScreenBase(int32_t topVal, int32_t botVal, uint32_t secLeft)
{
    tftGameScreenRaw(TFT_GAME_BASE_ICO_FNAME, TFT_GAME_B_COLOR, String (topVal), botVal2Str(botVal), mmss(secLeft));
}

void tftGameScreenHuman(int32_t topVal, int32_t botVal, uint32_t secLeft)
{
    tftGameScreenRaw(TFT_GAME_HUMN_ICO_FNAME, TFT_GAME_H_COLOR, String (topVal),  botVal2Str(botVal), mmss(secLeft));
}

void tftGameScreenZombie(int32_t topVal, int32_t botVal, uint32_t secLeft)
{
    tftGameScreenRaw(TFT_GAME_ZOMB_ICO_FNAME, TFT_GAME_Z_COLOR, String (topVal),  botVal2Str(botVal), mmss(secLeft));
}

void tftGameScreenTest(void)
{
    while(true)
    {
        for (int i = 0; i < 10; i++)
        {
            tftGameScreenBase(9000 + random(1000), 100 - random(200), random(200));
            delay(1000);
        }

        for (int i = 0; i < 10; i++)
        {
            tftGameScreenHuman(9000 + random(1000), 100 - random(200), random(200));
            delay(1000);
        }

        for (int i = 0; i < 10; i++)
        {
            tftGameScreenZombie(9000 + random(1000), 100 - random(200), random(200));
            delay(1000);
        }

    }
}