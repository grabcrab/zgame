#include "espPacket.h"

//////////////////
tEspPacket::tEspPacket(tGameRole dR)
{
    deviceID = ESP.getEfuseMac();     
    deviceRole = dR;
}
void tEspPacket::print(void)
{
    uint8_t *idPtr = (uint8_t*) &deviceID;
    //Serial.printf("%012X ", deviceID);
    Serial.printf("deviceRole = %d\tdeviceID = %02X:%02X:%02X:%02X:%02X:%02X\tpacketID = %llu\tcrc32 = %lu\r\n",
                    deviceRole, idPtr[0], idPtr[1], idPtr[2], idPtr[3], idPtr[4], idPtr[5], packetID, crc32);            
}