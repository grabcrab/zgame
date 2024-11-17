#ifndef __TFT_UTILS_H__
#define __TFT_UTILS_H__
#include <Arduino.h>

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
    uint16_t selfID = DEVICE_NUM;
};

//void tftInit(void);
void tftSleep(void);
void tftProcessMainScreen(tTftMainScreenRecord *dRec);
void tftBootScreen(void);
void tftSleepScreen(void);


#endif //__TFT_UTILS_H__