if "%~1"=="" GOTO ERR
mkspiffs_espressif32_arduino.exe -c data -p 256 -b 4096 -s 7340032 spiffs\data.bin
esptool.exe --chip esp32s3 --port %1 --baud 921600  --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_size detect 8060928 spiffs\data.bin

goto DONE

:ERR
echo No COM port specified!!! Usage: uploader.bat COM1
pause

:DONE

	