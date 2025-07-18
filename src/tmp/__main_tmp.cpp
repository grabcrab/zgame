#include <Arduino.h>
#include <WiFi.h>



#include <Wire.h>

// #include "soc/soc.h"
// #include "soc/rtc_cntl_reg.h"

#include "espRadio.h"
#include "kxtj3-1057.h"

#include "valPlayer.h"
#include "tft_utils.h"
#include "zgConfig.h"
#include "webPortalBase.h"
#include "../include/version.h"

extern void beaconJob(void);
extern void gameJob(void*);

extern void setupTFT(String textS);
extern void loopTFT(void);

void testVibro(void)
{
    pinMode(PIN_VIBRO, OUTPUT);
    digitalWrite(PIN_VIBRO, HIGH);
    delay(500);
    digitalWrite(PIN_VIBRO, LOW);
}

void testAccel(void)
{
    KXTJ3 myIMU(0x0F); // Address can be 0x0E or 0x0F
    float sampleRate =
    6.25; // HZ - Samples per second - 0.781, 1.563, 3.125, 6.25,
          // 12.5, 25, 50, 100, 200, 400, 800, 1600Hz
          // Sample rates ≥ 400Hz force High Resolution mode on
uint8_t accelRange = 2; // Accelerometer range = 2, 4, 8, 16g
bool highRes = false; // High Resolution mode on/off
      if (myIMU.begin(sampleRate, accelRange, highRes) ==
    IMU_SUCCESS) {
        Serial.println("IMU initialized.");
    } else {
        Serial.println("Failed to initialize IMU.");
        while(true); // stop running sketch if failed
    }

    uint8_t readData = 0;

    // Get the ID:
    if (myIMU.readRegister(&readData, KXTJ3_WHO_AM_I) ==
    IMU_SUCCESS) {
    Serial.print("Who am I? 0x");
    Serial.println(readData, HEX);
    } else {
        Serial.println("Communication error, stopping.");
        while(true); // stop running sketch if failed
    }

    //while(true)
    {

      myIMU.standby(false);

    uint8_t dataLowRes = 0;

    if (myIMU.readRegister(&dataLowRes, KXTJ3_XOUT_H) ==
    IMU_SUCCESS) {
        Serial.print(" Acceleration X RAW = ");
        Serial.println((int8_t)dataLowRes);

        // Read accelerometer data in mg as Float
        Serial.print(" Acceleration X float = ");
        Serial.println(myIMU.axisAccel(X), 4);
    }

    if (myIMU.readRegister(&dataLowRes, KXTJ3_YOUT_H) ==
    IMU_SUCCESS) {
        Serial.print(" Acceleration Y RAW = ");
        Serial.println((int8_t)dataLowRes);

        // Read accelerometer data in mg as Float
        Serial.print(" Acceleration Y float = ");
        Serial.println(myIMU.axisAccel(Y), 4);
    }

    if (myIMU.readRegister(&dataLowRes, KXTJ3_ZOUT_H) ==
    IMU_SUCCESS) {
        Serial.print(" Acceleration Z RAW = ");
        Serial.println((int8_t)dataLowRes);

        // Read accelerometer data in mg as Float
        Serial.print(" Acceleration Z float = ");
        Serial.println(myIMU.axisAccel(Z), 4);
    }
    Serial.println();
    delay(1000);
    }
}

void testRgb(void)
{
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, HIGH);
        

    for (int j = 0; j < 8; j++)
    {
        neoPixels.setPixelColor(j, neoPixels.Color(2, 0, 0));
        neoPixels.setPixelColor(j, neoPixels.Color(2, 0, 0));
        delay(100);
        neoPixels.show();
        neoPixels.show();

    }

    for (int j = 0; j < 8; j++)
    {
        neoPixels.setPixelColor(j, neoPixels.Color(0, 0, 2));
        neoPixels.setPixelColor(j, neoPixels.Color(0, 0, 2));
        delay(100);
        neoPixels.show();
        neoPixels.show();

    }

    for (int j = 0; j < 8; j++)
    {
        neoPixels.setPixelColor(j, neoPixels.Color(0, 2, 0));
        neoPixels.setPixelColor(j, neoPixels.Color(0, 2, 0));
        delay(100);
        neoPixels.show();
        neoPixels.show();

    }

    delay(1);

    // for (int i = 0; i < 5; i++)
    //     for (int j = 0; j < 7; j++)
    //     {
    //         pixels.setPixelColor(j, pixels.Color(0, 255, 0));
    //         pixels.show();
    //         delay(500);
    //         pixels.setPixelColor(j, pixels.Color(0, 0, 0));
    //         delay(500);
    //     }

}

// #include "DYPlayerArduino.h"
// DY::Player player(&Serial2);

// extern void audioLoop();
// extern void audioSetup();
// extern void audioOnline(void) ;
// extern void audioPlay(void);

void waitG0(void)
{
    pinMode(0, INPUT);
    while(!digitalRead(0))
    {
        Serial.println("Press button");
        delay(1000);
    }
}

extern void jobNone(void);
extern void jobServer(void);
extern void startPlayerJob(void);

void initDevice(void)
{
    zgConfigInit();
    switch(zgConfig()->DeviceRole)
    {
        case drServer:
            Serial.println(">>> SERVER ROLE");
            jobServer();
        break;

        case drPlayer:
            Serial.println(">>> PLAYER ROLE");
            startPlayerJob();
        break;

        case drNone:
            Serial.println(">>> NO ROLE");
            jobNone();
        break;
    }
}

void setup_tmp(void)
{
    Serial.begin(115200);
    //waitG0();
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, HIGH);
    SPIFFS.begin();
    setupTFT("BOOT");    
    selfPortalOnBoot(String(BUILD_NUMBER).toInt(), "X-GAME CONTROLLER");        
    //tftTestBmp();
    initDevice();
    delay(3000);
    Serial.println(">>> BOOT");
    
    Serial.printf("FLASH: %lu\r\n", ESP.getFlashChipSize());
    Serial.printf("PSRAM: %lu\r\n", ESP.getPsramSize());

    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 4000000);

        // if(!SPIFFS.begin(true))
    // {
    //   Serial.println("Error accessing SPIFFS");      
    //   while(true); 
    // }    
    
    
    // tftPrintText("VAL TEST");
    // valTest();    

    #ifdef ZBEACON
        beaconJob();
    #endif

    #ifdef ZRECEIVER

    #endif

    //Serial.println("!!! Wrong configuration !!!");
}


void loop_tmp(void)
{
    delay(1);
    //vTaskDelete(NULL);
    
    // audioPlay();
   
    // for (int i = 0; i < 60000; i++)
    // {
    //     audioLoop();
    //     delay(1);
    // }
    
}


