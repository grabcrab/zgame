# Zombie Game - Standalone Desktop Application

A desktop application that runs the ESP32 Zombie Game server with an integrated GUI. This application combines the Flask web server and PyQt6 GUI into a single executable instance.

## Features

- **Embedded Web Interface**: Full game control interface within a desktop window
- **Background Server**: Flask server runs automatically in the background
- **ESP32 Device Support**: Devices can connect to the server's API endpoints
- **Single Instance**: Everything runs from one application - no separate server needed

## Requirements

- Python 3.8 or higher
- pip (Python package manager)

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:

```bash
pip install Flask==3.0.0 PyQt6==6.6.1 PyQt6-WebEngine==6.6.0
```

### 2. Setup Project Structure

Create the following directory structure:

```
zombie_game/
├── zombie_game_app.py
├── requirements.txt
├── templates/
│   ├── main.html
│   ├── prepare.html
│   ├── game.html
│   └── end.html
└── static/
    └── logo.png (optional)
```

### 3. Copy Template Files

Copy your existing HTML template files into the `templates/` directory:
- `main.html`
- `prepare.html`
- `game.html`
- `end.html`

Optionally, add a logo image to the `static/` directory.

## Running the Application

### Basic Usage

```bash
python zombie_game_app.py
```

The application will:
1. Start the Flask server on `http://127.0.0.1:5000`
2. Open a desktop window with the game interface
3. Begin accepting connections from ESP32 devices

### Accessing from ESP32 Devices

ESP32 devices should connect to your computer's local IP address on port 5000.

**Find your local IP:**

- **Windows**: `ipconfig` (look for IPv4 Address)
- **macOS/Linux**: `ifconfig` or `ip addr` (look for inet address)

**Example ESP32 connection URL:**
```
http://192.168.1.100:5000/api/device?data={...}
```

Replace `192.168.1.100` with your actual local IP address.

## API Endpoint

### Device Update Endpoint

**URL:** `GET /api/device`

**Query Parameter:** `data` (JSON string)

**Required JSON Fields:**
```json
{
  "id": "device123",
  "ip": "192.168.1.100",
  "rssi": -65,
  "role": "neutral",
  "status": "sleep",
  "health": 100,
  "battery": 85,
  "comment": "Device operational"
}
```

**Response:**
```json
{
  "role": "human",
  "status": "game",
  "game_timeout": 30,
  "game_duration": 15
}
```

## Game States

1. **Sleep**: Initial state, no active game
2. **Prepare**: Setup phase - configure game parameters and wait for devices
3. **Game**: Active game in progress
4. **End**: Game finished, showing final results

## Configuration

Edit the following variables in `zombie_game_app.py` if needed:

```python
# Server configuration
HOST = '127.0.0.1'  # Change to '0.0.0.0' to accept external connections
PORT = 5000

# Game defaults
game_state = {
    'human_percentage': 50,  # % of devices assigned as humans
    'game_timeout': 30,      # Timeout in seconds
    'game_duration': 15,     # Game duration in minutes
}
```

## Troubleshooting

### Port Already in Use

If port 5000 is already in use, change the port in `zombie_game_app.py`:

```python
app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)
```

And update the browser URL:
```python
self.browser.setUrl(QUrl("http://127.0.0.1:5001/"))
```

### Templates Not Found

Ensure all HTML files are in the `templates/` directory:

```bash
ls templates/
# Should show: main.html  prepare.html  game.html  end.html
```

### Cannot Connect from ESP32

1. Make sure your computer's firewall allows incoming connections on port 5000
2. Verify ESP32 and computer are on the same network
3. Use your computer's actual IP address, not 127.0.0.1
4. Consider changing the Flask host to `0.0.0.0`:

```python
app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
```

### PyQt6 Import Errors

If you encounter import errors with PyQt6:

```bash
pip uninstall PyQt6 PyQt6-WebEngine
pip install PyQt6==6.6.1 PyQt6-WebEngine==6.6.0
```

## Building a Standalone Executable (Optional)

To create a standalone executable that doesn't require Python installation:

### Using PyInstaller

```bash
pip install pyinstaller

pyinstaller --onefile --windowed \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --name "ZombieGame" \
  zombie_game_app.py
```

The executable will be in the `dist/` directory.

## Development

### Logging

The application logs to the console. Change logging level in `zombie_game_app.py`:

```python
logging.basicConfig(level=logging.DEBUG)  # More verbose
logging.basicConfig(level=logging.INFO)   # Normal
logging.basicConfig(level=logging.ERROR)  # Errors only
```

### Adding Features

The Flask app and PyQt window are separated for easy modification:

- **Flask routes**: Add new routes in the Flask section
- **GUI changes**: Modify the `ZombieGameWindow` class
- **Game logic**: Update functions like `assign_roles()`

## License

This software is provided as-is for use with ESP32 Zombie Game devices.

## Support

For issues or questions, please check:
1. All template files are present
2. Port 5000 is available
3. Firewall allows connections
4. ESP32 devices use correct IP address
