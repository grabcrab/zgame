#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import hashlib
import shutil
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import logging

app = Flask(__name__)

# Настройки
SYNC_FOLDER = './sync_files'  # Папка для синхронизации
PORT = 5001
HOST = '0.0.0.0'

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_sync_folder():
    """Создание папки для синхронизации если она не существует"""
    if not os.path.exists(SYNC_FOLDER):
        os.makedirs(SYNC_FOLDER)
        logger.info(f"Создана папка синхронизации: {SYNC_FOLDER}")

def calculate_file_hash(filepath):
    """Вычисление хэша файла (совместимо с ESP32)"""
    try:
        with open(filepath, 'rb') as f:
            hash_value = 0
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                for byte in chunk:
                    hash_value = (hash_value * 31 + byte) & 0xFFFFFFFF
        return format(hash_value, 'X')
    except Exception as e:
        logger.error(f"Ошибка вычисления хэша для {filepath}: {e}")
        return ""

def find_file_in_subdirs(filename):
    """Find file in sync folder and all subdirectories"""
    try:
        for root, dirs, files in os.walk(SYNC_FOLDER):
            if filename in files:
                return os.path.join(root, filename)
    except Exception as e:
        logger.error(f"Error searching for file {filename}: {e}")
    return None

def get_file_list():
    """Get list of files in sync folder and all subdirectories"""
    files = []
    
    try:
        # Walk through all subdirectories
        for root, dirs, filenames in os.walk(SYNC_FOLDER):
            for filename in filenames:
                filepath = os.path.join(root, filename)
                if os.path.isfile(filepath):
                    # Use only filename without path for compatibility with ESP32
                    file_info = {
                        'name': filename,  # Only filename, no path
                        'size': os.path.getsize(filepath),
                        'hash': calculate_file_hash(filepath),
                        'full_path': filepath  # Internal use only
                    }
                    files.append(file_info)
    except Exception as e:
        logger.error(f"Error getting file list: {e}")
    
    return files

@app.route('/list', methods=['GET'])
def list_files():
    """Return list of files on server (flattened, without paths)"""
    try:
        files = get_file_list()
        # Remove full_path from response for ESP32 compatibility
        response_files = []
        for file_info in files:
            response_files.append({
                'name': file_info['name'],
                'size': file_info['size'],
                'hash': file_info['hash']
            })
        return jsonify({'files': response_files})
    except Exception as e:
        logger.error(f"Error in /list: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['PUT'])
def upload_file():
    """Upload endpoint - disabled for one-way sync (server to ESP32 only)"""
    return jsonify({'error': 'Upload not supported - sync is server to ESP32 only'}), 405

@app.route('/download', methods=['GET'])
def download_file():
    """Download file to ESP32 (searches in all subdirectories)"""
    try:
        filename = request.args.get('file')
        if not filename:
            return jsonify({'error': 'Filename not specified'}), 400
        
        # Clean filename for security
        filename = secure_filename(filename)
        filename = os.path.basename(filename)  # Remove any path separators
        
        if not filename or filename.startswith('.'):
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Search for file in all subdirectories
        found_filepath = find_file_in_subdirs(filename)
        
        if not found_filepath:
            return jsonify({'error': 'File not found'}), 404
        
        logger.info(f"File downloaded: {filename} from {found_filepath}")
        return send_file(found_filepath, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"File download error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete', methods=['DELETE'])
def delete_file():
    """Delete file - disabled for one-way sync"""
    return jsonify({'error': 'Delete not supported - sync is server to ESP32 only'}), 405

@app.route('/status', methods=['GET'])
def status():
    """Статус сервера"""
    try:
        files = get_file_list()
        return jsonify({
            'status': 'online',
            'sync_folder': SYNC_FOLDER,
            'files_count': len(files),
            'total_size': sum(f['size'] for f in files)
        })
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    """Main page"""
    file_count = len(get_file_list())
    return f"""
    <h1>ESP32 SPIFFS Sync Server (One-way: Server → ESP32)</h1>
    <p>Sync server is running</p>
    <p>Sync folder: {SYNC_FOLDER}</p>
    <p>Files available: {file_count}</p>
    <p>Available endpoints:</p>
    <ul>
        <li><a href="/list">/list</a> - file list</li>
        <li><a href="/status">/status</a> - server status</li>
        <li>/download?file=filename - download file (for ESP32)</li>
    </ul>
    <p><strong>Note:</strong> This server only syncs FROM server TO ESP32</p>
    """

def main():
    """Main function"""
    print("=== ESP32 SPIFFS Sync Server (One-way: Server → ESP32) ===")
    print(f"Port: {PORT}")
    print(f"Sync folder: {os.path.abspath(SYNC_FOLDER)}")
    print("Ctrl+C to stop server")
    
    # Initialize
    init_sync_folder()
    
    # Create test files and folders structure
    test_structure = {
        'config.txt': 'wifi_ssid=MyWiFi\nwifi_password=MyPassword',
        'data.json': '{"sensor": "temperature", "value": 25.6}',
        'web/index.html': '<html><body><h1>ESP32 Web Page</h1></body></html>',
        'web/style.css': 'body { font-family: Arial; }',
        'firmware/version.txt': 'v1.0.0',
        'logs/system.log': '2024-01-01 System started\n2024-01-01 WiFi connected'
    }
    
    for filepath, content in test_structure.items():
        full_path = os.path.join(SYNC_FOLDER, filepath)
        if not os.path.exists(full_path):
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Created test file: {filepath}")
    
    # Start server
    try:
        app.run(host=HOST, port=PORT, debug=False)
    except KeyboardInterrupt:
        print("\nServer stopped")
    except Exception as e:
        print(f"Server error: {e}")

if __name__ == '__main__':
    main()