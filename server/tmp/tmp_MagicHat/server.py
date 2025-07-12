from flask import Flask, request, jsonify, render_template, redirect, url_for
import json
import random
import time
from datetime import datetime, timedelta
import threading
import os

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
    # Get JSON data from query parameter 'data'
    data_str = request.args.get('data')
    if not data_str:
        return jsonify({'error': 'No data provided'}), 400

    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON format'}), 400

    if not all(key in data for key in ['id', 'ip', 'rssi', 'role', 'status', 'health', 'battery', 'comment']):
        return jsonify({'error': 'Missing required fields'}), 400

    with devices_lock:
        devices[data['id']] = {
            'id': data['id'],
            'ip': data['ip'],
            'rssi': data['rssi'],
            'role': data['role'],
            'status': data['status'],
            'health': data['health'],
            'battery': data['battery'],
            'comment': data['comment'],
            'last_updated': time.time()
        }

    response = {
        'role': 'neutral' if game_state['status'] == 'sleep' else devices[data['id']]['role'],
        'status': game_state['status'],
        'game_timeout': game_state['game_timeout'],
        'game_duration': game_state['game_duration']
    }
    return jsonify(response)

# Main screen (2.1)
@app.route('/')
def main_screen():
    with devices_lock:
        game_state['status'] = 'sleep'
        for device in devices.values():
            device['status'] = 'sleep'
    return render_template('main.html')

# Preparation screen (2.2)
# @app.route('/prepare', methods=['GET', 'POST'])
# def prepare_screen():
#     if request.method == 'POST':
#         game_state['human_percentage'] = int(request.form.get('human_percentage', 50))
#         game_state['game_timeout'] = int(request.form.get('game_timeout', 30))
#         game_state['game_duration'] = int(request.form.get('game_duration', 15))
#         return redirect(url_for('game_screen'))

#     with devices_lock:
#         game_state['status'] = 'prepare'
#         for device in devices.values():
#             device['status'] = 'prepare'
#         sorted_devices = sorted(devices.values(), key=lambda x: x['id'])
#     return render_template('prepare.html', devices=sorted_devices, game_state=game_state)

# # Game screen (2.3)
# @app.route('/game')
# def game_screen():
#     with devices_lock:
#         game_state['status'] = 'game'
#         game_state['game_start_time'] = datetime.now()
        
#         # Assign roles based on human_percentage
#         total_devices = len(devices)
#         if total_devices > 0:
#             human_count = round(total_devices * game_state['human_percentage'] / 100)
#             device_ids = list(devices.keys())
#             random.shuffle(device_ids)
#             game_state['humans'] = device_ids[:human_count]
#             game_state['zombies'] = device_ids[human_count:]
            
#             for dev_id in game_state['humans']:
#                 devices[dev_id]['role'] = 'human'
#                 devices[dev_id]['status'] = 'game'
#             for dev_id in game_state['zombies']:
#                 devices[dev_id]['role'] = 'zombie'
#                 devices[dev_id]['status'] = 'game'

#         humans = [devices[dev_id] for dev_id in game_state['humans']]
#         zombies = [devices[dev_id] for dev_id in game_state['zombies']]
    
#     return render_template('game.html', humans=humans, zombies=zombies, game_state=game_state)
@app.route('/prepare', methods=['GET', 'POST'])
def prepare_screen():
    if request.method == 'POST':
        game_state['human_percentage'] = int(request.form.get('human_percentage', 50))
        game_state['game_timeout'] = int(request.form.get('game_timeout', 30))
        game_state['game_duration'] = int(request.form.get('game_duration', 15))
        return redirect(url_for('game_screen'))

    with devices_lock:
        game_state['status'] = 'prepare'
        for device in devices.values():
            device['status'] = 'prepare'
        sorted_devices = sorted(devices.values(), key=lambda x: x['id'])
    return render_template('prepare.html', devices=sorted_devices, game_state=game_state)


# End game screen (2.4)
@app.route('/end')
def end_screen():
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
    return send_from_directory('static', path)

# Templates
@app.route('/templates/<path:path>')
def send_template(path):
    return send_from_directory('templates', path)

# Create static directory for logo
if not os.path.exists('static'):
    os.makedirs('static')

# Create templates directory
if not os.path.exists('templates'):
    os.makedirs('templates')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)