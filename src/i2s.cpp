/*
  ESP32 SD I2S Music Player
  esp32-i2s-sd-player.ino
  Plays MP3 file from microSD card
  Uses MAX98357 I2S Amplifier Module
  Uses ESP32-audioI2S Library - https://github.com/schreibfaul1/ESP32-audioI2S
  * 
  DroneBot Workshop 2022
  https://dronebotworkshop.com
*/

// Include required libraries
#include "Arduino.h"
#include "Audio.h"

#include "FS.h"
#include "SPIFFS.h"
 
 
// I2S Connections

 
 // Create Audio object
Audio audio;
 
void audioSetup() 
{
    
        // Start Serial Port
    Serial.begin(115200);
    
    // Start microSD Card
    if(!SPIFFS.begin(true))
    {
      Serial.println("Error accessing SPIFFS");
      while(true); 
    }
    
    // Setup I2S 
    audio.setPinout(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DOUT);    
    
    // Set Volume    
    audio.setVolume(10);
   
    
    // Open music file

    
}
 
void audioLoop()
{
    audio.loop();    
}

void audioPlay(void)
{
    if (audio.connecttoFS(SPIFFS,"/2.mp3"))
        Serial.println("FS play started");
    else 
        Serial.println("FS play ERROR");
}

#include "WiFiMulti.h"

WiFiMulti wifiMulti;

String ssid =     "Yam-Yam";
String password = "runner1978";

// #define I2S_LRC     26
// #define I2S_DOUT    25
// #define I2S_BCLK    27
// #define I2S_MCLK     0

void audioOnline(void) 
{
    Serial.begin(115200);
    wifiMulti.addAP(ssid.c_str(), password.c_str());
    wifiMulti.run();
    Serial.println("\nConnecting to Wi-Fi..");
    while(!WiFi.isConnected())
    {
        Serial.print(".");
        delay(1000);
    }

    Serial.println("DONE");
    //audio.forceMono(false);
    audio.setPinout(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DOUT);
    audio.setVolume(3); // 0...21
    audio.setConnectionTimeout(500, 2700);
    audio.setBufsize(0, 1000000);
    while(!audio.connecttohost("http://us3.internet-radio.com:8342/stream"))
    {
        Serial.println("Connecting to the host...");
        delay(1000);
    }
    Serial.println(">>> STREAM");
    while(true)
    {
        audio.loop();
        vTaskDelay(20);
    }
}