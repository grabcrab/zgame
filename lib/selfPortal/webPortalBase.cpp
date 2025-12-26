#include <FS.h>
#include <LittleFS.h>
#include <esp_wifi.h>

#include "webPortalBase.h"
#include "utils.h"

#include "html/index_html.h"
#include "html/device_html.h"
//#include "html/configuration_html.h"
//#include "html/configuration_files_portal_html.h"
//#include "html/configuration_file_management_html.h"
//#include "html/ota_html.h"
//#include "html/modbus_html.h"
#include "html/editor_page.h"




int tWebPortalBase::activityTimeMs;
String tWebPortalBase::_devID;
int tWebPortalBase::_SPIFFSUsed;
int tWebPortalBase::_SPIFFSTotal;
bool tWebPortalBase::isReset = false;
bool tWebPortalBase::isOTA = false;
String tWebPortalBase::otaLink = "";
String tWebPortalBase::otaSsid = "";
String tWebPortalBase::otaPass = "";

uint32_t tWebPortalBase::_versionNum;
String tWebPortalBase::_hdr1;
String tWebPortalBase::_hdr2;
String tWebPortalBase::_hdr3;

#define PAR_OTA_FILE_LINK "otaFileLink"
#define PAR_OTA_SSID "otaSSID"
#define PAR_OTA_PASS "otaPASS"
#define PAR_OTA_LINK "otaLINK"

#define PAR_CONFIG_FILES "configFiles"
#define PAR_CONFIG_FILE_CONTENT "inpConfFileContent"

String tWebPortalBase::otaFileLink = "";

String selectedConfigFile = "";

static uint32_t lastLedMs = 0;
static const uint32_t ledIntMs = 300;
static const uint32_t ledOnMs  = 50;

extern int simpleOtaLastError;
extern String simpleOtaLastErrorString;

/////////////////////////////////////
tWebPortalBase::tWebPortalBase(uint16_t port, uint32_t versionNum, String hdr1, String hdr2, String hdr3)
    : AsyncWebServer(port)
{
    _versionNum = versionNum;
    _hdr1 = hdr1;
    _hdr2 = hdr2;
    _hdr3 = hdr3;

    serverOnSetup();
    activityTimeMs = millis();
    createOtaLinkList(OTALINKLISTJSON);
} // constructor
/////////////////////////////////////
tWebPortalBase::~tWebPortalBase()
{
    // WiFi.softAPdisconnect(true);
}
/////////////////////////////////////
void tWebPortalBase::getESP32TimeString(String *str)
{
    // Timestamp format [YYYY.MM.DD HH:MM:SS]
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo))
    {
        Serial.println("Failed to obtain time");
        return;
    }
    char buffer[80];
    // strftime (buffer,80,"%F %I:%M%p",&timeinfo);
    strftime(buffer, 80, "%Y.%m.%d %T", &timeinfo);
    *str = String(buffer);
}
/////////////////////////////////////
void tWebPortalBase::getExtRTCTimeString(String *str)

{
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;

    char buffer[80];

    sprintf(buffer, "%4d.%02d.%02d %02d:%02d:%02d\n", year, month, day, hour, minute, second);

    *str = String(buffer);
}

static String getDeviceName(void)
{
    char buf[100];
    uint64_t mac64 = ESP.getEfuseMac();
    byte *macPtr = (byte*) &mac64;
    sprintf(buf, "GAME_%02X%02X%02X%02X%02X%02X", macPtr[0], macPtr[1], macPtr[2], macPtr[3], macPtr[4], macPtr[5]);
    String res = buf;
    return res;
}

static String getDeviceMac(void)
{
    char buf[100];
    uint64_t mac64 = ESP.getEfuseMac();
    byte *macPtr = (byte*) &mac64;
    sprintf(buf, "%02X:%02X:%02X:%02X:%02X:%02X", macPtr[0], macPtr[1], macPtr[2], macPtr[3], macPtr[4], macPtr[5]);
    String res = buf;
    return res;
}

