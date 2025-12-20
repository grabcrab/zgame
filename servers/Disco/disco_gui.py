import socket
import json
import psutil
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime

DISCO_PORT = 4210
TCP_PORT = 3232

class DiscoveryServer:
    def __init__(self, gui=None):
        self.gui = gui
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
                    # Skip loopback
                    if ip.startswith("127."):
                        continue
                    # Skip link-local APIPA
                    if ip.startswith("169.254."):
                        continue
                    interfaces.append({
                        'name': nic,
                        'ip': ip,
                        'enabled': True
                    })
        return interfaces
    
    def log(self, message, level="INFO"):
        """Log message to GUI if available, otherwise print"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        
        if self.gui:
            self.gui.add_log(log_message, level)
        else:
            print(log_message)
    
    def responder_worker(self, interface_ip, interface_name):
        """Worker thread for handling discovery requests on a specific interface"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)  # Add timeout to allow checking self.running
            
            # Bind to specific interface
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
                    if self.running:  # Only log if we're still supposed to be running
                        self.log(f"Error on {interface_name}: {str(e)}", "ERROR")
                    
        except Exception as e:
            self.log(f"Failed to bind to {interface_name} ({interface_ip}): {str(e)}", "ERROR")
        finally:
            try:
                sock.close()
            except:
                pass
    
    def start(self, interfaces):
        """Start responder threads for selected interfaces"""
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
        """Stop all responder threads"""
        if not self.running:
            return
        
        self.log("Stopping discovery server...")
        self.running = False
        
        # Close all sockets
        for sock in self.sockets:
            try:
                sock.close()
            except:
                pass
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=2.0)
        
        self.threads = []
        self.sockets = []
        self.log("Server stopped", "SUCCESS")


class DiscoveryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("xGAME discovery server")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # Set minimum window size
        self.root.minsize(600, 400)
        
        self.server = DiscoveryServer(gui=self)
        self.interfaces = []
        self.interface_vars = []
        
        self.create_widgets()
        self.refresh_interfaces()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        # Only the log frame (row=3) should expand
        main_frame.rowconfigure(3, weight=1)
        
        # ===== Header =====
        header_frame = ttk.LabelFrame(main_frame, text="Server Configuration", padding="10")
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        header_frame.columnconfigure(1, weight=1)
        
        ttk.Label(header_frame, text="Discovery Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Label(header_frame, text=str(DISCO_PORT), font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(header_frame, text="TCP Port:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Label(header_frame, text=str(TCP_PORT), font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=1, sticky=tk.W)
        
        # ===== Network Interfaces =====
        interface_frame = ttk.LabelFrame(main_frame, text="Network Interfaces", padding="10")
        interface_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        interface_frame.columnconfigure(0, weight=1)
        
        # Fixed height canvas for exactly 3 lines (approximately 70 pixels)
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
        
        # Refresh button
        refresh_btn = ttk.Button(interface_frame, text="Refresh Interfaces", command=self.refresh_interfaces)
        refresh_btn.grid(row=1, column=0, columnspan=2, pady=(5, 0))
        
        # ===== Control Buttons =====
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.start_btn = ttk.Button(control_frame, text="Start Server", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_btn = ttk.Button(control_frame, text="Stop Server", command=self.stop_server, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.clear_log_btn = ttk.Button(control_frame, text="Clear Log", command=self.clear_log)
        self.clear_log_btn.pack(side=tk.LEFT)
        
        # ===== Log Display =====
        log_frame = ttk.LabelFrame(main_frame, text="Server Log", padding="10")
        log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, state='disabled')
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure text tags for different log levels
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("SUCCESS", foreground="green")
        self.log_text.tag_config("WARNING", foreground="orange")
        self.log_text.tag_config("ERROR", foreground="red")
    
    def refresh_interfaces(self):
        """Refresh the list of network interfaces"""
        # Clear existing interface checkboxes
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.interface_vars = []
        self.interfaces = self.server.get_all_interfaces()
        
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
        
        self.add_log(f"Found {len(self.interfaces)} network interface(s)", "INFO")
        
        # Auto-start server if not already running
        if not self.server.running and hasattr(self, 'start_btn'):
            self.root.after(500, self.auto_start_server)
    
    def auto_start_server(self):
        """Automatically start the server after initialization"""
        if not self.server.running and self.interfaces:
            self.add_log("Auto-starting server...", "INFO")
            self.start_server()
    
    def start_server(self):
        """Start the discovery server"""
        # Get selected interfaces
        selected_interfaces = [
            interface for i, interface in enumerate(self.interfaces)
            if self.interface_vars[i].get()
        ]
        
        if not selected_interfaces:
            self.add_log("Please select at least one interface", "ERROR")
            return
        
        self.server.start(selected_interfaces)
        
        # Update button states
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
    
    def stop_server(self):
        """Stop the discovery server"""
        self.server.stop()
        
        # Update button states
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
    
    def add_log(self, message, level="INFO"):
        """Add a message to the log display"""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n", level)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
    
    def clear_log(self):
        """Clear the log display"""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
    
    def on_closing(self):
        """Handle window close event"""
        if self.server.running:
            self.server.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = DiscoveryGUI(root)
    root.mainloop()
    
# import socket
# import json
# import psutil
# import threading
# import time
# import tkinter as tk
# from tkinter import ttk, scrolledtext
# from datetime import datetime

# DISCO_PORT = 4210
# TCP_PORT = 3232

# class DiscoveryServer:
#     def __init__(self, gui=None):
#         self.gui = gui
#         self.running = False
#         self.threads = []
#         self.sockets = []
        
#     def get_all_interfaces(self):
#         """Get all available network interfaces with their IP addresses"""
#         interfaces = []
#         for nic, addrs in psutil.net_if_addrs().items():
#             for a in addrs:
#                 if a.family == socket.AF_INET:
#                     ip = a.address
#                     # Skip loopback
#                     if ip.startswith("127."):
#                         continue
#                     # Skip link-local APIPA
#                     if ip.startswith("169.254."):
#                         continue
#                     interfaces.append({
#                         'name': nic,
#                         'ip': ip,
#                         'enabled': True
#                     })
#         return interfaces
    
#     def log(self, message, level="INFO"):
#         """Log message to GUI if available, otherwise print"""
#         timestamp = datetime.now().strftime("%H:%M:%S")
#         log_message = f"[{timestamp}] [{level}] {message}"
        
#         if self.gui:
#             self.gui.add_log(log_message, level)
#         else:
#             print(log_message)
    
#     def responder_worker(self, interface_ip, interface_name):
#         """Worker thread for handling discovery requests on a specific interface"""
#         try:
#             sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#             sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#             sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
#             sock.settimeout(1.0)  # Add timeout to allow checking self.running
            
#             # Bind to specific interface
#             sock.bind((interface_ip, DISCO_PORT))
#             self.sockets.append(sock)
            
#             self.log(f"Listening on {interface_name} ({interface_ip}:{DISCO_PORT})", "SUCCESS")
            
#             while self.running:
#                 try:
#                     data, addr = sock.recvfrom(64)
#                     self.log(f"Received from {addr[0]}:{addr[1]} on {interface_name}: {data.decode('utf-8', errors='ignore')}")
                    
#                     if b'ESP32-LOOK' in data:
#                         response = interface_ip.encode()
#                         sock.sendto(response, addr)
#                         self.log(f"Sent response '{interface_ip}' to {addr[0]}:{addr[1]}", "SUCCESS")
                        
#                 except socket.timeout:
#                     continue
#                 except Exception as e:
#                     if self.running:  # Only log if we're still supposed to be running
#                         self.log(f"Error on {interface_name}: {str(e)}", "ERROR")
                    
#         except Exception as e:
#             self.log(f"Failed to bind to {interface_name} ({interface_ip}): {str(e)}", "ERROR")
#         finally:
#             try:
#                 sock.close()
#             except:
#                 pass
    
#     def start(self, interfaces):
#         """Start responder threads for selected interfaces"""
#         if self.running:
#             self.log("Server already running", "WARNING")
#             return
        
#         self.running = True
#         self.threads = []
#         self.sockets = []
        
#         if not interfaces:
#             self.log("No interfaces selected", "ERROR")
#             return
        
#         self.log(f"Starting discovery server on {len(interfaces)} interface(s)...")
        
#         for interface in interfaces:
#             if interface['enabled']:
#                 thread = threading.Thread(
#                     target=self.responder_worker,
#                     args=(interface['ip'], interface['name']),
#                     daemon=True
#                 )
#                 thread.start()
#                 self.threads.append(thread)
        
#         if not self.threads:
#             self.log("No interfaces were started", "ERROR")
#             self.running = False
    
#     def stop(self):
#         """Stop all responder threads"""
#         if not self.running:
#             return
        
#         self.log("Stopping discovery server...")
#         self.running = False
        
#         # Close all sockets
#         for sock in self.sockets:
#             try:
#                 sock.close()
#             except:
#                 pass
        
#         # Wait for threads to finish
#         for thread in self.threads:
#             thread.join(timeout=2.0)
        
#         self.threads = []
#         self.sockets = []
#         self.log("Server stopped", "SUCCESS")


# class DiscoveryGUI:
#     def __init__(self, root):
#         self.root = root
#         self.root.title("xGAME discovery server")
#         self.root.geometry("800x600")
#         self.root.resizable(True, True)
        
#         # Set minimum window size
#         self.root.minsize(600, 400)
        
#         self.server = DiscoveryServer(gui=self)
#         self.interfaces = []
#         self.interface_vars = []
        
#         self.create_widgets()
#         self.refresh_interfaces()
        
#         # Handle window close
#         self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
#     def create_widgets(self):
#         # Main container with padding
#         main_frame = ttk.Frame(self.root, padding="10")
#         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
#         # Configure grid weights
#         self.root.columnconfigure(0, weight=1)
#         self.root.rowconfigure(0, weight=1)
#         main_frame.columnconfigure(0, weight=1)
#         main_frame.rowconfigure(2, weight=1)
        
#         # ===== Header =====
#         header_frame = ttk.LabelFrame(main_frame, text="Server Configuration", padding="10")
#         header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
#         header_frame.columnconfigure(1, weight=1)
        
#         ttk.Label(header_frame, text="Discovery Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
#         ttk.Label(header_frame, text=str(DISCO_PORT), font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=1, sticky=tk.W)
        
#         ttk.Label(header_frame, text="TCP Port:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10))
#         ttk.Label(header_frame, text=str(TCP_PORT), font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=1, sticky=tk.W)
        
#         # ===== Network Interfaces =====
#         interface_frame = ttk.LabelFrame(main_frame, text="Network Interfaces", padding="10")
#         interface_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
#         interface_frame.columnconfigure(0, weight=1)
        
#         # Scrollable frame for interfaces
#         canvas = tk.Canvas(interface_frame, height=120)
#         scrollbar = ttk.Scrollbar(interface_frame, orient="vertical", command=canvas.yview)
#         self.scrollable_frame = ttk.Frame(canvas)
        
#         self.scrollable_frame.bind(
#             "<Configure>",
#             lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
#         )
        
#         canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
#         canvas.configure(yscrollcommand=scrollbar.set)
        
#         canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
#         scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
#         # Refresh button
#         refresh_btn = ttk.Button(interface_frame, text="Refresh Interfaces", command=self.refresh_interfaces)
#         refresh_btn.grid(row=1, column=0, columnspan=2, pady=(5, 0))
        
#         # ===== Control Buttons =====
#         control_frame = ttk.Frame(main_frame)
#         control_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
#         self.start_btn = ttk.Button(control_frame, text="Start Server", command=self.start_server)
#         self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
#         self.stop_btn = ttk.Button(control_frame, text="Stop Server", command=self.stop_server, state='disabled')
#         self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
#         self.clear_log_btn = ttk.Button(control_frame, text="Clear Log", command=self.clear_log)
#         self.clear_log_btn.pack(side=tk.LEFT)
        
#         # ===== Log Display =====
#         log_frame = ttk.LabelFrame(main_frame, text="Server Log", padding="10")
#         log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
#         log_frame.columnconfigure(0, weight=1)
#         log_frame.rowconfigure(0, weight=1)
        
#         self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, state='disabled')
#         self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
#         # Configure text tags for different log levels
#         self.log_text.tag_config("INFO", foreground="black")
#         self.log_text.tag_config("SUCCESS", foreground="green")
#         self.log_text.tag_config("WARNING", foreground="orange")
#         self.log_text.tag_config("ERROR", foreground="red")
    
#     def refresh_interfaces(self):
#         """Refresh the list of network interfaces"""
#         # Clear existing interface checkboxes
#         for widget in self.scrollable_frame.winfo_children():
#             widget.destroy()
        
#         self.interface_vars = []
#         self.interfaces = self.server.get_all_interfaces()
        
#         if not self.interfaces:
#             ttk.Label(self.scrollable_frame, text="No network interfaces found", foreground="red").pack(pady=10)
#             return
        
#         for i, interface in enumerate(self.interfaces):
#             var = tk.BooleanVar(value=True)
#             self.interface_vars.append(var)
            
#             cb = ttk.Checkbutton(
#                 self.scrollable_frame,
#                 text=f"{interface['name']} - {interface['ip']}",
#                 variable=var
#             )
#             cb.pack(anchor=tk.W, pady=2)
        
#         self.add_log(f"Found {len(self.interfaces)} network interface(s)", "INFO")
    
#     def start_server(self):
#         """Start the discovery server"""
#         # Get selected interfaces
#         selected_interfaces = [
#             interface for i, interface in enumerate(self.interfaces)
#             if self.interface_vars[i].get()
#         ]
        
#         if not selected_interfaces:
#             self.add_log("Please select at least one interface", "ERROR")
#             return
        
#         self.server.start(selected_interfaces)
        
#         # Update button states
#         self.start_btn.config(state='disabled')
#         self.stop_btn.config(state='normal')
    
#     def stop_server(self):
#         """Stop the discovery server"""
#         self.server.stop()
        
#         # Update button states
#         self.start_btn.config(state='normal')
#         self.stop_btn.config(state='disabled')
    
#     def add_log(self, message, level="INFO"):
#         """Add a message to the log display"""
#         self.log_text.config(state='normal')
#         self.log_text.insert(tk.END, message + "\n", level)
#         self.log_text.see(tk.END)
#         self.log_text.config(state='disabled')
    
#     def clear_log(self):
#         """Clear the log display"""
#         self.log_text.config(state='normal')
#         self.log_text.delete(1.0, tk.END)
#         self.log_text.config(state='disabled')
    
#     def on_closing(self):
#         """Handle window close event"""
#         if self.server.running:
#             self.server.stop()
#         self.root.destroy()


# if __name__ == "__main__":
#     root = tk.Tk()
#     app = DiscoveryGUI(root)
#     root.mainloop()
