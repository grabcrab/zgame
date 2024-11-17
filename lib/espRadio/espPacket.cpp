#include "espPacket.h"

//////////////////
tEspPacket::tEspPacket(uint16_t dn)
{
    deviceID = ESP.getEfuseMac(); 
    deviceNum = dn;    
}
void tEspPacket::print(void)
{
    uint8_t *idPtr = (uint8_t*) &deviceID;
    //Serial.printf("%012X ", deviceID);
    Serial.printf("deviceNum = %d\tdeviceID = %02X:%02X:%02X:%02X:%02X:%02X\tpacketID = %llu\tcrc32 = %lu\r\n",
                    deviceNum, idPtr[0], idPtr[1], idPtr[2], idPtr[3], idPtr[4], idPtr[5], packetID, crc32);
            
}