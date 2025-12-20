#!/usr/bin/env python3
"""
Zombie Game - Standalone Application
A desktop application that runs the zombie game server and GUI in a single instance.
"""

import sys
import os
import json
import random
import time
import threading
import logging
import socket
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, render_template, redirect, url_for, send_from_directory
from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QLabel, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

# Try to import config, use defaults if not found
try:
    from config import *
except ImportError:
    # Default configuration
    SERVER_HOST = '0.0.0.0'
    SERVER_PORT = 5000
    DEFAULT_HUMAN_PERCENTAGE = 50
    DEFAULT_GAME_TIMEOUT = 30
    DEFAULT_GAME_DURATION = 15
    WINDOW_WIDTH = 1400
    WINDOW_HEIGHT = 900
    WINDOW_TITLE = "Zombie Game - Server Control"
    LOG_LEVEL = "INFO"

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'zombie-game-secret-key'

# In-memory storage for device data
devices = {}
game_state = {
    'status': 'sleep',
    'human_percentage': DEFAULT_HUMAN_PERCENTAGE,
    'game_timeout': DEFAULT_GAME_TIMEOUT,
    'game_duration': DEFAULT_GAME_DURATION,
    'game_start_time': None,
    'zombies': [],
    'humans': []
}

# Lock for thread-safe device updates
devices_lock = threading.Lock()


def assign_roles():
    """Assign roles to devices based on human percentage"""
    with devices_lock:
        device_list = list(devices.keys())
        if not device_list:
            return
        
        # Calculate number of humans
        total_devices = len(device_list)
        num_humans = max(1, int(total_devices * game_state['human_percentage'] / 100))
        
        # Randomly select humans
        random.shuffle(device_list)
        selected_humans = device_list[:num_humans]
        
        # Clear existing role assignments
        game_state['humans'] = []
        game_state['zombies'] = []
        
        # Assign roles
        for device_id in device_list:
            if device_id in selected_humans:
                devices[device_id]['role'] = 'human'
                game_state['humans'].append(device_id)
            else:
                devices[device_id]['role'] = 'zombie'
                game_state['zombies'].append(device_id)
        
        logger.debug(f"Assigned roles: {num_humans} humans, {total_devices - num_humans} zombies")


# Flask Routes
@app.route('/api/device', methods=['GET'])
def device_update():
    logger.debug("Received request to /api/device")
    data_str = request.args.get('data')
    if not data_str:
        logger.error("No data provided in query parameter")
        return jsonify({'error': 'No data provided'}), 400

    try:
        data = json.loads(data_str)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {e}")
        return jsonify({'error': 'Invalid JSON format'}), 400

    if not all(key in data for key in ['id', 'ip', 'rssi', 'role', 'status', 'health', 'battery', 'comment']):
        logger.error("Missing required fields in JSON data")
        return jsonify({'error': 'Missing required fields'}), 400

    with devices_lock:
        # In 'game' state, allow role changes to 'human' or 'zombie'
        if game_state['status'] == 'game' and data['role'] in ['human', 'zombie']:
            role = data['role']
            # Update humans/zombies lists
            if data['id'] in game_state['humans'] and role == 'zombie':
                game_state['humans'].remove(data['id'])
                game_state['zombies'].append(data['id'])
            elif data['id'] in game_state['zombies'] and role == 'human':
                game_state['zombies'].remove(data['id'])
                game_state['humans'].append(data['id'])
        else:
            # Preserve existing role in prepare/game/end states, or use neutral for sleep
            if game_state['status'] == 'sleep':
                role = 'neutral'
            else:
                role = devices.get(data['id'], {}).get('role', 'neutral')

        devices[data['id']] = {
            'id': data['id'],
            'ip': data['ip'],
            'rssi': data['rssi'],
            'role': role,
            'status': data['status'],
            'health': data['health'],
            'battery': data['battery'],
            'comment': data['comment'],
            'last_updated': time.time()
        }
        logger.debug(f"Updated device {data['id']} with role: {devices[data['id']]['role']}")

    response = {
        'role': devices[data['id']]['role'],
        'status': game_state['status'],
        'game_timeout': game_state['game_timeout'],
        'game_duration': game_state['game_duration']
    }
    logger.debug(f"Sending response: {response}")
    return jsonify(response)


@app.route('/')
def main_screen():
    logger.debug("Rendering main screen")
    with devices_lock:
        game_state['status'] = 'sleep'
        game_state['humans'] = []
        game_state['zombies'] = []
        for device in devices.values():
            device['status'] = 'sleep'
            device['role'] = 'neutral'
    return render_template('main.html')


@app.route('/prepare', methods=['GET', 'POST'])
def prepare_screen():
    logger.debug(f"Handling /prepare with method: {request.method}")
    if request.method == 'POST':
        try:
            game_state['human_percentage'] = int(request.form.get('human_percentage', 50))
            game_state['game_timeout'] = int(request.form.get('game_timeout', 30))
            game_state['game_duration'] = int(request.form.get('game_duration', 15))
            logger.debug(f"Updated game_state: {game_state}")
            
            # Assign roles before starting the game
            assign_roles()
            
            return redirect(url_for('game_screen'))
        except ValueError as e:
            logger.error(f"Invalid form data: {e}")
            return jsonify({'error': 'Invalid form data'}), 400

    with devices_lock:
        game_state['status'] = 'prepare'
        for device in devices.values():
            device['status'] = 'prepare'
        sorted_devices = sorted(devices.values(), key=lambda x: x['id'])
    return render_template('prepare.html', devices=sorted_devices, game_state=game_state)


