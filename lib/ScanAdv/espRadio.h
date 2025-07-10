#ifndef __ESP_RADIO_H__
#define __ESP_RADIO_H__
#include  <Arduino.h>

#include "espPacket.h"
#include "espRx.h"

#define ENOW_Q_LEN          20
//#define ESP_CHANNEL         9

struct tPacketRecord
{
    tEspPacket      rec;
    unsigned long   ms;
    int             rssi; 
};

bool receivePacket(tEspPacket *rData, int &rssi, unsigned long &ms);
void prepareWiFi(void);
bool initRadio(void);
bool sendEspRawPacket(void *dataBuf, uint16_t bSize);
bool sendEspPacket(tEspPacket *rData);
void espInitRxTx(tGameRole dR, bool rx_ = true);
void espProcessRx(unsigned long toMs);
void espProcessTx(void);

#endif