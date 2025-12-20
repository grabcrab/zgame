# Zombie Game - Desktop Application Package

## What You've Received

This package contains everything you need to run your Zombie Game server as a standalone desktop application.

### Files Included

1. **zombie_game_app.py** - Main application (Flask + PyQt6)
2. **config.py** - Configuration file (server settings, game defaults)
3. **requirements.txt** - Python dependencies
4. **setup.py** - Automated setup script
5. **test_api.py** - API testing utility
6. **README.md** - Complete documentation
7. **QUICKSTART.md** - Quick start guide
8. **run_zombie_game.bat** - Windows launcher
9. **run_zombie_game.sh** - Linux/macOS launcher

### Key Features

✓ **Single Application**: Server and GUI in one window
✓ **Background Server**: Flask runs automatically
✓ **Network Access**: ESP32 devices can connect over WiFi
✓ **Configuration**: Easy customization via config.py
✓ **Auto-Setup**: One-command installation
✓ **Cross-Platform**: Works on Windows, macOS, and Linux

## Installation Steps

### Method 1: Automatic Setup (Recommended)

#### Windows
1. Extract all files to a folder
2. Double-click `run_zombie_game.bat`
3. Wait for automatic setup
4. Application will start

#### Linux/macOS
```bash
# Extract files and navigate to directory
cd zombie_game

# Run the launcher
./run_zombie_game.sh
```

### Method 2: Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Setup directories and templates
python setup.py

# Run application
python zombie_game_app.py
```

## Directory Structure After Setup

```
zombie_game/
├── zombie_game_app.py      # Main application
├── config.py               # Configuration
├── requirements.txt        # Dependencies
├── setup.py               # Setup script
├── test_api.py            # API tester
├── README.md              # Full documentation
├── QUICKSTART.md          # Quick guide
├── run_zombie_game.bat    # Windows launcher
├── run_zombie_game.sh     # Linux/macOS launcher
├── templates/             # HTML templates (auto-created)
│   ├── main.html
│   ├── prepare.html
│   ├── game.html
│   └── end.html
└── static/                # Static files (auto-created)
    └── logo.png (optional)
```

## Connecting ESP32 Devices

### 1. Find Your Computer's IP Address

**Windows**: Open Command Prompt
```cmd
ipconfig
```
Look for "IPv4 Address" (e.g., 192.168.1.100)

**macOS/Linux**: Open Terminal
```bash
ifconfig
# or
ip addr
```
Look for "inet" address

### 2. Configure ESP32

Update ESP32 code to connect to:
```
http://YOUR_IP:5000/api/device
```

Example:
```
http://192.168.1.100:5000/api/device?data={...}
```

### 3. Verify Configuration

Check `config.py` has:
```python
SERVER_HOST = '0.0.0.0'  # Accept network connections
SERVER_PORT = 5000
```

## Testing the Server

Use the included test script:

```bash
python test_api.py
```

This will:
- Test single device connection
- Test multiple devices
- Test game state flow
- Offer interactive testing mode

## Configuration Options

Edit `config.py` to customize:

```python
# Network Settings
SERVER_HOST = '0.0.0.0'  # '0.0.0.0' for network access
SERVER_PORT = 5000        # Change if port is in use

# Game Defaults
DEFAULT_HUMAN_PERCENTAGE = 50  # 25-75%
DEFAULT_GAME_TIMEOUT = 30      # seconds
DEFAULT_GAME_DURATION = 15     # minutes

# Window Settings
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
WINDOW_TITLE = "Zombie Game - Server Control"

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
```

## Troubleshooting

### Problem: PyQt6 Not Installed
**Solution:**
```bash
pip install PyQt6==6.6.1 PyQt6-WebEngine==6.6.0
```

### Problem: Port 5000 Already in Use
**Solution:** Edit `config.py`
```python
SERVER_PORT = 5001  # Use different port
```

### Problem: ESP32 Cannot Connect
**Solutions:**
1. Check firewall allows port 5000
2. Verify same WiFi network
3. Confirm `SERVER_HOST = '0.0.0.0'`
4. Use actual IP, not 127.0.0.1

### Problem: Templates Not Found
**Solution:**
```bash
python setup.py
```

### Problem: Application Won't Start
**Solutions:**
1. Check Python version: `python --version` (need 3.8+)
2. Reinstall dependencies: `pip install -r requirements.txt`
3. Check logs in console for specific errors

## Differences from Original Server

### Before (Separate Server + Browser)
- Run: `python server.py`
- Open browser manually
- Navigate to `http://localhost:5000`
- Two separate processes

### After (Integrated Application)
- Run: `python zombie_game_app.py`
- Window opens automatically
- Server embedded in application
- Single process, single window

## Support and Documentation

- **Full Documentation**: See `README.md`
- **Quick Start**: See `QUICKSTART.md`
- **Test Server**: Run `python test_api.py`
- **Check Logs**: Console output shows detailed info

## Network Information Display

When running, the application shows:
- **Local Access**: For your browser (127.0.0.1)
- **Network Access**: For ESP32 devices (your IP)
- **Server Status**: Running/Stopped

This information appears at the top of the application window.

## Additional Features

### Server Info Bar
Top of window shows:
- Server status
- Local access URL
- Network access URL (for ESP32)

### Graceful Shutdown
Confirmation dialog when closing to prevent accidental exit

### Auto-Detection
Application automatically detects your IP address for ESP32 connections

### Configuration Flexibility
All settings adjustable without code changes

## Next Steps

1. **Install**: Run automatic setup script
2. **Configure**: Edit `config.py` if needed
3. **Test**: Use `test_api.py` to verify server
4. **Connect**: Configure ESP32 devices with your IP
5. **Play**: Start the game!

## Questions?

Check the documentation:
- `README.md` - Complete guide
- `QUICKSTART.md` - Fast setup
- Console logs - Detailed information

Enjoy your Zombie Game!