void tWebPortalBase::wifiAPSetup()
{
    const String ap_ssid = getDeviceName();
    const char *ap_passphrase = WEB_PORTAL_WIFI_PASSWORD;
    IPAddress local_IP(192, 168, 4, 1);
    IPAddress gateway(192, 168, 4, 9);
    IPAddress subnet(255, 255, 255, 0);
    String ipS;

    // Serial.print("Setting soft-AP configuration ... ");
    // Serial.println(WiFi.softAPConfig(local_IP, gateway, subnet) ? "Ready" : "Failed!");
    WiFi.setTxPower(WIFI_POWER_7dBm);
    esp_wifi_deinit();
    WiFi.mode(WIFI_AP);
    esp_wifi_set_protocol(WIFI_IF_AP, WIFI_PROTOCOL_11B);
    // esp_wifi_set_max_tx_power(84);
    // esp_wifi_set_channel(ESP_CHANNEL, WIFI_SECOND_CHAN_NONE);


    if (!LittleFS.begin(false))
        if (!LittleFS.begin(true))
        {
            Serial.println("[wifiAPSetup] An Error has occurred while mounting SPIFFS");
            // return;
        }
    _SPIFFSUsed = LittleFS.usedBytes();
    Serial.print("SPIFFS Used bytes=");
    Serial.println(_SPIFFSUsed);
    _SPIFFSTotal = LittleFS.totalBytes();
    Serial.print("SPIFFS Total bytes=");
    Serial.println(_SPIFFSTotal);

    Serial.printf("\nSetting soft-AP [%s][%s]... ", ap_ssid.c_str(), ap_passphrase);
    Serial.println(WiFi.softAP(ap_ssid.c_str(), ap_passphrase) ? "Ready" : "Failed!");
    Serial.print("Soft-AP IP address = ");
    ipS = WiFi.softAPIP().toString();
    Serial.println(ipS);
    portalTft("Config portal:", ap_ssid, ipS);
    webDnsInit();    
}

/////////////////////////////////////
String tWebPortalBase::processor(const String &var)
{
    Serial.println(var);
    activityTimeMs = millis();

    if (var == "HEAP_CURR_VAL_PLACEHOLDER")
    {
        return String(ESP.getFreeHeap());
    }

    if (var == "ESP32_DEV_ID_PLACEHOLDER")
    {
        return getDeviceMac();
    }

    if (var == "FIRMWARE_VERSION_PLACEHOLDER")
    {
        return String(_versionNum);
    }
    
    if (var == "ESP32_TEMPERATURE_PLACEHOLDER")
    {
       return String("TEMP_111");
    }

    if (var == "VCC_PLACEHOLDER")
    {
       return String("VCC_111");
    }

    if (var == "WEB_PORTAL_NAME_PLACEHOLDER")
    {
        String portalName = LOCAL_PORTAL_NAME;
        portalName.replace("_", " ");
        return portalName;
    }
    
    if (var == "SPIFFS_USED_PLACEHOLDER")
    {
        return String(_SPIFFSUsed);
    }

    if (var == "SPIFFS_TOTAL_PLACEHOLDER")
    {
        return String(_SPIFFSTotal);
    }

    if (var == "HEADERLINE1_PLACEHOLDER")
    {
        return String(_hdr1);
    }

    if (var == "HEADERLINE2_PLACEHOLDER")
    {
        return String(_hdr2);
    }

    if (var == "HEADERLINE3_PLACEHOLDER")
    {
        return String(_hdr3);
    }

    return String();
}

/////////////////////////////////////
void tWebPortalBase::notFound(AsyncWebServerRequest *request)
{
    request->send(404, "text/plain", "Not found");
    activityTimeMs = millis();
}

