#include <esp_now.h>
#include <WiFi.h>

#include "espRadio.h"
#include "espRx.h"
#include "espScanRecords.h"

uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};


QueueHandle_t radioQ;

static uint16_t deviceNum;
static tEspPacket *rxPacket = NULL; 
static tEspPacket *txPacket = NULL; 
RTC_DATA_ATTR int espPacketID = 0;
static bool wasRadioInit = false;
static bool receiverWasStarted = false;

/////////////////
bool initRadio(void)
{
    if (wasRadioInit)
        return true;
    // WiFi.mode(WIFI_STA);
    Serial.println();
    Serial.println(WiFi.macAddress());

    if (esp_now_init() != ESP_OK)
    {
        Serial.println("Error initializing ESP-NOW");
        return false;
    }
    else
        Serial.println("ESPNow init OK");

    // register peer
    esp_now_peer_info_t peerInfo;
    memset(&peerInfo, 0, sizeof(peerInfo));

    memcpy(peerInfo.peer_addr, broadcastAddress, 6);
    peerInfo.channel = ESP_CHANNEL;
    peerInfo.encrypt = false;

    esp_err_t addStatus = esp_now_add_peer(&peerInfo);

    if (addStatus == ESP_OK)
    {
        // Pair success
        Serial.println("Pair success");
        return true;
    }
    else if (addStatus == ESP_ERR_ESPNOW_NOT_INIT)
    {
        // How did we get so far!!
        Serial.println("ESPNOW Not Init");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_ARG)
    {
        Serial.println("Invalid Argument");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_FULL)
    {
        Serial.println("Peer list full");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_NO_MEM)
    {
        Serial.println("Out of memory");
        return false;
    }
    else if (addStatus == ESP_ERR_ESPNOW_EXIST)
    {
        Serial.println("Peer Exists");
        return true;
    }
    else
    {
        Serial.println("Not sure what happened");
        return false;
    }

    return true;
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
    uint32_t packCount = 0;
    unsigned long lastPrintedMs = millis();
    tEspPacket rPacket(devID);
    initRadio();
    while(true)
    {
        sendEspPacket(&rPacket);
        //Serial.println(rPacket.packetID);
        //rPacket.print();
        delay(intMs);  
        packCount++;      
        if (millis() - lastPrintedMs > 1000)
        {
            Serial.println(packCount);
            packCount = 0;
            lastPrintedMs = millis();
        }
    }
}
/////////////////



void  espInitRxTx(uint16_t deviceN)
{
    deviceNum = deviceN;
    if (rxPacket == NULL)
        rxPacket = new tEspPacket(deviceNum);

    if (txPacket == NULL)
        txPacket = new tEspPacket(deviceNum);
    rssiReaderInit();
    initRadio();
    startReceiver();
}

void espProcessRx(unsigned long toMs)
{
    int rssi;
    unsigned long ms;
    unsigned long startMs = millis();
    while(millis() - startMs < toMs)
    if (receivePacket(rxPacket, rssi, ms))
    {
        addRecord(rxPacket->deviceNum, ms, rssi);
    }
    else 
    {
        delay(1);
    }

    // if (millis() - lastSentMs > 25)
    // {
    //     packCount++;    
    //     lastSentMs = millis();            
    //     sendEspPacket(&sPacket);            
    // }
}

void espProcessTx(void)
{
    sendEspPacket(txPacket);   
}

