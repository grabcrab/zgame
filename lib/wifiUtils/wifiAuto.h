#pragma once
#include <WiFi.h>
#include <WiFiMulti.h>
#include "xgConfig.h"

#define WIFI_AUTO_RECONNECT (true)

namespace WiFiAutoConnect
{
    bool begin(uint32_t toMs);
    bool isConnected(void);
    String currentSSID(void);
    void disconnect(void);
    bool maintain(uint32_t toMs);
}