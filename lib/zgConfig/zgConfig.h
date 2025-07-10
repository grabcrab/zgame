#pragma once

#include <Arduino.h>

#define DEF_MDNS_NAME "zgame"
#define MDNS_DOMAIN   ".local"


#define CFG_STR_LEN 128

#define ZG_CONFIG_FILE_NAME "/config.json"

enum tDeviceRole
{
    drNone,
    drServer,
    drPlayer
};

struct tZgConfig
{
    bool loaded = false;
    String DeviceRoleStr;
    tDeviceRole DeviceRole = drNone;
    String ServerName;
    String OtaLink;
    String WiFiSSID = "tcutestnet";
    String WiFiPASS = "tcutestpass";
        
    void load(void);    
    void print(void);
};

void zgConfigInit(void);
tZgConfig *zgConfig(void);