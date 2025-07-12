from flask import Flask, request, jsonify, render_template, redirect, url_for
import json
import random
import time
from datetime import datetime, timedelta
import threading
import os
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory storage for device data
devices = {}
game_state = {
    'status': 'sleep',
    'human_percentage': 50,
    'game_timeout': 30,
    'game_duration': 15,
    'game_start_time': None,
    'zombies': [],
    'humans': []
}

# Lock for thread-safe device updates
devices_lock = threading.Lock()

# Handle GET requests from devices
@app.route('/api/device', methods=['GET'])
def device_update():
    logger.debug("Received request to /api/device")
    # Get JSON data from query parameter 'data'
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
            # Preserve existing role in other states or if incoming role is invalid
            role = devices.get(data['id'], {}).get('role', 'neutral') if game_state['status'] in ['game', 'prepare', 'end'] else data['role']

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
        'role': 'neutral' if game_state['status'] == 'sleep' else devices[data['id']]['role'],
        'status': game_state['status'],
        'game_timeout': game_state['game_timeout'],
        'game_duration': game_state['game_duration']
    }
    logger.debug(f"Sending response: {response}")
    return jsonify(response)

# Main screen (2.1)
@app.route('/')
def main_screen():
    logger.debug("Rendering main screen")
    with devices_lock:
        game_state['status'] = 'sleep'
        for device in devices.values():
            device['status'] = 'sleep'
            device['role'] = 'neutral'
    return render_template('main.html')

# Preparation screen (2.2)
@app.route('/prepare', methods=['GET', 'POST'])
def prepare_screen():
    logger.debug(f"Handling /prepare with method: {request.method}")
    if request.method == 'POST':
        try:
            game_state['human_percentage'] = int(request.form.get('human_percentage', 50))
            game_state['game_timeout'] = int(request.form.get('game_timeout', 30))
            game_state['game_duration'] = int(request.form.get('game_duration', 15))
            logger.debug(f"Updated game_state: {game_state}")
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

# Game screen (2.3)
@app.route('/game')
def game_screen():
    logger.debug("Rendering game screen")
    with devices_lock:
        game_state['status'] = 'game'
        game_state['game_start_time'] = datetime.now()
        # Clear devices list at the start of a new game
        devices.clear()
        game_state['humans'] = []
        game_state['zombies'] = []
        logger.debug("Cleared devices and role lists for new game")
    
    return render_template('game.html', humans=[], zombies=[], game_state=game_state)

# Add a minute to game duration
@app.route('/add_minute', methods=['POST'])
def add_minute():
    logger.debug("Adding one minute to game duration")
    with devices_lock:
        game_state['game_duration'] += 1
        logger.debug(f"New game_duration: {game_state['game_duration']}")
    return jsonify({'success': True})

# End game screen (2.4)
@app.route('/end')
def end_screen():
    logger.debug("Rendering end screen")
    with devices_lock:
        game_state['status'] = 'end'
        for device in devices.values():
            device['status'] = 'end'
        humans = [devices[dev_id] for dev_id in game_state['humans']]
        zombies = [devices[dev_id] for dev_id in game_state['zombies']]
    return render_template('end.html', humans=humans, zombies=zombies)

# Static files (logo)
@app.route('/static/<path:path>')
def send_static(path):
    logger.debug(f"Serving static file: {path}")
    return send_from_directory('static', path)

# Create static directory for logo
if not os.path.exists('static'):
    os.makedirs('static')

# Create templates directory
if not os.path.exists('templates'):
    os.makedirs('templates')

if __name__ == '__main__':
    logger.info("Starting Flask server on port 5000")
    app.run(host='0.0.0.0', port=5000, debug=True)