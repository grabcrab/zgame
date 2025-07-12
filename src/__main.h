#pragma once

#include <Arduino.h>

#define DEF_SSID                "tcutestnet"
#define DEF_PASS                "tcutestpass"
#define DEF_FILE_SERVER_ADDR    "http://192.168.1.120:5001"
#define DEF_OTA_SERVER_ADDR     "http://192.168.1.120:5005"
#define DEF_CAN_SKIP_OTA        (true)
#define DEF_TO_MS               15000
#define DEF_NET_WAIT_MS         15000

#define DEF_WIFI_CHANNEL        1

#define DEF_USE_TFT             (true)

//PATTERNS
#define ON_BOOT_PATTERN "StartIt"

bool initOnBoot(void);

bool netConnect(uint16_t toMs);
bool netWait(uint16_t toMs);
void radioConnect(void);