@app.route('/game')
def game_screen():
    logger.debug("Rendering game screen")
    with devices_lock:
        game_state['status'] = 'game'
        if game_state['game_start_time'] is None:
            game_state['game_start_time'] = datetime.now()
        
        # Update device statuses to 'game'
        for device in devices.values():
            device['status'] = 'game'
        
        # Get current humans and zombies
        humans = [devices[dev_id] for dev_id in game_state['humans'] if dev_id in devices]
        zombies = [devices[dev_id] for dev_id in game_state['zombies'] if dev_id in devices]
        
        logger.debug(f"Game screen: {len(humans)} humans, {len(zombies)} zombies")
    
    return render_template('game.html', humans=humans, zombies=zombies, game_state=game_state)


@app.route('/add_minute', methods=['POST'])
def add_minute():
    logger.debug("Adding one minute to game duration")
    with devices_lock:
        game_state['game_duration'] += 1
        logger.debug(f"New game_duration: {game_state['game_duration']}")
    return jsonify({'success': True})


@app.route('/end')
def end_screen():
    logger.debug("Rendering end screen")
    with devices_lock:
        game_state['status'] = 'end'
        for device in devices.values():
            device['status'] = 'end'
        humans = [devices[dev_id] for dev_id in game_state['humans'] if dev_id in devices]
        zombies = [devices[dev_id] for dev_id in game_state['zombies'] if dev_id in devices]
    return render_template('end.html', humans=humans, zombies=zombies)


@app.route('/static/<path:path>')
def send_static(path):
    logger.debug(f"Serving static file: {path}")
    return send_from_directory('static', path)


# PyQt6 Application
class ZombieGameWindow(QMainWindow):
    """Main application window with embedded web browser"""
    
    def __init__(self, server_url):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Create central widget with layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Add server info label
        self.info_label = QLabel()
        self.update_server_info(server_url)
        layout.addWidget(self.info_label)
        
        # Create web view
        self.browser = QWebEngineView()
        layout.addWidget(self.browser)
        
        # Enable developer tools and other settings
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
        # Load the main page
        self.browser.setUrl(QUrl(server_url))
        
        logger.info("Zombie Game window initialized")
    
    def update_server_info(self, server_url):
        """Update the server information label"""
        local_ip = get_local_ip()
        info_text = f"<b>Server Status:</b> Running | <b>Local Access:</b> {server_url}"
        if local_ip != "127.0.0.1":
            info_text += f" | <b>Network Access (for ESP32):</b> http://{local_ip}:{SERVER_PORT}"
        self.info_label.setText(info_text)
        self.info_label.setStyleSheet("padding: 5px; background-color: #e8f5e9; border-bottom: 1px solid #4caf50;")
    
    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self, 
            'Exit',
            'Are you sure you want to exit?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()


class FlaskThread(threading.Thread):
    """Thread to run Flask server"""
    
    def __init__(self, host, port):
        super().__init__()
        self.daemon = True
        self.host = host
        self.port = port
        
    def run(self):
        """Run Flask server"""
        logger.info(f"Starting Flask server on http://{self.host}:{self.port}")
        app.run(host=self.host, port=self.port, debug=False, use_reloader=False)


def setup_directories():
    """Create necessary directories and copy template files"""
    # Create templates directory
    templates_dir = Path('templates')
    templates_dir.mkdir(exist_ok=True)
    
    # Create static directory
    static_dir = Path('static')
    static_dir.mkdir(exist_ok=True)
    
    logger.info("Directories created successfully")
    
    return templates_dir, static_dir


def get_local_ip():
    """Get the local IP address of the machine"""
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


def main():
    """Main application entry point"""
    # Setup directories
    templates_dir, static_dir = setup_directories()
    
    # Check if template files exist
    required_templates = ['main.html', 'prepare.html', 'game.html', 'end.html']
    missing_templates = [t for t in required_templates if not (templates_dir / t).exists()]
    
    if missing_templates:
        logger.error(f"Missing template files: {missing_templates}")
        logger.error("Please ensure all HTML template files are in the 'templates' directory")
        logger.error("Run 'python setup.py' to copy template files automatically")
        return 1
    
    # Get local IP for display
    local_ip = get_local_ip()
    
    # Start Flask server in background thread
    flask_thread = FlaskThread(SERVER_HOST, SERVER_PORT)
    flask_thread.start()
    
    # Give Flask a moment to start
    time.sleep(1)
    
    # Determine server URL for browser
    server_url = f"http://127.0.0.1:{SERVER_PORT}/"
    
    # Create and run Qt application
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Zombie Game")
    qt_app.setOrganizationName("ZombieGame")
    
    window = ZombieGameWindow(server_url)
    window.show()
    
    logger.info("=" * 70)
    logger.info("Application started successfully")
    logger.info("=" * 70)
    logger.info(f"Server is running on: http://{SERVER_HOST}:{SERVER_PORT}")
    logger.info(f"Local access (browser): {server_url}")
    
    if local_ip != "127.0.0.1" and SERVER_HOST == "0.0.0.0":
        logger.info(f"Network access (ESP32): http://{local_ip}:{SERVER_PORT}")
        logger.info(f"ESP32 devices should connect to: http://{local_ip}:{SERVER_PORT}/api/device")
    elif SERVER_HOST == "127.0.0.1":
        logger.warning("Server is configured for local-only access")
        logger.warning("To accept ESP32 connections, change SERVER_HOST to '0.0.0.0' in config.py")
    
    logger.info("=" * 70)
    
    return qt_app.exec()


if __name__ == '__main__':
    sys.exit(main())
