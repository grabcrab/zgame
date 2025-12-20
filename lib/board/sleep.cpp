#include "board.h"

#include <driver/rtc_io.h>
#include <esp_sleep.h>
#include <esp32-hal-gpio.h>

void boardStartSleep(bool btnWake, bool accelWake)
{
    Serial.print(">>> boardStartSleep: ");
    
    uint64_t ext1_wakeup_mask = 0;
    
    // Configure button wake-up (GPIO0 - active LOW, needs pull-up)
    if (btnWake)
    {
        Serial.print("[BTN WAKE] ");
        
        // Initialize RTC GPIO for the button
        rtc_gpio_init((gpio_num_t)BUTTON_PIN);
        rtc_gpio_set_direction((gpio_num_t)BUTTON_PIN, RTC_GPIO_MODE_INPUT_ONLY);
        rtc_gpio_pullup_en((gpio_num_t)BUTTON_PIN);
        rtc_gpio_pulldown_dis((gpio_num_t)BUTTON_PIN);
        
        // Add to ext1 wake mask (wake on LOW for button press)
        ext1_wakeup_mask |= (1ULL << BUTTON_PIN);
    }
    
    // Configure accelerometer interrupt wake-up (active HIGH typically)
    if (accelWake)
    {
        if (accelWakeOnShake())
        {
            Serial.print("[ACCEL WAKE] ");
            
            // Initialize RTC GPIO for accelerometer interrupt
            rtc_gpio_init((gpio_num_t)ACCEL_INT_PIN);
            rtc_gpio_set_direction((gpio_num_t)ACCEL_INT_PIN, RTC_GPIO_MODE_INPUT_ONLY);
            rtc_gpio_pulldown_en((gpio_num_t)ACCEL_INT_PIN);
            rtc_gpio_pullup_dis((gpio_num_t)ACCEL_INT_PIN);
            
            // Add to ext1 wake mask
            ext1_wakeup_mask |= (1ULL << ACCEL_INT_PIN);
        }
        else 
        {
            Serial.print("[ACCEL ERROR] ");
        }
    }
    
    // Configure wake-up sources
    // Button is active-low (pressed = LOW), Accel interrupt is active-high
    // We need to handle these differently since ext1 can only wake on ALL_LOW or ANY_HIGH
    
    if (btnWake && accelWake && ext1_wakeup_mask)
    {
        // When both are enabled, we have a conflict:
        // - Button needs wake on LOW
        // - Accelerometer needs wake on HIGH
        // Solution: Use ext0 for button (single GPIO, level-triggered)
        //           Use ext1 for accelerometer (can do ANY_HIGH)
        
        // Reconfigure: Use ext0 for button
        esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);  // Wake on LOW
        
        // Use ext1 for accelerometer only
        esp_sleep_enable_ext1_wakeup(1ULL << ACCEL_INT_PIN, ESP_EXT1_WAKEUP_ANY_HIGH);
    }
    else if (btnWake)
    {
        // Only button wake - use ext0
        esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);  // Wake on LOW
    }
    else if (accelWake && ext1_wakeup_mask)
    {
        // Only accelerometer wake - use ext1
        esp_sleep_enable_ext1_wakeup(ext1_wakeup_mask, ESP_EXT1_WAKEUP_ANY_HIGH);
    }
    
    Serial.println();
    Serial.flush();
    
    // Turn off board power
    boardPowerOff();
    
    // Configure power domains for deep sleep
    // IMPORTANT: Keep RTC_PERIPH ON to maintain GPIO state for wake-up!
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
    
    // These can be turned off to save power
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_SLOW_MEM, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_FAST_MEM, ESP_PD_OPTION_OFF);
    esp_sleep_pd_config(ESP_PD_DOMAIN_XTAL, ESP_PD_OPTION_OFF);
    
    delay(100);
    
    esp_deep_sleep_start();
}