#include <Arduino.h>
#include <WiFi.h>

#include "espRadio.h"

void communicatorJob(void*)
{   
    unsigned long lastBeaconMs = 0;
    unsigned long lastPrintedMs = 0;
    const int beaconRssi = -40;
    Serial.println(">>> gameJob");    
    //onBoot();
    //tftInit();
    //testRgb();
    tTftMainScreenRecord dRec;    
    //BEACON_INTERVAL_MS
    delay(10);
    while(true)
    {
        espProcessRx(RECEIVER_INTERVAL_MS);
        //checkBtn();
        if (millis() - lastBeaconMs > BEACON_INTERVAL_MS)
        {
            espProcessTx();
            lastBeaconMs = millis();
        }

        if (millis() - lastPrintedMs > 1000)
        {
            // printRecords(1500);
            // Serial.println("----------\n\n");
            lastPrintedMs = millis();
        }        
        dRec.vcc = getVcc();
        //getNearestRecord(dRec.dNum, dRec.rssi, 500);
        //tftProcessMainScreen(&dRec);
        updateCurrHitPoints(&gameRecord);
        if (checkIfApPortal(beaconRssi))
        {
            Serial.println("----> AP PORTAL");
            tftPrintThreeLines("AP PORTAL", "BEACON", "DETECTED", TFT_BLACK, TFT_BLUE);
            delay(3000);
            startSelfPortal();
        }
        delay(5);
    }    
}



void setup()
{
    prepareWiFi();
    rssiReaderInit();
    initRadio();
    espInitRxTx(grPinger, true);
}


void loop()
{

}