#ifndef __TCU_BOARD_H__
#define __TCU_BOARD_H__
#ifndef ESP32_S3
#include <Arduino.h>

#define LED_PIN           14
#define SENSOR_POWER_PIN  12
#define DALLAS_PIN        15


// #define VOLTAGE_PIN 0
// #define PREFS_VALUE_NAME  "voltcf1"
// #define VOLTAGE_CALIBRATION_LEVEL 2600.0
// #define COEFF_NOT_DEFINED  90.0


void boardInit(void);
void boardShutdown(void);

int boardGetBatteryVoltageMV(void);
void boardIsolatePin(gpio_num_t pin, bool init);
void boardUnisolatePin(gpio_num_t pin);
void boardIsolatePins(void);
void boardUnisolatePins(void);

void boardLed(unsigned int ms);
void boardLedOn(void);
void boardLedOff(void);
void boardOnSensorPower(void);
void boardOffSensorPower(void);
void save_ADC_Reg(void);
void restore_ADC_Reg(void);

float tsReadDallas(uint32_t &errCount);

#endif //__TCU_BOARD_H__
#endif //#ifndef ESP32_S3