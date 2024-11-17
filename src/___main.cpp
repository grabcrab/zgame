#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>

#include <Adafruit_NeoPixel.h>
#include <Wire.h>

// #include "soc/soc.h"
// #include "soc/rtc_cntl_reg.h"

#include "espRadio.h"
#include "kxtj3-1057.h"

extern void beaconJob(void);
extern void receiverJob(void*);

extern void setupTFT(void);
extern void loopTFT(void);

Adafruit_NeoPixel pixels(8, PIN_LED_MATRIX, NEO_GRB + NEO_KHZ800);

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
        pixels.setPixelColor(j, pixels.Color(2, 0, 0));
        delay(100);
        pixels.show();

    }

    for (int j = 0; j < 8; j++)
    {
        pixels.setPixelColor(j, pixels.Color(0, 0, 2));
        delay(100);
        pixels.show();

    }

    for (int j = 0; j < 8; j++)
    {
        pixels.setPixelColor(j, pixels.Color(0, 2, 0));
        delay(100);
        pixels.show();

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

void prepareWiFi(void)
{
    WiFi.mode(WIFI_AP_STA);
    WiFi.setTxPower(WIFI_POWER_19_5dBm);
    //esp_wifi_set_mode(ESPNOW_WIFI_MODE);
    esp_wifi_start();
    //esp_wifi_set_protocol( WIFI_IF_STA , WIFI_PROTOCOL_LR);
    esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B|WIFI_PROTOCOL_11G|WIFI_PROTOCOL_11N|WIFI_PROTOCOL_LR);
  
    if (esp_wifi_set_max_tx_power(WIFI_TX_POWER) != ESP_OK)
    {
        Serial.printf("esp_wifi_set_max_tx_power(%d) ERROR!!!\r\n", WIFI_TX_POWER);
    }
    esp_wifi_set_channel(ESP_CHANNEL, WIFI_SECOND_CHAN_NONE);
}
// #include "DYPlayerArduino.h"
// DY::Player player(&Serial2);

extern void audioLoop();
extern void audioSetup();
extern void audioOnline(void) ;
extern void audioPlay(void);

void setup(void)
{
    
    ///WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
    Serial.begin(115200);
    // while(!Serial.available())
    // {
    //     Serial.print("*");
    //     delay(1000);
    // }
    Serial.println(">>> BOOT");
    delay(10);
    Serial.printf("FLASH: %lu\r\n", ESP.getFlashChipSize());
    Serial.printf("PSRAM: %lu\r\n", ESP.getPsramSize());

    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 4000000);
    
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, HIGH);
    //testVibro();
    //audioOnline();    
    

    prepareWiFi();
    espInitRxTx(DEVICE_NUM);
    //Serial2.begin(115200, SERIAL_8N1, 11, 12);

    

    //while(true) 
    
    // player.begin();
    // player.setVolume(15); // 50% Volume
    // player.setCycleMode(DY::PlayMode::Repeat); // Play all and repeat.
    // player.play();
    // while(1) delay(1);

    setupTFT();
    // while(1)
    //     loopTFT();
    

    #ifdef ZBEACON
        beaconJob();
    #endif

    #ifdef ZRECEIVER
        //receiverJob();
        xTaskCreatePinnedToCore(
        receiverJob,             /* Function to implement the task */
        "receiverJob",           /* Name of the task */
        25000,                  /* Stack size in words */
        NULL,                  /* Task input parameter */
        7 | portPRIVILEGE_BIT, /* Priority of the task */
        NULL,                  /* Task handle. */
        1                      /* Core where the task should run */
    );
    #endif

    Serial.println("!!! Wrong configuration !!!");
}


void loop(void)
{
    //vTaskDelete(NULL);
    audioSetup();
    audioPlay();
   // delay(20000);
    while(true)
    {
        Serial.println("--> LOOP");    
        testAccel();
        testVibro();
        testRgb();

        for (int i = 0; i < 5000; i++)
        {
            audioLoop();
            delay(1);
        }        
    
    }
    delay(5000);
}


