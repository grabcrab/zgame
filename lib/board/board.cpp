#include <board.h>
#include <esp_adc_cal.h>

#include "pin_config.h"

void boardPowerOn(void)
{
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, HIGH);
}

void boardPowerOff(void)
{
    pinMode(PIN_POWER, OUTPUT);
    digitalWrite(PIN_POWER, LOW);
}

uint16_t boardGetVcc(void)
{
    esp_adc_cal_characteristics_t adc_chars;

    // Get the internal calibration value of the chip
    esp_adc_cal_value_t val_type = esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_11, ADC_WIDTH_BIT_12, 1100, &adc_chars);
    uint32_t raw = analogRead(PIN_BAT_VOLT);
    uint32_t v1 = esp_adc_cal_raw_to_voltage(raw, &adc_chars) * 2;
    return v1;
}

uint8_t boardGetVccPercent(void)
{
    int voltage_mV = boardGetVcc();
    const int voltage_table[][2] = 
    {
        {4200, 100},
        {4150, 95},
        {4110, 90},
        {4080, 85},
        {4020, 80},
        {3980, 75},
        {3950, 70},
        {3910, 65},
        {3870, 60},
        {3850, 55},
        {3840, 50},
        {3820, 45},
        {3800, 40},
        {3790, 35},
        {3770, 30},
        {3750, 25},
        {3730, 20},
        {3710, 15},
        {3690, 10},
        {3610, 5},
        {3000, 0}
    };

    const int table_size = sizeof(voltage_table) / sizeof(voltage_table[0]);

    // Handle edge cases
    if (voltage_mV >= voltage_table[0][0])
        return voltage_table[0][1];
    if (voltage_mV <= voltage_table[table_size - 1][0])
        return voltage_table[table_size - 1][1];

    // Linear interpolation between table values
    for (int i = 0; i < table_size - 1; i++)
    {
        if (voltage_mV <= voltage_table[i][0] && voltage_mV >= voltage_table[i + 1][0])
        {
            int v1 = voltage_table[i + 1][0];
            int v2 = voltage_table[i][0];
            int p1 = voltage_table[i + 1][1];
            int p2 = voltage_table[i][1];

            return p1 + (voltage_mV - v1) * (p2 - p1) / (v2 - v1);
        }
    }

    return 0; // Fallback
}