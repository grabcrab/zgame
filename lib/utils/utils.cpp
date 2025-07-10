#include "utils.h"

void ledSet(uint8_t R, uint8_t G, uint8_t B, uint8_t LC, uint8_t LW)
{
    digitalWrite(RGB_RED_PIN, R);
    digitalWrite(RGB_GREEN_PIN, G);
    digitalWrite(RGB_BLUE_PIN, B);
    if (LC != LED_DONT_CHANGE)
        digitalWrite(LC_PIN, LC);
    if (LC != LED_DONT_CHANGE)
        digitalWrite(LW_PIN, LW);
}

void ledInit(void)
{
    pinMode(RGB_RED_PIN, OUTPUT);
    digitalWrite(RGB_RED_PIN, LOW);

    pinMode(RGB_GREEN_PIN, OUTPUT);
    digitalWrite(RGB_GREEN_PIN, LOW);

    pinMode(RGB_BLUE_PIN, OUTPUT);
    digitalWrite(RGB_BLUE_PIN, LOW);

    pinMode(LC_PIN, OUTPUT);
    digitalWrite(LC_PIN, LOW);

    pinMode(LW_PIN, OUTPUT);
    digitalWrite(LW_PIN, LOW);
}

void ledHello(void)
{
    ledSet(1, 0, 0, 0, 0);
    delay(LED_HELLO_DELAY);
    ledSet(0, 1, 0, 0, 0);
    delay(LED_HELLO_DELAY);
    ledSet(0, 0, 1, 0, 0);
    delay(LED_HELLO_DELAY);
    ledSet(0, 0, 0, 1, 0);
    delay(LED_HELLO_DELAY);
    ledSet(0, 0, 0, 0, 1);
    delay(LED_HELLO_DELAY);
    ledSet(0, 0, 0, 0, 0);
}

void ledRed(tLedState ls)
{
    uint8_t ledState = uint8_t(ls);
    ledSet(ledState, 0, 0, digitalRead(LC_PIN), digitalRead(LW_PIN));
}

void ledGreen(tLedState ls)
{
    uint8_t ledState = uint8_t(ls);
    ledSet(0, ledState, 0, digitalRead(LC_PIN), digitalRead(LW_PIN));
}

void ledBlue(tLedState ls)
{
    uint8_t ledState = uint8_t(ls);
    ledSet(0, 0, ledState, digitalRead(LC_PIN), digitalRead(LW_PIN));
}

void ledRgbOff(void)
{
    ledSet(0, 0, 0, 0, 0);
}

uint32_t hexToInt(String hexStr)
{
    hexStr.replace("0x", "");
    hexStr.replace("0X", "");
    hexStr.toUpperCase();
    uint32_t res;
    sscanf(hexStr.c_str(), "%X", &res);
    return res;
}

uint32_t hexoDecToInt(String strVal)
{
    if (strVal.indexOf("x") >= 0)
        return hexToInt(strVal);
    return (uint32_t)strVal.toInt();
}

#define base16char(i) ("0123456789ABCDEF"[i])
String int64String(uint64_t value, uint8_t base, bool prefix, bool sign)
{
    if (base < 2)
        base = 2;
    else if (base > 16)
        base = 16;

    // start at position 64 (65th byte) and work backwards
    uint8_t i = 64;

    char buffer[66] = {0};

    if (value == 0)
        buffer[i--] = '0';
    else
    {
        uint8_t base_multiplied = 3;
        uint16_t multiplier = base * base * base;

        if (base < 16)
        {
            multiplier *= base;
            base_multiplied++;
        }
        if (base < 8)
        {
            multiplier *= base;
            base_multiplied++;
        }

        while (value > multiplier)
        {
            uint64_t q = value / multiplier;
            // get remainder without doing another division with %
            uint16_t r = value - q * multiplier;

            for (uint8_t j = 0; j < base_multiplied; j++)
            {
                uint16_t rq = r / base;
                buffer[i--] = base16char(r - rq * base);
                r = rq;
            }

            value = q;
        }

        uint16_t remaining = value;
        while (remaining > 0)
        {
            uint16_t q = remaining / base;
            buffer[i--] = base16char(remaining - q * base);
            remaining = q;
        }
    }

    if (base == DEC && sign)
        buffer[i--] = '-';
    else if (prefix)
    {
        if (base == HEX)
        {
            // 0x prefix
            buffer[i--] = 'x';
            buffer[i--] = '0';
        }
        else if (base == OCT)
            buffer[i--] = '0';
        else if (base == BIN)
            buffer[i--] = 'B';
    }

    // return String starting at position i + 1
    return String(&buffer[i + 1]);
}

String int64String(int64_t value, uint8_t base, bool prefix)
{
    // Signed numbers only make sense for decimal numbers
    bool sign = base == DEC && value < 0;

    uint64_t uvalue = sign ? -value : value;

    // call the unsigned function to format the number
    return int64String(uvalue, base, prefix, sign);
}

String utilsUint64ToHexString(uint64_t input)
{
    return int64String(input, HEX, false);
}

uint64_t utilsGetDeviceID64(void)
{
    return ESP.getEfuseMac();
}

String utilsGetDeviceID64Hex(void)
{
    return utilsUint64ToHexString(utilsGetDeviceID64());
}