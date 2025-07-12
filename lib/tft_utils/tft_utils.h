#ifndef __TFT_UTILS_H__
#define __TFT_UTILS_H__
#include <Arduino.h>
#include <TFT_eSPI.h>



#define VCC_FONT         1
#define RSSI_FONT        7
#define REMOTE_ID_FONT   7   
#define SELF_ID_FONT     4
#define BOOT_FONT        4

#define FORCE_UPDATE_AFTER_MS       5000
#define DELTA_RSSI_FOR_TFT_UPDATE   5

// struct lcd_cmd_t
// {
//     uint8_t cmd;
//     uint8_t data[14];
//     uint8_t len;
// };

struct tTftMainScreenRecord
{
    uint16_t vcc = 3333;
    int rssi = -77;
    uint16_t dNum = 55;
    uint16_t selfID = 0;
};

struct tSprite
{
    TFT_eSprite *spr = NULL;
    int sX;
    int sY;
    int sW;
    int sH;
    ~tSprite();
    void init(TFT_eSPI *tft, int xx, int yy, int ww, int hh);    
    void pushColors(void);
    void clear(uint16_t bgColor);
    void drawBmp(const char *filename, int16_t x = 0, int16_t y = 0);
};

//void tftInit(void);
void setupTFT(String textS);
void tftSleep(void);
void tftProcessMainScreen(tTftMainScreenRecord *dRec);
void tftBootScreen(void);
void tftSleepScreen(void);
void tftPrintText(String txt, uint16_t bgColor = TFT_BLACK, uint16_t txtColor = TFT_GREEN);
void tftPrintThreeLines(String txt1, String txt2, String txt3, uint16_t bgColor, uint16_t txtColor);


void tftDrawBmp(const char *filename, int16_t x, int16_t y, uint16_t wLimit = 0, uint16_t hLimit = 0);
void tftTestBmp(void);



#endif //__TFT_UTILS_H__