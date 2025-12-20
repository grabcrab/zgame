# Zombie Game Configuration File
# Edit these settings to customize your application

# Server Configuration
# Set HOST to '0.0.0.0' to accept connections from ESP32 devices on your network
# Set HOST to '127.0.0.1' to only allow local connections
SERVER_HOST = '0.0.0.0'  # Default: accept external connections
SERVER_PORT = 5000

# Game Default Settings
DEFAULT_HUMAN_PERCENTAGE = 50  # Percentage of devices assigned as humans (25-75)
DEFAULT_GAME_TIMEOUT = 30      # Timeout in seconds
DEFAULT_GAME_DURATION = 15     # Game duration in minutes

# Window Settings
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
WINDOW_TITLE = "Zombie Game - Server Control"

# Logging Level
# Options: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL = "INFO"
