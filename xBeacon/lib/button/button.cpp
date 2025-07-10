#include "button.h"
tButtonResult readButton(void)
{
    const int buttonPin = 0;              // GPIO_0
    const int shortPressThreshold = 1000; // 1 секунда в миллисекундах
    const int longPressThreshold = 5000;  // 5 секунд в миллисекундах

    // Если кнопка не нажата, сразу возвращаем brNone
    if (digitalRead(buttonPin) == HIGH)
    { // Предполагается, что кнопка подтянута к VCC и замыкает на GND
        return brNone;
    }

    // Кнопка нажата, начинаем отсчет времени
    unsigned long pressStartTime = millis();

    // Ждем отпускания кнопки или достижения максимального времени
    while (digitalRead(buttonPin) == LOW)
    {
        unsigned long currentDuration = millis() - pressStartTime;

        // Если превышено максимальное время длинного нажатия
        if (currentDuration > longPressThreshold)
        {
            // Ждем отпускания кнопки перед возвратом
            while (digitalRead(buttonPin) == LOW)
            {
                delay(10);
            }
            return brLong;
        }

        delay(10); // Небольшая задержка для стабильности
    }

    // Кнопка отпущена, определяем длительность нажатия
    unsigned long pressDuration = millis() - pressStartTime;

    if (pressDuration >= shortPressThreshold)
    {
        return brLong; // Длинное нажатие (1-5 секунд)
    }
    else
    {
        return brShort; // Короткое нажатие (до 1 секунды)
    }
}