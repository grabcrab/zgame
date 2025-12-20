# Quick Start Guide - Zombie Game Desktop App

## Installation (First Time Only)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Application

```bash
python setup.py
```

This will:
- Create `templates/` and `static/` directories
- Copy HTML template files
- Check for required dependencies

## Running the Application

```bash
python zombie_game_app.py
```

## Configuration

Edit `config.py` to customize:

```python
SERVER_HOST = '0.0.0.0'  # Accept external connections
SERVER_PORT = 5000        # Server port
```

## Connecting ESP32 Devices

### Find Your IP Address

**Windows:**
```cmd
ipconfig
```
Look for "IPv4 Address" under your active network adapter.

**macOS/Linux:**
```bash
ifconfig
# or
ip addr
```
Look for "inet" address (e.g., 192.168.1.100).

### ESP32 Connection

Configure ESP32 devices to connect to:
```
http://YOUR_IP_ADDRESS:5000/api/device
```

Example:
```
http://192.168.1.100:5000/api/device?data={...}
```

## Troubleshooting

### PyQt6 Not Installed
```bash
pip install PyQt6==6.6.1 PyQt6-WebEngine==6.6.0
```

### Port 5000 Already in Use
Edit `config.py`:
```python
SERVER_PORT = 5001  # Use different port
```

### ESP32 Cannot Connect

1. Check firewall settings (allow port 5000)
2. Ensure computer and ESP32 are on same network
3. Verify `SERVER_HOST = '0.0.0.0'` in `config.py`
4. Use computer's actual IP address (not 127.0.0.1)

### Template Files Not Found

Run setup again:
```bash
python setup.py
```

Or manually copy HTML files to `templates/` directory.

## File Structure

```
zombie_game/
├── zombie_game_app.py    # Main application
├── config.py             # Configuration file
├── requirements.txt      # Python dependencies
├── setup.py             # Setup script
├── README.md            # Full documentation
├── QUICKSTART.md        # This file
├── templates/           # HTML templates
│   ├── main.html
│   ├── prepare.html
│   ├── game.html
│   └── end.html
└── static/              # Static files
    └── logo.png         # Optional logo
```

## Common Commands

```bash
# First time setup
pip install -r requirements.txt
python setup.py

# Run application
python zombie_game_app.py

# Check your IP address (Windows)
ipconfig

# Check your IP address (macOS/Linux)
ifconfig
```

## Support

Check logs in the console for detailed error messages.

Common issues:
- Missing templates → Run `python setup.py`
- Port in use → Change `SERVER_PORT` in `config.py`
- ESP32 can't connect → Check firewall and network settings
