#ifndef __ESP_PACKET_H__
#define __ESP_PACKET_H__

#include <Arduino.h>

#include "gameRole.h"

#define ESP_PAYLOAD_SIZE    20

struct __attribute__((packed)) tEspPacket 
{   
    uint32_t        crc32           = 0;
    uint32_t        espProtocolID   = ESP_PROTOCOL_ID;
    uint64_t        deviceID        = 0;    
    uint64_t        packetID        = 0;    
    tGameRole       deviceRole      = grNone;
    int             hitPointsNear   = -500; 
    int             hitPointsMiddle = -200;
    int             hitPointsFar    = -50;    
    uint8_t         payload[ESP_PAYLOAD_SIZE];
                    tEspPacket(tGameRole dR = grNone);
    void            print(void);
};

//int i = sizeof(tEspPacket);
// int j = sizeof(tEspParam);

#endif

