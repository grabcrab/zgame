#include "espRx.h"

#include <esp_wifi.h>

volatile int rssiVal = 0;
static SemaphoreHandle_t rssiMutex;

static void setRssi(int rssi)
{
    if (xSemaphoreTake(rssiMutex, ( TickType_t ) 100 ) == pdTRUE )
    {
        rssiVal = rssi;
        xSemaphoreGive(rssiMutex);
    }
}

int getRssi(void)
{
    int res;
    if (xSemaphoreTake(rssiMutex, ( TickType_t ) 100 ) == pdTRUE )
    {
        res = rssiVal;
        xSemaphoreGive(rssiMutex);
    }
    return res;
}

void promiscuous_rx_cb(void *buf, wifi_promiscuous_pkt_type_t type) 
{

    // All espnow traffic uses action frames which are a subtype of the mgmnt frames so filter out everything else.
    if (type != WIFI_PKT_MGMT){ return; }

    typedef struct {
      unsigned frame_ctrl: 16;
      unsigned duration_id: 16;
      uint8_t receiver_addr[6];
      uint8_t sender_oui[3]; // Organizationally Unique Identifier
      uint8_t sender_uaa[3]; // Universally Administred Address
      uint8_t filtering_addr[6];
      unsigned sequence_ctrl: 16;
      uint8_t addr4[6]; // optional
    } wifi_ieee80211_mac_hdr_t;

    typedef struct {
      wifi_ieee80211_mac_hdr_t hdr;
      uint8_t payload[0]; // network data ended with 4 bytes csum (CRC32) 
    } wifi_ieee80211_packet_t;

    const wifi_promiscuous_pkt_t *ppkt = (wifi_promiscuous_pkt_t *)buf;
    const wifi_ieee80211_packet_t *ipkt = (wifi_ieee80211_packet_t *)ppkt->payload;
    const wifi_ieee80211_mac_hdr_t *hdr = &ipkt->hdr;

    static const uint8_t ACTION_SUBTYPE = 0xd0;
    static const uint8_t ESPRESSIF_OUI[] = {0x30, 0xAE, 0xA4}; // one of them
    if (ACTION_SUBTYPE == (hdr->frame_ctrl & 0xFF))
    {
        setRssi(ppkt->rx_ctrl.rssi);
        //Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X %d\r\n", hdr->addr4[0], hdr->addr4[1], hdr->addr4[2], hdr->addr4[3], hdr->addr4[4], hdr->addr4[5], ppkt->rx_ctrl.rssi);
    }
    
    // if ((ACTION_SUBTYPE == (hdr->frame_ctrl & 0xFF)) &&
    //     (memcmp(hdr->sender_oui, ESPRESSIF_OUI, 3) == 0)) {
    //     Serial.printf("RSSI = %d\r\n", ppkt->rx_ctrl.rssi );
    // }
}

void rssiReaderInit(void)
{
    rssiMutex = xSemaphoreCreateMutex(); 
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_promiscuous_rx_cb(&promiscuous_rx_cb);    
}