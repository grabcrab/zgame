#include "zgConfig.h"

#include <ArduinoJson.h>
#include <FS.h>
#include <SPIFFS.h>

tZgConfig zgConfig_;

tDeviceRole str2role(String str)
{
    if (str == "PLAYER") return drPlayer;
    if (str == "SERVER") return drServer;
    return drNone;    
}

void tZgConfig::load(void)
{
    JsonDocument doc;
    const char *bufPtr;
    
    if(!SPIFFS.begin(true, "/spiffs", 5))
        if(!SPIFFS.begin(true, "/spiffs", 5))
        {
            Serial.println("!!!! tZgConfig::load: ERROR while mounting SPIFFS!");    
            return;
        }    

    if (!SPIFFS.exists(ZG_CONFIG_FILE_NAME))
    {
        Serial.printf(">>> No boot config file <%s>\r\n", ZG_CONFIG_FILE_NAME);
        return;
    }

    File f = SPIFFS.open(ZG_CONFIG_FILE_NAME, "r");
    if (!f)
    {
        Serial.printf(">>> Error opening boot config file <%s>\r\n", ZG_CONFIG_FILE_NAME);
        return;
    }
    else 
    {
        Serial.printf(">>> Boot config file found: %s\r\n", ZG_CONFIG_FILE_NAME);
    }

    DeserializationError error = deserializeJson(doc, f);
    if (error)
    {
        Serial.printf("!!! JSON deserialize ERROR [%s]\r\n", error.c_str());
        f.close();
        return;
    }

    memset(this, 0, sizeof(tZgConfig));

    
    

    DeviceRoleStr = doc["DeviceRole"] | "";
    DeviceRole = str2role(DeviceRoleStr);

    ServerName = doc["ServerName"] | "zgame";
    OtaLink = doc["OtaLink"] | "";

    WiFiSSID = doc["WiFiSSID"] | "tcutestnet";
    WiFiPASS = doc["WiFiPASS"] | "tcutestpass";

    f.close();
    
    loaded = true;
}

void tZgConfig::print(void)
{
    Serial.println("----------------------------------------------------------------");
    Serial.println("ZG Controller config:");
    if (loaded)
        Serial.println("\tLOADED FROM JSON");
    else 
        Serial.println("\t!!! DEFAULT VALUES !!!");
    
    Serial.printf("\t        DeviceRoleStr = %s\r\n", DeviceRoleStr.c_str());
    Serial.printf("\t           ServerName = %s\r\n", ServerName.c_str());
    Serial.printf("\t             WiFiSSID = %s\r\n", WiFiSSID.c_str());
    Serial.printf("\t             WiFiPASS = %s\r\n", WiFiPASS.c_str());
    Serial.printf("\t              OtaLink = %s\r\n", OtaLink.c_str());

    Serial.println("----------------------------------------------------------------");
}

void zgConfigInit(void)
{
    zgConfig_.load();
    zgConfig_.print();
}

tZgConfig *zgConfig(void)
{
    return &zgConfig_;
}