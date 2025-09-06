# SPOTO ESP32 SPIFFS Manager - User Manual

## Overview

ESP32 SPIFFS Manager is a Python tool that allows you to upload and download files to/from your ESP32's SPIFFS (SPI Flash File System) partition.

## Prerequisites

### Required Files

Ensure these files are in the same directory as the Python script:

- `esptool.exe` - ESP32 flash tool
- `mkspiffs_espressif32_arduino.exe` - SPIFFS creation tool
- `spiffs_manager.py` - Main Python script
- `_spiffs_manager.bat` - Batch file to run the script

### Required Software

- **Python 3.x** installed on your system
- **pyserial library**: Install with `pip install pyserial`

### Hardware

- ESP32-S3 development board
- USB cable for connection

## How to Use

### Starting the Tool

1. Double-click `*spiffs*manager.bat` or run `python spiffs_manager.py` in command prompt
2. The tool will automatically check for required files and dependencies

### Main Menu Options

The tool presents three options:

1. **Download SPIFFS from ESP32** - Extract files from ESP32 to your computer
2. **Upload SPIFFS to ESP32** - Send files from your computer to ESP32
3. **Exit** - Close the program

### COM Port Selection

The tool automatically detects available COM ports and displays them in a numbered list:

**Example:**

```
Detected COM ports:
1. COM8 - USB-Enhanced-SERIAL CH343 (COM8)
2. COM10 - USB Serial Device (COM10)
3. COM28 - Standard Serial over Bluetooth link (COM28)
4. COM29 - Standard Serial over Bluetooth link (COM29)
5. Enter manually
```

**How to select:**

- **Enter the number** (1-4 in this example) corresponding to your ESP32
- ESP32 devices typically show as "USB-Enhanced-SERIAL" or "USB Serial Device"
- **Avoid Bluetooth ports** (COM28, COM29 in example) - these won't work for ESP32
- Choose **option 5** to manually enter a COM port if your device isn't listed
- **Manual format**: `COM15` (Windows) or similar

## Operations

### Downloading Files from ESP32

1. Select option **1** from the main menu
2. Choose your ESP32's COM port
3. The tool will:
   - Read the SPIFFS partition from ESP32
   - Create/clear the `data` folder
   - Extract all files to the `data` folder

### Uploading Files to ESP32

1. Create a `data` folder in the script directory
2. Place all files you want to upload in the `data` folder
3. Select option **2** from the main menu
4. Choose your ESP32's COM port
5. The tool will:
   - Create a SPIFFS image from your `data` folder
   - Upload it to the ESP32's SPIFFS partition

## Directory Structure

```
your-project/
├── *spiffs*manager.bat      # Batch file to run the tool
├── spiffs_manager.py        # Main Python script
├── esptool.exe             # ESP32 flash tool
├── mkspiffs_espressif32_arduino.exe  # SPIFFS creation tool
├── partition-table.bin     # Generated during download operations
├── data/                   # Your files for upload/download
│   ├── cloud_config.json   # Example files
│   ├── logo.png
│   ├── mini_config.json
│   └── zero.json
└── spiffs/                 # Generated SPIFFS images
    └── data.bin           # Created during upload operations
```

## Important Notes

- **Target Device**: Configured for ESP32-S3 chips
- **SPIFFS Partition**: Uses address `0x670000` with size `0x180000` (1.5MB)
- **Data Safety**: Download operation clears the `data` folder first
- **File Limits**: Respect SPIFFS size limitations (1.5MB total)

## Troubleshooting

### Common Issues

- **"No COM ports detected"**: Check USB cable and ESP32 connection
- **"Missing required files"**: Ensure `esptool.exe` and `mkspiffs_espressif32_arduino.exe` are present
- **"pyserial library not found"**: Run `pip install pyserial`
- **Upload fails**: Ensure `data` folder exists with files to upload

### ESP32 Connection Tips

- Press and hold BOOT button during upload if needed
- Use a quality USB cable (some cables are power-only)
- Try different USB ports
- Check Windows Device Manager for driver issues

## Command Line Usage

You can also run the script directly:

```bash
python spiffs_manager.py
```

## File Size Considerations

- Total SPIFFS size: 1.5MB (1,572,864 bytes)
- Leave some free space for filesystem overhead
- Monitor your `data` folder size before uploading
