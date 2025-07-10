#pragma once

#include "Arduino.h"
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>

#include <WiFi.h>
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>



#include "json\default_ota_json.h"


#define DEFAULT_HTPP_PORT       80
#define WEB_PORTAL_LOGIN        "admin"
#define WEB_PORTAL_PASSWORD     ""
#define AUTO_OFF_TIMEOUT_S      (10 * 60)
#define WEB_PORTAL_WIFI_PASSWORD    ""//"987654321"

#define OTALINKLISTJSON                     "/otaLinkList.json"
#define OTA_LINKS_JSON_DOC_MAX              2000
#define DEVICE_AND_OTA_LINK_FILE_NAME       "/otaLinkList.html"

// #define CONFIGURATION_FILES_PORTAL_FILE_NAME  "/configFilesPortal.htm"
// #define CONFIGURATION_FILE_MANAGEMENT_FILE_NAME  "/configFileManagement.htm"

#define CONFIGURATION_FILES_PORTAL_FILE_NAME  "/cfFPl.htm"
#define CONFIGURATION_FILE_MANAGEMENT_FILE_NAME  "/cfFMng.htm"

#define LOCAL_PORTAL_BEACON_PRFX "portal"
#define LOCAL_PORTAL_NAME         "X-GAME PORTAL"


class tWebPortalBase: public AsyncWebServer 
{
    public:
        tWebPortalBase(uint16_t port = DEFAULT_HTPP_PORT, uint32_t versionNum = 0, String hdr1 = "", String hdr2 = "", String hdr3 = "");
        ~tWebPortalBase();
        void wifiAPSetup();
        static void getESP32TimeString(String *str);
        static void getExtRTCTimeString(String *str);
        static bool isTimeout();
        static void server_loop();

        static uint32_t _versionNum;
        static String _hdr1;
        static String _hdr2;
        static String _hdr3;
        static String _devID;
        static int activityTimeMs;
        static int _SPIFFSUsed;
        static int _SPIFFSTotal;
        static String otaFileLink;
        static String otaLink;
        static String otaSsid;
        static String otaPass;

        static bool isReset;
        static bool isOTA;
    
        void serverOnSetup(); 
        static String processor(const String& var);
        // static constexpr char* http_username = WEB_PORTAL_LOGIN;
        // static constexpr char* http_password = WEB_PORTAL_PASSWORD;
        static void notFound(AsyncWebServerRequest *request);
        esp_err_t createOtaLinkList(const char* otaLinkListJsonFile);
        static void directBinOTA(void);        
};

void createConfigurationFilesPortal(void);
void createConfigurationFilePage(void);

void listFiles(AsyncWebServerRequest *request);
void getFile(AsyncWebServerRequest *request);
void saveFile(AsyncWebServerRequest *request);
void handleUploadProcess(AsyncWebServerRequest *request, String filename, size_t index, uint8_t *data, size_t len, bool final);
void handleUploadResponse(AsyncWebServerRequest *request);
void handleDownload(AsyncWebServerRequest *request);
void handleFileManager(AsyncWebServerRequest *request);
void handleDelete(AsyncWebServerRequest *request);

bool loopOTA(void);
void handleOtaUpdateUpload(AsyncWebServerRequest *request, String filename, size_t index, uint8_t *data, size_t len, bool final);
void handleOtaUpdateResponse(AsyncWebServerRequest *request);
void handleOtaComplete(AsyncWebServerRequest *request);
void handleOtaPage(AsyncWebServerRequest *request);


void webDnsInit_AP(void);
void webDnsLoop_AP(void);

void initPortalBleScanner(bool initBLE = true, String pattern = LOCAL_PORTAL_BEACON_PRFX, void* callback = NULL);
void loopPortalBeacon(void);

void selfPortalOnBoot(uint32_t fwVersion, String portalName);
void startSelfPortal(void);

extern void portalTft(String s1, String s2, String s3); 

void webDnsInit(void);
void webDnsLoop(void);