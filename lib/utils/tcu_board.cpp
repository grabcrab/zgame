#ifndef ESP32_S3

#include <soc/sens_reg.h>
//#include <OneWire.h>
#include <DallasTemperature.h>

#include "tcu_board.h"

uint64_t reg_b;             

extern "C"  esp_err_t rtc_gpio_isolate(gpio_num_t gpio_num);
extern "C"  esp_err_t rtc_gpio_hold_dis(gpio_num_t gpio_num);
extern "C"  int rom_phy_get_vdd33();

OneWire oneWire(DALLAS_PIN);
DallasTemperature sensors(&oneWire);

float tsReadDallas(uint32_t &errCount)
{
    float t;
    sensors.begin();
    sensors.setResolution(10);    
    sensors.requestTemperatures(); 
    t = sensors.getTempCByIndex(0);    
    if ((t<-50)||(t>=85)||(t==25.0))
    {
        Serial.printf("tsReadDallas: wrong value (%.2f), remeasuring[1]\r\n", t);
        sensors.requestTemperatures();
        delay(1200);
        t = sensors.getTempCByIndex(0);
        errCount++;
    }

    if ((t<-50)||(t>=85)||(t==25.0))
    {
        Serial.printf("tsReadDallas: wrong value (%.2f), remeasuring[2]\r\n", t);
        sensors.requestTemperatures();
        delay(1200);
        t = sensors.getTempCByIndex(0);
        errCount++;
    }    
    return t;   
}

void boardIsolatePin(gpio_num_t pin, bool init)
{
    if (init)
    {
        pinMode(pin, OUTPUT);
        digitalWrite(pin,LOW);
    }
    rtc_gpio_isolate(pin);
}

void boardUnisolatePin(gpio_num_t pin)
{
    rtc_gpio_hold_dis(pin);
}

void isolateGPIO_0(void)
{
    pinMode(GPIO_NUM_0, OUTPUT);
    digitalWrite(GPIO_NUM_0,HIGH);
    rtc_gpio_isolate(GPIO_NUM_0);
}

void boardIsolatePins(void)
{    
    boardLedOff();    
    boardIsolatePin(GPIO_NUM_14, true);
    boardIsolatePin(GPIO_NUM_12, true);
    boardIsolatePin(GPIO_NUM_27, false);
    //boardIsolatePin(GPIO_NUM_21, false);    
    //boardIsolatePin(GPIO_NUM_22, false);    
    isolateGPIO_0();
    //boardIsolatePin(GPIO_NUM_1, false);
    //boardIsolatePin(GPIO_NUM_3, false);
    boardIsolatePin(GPIO_NUM_36, false);
    //boardIsolatePin(GPIO_NUM_23, false);    
    boardIsolatePin(GPIO_NUM_15, false);
}

void boardUnisolatePins(void)
{
    #ifndef ESP32_S3
    boardUnisolatePin(GPIO_NUM_14);
    boardUnisolatePin(GPIO_NUM_12); 
    boardUnisolatePin(GPIO_NUM_27);
    //boardUnisolatePin(GPIO_NUM_21);
    boardUnisolatePin(GPIO_NUM_22);
    boardUnisolatePin(GPIO_NUM_0);
    //boardUnisolatePin(GPIO_NUM_1);
    //boardUnisolatePin(GPIO_NUM_3);
    boardUnisolatePin(GPIO_NUM_36);
    //boardUnisolatePin(GPIO_NUM_23);
    boardUnisolatePin(GPIO_NUM_15);    
    #endif //ESP32_S3
}

void boardInit(void)
{    
    boardUnisolatePins();
    pinMode(LED_PIN,OUTPUT);
    boardLedOff();
    //boardOnSensorPower();
    save_ADC_Reg();
}

void boardShutdown(void)
{
    boardLedOff();
    boardIsolatePins();
    boardOffSensorPower(); 
    restore_ADC_Reg();
}

void boardLed(unsigned int ms)
{
    boardLedOn();
    delay(ms);
    boardLedOff();  
}

void boardLedOn(void)
{
    digitalWrite(LED_PIN,HIGH);
}

void boardLedOff(void)
{
    digitalWrite(LED_PIN,LOW); 
}

void boardGetBatVoltage(void)
{
    float res;
    int internalBatReading = 0;
    btStart();
    res = rom_phy_get_vdd33();
    btStop();   
    Serial.println(res);
}

void boardOnSensorPower(void)
{
 pinMode(SENSOR_POWER_PIN, OUTPUT);
 digitalWrite(SENSOR_POWER_PIN,HIGH);
}

void boardOffSensorPower(void)
{
 digitalWrite(SENSOR_POWER_PIN,LOW);
}

int boardGetBatteryVoltageMV(void)
{
    int internalBatReading = 0;
    btStart();
    float volt = 0;
    internalBatReading = rom_phy_get_vdd33();
    volt = (((float)internalBatReading/(float)6245)*3.3)*1000;
    btStop();   
    return volt;
}

void save_ADC_Reg(void)
{
    #ifndef ESP32_S3
    reg_b = READ_PERI_REG(SENS_SAR_READ_CTRL2_REG);
    #endif
}

void restore_ADC_Reg(void)
{
    #ifndef ESP32_S3
    WRITE_PERI_REG(SENS_SAR_READ_CTRL2_REG, reg_b);
    SET_PERI_REG_MASK(SENS_SAR_READ_CTRL2_REG, SENS_SAR2_DATA_INV);
    #endif
}
#endif //#ifndef ESP32_S3