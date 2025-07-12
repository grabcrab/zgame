#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>

#include "espRadio.h"
#include "espRx.h"
#include "espScanRecords.h"

uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};


QueueHandle_t radioQ;

static uint16_t deviceNum;
static tEspPacket rxPacket; 
static tEspPacket *txPacket = NULL; 
RTC_DATA_ATTR int espPacketID = 0;
static bool wasRadioInit = false;
static bool receiverWasStarted = false;
extern uint8_t wifiChannel;

/////////////////
void prepareWiFi(void)
{
    esp_wifi_set_channel(wifiChannel, WIFI_SECOND_CHAN_NONE);
    WiFi.mode(WIFI_AP_STA);
    WiFi.setTxPower(WIFI_POWER_19_5dBm);
    //esp_wifi_set_mode(ESPNOW_WIFI_MODE);
    esp_wifi_start();
    //esp_wifi_set_protocol( WIFI_IF_STA , WIFI_PROTOCOL_LR);
    esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B|WIFI_PROTOCOL_11G|WIFI_PROTOCOL_11N|WIFI_PROTOCOL_LR);
    //esp_wifi_set_ps(WIFI_PS_NONE);

    // wifi_config_t wifi_config;
    // esp_wifi_get_config(WIFI_IF_STA, &wifi_config);
    // esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT40);

    // esp_wifi_config_11b_rate(WIFI_IF_STA, true);
  
    if (esp_wifi_set_max_tx_power(WIFI_TX_POWER) != ESP_OK)
    {
        Serial.printf("esp_wifi_set_max_tx_power(%d) ERROR!!!\r\n", WIFI_TX_POWER);
    }
    esp_wifi_set_channel(wifiChannel, WIFI_SECOND_CHAN_NONE);
}

bool initRadio(void)
{
    if (wasRadioInit)
    {
        return true;
    }
    // WiFi.mode(WIFI_STA);
    Serial.println();
    Serial.println(WiFi.macAddress());

    if (esp_now_init() != ESP_OK)
    {
        Serial.println("!!! initRadio ERROR: initializing ESP-NOW");
        return false;
    }
    else
    {
        Serial.println(">>> initRadio: ESPNow init OK");
    }

    // register peer
    esp_now_peer_info_t peerInfo;
    memset(&peerInfo, 0, sizeof(peerInfo));

    memcpy(peerInfo.peer_addr, broadcastAddress, 6);
    peerInfo.channel = wifiChannel;
    peerInfo.encrypt = false;

    esp_err_t addStatus = esp_now_add_peer(&peerInfo);

    if (addStatus == ESP_OK)
    {
        // Pair success
        Serial.println(">>> initRadio: pair success");
        wasRadioInit = true;
        return true;
    }
    else if (addStatus == ESP_ERR_ESPNOW_NOT_INIT)
    {
        // How did we get so far!!
        Serial.println("!!! initRadio ERROR: ESPNOW Not Init");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_ARG)
    {
        Serial.println("!!! initRadio ERROR: Invalid Argument");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_FULL)
    {
        Serial.println("!!! initRadio ERROR: Peer list full");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_NO_MEM)
    {
        Serial.println("!!! initRadio ERROR: Out of memory");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_EXIST)
    {
        Serial.println("!!! initRadio ERROR: Peer Exists");
        return true;
    }
    else
    {
        Serial.println("!!! initRadio ERROR: Not sure what happened");
        return false;
    }

    return false;
}
/////////////////
bool sendEspPacket(tEspPacket *rData)
{    
    rData->packetID++;
    return sendEspRawPacket(rData, sizeof(tEspPacket));
}
/////////////////
bool sendEspRawPacket(void *dataBuf, uint16_t bSize)
{
    wasRadioInit = initRadio();

    if (!wasRadioInit)
    {
        Serial.println("E112");
        return false;
    }

    esp_err_t result = esp_now_send(broadcastAddress, (uint8_t*) dataBuf, bSize);

    return (result == ESP_OK);
}
/////////////////
void OnDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len)
{
    tPacketRecord dRecord;    
    memcpy(&dRecord.rec, incomingData, sizeof(tEspPacket));    
    dRecord.rssi = getRssi();    
    dRecord.ms = millis();
    xQueueSend(radioQ, &dRecord, 1000);
}
/////////////////
bool startReceiver(void)
{
    if (receiverWasStarted)
        return true;
    radioQ = xQueueCreate(ENOW_Q_LEN, sizeof(tPacketRecord));

    if (esp_now_register_recv_cb(OnDataRecv) == ESP_OK)
    {
        Serial.println("ESP receiver started");
        return true;
    }
    else
    {
        Serial.println("ESP receiver FAILED!!!");
    }
    return false;
}
/////////////////
bool receivePacket(tEspPacket *rData, int &rssi, unsigned long &ms)
{
    tPacketRecord dRecord;   
    wasRadioInit = initRadio();
    if (!wasRadioInit)
    {
        return false;
    }
    receiverWasStarted = startReceiver();
    if (!receiverWasStarted)
    {
        return false;
    }
    BaseType_t res = xQueueReceive(radioQ, &dRecord, 1);

    if (res == pdTRUE)
    {
        memcpy(rData, &dRecord.rec, sizeof(tEspPacket));
        if (rData->espProtocolID == ESP_PROTOCOL_ID)
        {
            rssi = dRecord.rssi;
            ms   = dRecord.ms;
            return true;
        }
    }

    return false;
}
/////////////////
void testSender(uint16_t devID, uint16_t intMs)
{
    // uint32_t packCount = 0;
    // unsigned long lastPrintedMs = millis();
    // tEspPacket rPacket();
    // initRadio();
    // while(true)
    // {
    //     sendEspPacket(&rPacket);
    //     //Serial.println(rPacket.packetID);
    //     //rPacket.print();
    //     delay(intMs);  
    //     packCount++;      
    //     if (millis() - lastPrintedMs > 1000)
    //     {
    //         Serial.println(packCount);
    //         packCount = 0;
    //         lastPrintedMs = millis();
    //     }
    // }
}
/////////////////
void  espInitRxTx(tEspPacket *txPack, bool doRx)
{        
    txPacket = txPack;
    rssiReaderInit();
    initRadio();
    if (doRx)
    {
        startReceiver();
    }
}

extern void addScannedRecord(tEspPacket *rData, unsigned long lastMs, int rssi);
void espProcessRx(unsigned long toMs)
{
    int rssi;
    unsigned long ms;
    unsigned long startMs = millis();
    while(millis() - startMs < toMs)
    {
        if (receivePacket(&rxPacket, rssi, ms))
        {            
            addScannedRecord(&rxPacket, /*rxPacket->deviceRole,*/ ms, rssi);                        
        }
    }
}

void espProcessTx(void)
{
    if (!sendEspPacket(txPacket))
    {        
    }
}

