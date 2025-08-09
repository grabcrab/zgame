#include "tft_utils.h"

#include "TFT_eSPI.h"

#include "pin_config.h"
#include "rm67162.h"

//TFT_eSPI tft = TFT_eSPI();
extern TFT_eSPI tft;
extern TFT_eSprite spr;
// lcd_cmd_t lcd_st7789v[] = {
//     {0x11, {0}, 0 | 0x80},
//     {0x3A, {0X05}, 1},
//     {0xB2, {0X0B, 0X0B, 0X00, 0X33, 0X33}, 5},
//     {0xB7, {0X75}, 1},
//     {0xBB, {0X28}, 1},
//     {0xC0, {0X2C}, 1},
//     {0xC2, {0X01}, 1},
//     {0xC3, {0X1F}, 1},
//     {0xC6, {0X13}, 1},
//     {0xD0, {0XA7}, 1},
//     {0xD0, {0XA4, 0XA1}, 2},
//     {0xD6, {0XA1}, 1},
//     {0xE0, {0XF0, 0X05, 0X0A, 0X06, 0X06, 0X03, 0X2B, 0X32, 0X43, 0X36, 0X11, 0X10, 0X2B, 0X32}, 14},
//     {0xE1, {0XF0, 0X08, 0X0C, 0X0B, 0X09, 0X24, 0X2B, 0X22, 0X43, 0X38, 0X15, 0X16, 0X2F, 0X37}, 14},
// };

// void tftInit(void)
// {
//     pinMode(PIN_POWER_ON, OUTPUT);
//     digitalWrite(PIN_POWER_ON, HIGH);

//     spr.begin();

//     for (uint8_t i = 0; i < (sizeof(lcd_st7789v) / sizeof(lcd_cmd_t)); i++) {
//         spr.writecommand(lcd_st7789v[i].cmd);
//         for (int j = 0; j < (lcd_st7789v[i].len & 0x7f); j++) {
//             spr.writedata(lcd_st7789v[i].data[j]);
//         }

//         if (lcd_st7789v[i].len & 0x80) {
//             delay(120);
//         }
//     }

//     spr.setRotation(3);
//     spr.setSwapBytes(true);

// #if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5,0,0)
//     ledcSetup(0, 2000, 8);
//     ledcAttachPin(PIN_LCD_BL, 0);
//     ledcWrite(0, 255);
// #else
//     ledcAttach(PIN_LCD_BL, 200, 8);
//     ledcWrite(PIN_LCD_BL, 255);
// #endif
// //     while(true)
// //     for (int i = 0; i < 10; i ++)
// //     {
// //         spr.fillScreen(TFT_BLACK);
// //         spr.setTextColor(TFT_GREEN, TFT_BLACK);
// //         String txtS = "F_" + String(i);
// //         Serial.println(txtS);
// //         spr.drawString(txtS, 2, 2, i);
// //         delay(5000);
// //     }
// }

static tTftMainScreenRecord prevRec;
static unsigned long lastTftUpdatedMs = 0;
static bool tftGetUpdateStatus(tTftMainScreenRecord *dRec)
{
    if (!lastTftUpdatedMs) return true;
    if (millis() - lastTftUpdatedMs > FORCE_UPDATE_AFTER_MS) return true;
    if (prevRec.dNum != dRec->dNum) return true;
    if (abs(prevRec.rssi - dRec->rssi) > DELTA_RSSI_FOR_TFT_UPDATE) 
        return true;
    return false;
}

void tftProcessMainScreen(tTftMainScreenRecord *dRec)
{
    //unsigned long ms = millis();
    if (!tftGetUpdateStatus(dRec)) return;
    prevRec = *dRec;
    lastTftUpdatedMs = millis();
    String vccStr  = String(dRec->vcc) + "mV";
    String idStr   = String(dRec->selfID);
    String rssiStr = String(dRec->rssi);
    String dNumStr = String(dRec->dNum);
    spr.fillScreen(TFT_BLACK);
    spr.setTextColor(TFT_GREEN, TFT_BLACK);
    
    spr.setTextSize(1);
    spr.setTextDatum(TR_DATUM);
    spr.drawString(vccStr, TFT_WIDTH, 0, VCC_FONT);

    spr.setTextSize(0);
    spr.setTextDatum(BR_DATUM);
    spr.drawString(idStr, TFT_WIDTH, TFT_HEIGHT, SELF_ID_FONT);

    spr.setTextDatum(TC_DATUM);
    spr.setTextSize(2);
    spr.drawString(rssiStr, TFT_WIDTH/2 - 25, 10, RSSI_FONT);
    spr.setTextSize(1);
    spr.drawString(dNumStr, TFT_WIDTH/2, 115, REMOTE_ID_FONT);
    lcd_PushColors(0, 0, TFT_WIDTH, TFT_HEIGHT, (uint16_t *)spr.getPointer());

    //Serial.printf("tft %lu ms\r\n", millis() - ms);
}

void tftBootScreen(void)
{
    spr.fillScreen(TFT_BLACK);
    spr.setTextColor(TFT_GREEN, TFT_BLACK);
    spr.setTextDatum(MC_DATUM);
    spr.setTextSize(2);
    spr.drawString("HOLD", TFT_WIDTH/2, TFT_HEIGHT/2, BOOT_FONT);
    lcd_PushColors(0, 0, TFT_WIDTH, TFT_HEIGHT, (uint16_t *)spr.getPointer());
}

void tftSleepScreen(void)
{
    spr.fillScreen(TFT_BLACK);
    spr.setTextColor(TFT_GREEN, TFT_BLACK);
    spr.setTextDatum(MC_DATUM);
    spr.setTextSize(2);
    spr.drawString("SLEEP", TFT_WIDTH/2, TFT_HEIGHT/2, BOOT_FONT);
    lcd_PushColors(0, 0, TFT_WIDTH, TFT_HEIGHT, (uint16_t *)spr.getPointer());
}

void tftSleep(void)
{
    // pinMode(PIN_LCD_BL,OUTPUT); 
    // digitalWrite(PIN_LCD_BL,LOW); 
    // spr.writecommand(ST7789_DISPOFF);
    // spr.writecommand(ST7789_SLPIN);

}