#ifndef __ESP_PACKET_H__
#define __ESP_PACKET_H__

#include <Arduino.h>

#define ESP_PAYLOAD_SIZE    200

struct __attribute__((packed)) tEspPacket 
{   
    uint32_t        crc32           = 0;
    uint32_t        espProtocolID   = ESP_PROTOCOL_ID;
    uint64_t        deviceID        = 0;
    uint16_t        deviceNum       = 0xffff;
    uint64_t        packetID        = 0;
    uint8_t         payload[ESP_PAYLOAD_SIZE];
                    tEspPacket(uint16_t dn = 0xffff);
    void            print(void);
};

//int i = sizeof(tEspPacket);
// int j = sizeof(tEspParam);

#endif