/////////////////////////////////////
void tWebPortalBase::serverOnSetup()
{    
    on("/", HTTP_GET, [](AsyncWebServerRequest *request)
    {
        Serial.println("<index>");
        // if(!request->authenticate(WEB_PORTAL_LOGIN, WEB_PORTAL_PASSWORD))
        //     return request->requestAuthentication();
        request->send_P(200, "text/html", index_html, processor); 
        activityTimeMs = millis();
    }); // index_html

    on("/doReset", HTTP_GET, [](AsyncWebServerRequest *request)
    {
        Serial.println("<doReset>");
        request->send_P(200, "text/html", "Restarted. Close the page.", processor); 
        delay(2000);
        isReset = true; 
    });

    on("/doOtaStart", HTTP_GET, [](AsyncWebServerRequest *request)
    {
        String otaContent = "OTA over Wi-Fi has been started. \r\n"; 
        otaContent += "This Web-portal is not available anymore. Please follow the LED indicators.\n\r";
        isOTA = true;
        request->send_P(200, "text/html", otaContent.c_str(), processor); 
        activityTimeMs = millis();
    });    
    
    // on("/configuration", HTTP_GET, [](AsyncWebServerRequest *request)
    // {
    //     // if(!request->authenticate(WEB_PORTAL_LOGIN, WEB_PORTAL_PASSWORD))
    //     //     return request->requestAuthentication();
    //     request->send_P(200, "text/html", configuration_html, processor);    
    //     activityTimeMs = millis();    
    // });

    // on("/wifiOta", HTTP_GET, [](AsyncWebServerRequest *request)
    // {
    //     // if(!request->authenticate(WEB_PORTAL_LOGIN, WEB_PORTAL_PASSWORD))
    //     //     return request->requestAuthentication();
    //     request->send_P(200, "text/html", ota_html, processor);   
    //     activityTimeMs = millis();     
    // });

    on("/ota", HTTP_GET, handleOtaPage);
    on("/update", HTTP_POST, handleOtaUpdateResponse, handleOtaUpdateUpload);
    on("/ota_complete", HTTP_GET, handleOtaComplete);



    // on("/modbus", HTTP_GET, [](AsyncWebServerRequest *request)
    // {
    //     // if(!request->authenticate(WEB_PORTAL_LOGIN, WEB_PORTAL_PASSWORD))
    //     //     return request->requestAuthentication();
    //     request->send_P(200, "text/html", modbus_html, processor); 
    //     activityTimeMs = millis();       
    // });
    
  
    on("/doOTA", HTTP_GET, [](AsyncWebServerRequest *request)
    {
        Serial.println("<doOTA>");
        if (request->hasParam(PAR_OTA_SSID)) 
        {
            //otaFileLink = request->getParam(PAR_OTA_FILE_LINK)->value();
            otaLink = request->getParam(PAR_OTA_LINK)->value();
            otaSsid = request->getParam(PAR_OTA_SSID)->value();
            otaPass = request->getParam(PAR_OTA_PASS)->value();
            activityTimeMs = millis();

            if (otaLink == "")
            {        
                request->send_P(200, "text/html", "Error! The URL can't be empty! <a href=\"/wifiOta\">BACK</a>.", processor);  
            }

            if (otaSsid == "")
            {
                request->send_P(200, "text/html", "Error! The SSID can't be empty! <a href=\"/wifiOta\">BACK</a>.", processor);  
            }

            String otaContent = "OTA over Wi-Fi is going to start. <br> \r\n";
            
            otaContent += ("OTA url: <u>" + otaLink + "</u><br>\r\n");
            otaContent +="Please check if " + otaSsid + "/" + otaPass + " Wi-Fi network is available.<br>\r\n";      
            otaContent += "Press  <a href=\"/doOtaStart\"> START </a> or <a href=\"/device\"> BACK </a>\n\r";
        //      otaContent += "This Web-portal is not available anymore. Please follow the LED indicators.\n\r";
            request->send_P(200, "text/html", otaContent.c_str(), processor);
            activityTimeMs = millis();
        }
        else 
        {
            request->send_P(200, "text/html", "Error in the request! Report to administrator! <a href=\"/wifiOta\">BACK</a>.", processor); 
        }
        request->send_P(200, "text/html", "Unknown error!!! Report to administrator! <a href=\"/wifiOta\">BACK</a>.", processor); 
        activityTimeMs = millis();
    });

    
    
    on("/device", HTTP_GET, [](AsyncWebServerRequest *request)
    {
        Serial.println("<DEVICE>");
        // if (!request->authenticate(WEB_PORTAL_LOGIN, WEB_PORTAL_PASSWORD))
        // {
        //     Serial.println("Bad authentification!!!");
        //     return request->requestAuthentication();
        // }
        request->send_P(200, "text/html", device_html, processor);
        activityTimeMs = millis();
    });

    

    on("/editor", HTTP_GET, [](AsyncWebServerRequest *request)
    {
        Serial.println(">>> EDITOR");
        request->send_P(200, "text/html", editor_page);
    });
    
    on("/listFiles", HTTP_GET, listFiles);
    on("/getFile", HTTP_GET, getFile);
    on("/saveFile", HTTP_POST, saveFile);
    on("/files", HTTP_GET, handleFileManager);
    on("/download", HTTP_GET, handleDownload);
    on("/upload", HTTP_POST, handleUploadResponse, handleUploadProcess);
    on("/delete", HTTP_GET, handleDelete);

    on("/logo", HTTP_GET, [](AsyncWebServerRequest *request)
    {
        request->send(SPIFFS, "/logo.png", "image/png");
    });

    onNotFound(notFound);
}

/////////////////////////////////////


void tWebPortalBase::server_loop()
{
    if (isReset == true)
    {
        isReset = false;
        Serial.println("--------------- RESET ------------------");        
        delay(100);
        ESP.restart();
    }
    // if (isOTA == true)
    // {
    //     isOTA = false;
    //     Serial.println("OTA started: ");
    //     directBinOTA();
    // }    
    webDnsLoop();

    if (loopOTA()) 
    {
        return;
    }
}
/////////////////////////////////////
bool tWebPortalBase::isTimeout()
{
    return (millis() > activityTimeMs + AUTO_OFF_TIMEOUT_S * 1000);
}

/////////////////////////////////////
esp_err_t tWebPortalBase::createOtaLinkList(const char *otaLinkListJsonFile)
{    
    return ESP_OK;
}
/////////////////////////////////////
