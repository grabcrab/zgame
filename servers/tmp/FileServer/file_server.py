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

def get_file_list():
    """Получение списка файлов в папке синхронизации"""
    files = []
    
    try:
        for filename in os.listdir(SYNC_FOLDER):
            filepath = os.path.join(SYNC_FOLDER, filename)
            if os.path.isfile(filepath):
                file_info = {
                    'name': filename,
                    'size': os.path.getsize(filepath),
                    'hash': calculate_file_hash(filepath)
                }
                files.append(file_info)
    except Exception as e:
        logger.error(f"Ошибка получения списка файлов: {e}")
    
    return files

@app.route('/list', methods=['GET'])
def list_files():
    """Возвращает список файлов на сервере"""
    try:
        files = get_file_list()
        return jsonify({'files': files})
    except Exception as e:
        logger.error(f"Ошибка в /list: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['PUT'])
def upload_file():
    """Загрузка файла от ESP32"""
    try:
        filename = request.headers.get('X-Filename')
        if not filename:
            return jsonify({'error': 'Не указано имя файла'}), 400
        
        # Безопасное имя файла
        filename = secure_filename(filename)
        if filename.startswith('/'):
            filename = filename[1:]
        
        filepath = os.path.join(SYNC_FOLDER, filename)
        
        # Создаем подпапки если нужно
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Сохраняем файл
        with open(filepath, 'wb') as f:
            f.write(request.data)
        
        logger.info(f"Файл загружен: {filename}")
        return jsonify({'message': 'Файл успешно загружен'})
        
    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['GET'])
def download_file():
    """Скачивание файла ESP32"""
    try:
        filename = request.args.get('file')
        if not filename:
            return jsonify({'error': 'Не указано имя файла'}), 400
        
        # Безопасное имя файла
        filename = secure_filename(filename)
        if filename.startswith('/'):
            filename = filename[1:]
        
        filepath = os.path.join(SYNC_FOLDER, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'Файл не найден'}), 404
        
        logger.info(f"Файл скачан: {filename}")
        return send_file(filepath, as_attachment=True)
        
    except Exception as e:
        logger.error(f"Ошибка скачивания файла: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete', methods=['DELETE'])
def delete_file():
    """Удаление файла"""
    try:
        filename = request.args.get('file')
        if not filename:
            return jsonify({'error': 'Не указано имя файла'}), 400
        
        # Безопасное имя файла
        filename = secure_filename(filename)
        if filename.startswith('/'):
            filename = filename[1:]
        
        filepath = os.path.join(SYNC_FOLDER, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'Файл не найден'}), 404
        
        os.remove(filepath)
        logger.info(f"Файл удален: {filename}")
        return jsonify({'message': 'Файл успешно удален'})
        
    except Exception as e:
        logger.error(f"Ошибка удаления файла: {e}")
        return jsonify({'error': str(e)}), 500

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
    """Главная страница"""
    return f"""
    <h1>ESP32 SPIFFS Sync Server</h1>
    <p>Сервер синхронизации для ESP32 запущен</p>
    <p>Папка синхронизации: {SYNC_FOLDER}</p>
    <p>Доступные endpoint'ы:</p>
    <ul>
        <li><a href="/list">/list</a> - список файлов</li>
        <li><a href="/status">/status</a> - статус сервера</li>
        <li>/upload - загрузка файла (PUT)</li>
        <li>/download?file=filename - скачивание файла</li>
        <li>/delete?file=filename - удаление файла (DELETE)</li>
    </ul>
    """

def main():
    """Основная функция"""
    print("=== ESP32 SPIFFS Sync Server ===")
    print(f"Порт: {PORT}")
    print(f"Папка синхронизации: {os.path.abspath(SYNC_FOLDER)}")
    print("Ctrl+C для остановки сервера")
    
    # Инициализация
    init_sync_folder()
    
    # Создаем несколько тестовых файлов
    test_files = [
        ('test1.txt', 'Тестовый файл 1\nСодержимое файла'),
        ('test2.json', '{"name": "test", "value": 123}'),
        ('config.txt', 'wifi_ssid=MyWiFi\nwifi_password=MyPassword')
    ]
    
    for filename, content in test_files:
        filepath = os.path.join(SYNC_FOLDER, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Создан тестовый файл: {filename}")
    
    # Запуск сервера
    try:
        app.run(host=HOST, port=PORT, debug=False)
    except KeyboardInterrupt:
        print("\nСервер остановлен")
    except Exception as e:
        print(f"Ошибка сервера: {e}")

if __name__ == '__main__':
    main()