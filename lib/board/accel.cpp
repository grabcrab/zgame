#include "board.h"

#include "kxtj3-1057.h"

KXTJ3 myIMU(KXTJ3_ADDR);
#define IMU_SAMPLE_RATE (6.25)
#define IMU_ACCEL_RANGE (2)
#define IMU_HIGH_RES (false)

// Wake-up configuration
// Threshold (g) = threshold (counts) / 256 (counts/g)
// For 0.5g threshold: 0.5 * 256 = 128 counts
#define WAKE_THRESHOLD_COUNTS (128)

// Movement duration before wake-up triggers
// timeDur (sec) = WAKEUP_COUNTER (counts) / Wake-Up Function ODR (Hz)
// For 6.25 Hz and 1 count: 1/6.25 = 0.16 sec
#define WAKE_MOVE_DURATION (1)

// Non-activity time before another interrupt can trigger
// For 6.25 Hz and 1 count: 1/6.25 = 0.16 sec
#define WAKE_NA_DURATION (1)

bool accelInit(void)
{
    if (myIMU.begin(IMU_SAMPLE_RATE, IMU_ACCEL_RANGE, IMU_HIGH_RES) == IMU_SUCCESS)
    {
        Serial.println(">>> accelInit: OK");
        return true;
    }
    else
    {
        Serial.println("!!! accelInit: ERROR!");
        return false;
    }
}

bool accelWakeOnShake(void)
{
    // Configure the KXTJ3 accelerometer for motion wake-up interrupt
    // using the library's intConf() method
    //
    // Parameters:
    //   threshold: -2048 to 2047 counts (g = counts/256)
    //   moveDur:   1-255 counts (time = counts / ODR)
    //   naDur:     1-255 counts (non-activity time)
    //   polarity:  HIGH = active high interrupt (matches ESP32 ext1 ANY_HIGH)
    //   wuRate:    -1 = use IMU sample rate
    //   latched:   true = latch interrupt until cleared
    //   pulsed:    false = not pulsed
    //   motion:    true = enable wake-up/motion detection
    //   dataReady: false = don't trigger on data ready
    //   intPin:    true = enable physical interrupt pin output
    
    kxtj3_status_t result = myIMU.intConf(
        WAKE_THRESHOLD_COUNTS,  // threshold in counts (128 = ~0.5g)
        WAKE_MOVE_DURATION,     // movement duration counter
        WAKE_NA_DURATION,       // non-activity duration counter
        HIGH,                   // polarity: active HIGH (for ESP32 ext1 wakeup)
        -1,                     // wuRate: use IMU data rate
        true,                   // latched: yes, latch until cleared
        false,                  // pulsed: no
        true,                   // motion: enable wake-up function
        false,                  // dataReady: disabled
        true                    // intPin: enable interrupt pin
    );
    
    if (result != IMU_SUCCESS)
    {
        Serial.print("!!! accelWakeOnShake: intConf failed with error ");
        Serial.println(result);
        return false;
    }
    
    Serial.println(">>> accelWakeOnShake: OK");
    return true;
}