#!/usr/bin/env python3
"""
Multi-threaded OTA Server for ESP32
Supports up to 50 concurrent connections
Server for ESP32 firmware updates with MD5 verification
"""

import hashlib
import os
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

class OTAHandler(BaseHTTPRequestHandler):
    FIRMWARE_DIR = "./firmware"  # Folder with bin files
    FIRMWARE_FILE = "firmware.bin"  # Firmware file name
    
    # Cached data for performance improvement
    _cached_md5 = None
    _cached_size = None
    _cached_mtime = None
    _cache_lock = threading.Lock()
    
    def do_GET(self):
        """Handle GET requests"""
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
            print(f"Error handling request: {e}")
            self.send_error(500, "Internal Server Error")
    
    def handle_version_check(self):
        """Send MD5 hash of current firmware with caching"""
        try:
            firmware_path = os.path.join(self.FIRMWARE_DIR, self.FIRMWARE_FILE)
            
            if not os.path.exists(firmware_path):
                self.send_error(404, "Firmware not found")
                return
            
            # Get data with caching
            md5_hash, file_size = self.get_cached_firmware_info(firmware_path)
            
            response_data = {
                "version": md5_hash,
                "size": file_size,
                "filename": self.FIRMWARE_FILE,
                "timestamp": int(time.time())
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
            
            print(f"[{threading.current_thread().name}] Version check: MD5={md5_hash}, Size={file_size}")
            
        except Exception as e:
            print(f"Error in version check: {e}")
            self.send_error(500, "Internal Server Error")
    
    def handle_firmware_download(self):
        """Send firmware file with Range request support"""
        try:
            firmware_path = os.path.join(self.FIRMWARE_DIR, self.FIRMWARE_FILE)
            
            if not os.path.exists(firmware_path):
                self.send_error(404, "Firmware not found")
                return
            
            file_size = os.path.getsize(firmware_path)
            
            # Support Range requests for resumable downloads
            range_header = self.headers.get('Range')
            if range_header:
                ranges = range_header.replace('bytes=', '').split('-')
                range_start = int(ranges[0]) if ranges[0] else 0
                range_end = int(ranges[1]) if ranges[1] else file_size - 1
                
                content_length = range_end - range_start + 1
                
                self.send_response(206)  # Partial Content
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Content-Range", f"bytes {range_start}-{range_end}/{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Disposition", f"attachment; filename={self.FIRMWARE_FILE}")
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
                
                print(f"[{threading.current_thread().name}] Partial firmware sent: {range_start}-{range_end}/{file_size}")
            else:
                # Full download
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Disposition", f"attachment; filename={self.FIRMWARE_FILE}")
                self.end_headers()
                
                with open(firmware_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                
                print(f"[{threading.current_thread().name}] Full firmware sent: {self.FIRMWARE_FILE} ({file_size} bytes)")
            
        except Exception as e:
            print(f"Error sending firmware: {e}")
            self.send_error(500, "Internal Server Error")
    
    def handle_status(self):
        """Server status and active connection count"""
        try:
            active_threads = threading.active_count()
            firmware_path = os.path.join(self.FIRMWARE_DIR, self.FIRMWARE_FILE)
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
            print(f"Error in status check: {e}")
            self.send_error(500, "Internal Server Error")
    
    def get_cached_firmware_info(self, firmware_path):
        """Get firmware information with caching"""
        with self._cache_lock:
            current_mtime = os.path.getmtime(firmware_path)
            
            # Check if cache needs to be updated
            if (self._cached_md5 is None or 
                self._cached_mtime != current_mtime):
                
                print("Calculating MD5 (cache miss or file changed)...")
                self._cached_md5 = self.calculate_md5(firmware_path)
                self._cached_size = os.path.getsize(firmware_path)
                self._cached_mtime = current_mtime
                print(f"MD5 cached: {self._cached_md5}")
            
            return self._cached_md5, self._cached_size
    
    def calculate_md5(self, file_path):
        """Calculate MD5 hash of file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def log_message(self, format, *args):
        """Log requests with thread information"""
        thread_name = threading.current_thread().name
        print(f"[{self.date_time_string()}] [{thread_name}] {format % args}")

class ThreadedOTAServer(ThreadingHTTPServer):
    """Multi-threaded OTA server with connection limit"""
    
    def __init__(self, server_address, RequestHandlerClass, max_connections=50):
        super().__init__(server_address, RequestHandlerClass)
        self.max_connections = max_connections
        self.connection_count = 0
        self.connection_lock = threading.Lock()
        # Configure socket for address reuse
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    def process_request(self, request, client_address):
        """Process request with connection limit check"""
        with self.connection_lock:
            if self.connection_count >= self.max_connections:
                print(f"Connection limit reached ({self.max_connections}), rejecting {client_address}")
                request.close()
                return
            
            self.connection_count += 1
            current_connections = self.connection_count
        
        print(f"New connection from {client_address} (active: {current_connections})")
        
        # Create thread for request handling
        thread = threading.Thread(
            target=self._handle_request_with_cleanup,
            args=(request, client_address),
            name=f"OTA-{client_address[0]}:{client_address[1]}"
        )
        thread.daemon = True
        thread.start()
    
    def _handle_request_with_cleanup(self, request, client_address):
        """Handle request with connection counter cleanup"""
        try:
            self.finish_request(request, client_address)
        except Exception as e:
            print(f"Error handling request from {client_address}: {e}")
        finally:
            with self.connection_lock:
                self.connection_count -= 1
                current_connections = self.connection_count
            print(f"Connection closed for {client_address} (active: {current_connections})")
            request.close()

def main():
    import socket
    
    # Create firmware folder if it doesn't exist
    firmware_dir = "./firmware"
    if not os.path.exists(firmware_dir):
        os.makedirs(firmware_dir)
        print(f"Created firmware directory: {firmware_dir}")
    
    # Check firmware file existence
    firmware_file = os.path.join(firmware_dir, "firmware.bin")
    if not os.path.exists(firmware_file):
        print(f"Warning: Firmware file not found: {firmware_file}")
        print("Please place your firmware.bin file in the firmware directory")
    else:
        # Pre-calculate MD5 for caching
        print("Pre-calculating firmware MD5...")
        hash_md5 = hashlib.md5()
        with open(firmware_file, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        
        # Set cached values
        OTAHandler._cached_md5 = hash_md5.hexdigest()
        OTAHandler._cached_size = os.path.getsize(firmware_file)
        OTAHandler._cached_mtime = os.path.getmtime(firmware_file)
        print(f"Firmware MD5 pre-calculated: {OTAHandler._cached_md5}")
    
    # Server settings
    server_address = ('', 5005)
    max_connections = 50
    
    # Create multi-threaded server
    httpd = ThreadedOTAServer(server_address, OTAHandler, max_connections)
    
    print(f"Multi-threaded OTA Server starting on port 5005...")
    print(f"Maximum concurrent connections: {max_connections}")
    print(f"Firmware directory: {os.path.abspath(firmware_dir)}")
    print(f"Endpoints:")
    print(f"  GET /version - Check firmware version (MD5)")
    print(f"  GET /update  - Download firmware")
    print(f"  GET /status  - Server status")
    print(f"Server ready at http://localhost:5005")
    print(f"Thread pool ready for handling multiple ESP32 devices")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        print(f"Active connections: {httpd.connection_count}")
        httpd.shutdown()
        httpd.server_close()

if __name__ == "__main__":
    main()