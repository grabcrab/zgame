#include "board.h"

#include <driver/rtc_io.h>
#include <esp_sleep.h>
#include <esp32-hal-gpio.h>


void boardStartSleep(bool btnWake, bool accelWake)
{
    Serial.print(">>> boardStartSleep: ");
        
    rtc_gpio_pullup_dis  ((gpio_num_t) BUTTON_PIN);
    rtc_gpio_pulldown_dis((gpio_num_t) BUTTON_PIN);
    rtc_gpio_pullup_dis  ((gpio_num_t) ACCEL_INT_PIN);
    rtc_gpio_pulldown_dis((gpio_num_t) ACCEL_INT_PIN);

    // if (btnWake)    
    // {
    //     Serial.print("[BTN WAKE] ");
    //     rtc_gpio_deinit((gpio_num_t) BUTTON_PIN);                      
    //     esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);
    // }
    
    if (accelWake)
    {
        if (accelWakeOnShake())
        {
            Serial.print("[ACCEL WAKE] ");
            rtc_gpio_deinit((gpio_num_t) ACCEL_INT_PIN);                   
            esp_sleep_enable_ext1_wakeup(
                1ULL << ACCEL_INT_PIN,                        
                ESP_EXT1_WAKEUP_ANY_HIGH);                    
        }
        else 
        {
            Serial.print("[ACCEL ERROR] ");
        }
    }
    Serial.println();
    boardPowerOff();
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_SLOW_MEM, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_FAST_MEM, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_XTAL, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_CPU,  ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_VDDSDIO, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_MAX, ESP_PD_OPTION_OFF);
    delay(100);
    
    esp_deep_sleep_start();
}

