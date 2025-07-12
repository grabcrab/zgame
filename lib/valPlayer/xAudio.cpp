#include "valPlayer.h"

#include "Arduino.h"
#include "Audio.h"

static Audio audio;

bool audioPlay(const char *fName, int volume)
{
    audio.setPinout(PIN_I2S_BCLK, PIN_I2S_LRC, PIN_I2S_DOUT);    
    audio.stopSong();
    audio.setVolume(volume);
    audio.setBufsize(0, 1000000);

    if (audio.connecttoFS(PSRamFS, fName))
    {
        //Serial.println("FS play started");
        return true;
    }
    Serial.printf("!!! FS play ERROR: %s\r\n", fName);
    return false;
}

void audioLoop(void)
{
    audio.loop();    
}