// /*
//   ESP32 SD I2S Music Player
//   esp32-i2s-sd-player.ino
//   Plays MP3 file from microSD card
//   Uses MAX98357 I2S Amplifier Module
//   Uses ESP32-audioI2S Library - https://github.com/schreibfaul1/ESP32-audioI2S
//   * 
//   DroneBot Workshop 2022
//   https://dronebotworkshop.com
// */

// // Include required libraries
// #include "Arduino.h"
// #include "Audio.h"

// #include "FS.h"
// #include "SPIFFS.h"
 
 
// // I2S Connections

 
//  // Create Audio object
// Audio audio;
 
 
// void audioLoop()
// {
//     audio.loop();    
// }

// bool audioPlay(const char *fName, int volume)
// {
//     audio.setPinout(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DOUT);    
//     audio.setVolume(volume);

//     if (!audio.connecttoFS(SPIFFS, fName))
//     {
//         //Serial.println("FS play started");
//         return true;
//     }
//     else 
//     {
//         Serial.printf("!!! FS play ERROR: %s\r\n", fName);
//     }
// }

// #include "WiFiMulti.h"

// WiFiMulti wifiMulti;

// String ssid =     "Yam-Yam";
// String password = "runner1978";

// // #define I2S_LRC     26
// // #define I2S_DOUT    25
// // #define I2S_BCLK    27
// // #define I2S_MCLK     0

// void audioOnline(void) 
// {
//     Serial.begin(115200);
//     wifiMulti.addAP(ssid.c_str(), password.c_str());
//     wifiMulti.run();
//     Serial.println("\nConnecting to Wi-Fi..");
//     while(!WiFi.isConnected())
//     {
//         Serial.print(".");
//         delay(1000);
//     }

//     Serial.println("DONE");
//     //audio.forceMono(false);
//     audio.setPinout(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DOUT);
//     audio.setVolume(3); // 0...21
//     audio.setConnectionTimeout(500, 2700);
//     audio.setBufsize(0, 1000000);
//     while(!audio.connecttohost("http://us3.internet-radio.com:8342/stream"))
//     {
//         Serial.println("Connecting to the host...");
//         delay(1000);
//     }
//     Serial.println(">>> STREAM");
//     while(true)
//     {
//         audio.loop();
//         vTaskDelay(20);
//     }
// }