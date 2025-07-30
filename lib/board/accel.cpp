#include "board.h"

#include "kxtj3-1057.h"

KXTJ3 myIMU(KXTJ3_ADDR);
#define IMU_SAMPLE_RATE (6.25)
#define IMU_ACCEL_RANGE (2)
#define IMU_HIGH_RES (false)

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
    return true;
}

