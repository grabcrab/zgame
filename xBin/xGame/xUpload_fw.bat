if "%~1"=="" GOTO ERR
esptool.exe --port %1 --chip esp32s3 --baud 921600 write_flash 0x00000 bin\bootloader.bin
timeout /t 3 /nobreak
esptool.exe --port %1 --chip esp32s3 --baud 921600 write_flash 0x08000 bin\partitions.bin
timeout /t 3 /nobreak
esptool.exe --port %1 --chip esp32s3 --baud 921600 write_flash 0x10000 bin\firmware.bin
timeout /t 3 /nobreak

goto DONE

:ERR
echo No COM port specified!!! Usege: uploader.bat COM1
pause

:DONE
