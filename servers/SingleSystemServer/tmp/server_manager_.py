#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xGAME Server Manager
Combined GUI for Discovery, File Server, and OTA servers
"""

import socket
import json
import hashlib
import os
import sys
import psutil
import threading
import time
import subprocess
import platform
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import urllib.parse

# ============== Configuration ==============
DISCO_PORT = 4210
TCP_PORT = 3232
FILE_SERVER_PORT = 5001
OTA_SERVER_PORT = 5005

SYNC_FOLDER = './sync_files'
FIRMWARE_DIR = './firmware'
FIRMWARE_FILE = 'firmware.bin'

# ============== Discovery Server ==============
class DiscoveryServer:
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.running = False
        self.threads = []
        self.sockets = []
        
    def get_all_interfaces(self):
        """Get all available network interfaces with their IP addresses"""
        interfaces = []
        for nic, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    ip = a.address
                    if ip.startswith("127.") or ip.startswith("169.254."):
                        continue
                    interfaces.append({
                        'name': nic,
                        'ip': ip,
                        'enabled': True
                    })
        return interfaces
    
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        if self.log_callback:
            self.log_callback(log_message, level)
        else:
            print(log_message)
    
    def responder_worker(self, interface_ip, interface_name):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            sock.bind((interface_ip, DISCO_PORT))
            self.sockets.append(sock)
            
            self.log(f"Listening on {interface_name} ({interface_ip}:{DISCO_PORT})", "SUCCESS")
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(64)
                    self.log(f"Received from {addr[0]}:{addr[1]} on {interface_name}: {data.decode('utf-8', errors='ignore')}")
                    
                    if b'ESP32-LOOK' in data:
                        response = interface_ip.encode()
                        sock.sendto(response, addr)
                        self.log(f"Sent response '{interface_ip}' to {addr[0]}:{addr[1]}", "SUCCESS")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log(f"Error on {interface_name}: {str(e)}", "ERROR")
                    
        except Exception as e:
            self.log(f"Failed to bind to {interface_name} ({interface_ip}): {str(e)}", "ERROR")
        finally:
            try:
                sock.close()
            except:
                pass
    
    def start(self, interfaces):
        if self.running:
            self.log("Server already running", "WARNING")
            return
        
        self.running = True
        self.threads = []
        self.sockets = []
        
        if not interfaces:
            self.log("No interfaces selected", "ERROR")
            return
        
        self.log(f"Starting discovery server on {len(interfaces)} interface(s)...")
        
        for interface in interfaces:
            if interface['enabled']:
                thread = threading.Thread(
                    target=self.responder_worker,
                    args=(interface['ip'], interface['name']),
                    daemon=True
                )
                thread.start()
                self.threads.append(thread)
        
        if not self.threads:
            self.log("No interfaces were started", "ERROR")
            self.running = False
    
    def stop(self):
        if not self.running:
            return
        
        self.log("Stopping discovery server...")
        self.running = False
        
        for sock in self.sockets:
            try:
                sock.close()
            except:
                pass
        
        for thread in self.threads:
            thread.join(timeout=2.0)
        
        self.threads = []
        self.sockets = []
        self.log("Server stopped", "SUCCESS")


# ============== File Server ==============
class FileServer:
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.running = False
        self.server_thread = None
        self.app = None
        self.sync_folder = SYNC_FOLDER
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        if self.log_callback:
            self.log_callback(log_message, level)
        else:
            print(log_message)
    
    def init_sync_folder(self):
        if not os.path.exists(self.sync_folder):
            os.makedirs(self.sync_folder)
            self.log(f"Created sync folder: {self.sync_folder}", "SUCCESS")
    
    def calculate_file_hash(self, filepath):
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
            self.log(f"Hash calculation error for {filepath}: {e}", "ERROR")
            return ""
    
    def find_file_in_subdirs(self, filename):
        try:
            for root, dirs, files in os.walk(self.sync_folder):
                if filename in files:
                    return os.path.join(root, filename)
        except Exception as e:
            self.log(f"Error searching for file {filename}: {e}", "ERROR")
        return None
    
    def get_file_list(self):
        files = []
        try:
            for root, dirs, filenames in os.walk(self.sync_folder):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    if os.path.isfile(filepath):
                        file_info = {
                            'name': filename,
                            'size': os.path.getsize(filepath),
                            'hash': self.calculate_file_hash(filepath),
                            'full_path': filepath
                        }
                        files.append(file_info)
        except Exception as e:
            self.log(f"Error getting file list: {e}", "ERROR")
        return files
    
    def create_flask_app(self):
        app = Flask(__name__)
        server = self
        
        @app.route('/list', methods=['GET'])
        def list_files():
            try:
                files = server.get_file_list()
                response_files = [{'name': f['name'], 'size': f['size'], 'hash': f['hash']} for f in files]
                server.log(f"File list requested - {len(files)} files", "INFO")
                return jsonify({'files': response_files})
            except Exception as e:
                server.log(f"Error in /list: {e}", "ERROR")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/download', methods=['GET'])
        def download_file():
            try:
                filename = request.args.get('file')
                if not filename:
                    return jsonify({'error': 'Filename not specified'}), 400
                
                filename = secure_filename(filename)
                filename = os.path.basename(filename)
                
                if not filename or filename.startswith('.'):
                    return jsonify({'error': 'Invalid filename'}), 400
                
                found_filepath = server.find_file_in_subdirs(filename)
                
                if not found_filepath:
                    server.log(f"File not found: {filename}", "WARNING")
                    return jsonify({'error': 'File not found'}), 404
                
                server.log(f"File downloaded: {filename}", "SUCCESS")
                return send_file(found_filepath, as_attachment=True, download_name=filename)
                
            except Exception as e:
                server.log(f"Download error: {e}", "ERROR")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/status', methods=['GET'])
        def status():
            try:
                files = server.get_file_list()
                return jsonify({
                    'status': 'online',
                    'sync_folder': server.sync_folder,
                    'files_count': len(files),
                    'total_size': sum(f['size'] for f in files)
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @app.route('/', methods=['GET'])
        def index():
            file_count = len(server.get_file_list())
            return f"ESP32 SPIFFS Sync Server - {file_count} files available"
        
        return app
    
    def run_server(self):
        try:
            from werkzeug.serving import make_server
            self.app = self.create_flask_app()
            self.http_server = make_server('0.0.0.0', FILE_SERVER_PORT, self.app, threaded=True)
            self.log(f"File server started on port {FILE_SERVER_PORT}", "SUCCESS")
            self.http_server.serve_forever()
        except Exception as e:
            self.log(f"File server error: {e}", "ERROR")
            self.running = False
    
    def start(self):
        if self.running:
            self.log("File server already running", "WARNING")
            return
        
        self.init_sync_folder()
        self.running = True
        self.log(f"Starting file server on port {FILE_SERVER_PORT}...")
        self.log(f"Sync folder: {os.path.abspath(self.sync_folder)}", "INFO")
        
        files = self.get_file_list()
        self.log(f"Files available: {len(files)}", "INFO")
        
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()
    
    def stop(self):
        if not self.running:
            return
        
        self.log("Stopping file server...")
        self.running = False
        
        if hasattr(self, 'http_server'):
            try:
                self.http_server.shutdown()
            except:
                pass
        
        self.log("File server stopped", "SUCCESS")


# ============== OTA Server ==============
class OTAHandler(BaseHTTPRequestHandler):
    server_instance = None
    _cached_md5 = None
    _cached_size = None
    _cached_mtime = None
    _cache_lock = threading.Lock()
    
    def do_GET(self):
        try:
            parsed_path = urllib.parse.urlparse(self.path)
            
            if parsed_path.path == "/version":
                self.handle_version_check()
            elif parsed_path.path == "/update":
                self.handle_firmware_download()
            elif parsed_path.path == "/status":
                self.handle_status()
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            self.log_to_gui(f"Error handling request: {e}", "ERROR")
            self.send_error(500, "Internal Server Error")
    
    def log_to_gui(self, message, level="INFO"):
        if OTAHandler.server_instance and OTAHandler.server_instance.log_callback:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] [{level}] {message}"
            OTAHandler.server_instance.log_callback(log_message, level)
    
    def handle_version_check(self):
        try:
            firmware_path = os.path.join(FIRMWARE_DIR, FIRMWARE_FILE)
            
            if not os.path.exists(firmware_path):
                self.send_error(404, "Firmware not found")
                return
            
            md5_hash, file_size = self.get_cached_firmware_info(firmware_path)
            
            response_data = {
                "version": md5_hash,
                "size": file_size,
                "filename": FIRMWARE_FILE,
                "timestamp": int(time.time())
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
            
            self.log_to_gui(f"Version check: MD5={md5_hash[:16]}..., Size={file_size}", "INFO")
            
        except Exception as e:
            self.log_to_gui(f"Error in version check: {e}", "ERROR")
            self.send_error(500, "Internal Server Error")
    
    def handle_firmware_download(self):
        try:
            firmware_path = os.path.join(FIRMWARE_DIR, FIRMWARE_FILE)
            
            if not os.path.exists(firmware_path):
                self.send_error(404, "Firmware not found")
                return
            
            file_size = os.path.getsize(firmware_path)
            
            range_header = self.headers.get('Range')
            if range_header:
                ranges = range_header.replace('bytes=', '').split('-')
                range_start = int(ranges[0]) if ranges[0] else 0
                range_end = int(ranges[1]) if ranges[1] else file_size - 1
                
                content_length = range_end - range_start + 1
                
                self.send_response(206)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Content-Range", f"bytes {range_start}-{range_end}/{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Disposition", f"attachment; filename={FIRMWARE_FILE}")
                self.end_headers()
                
                with open(firmware_path, 'rb') as f:
                    f.seek(range_start)
                    sent = 0
                    while sent < content_length:
                        chunk_size = min(8192, content_length - sent)
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        sent += len(chunk)
                
                self.log_to_gui(f"Partial firmware sent: {range_start}-{range_end}/{file_size}", "SUCCESS")
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Disposition", f"attachment; filename={FIRMWARE_FILE}")
                self.end_headers()
                
                with open(firmware_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                
                self.log_to_gui(f"Full firmware sent: {FIRMWARE_FILE} ({file_size} bytes)", "SUCCESS")
            
        except Exception as e:
            self.log_to_gui(f"Error sending firmware: {e}", "ERROR")
            self.send_error(500, "Internal Server Error")
    
    def handle_status(self):
        try:
            active_threads = threading.active_count()
            firmware_path = os.path.join(FIRMWARE_DIR, FIRMWARE_FILE)
            firmware_exists = os.path.exists(firmware_path)
            
            status_data = {
                "status": "running",
                "active_threads": active_threads,
                "firmware_available": firmware_exists,
                "timestamp": int(time.time())
            }
            
            if firmware_exists:
                md5_hash, file_size = self.get_cached_firmware_info(firmware_path)
                status_data["firmware_md5"] = md5_hash
                status_data["firmware_size"] = file_size
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(status_data).encode())
            
        except Exception as e:
            self.log_to_gui(f"Error in status check: {e}", "ERROR")
            self.send_error(500, "Internal Server Error")
    
    def get_cached_firmware_info(self, firmware_path):
        with self._cache_lock:
            current_mtime = os.path.getmtime(firmware_path)
            
            if (self._cached_md5 is None or self._cached_mtime != current_mtime):
                self._cached_md5 = self.calculate_md5(firmware_path)
                self._cached_size = os.path.getsize(firmware_path)
                self._cached_mtime = current_mtime
            
            return self._cached_md5, self._cached_size
    
    def calculate_md5(self, file_path):
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def log_message(self, format, *args):
        pass  # Suppress default logging


class ThreadedOTAServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, max_connections=50):
        super().__init__(server_address, RequestHandlerClass)
        self.max_connections = max_connections
        self.connection_count = 0
        self.connection_lock = threading.Lock()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


class OTAServer:
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.running = False
        self.server_thread = None
        self.httpd = None
        self.firmware_dir = FIRMWARE_DIR
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        if self.log_callback:
            self.log_callback(log_message, level)
        else:
            print(log_message)
    
    def init_firmware_dir(self):
        if not os.path.exists(self.firmware_dir):
            os.makedirs(self.firmware_dir)
            self.log(f"Created firmware directory: {self.firmware_dir}", "SUCCESS")
    
    def run_server(self):
        try:
            OTAHandler.server_instance = self
            self.httpd = ThreadedOTAServer(('', OTA_SERVER_PORT), OTAHandler, max_connections=50)
            self.log(f"OTA server started on port {OTA_SERVER_PORT}", "SUCCESS")
            self.httpd.serve_forever()
        except Exception as e:
            self.log(f"OTA server error: {e}", "ERROR")
            self.running = False
    
    def start(self):
        if self.running:
            self.log("OTA server already running", "WARNING")
            return
        
        self.init_firmware_dir()
        self.running = True
        self.log(f"Starting OTA server on port {OTA_SERVER_PORT}...")
        self.log(f"Firmware directory: {os.path.abspath(self.firmware_dir)}", "INFO")
        
        firmware_path = os.path.join(self.firmware_dir, FIRMWARE_FILE)
        if os.path.exists(firmware_path):
            file_size = os.path.getsize(firmware_path)
            self.log(f"Firmware file found: {FIRMWARE_FILE} ({file_size} bytes)", "SUCCESS")
        else:
            self.log(f"Warning: Firmware file not found: {FIRMWARE_FILE}", "WARNING")
        
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()
    
    def stop(self):
        if not self.running:
            return
        
        self.log("Stopping OTA server...")
        self.running = False
        
        if self.httpd:
            try:
                self.httpd.shutdown()
            except:
                pass
        
        self.log("OTA server stopped", "SUCCESS")


# ============== Main GUI ==============
class ServerManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("xGAME Server Manager")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        self.root.minsize(800, 600)
        
        # Initialize servers
        self.disco_server = DiscoveryServer(log_callback=self.add_disco_log)
        self.file_server = FileServer(log_callback=self.add_file_log)
        self.ota_server = OTAServer(log_callback=self.add_ota_log)
        
        self.interfaces = []
        self.interface_vars = []
        
        self.create_widgets()
        self.refresh_interfaces()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Auto-start all servers after a short delay
        self.root.after(500, self.auto_start_all_servers)
    
    def create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # ===== Header with Server Status =====
        header_frame = ttk.LabelFrame(main_frame, text="Server Status", padding="10")
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        header_frame.columnconfigure(1, weight=1)
        header_frame.columnconfigure(3, weight=1)
        header_frame.columnconfigure(5, weight=1)
        
        # Discovery Server Status
        ttk.Label(header_frame, text="Discovery:", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.disco_status_label = ttk.Label(header_frame, text="● Stopped", foreground="red")
        self.disco_status_label.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        
        # File Server Status
        ttk.Label(header_frame, text="File Server:", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.file_status_label = ttk.Label(header_frame, text="● Stopped", foreground="red")
        self.file_status_label.grid(row=0, column=3, sticky=tk.W, padx=(0, 20))
        
        # OTA Server Status
        ttk.Label(header_frame, text="OTA Server:", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        self.ota_status_label = ttk.Label(header_frame, text="● Stopped", foreground="red")
        self.ota_status_label.grid(row=0, column=5, sticky=tk.W)
        
        # Port info
        ttk.Label(header_frame, text=f"Ports: Discovery={DISCO_PORT}, File={FILE_SERVER_PORT}, OTA={OTA_SERVER_PORT}",
                  font=('TkDefaultFont', 8)).grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(5, 0))
        
        # ===== Notebook with Tabs =====
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create tabs
        self.create_discovery_tab()
        self.create_file_server_tab()
        self.create_ota_server_tab()
    
    def create_discovery_tab(self):
        """Create the Discovery Server tab"""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="Discovery Server")
        
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        
        # Network Interfaces
        interface_frame = ttk.LabelFrame(tab, text="Network Interfaces", padding="10")
        interface_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        interface_frame.columnconfigure(0, weight=1)
        
        canvas = tk.Canvas(interface_frame, height=70, highlightthickness=0)
        scrollbar = ttk.Scrollbar(interface_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        refresh_btn = ttk.Button(interface_frame, text="Refresh Interfaces", command=self.refresh_interfaces)
        refresh_btn.grid(row=1, column=0, columnspan=2, pady=(5, 0))
        
        # Control Buttons
        control_frame = ttk.Frame(tab)
        control_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.disco_start_btn = ttk.Button(control_frame, text="Start Server", command=self.start_disco_server)
        self.disco_start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.disco_stop_btn = ttk.Button(control_frame, text="Stop Server", command=self.stop_disco_server, state='disabled')
        self.disco_stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(control_frame, text="Clear Log", command=self.clear_disco_log).pack(side=tk.LEFT)
        
        # Log Display
        log_frame = ttk.LabelFrame(tab, text="Server Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.disco_log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, state='disabled')
        self.disco_log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.disco_log_text.tag_config("INFO", foreground="black")
        self.disco_log_text.tag_config("SUCCESS", foreground="green")
        self.disco_log_text.tag_config("WARNING", foreground="orange")
        self.disco_log_text.tag_config("ERROR", foreground="red")
    
    def create_file_server_tab(self):
        """Create the File Server tab"""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="File Server")
        
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        
        # Server Info
        info_frame = ttk.LabelFrame(tab, text="Server Configuration", padding="10")
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        info_frame.columnconfigure(1, weight=1)
        
        ttk.Label(info_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Label(info_frame, text=str(FILE_SERVER_PORT), font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(info_frame, text="Sync Folder:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10))
        self.sync_folder_label = ttk.Label(info_frame, text=os.path.abspath(SYNC_FOLDER), font=('TkDefaultFont', 9, 'bold'))
        self.sync_folder_label.grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(info_frame, text="Files:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10))
        self.file_count_label = ttk.Label(info_frame, text="0", font=('TkDefaultFont', 9, 'bold'))
        self.file_count_label.grid(row=2, column=1, sticky=tk.W)
        
        # Control Buttons
        control_frame = ttk.Frame(tab)
        control_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.file_start_btn = ttk.Button(control_frame, text="Start Server", command=self.start_file_server)
        self.file_start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.file_stop_btn = ttk.Button(control_frame, text="Stop Server", command=self.stop_file_server, state='disabled')
        self.file_stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(control_frame, text="Open Sync Folder", command=self.open_sync_folder).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(control_frame, text="Refresh Files", command=self.refresh_file_count).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(control_frame, text="Clear Log", command=self.clear_file_log).pack(side=tk.LEFT)
        
        # Log Display
        log_frame = ttk.LabelFrame(tab, text="Server Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.file_log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, state='disabled')
        self.file_log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.file_log_text.tag_config("INFO", foreground="black")
        self.file_log_text.tag_config("SUCCESS", foreground="green")
        self.file_log_text.tag_config("WARNING", foreground="orange")
        self.file_log_text.tag_config("ERROR", foreground="red")
    
    def create_ota_server_tab(self):
        """Create the OTA Server tab"""
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="OTA Server")
        
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        
        # Server Info
        info_frame = ttk.LabelFrame(tab, text="Server Configuration", padding="10")
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        info_frame.columnconfigure(1, weight=1)
        
        ttk.Label(info_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Label(info_frame, text=str(OTA_SERVER_PORT), font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(info_frame, text="Firmware Folder:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10))
        self.firmware_folder_label = ttk.Label(info_frame, text=os.path.abspath(FIRMWARE_DIR), font=('TkDefaultFont', 9, 'bold'))
        self.firmware_folder_label.grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(info_frame, text="Firmware:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10))
        self.firmware_status_label = ttk.Label(info_frame, text="Not found", foreground="red")
        self.firmware_status_label.grid(row=2, column=1, sticky=tk.W)
        
        # Control Buttons
        control_frame = ttk.Frame(tab)
        control_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.ota_start_btn = ttk.Button(control_frame, text="Start Server", command=self.start_ota_server)
        self.ota_start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.ota_stop_btn = ttk.Button(control_frame, text="Stop Server", command=self.stop_ota_server, state='disabled')
        self.ota_stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(control_frame, text="Open Firmware Folder", command=self.open_firmware_folder).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(control_frame, text="Refresh Status", command=self.refresh_firmware_status).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(control_frame, text="Clear Log", command=self.clear_ota_log).pack(side=tk.LEFT)
        
        # Log Display
        log_frame = ttk.LabelFrame(tab, text="Server Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.ota_log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, state='disabled')
        self.ota_log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.ota_log_text.tag_config("INFO", foreground="black")
        self.ota_log_text.tag_config("SUCCESS", foreground="green")
        self.ota_log_text.tag_config("WARNING", foreground="orange")
        self.ota_log_text.tag_config("ERROR", foreground="red")
    
    # ===== Discovery Server Methods =====
    def refresh_interfaces(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.interface_vars = []
        self.interfaces = self.disco_server.get_all_interfaces()
        
        if not self.interfaces:
            ttk.Label(self.scrollable_frame, text="No network interfaces found", foreground="red").pack(pady=10)
            return
        
        for i, interface in enumerate(self.interfaces):
            var = tk.BooleanVar(value=True)
            self.interface_vars.append(var)
            
            cb = ttk.Checkbutton(
                self.scrollable_frame,
                text=f"{interface['name']} - {interface['ip']}",
                variable=var
            )
            cb.pack(anchor=tk.W, pady=2)
        
        self.add_disco_log(f"[{datetime.now().strftime('%H:%M:%S')}] [INFO] Found {len(self.interfaces)} network interface(s)", "INFO")
    
    def start_disco_server(self):
        selected_interfaces = [
            interface for i, interface in enumerate(self.interfaces)
            if self.interface_vars[i].get()
        ]
        
        if not selected_interfaces:
            self.add_disco_log(f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Please select at least one interface", "ERROR")
            return
        
        self.disco_server.start(selected_interfaces)
        self.disco_start_btn.config(state='disabled')
        self.disco_stop_btn.config(state='normal')
        self.disco_status_label.config(text="● Running", foreground="green")
    
    def stop_disco_server(self):
        self.disco_server.stop()
        self.disco_start_btn.config(state='normal')
        self.disco_stop_btn.config(state='disabled')
        self.disco_status_label.config(text="● Stopped", foreground="red")
    
    def add_disco_log(self, message, level="INFO"):
        self.disco_log_text.config(state='normal')
        self.disco_log_text.insert(tk.END, message + "\n", level)
        self.disco_log_text.see(tk.END)
        self.disco_log_text.config(state='disabled')
    
    def clear_disco_log(self):
        self.disco_log_text.config(state='normal')
        self.disco_log_text.delete(1.0, tk.END)
        self.disco_log_text.config(state='disabled')
    
    # ===== File Server Methods =====
    def start_file_server(self):
        self.file_server.start()
        self.file_start_btn.config(state='disabled')
        self.file_stop_btn.config(state='normal')
        self.file_status_label.config(text="● Running", foreground="green")
        self.refresh_file_count()
    
    def stop_file_server(self):
        self.file_server.stop()
        self.file_start_btn.config(state='normal')
        self.file_stop_btn.config(state='disabled')
        self.file_status_label.config(text="● Stopped", foreground="red")
    
    def add_file_log(self, message, level="INFO"):
        self.file_log_text.config(state='normal')
        self.file_log_text.insert(tk.END, message + "\n", level)
        self.file_log_text.see(tk.END)
        self.file_log_text.config(state='disabled')
    
    def clear_file_log(self):
        self.file_log_text.config(state='normal')
        self.file_log_text.delete(1.0, tk.END)
        self.file_log_text.config(state='disabled')
    
    def refresh_file_count(self):
        files = self.file_server.get_file_list()
        self.file_count_label.config(text=str(len(files)))
    
    def open_sync_folder(self):
        folder = os.path.abspath(SYNC_FOLDER)
        if not os.path.exists(folder):
            os.makedirs(folder)
        self.open_folder(folder)
    
    # ===== OTA Server Methods =====
    def start_ota_server(self):
        self.ota_server.start()
        self.ota_start_btn.config(state='disabled')
        self.ota_stop_btn.config(state='normal')
        self.ota_status_label.config(text="● Running", foreground="green")
        self.refresh_firmware_status()
    
    def stop_ota_server(self):
        self.ota_server.stop()
        self.ota_start_btn.config(state='normal')
        self.ota_stop_btn.config(state='disabled')
        self.ota_status_label.config(text="● Stopped", foreground="red")
    
    def add_ota_log(self, message, level="INFO"):
        self.ota_log_text.config(state='normal')
        self.ota_log_text.insert(tk.END, message + "\n", level)
        self.ota_log_text.see(tk.END)
        self.ota_log_text.config(state='disabled')
    
    def clear_ota_log(self):
        self.ota_log_text.config(state='normal')
        self.ota_log_text.delete(1.0, tk.END)
        self.ota_log_text.config(state='disabled')
    
    def refresh_firmware_status(self):
        firmware_path = os.path.join(FIRMWARE_DIR, FIRMWARE_FILE)
        if os.path.exists(firmware_path):
            size = os.path.getsize(firmware_path)
            self.firmware_status_label.config(text=f"{FIRMWARE_FILE} ({size:,} bytes)", foreground="green")
        else:
            self.firmware_status_label.config(text="Not found", foreground="red")
    
    def open_firmware_folder(self):
        folder = os.path.abspath(FIRMWARE_DIR)
        if not os.path.exists(folder):
            os.makedirs(folder)
        self.open_folder(folder)
    
    # ===== Utility Methods =====
    def open_folder(self, folder):
        """Open folder in system file manager"""
        try:
            if platform.system() == 'Windows':
                os.startfile(folder)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', folder])
            else:  # Linux
                subprocess.run(['xdg-open', folder])
        except Exception as e:
            self.add_file_log(f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Could not open folder: {e}", "ERROR")
    
    def auto_start_all_servers(self):
        """Auto-start all servers on application launch"""
        self.add_disco_log(f"[{datetime.now().strftime('%H:%M:%S')}] [INFO] Auto-starting all servers...", "INFO")
        
        # Start Discovery Server
        if self.interfaces:
            self.start_disco_server()
        
        # Start File Server
        self.start_file_server()
        
        # Start OTA Server
        self.start_ota_server()
    
    def on_closing(self):
        """Handle window close event"""
        # Stop all servers
        if self.disco_server.running:
            self.disco_server.stop()
        if self.file_server.running:
            self.file_server.stop()
        if self.ota_server.running:
            self.ota_server.stop()
        
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ServerManagerGUI(root)
    root.mainloop()
