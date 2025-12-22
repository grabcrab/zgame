#!/usr/bin/env python3
"""
Zombie Game - Test Client
A GUI application that simulates multiple virtual ESP32 devices 
connecting to the Zombie Game server for testing purposes.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import random
import time
import threading
import requests
import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime


@dataclass
class VirtualDevice:
    """Represents a virtual ESP32 device"""
    device_id: str
    ip: str = "192.168.1.100"
    rssi: int = -50
    role: str = "neutral"
    status: str = "sleep"
    health: int = 100
    battery: int = 100
    comment: str = ""
    last_response: Optional[dict] = None
    last_update: Optional[float] = None
    error_count: int = 0
    
    def to_request_data(self) -> dict:
        """Convert to request data format"""
        return {
            'id': self.device_id,
            'ip': self.ip,
            'rssi': self.rssi,
            'role': self.role,
            'status': self.status,
            'health': self.health,
            'battery': self.battery,
            'comment': self.comment
        }


class DeviceSimulator:
    """Manages virtual device communication with server"""
    
    def __init__(self, server_url: str, device: VirtualDevice, update_callback):
        self.server_url = server_url
        self.device = device
        self.update_callback = update_callback
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.poll_interval = 2.0  # seconds
        
    def start(self):
        """Start the device simulation"""
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the device simulation"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            
    def _run_loop(self):
        """Main simulation loop"""
        while self.running:
            try:
                self._send_update()
            except Exception as e:
                self.device.error_count += 1
                print(f"Device {self.device.device_id} error: {e}")
            
            # Notify UI
            if self.update_callback:
                self.update_callback(self.device)
                
            time.sleep(self.poll_interval)
            
    def _send_update(self):
        """Send device update to server"""
        data = self.device.to_request_data()
        params = {'data': json.dumps(data)}
        
        response = requests.get(
            f"{self.server_url}/api/device",
            params=params,
            timeout=5.0
        )
        
        if response.status_code == 200:
            resp_data = response.json()
            self.device.last_response = resp_data
            self.device.last_update = time.time()
            
            # Update device state from server response
            if 'role' in resp_data:
                self.device.role = resp_data['role']
            if 'status' in resp_data:
                self.device.status = resp_data['status']
        else:
            self.device.error_count += 1
            
    def simulate_infection(self):
        """Simulate this device becoming a zombie (human -> zombie)"""
        if self.device.role == 'human':
            self.device.role = 'zombie'
            self.device.health = max(0, self.device.health - 25)
            
    def simulate_healing(self):
        """Simulate healing (restore health)"""
        self.device.health = min(100, self.device.health + 25)


class ZombieTestClientApp:
    """Main GUI Application for Test Client"""
    
    def __init__(self, root, server_url: str, num_devices: int):
        self.root = root
        self.server_url = server_url.rstrip('/')
        self.num_devices = num_devices
        
        self.root.title(f"Zombie Game - Test Client ({num_devices} devices)")
        self.root.geometry("1300x800")
        self.root.minsize(1100, 600)
        
        # Device management
        self.devices: Dict[str, VirtualDevice] = {}
        self.simulators: Dict[str, DeviceSimulator] = {}
        self.running = False
        
        # UI update queue
        self.pending_updates = []
        self.update_lock = threading.Lock()
        
        # Setup UI
        self.setup_styles()
        self.create_ui()
        
        # Create virtual devices
        self.create_devices(num_devices)
        
        # Setup close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start UI update loop
        self.root.after(100, self.process_updates)
        
    def setup_styles(self):
        """Setup ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('Title.TLabel', font=('Arial', 18, 'bold'), foreground='#2c3e50')
        style.configure('Header.TLabel', font=('Arial', 14, 'bold'), foreground='#34495e')
        style.configure('Info.TLabel', font=('Arial', 10), foreground='#7f8c8d')
        style.configure('Status.TLabel', font=('Arial', 11), foreground='#27ae60')
        style.configure('Error.TLabel', font=('Arial', 11), foreground='#e74c3c')
        
        style.configure('Start.TButton', font=('Arial', 11, 'bold'), padding=8)
        style.configure('Stop.TButton', font=('Arial', 11, 'bold'), padding=8)
        style.configure('Action.TButton', font=('Arial', 10), padding=5)
        
        # Treeview colors for roles
        style.configure('Treeview', rowheight=25)
        
    def create_ui(self):
        """Create the main UI"""
        # Main container
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(expand=True, fill='both')
        
        # Header frame
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill='x', pady=(0, 10))
        
        # Title
        title = ttk.Label(header_frame, text="🧪 Zombie Game Test Client", style='Title.TLabel')
        title.pack(side='left')
        
        # Connection info
        self.connection_label = ttk.Label(
            header_frame, 
            text=f"Server: {self.server_url}", 
            style='Info.TLabel'
        )
        self.connection_label.pack(side='right')
        
        # Control frame
        control_frame = ttk.LabelFrame(main_frame, text="Controls", padding=10)
        control_frame.pack(fill='x', pady=(0, 10))
        
        # Server URL entry
        url_frame = ttk.Frame(control_frame)
        url_frame.pack(fill='x', pady=5)
        
        ttk.Label(url_frame, text="Server URL:").pack(side='left')
        self.url_var = tk.StringVar(value=self.server_url)
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=40)
        self.url_entry.pack(side='left', padx=10)
        
        ttk.Button(url_frame, text="Update URL", command=self.update_server_url,
                  style='Action.TButton').pack(side='left')
        
        # Button frame
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill='x', pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ Start All Devices", 
                                    command=self.start_all_devices,
                                    style='Start.TButton')
        self.start_btn.pack(side='left', padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹ Stop All Devices", 
                                   command=self.stop_all_devices,
                                   style='Stop.TButton', state='disabled')
        self.stop_btn.pack(side='left', padx=5)
        
        ttk.Separator(btn_frame, orient='vertical').pack(side='left', fill='y', padx=15)
        
        ttk.Button(btn_frame, text="🧟 Infect Selected", 
                  command=self.infect_selected,
                  style='Action.TButton').pack(side='left', padx=5)
        
        ttk.Button(btn_frame, text="💚 Heal Selected", 
                  command=self.heal_selected,
                  style='Action.TButton').pack(side='left', padx=5)
        
        ttk.Button(btn_frame, text="🔀 Random Infection", 
                  command=self.random_infection,
                  style='Action.TButton').pack(side='left', padx=5)
        
        ttk.Separator(btn_frame, orient='vertical').pack(side='left', fill='y', padx=15)
        
        ttk.Button(btn_frame, text="🔄 Refresh", 
                  command=self.refresh_device_list,
                  style='Action.TButton').pack(side='left', padx=5)
        
        # Status frame
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(fill='x', pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Status: Stopped", style='Info.TLabel')
        self.status_label.pack(side='left')
        
        self.stats_label = ttk.Label(status_frame, text="", style='Info.TLabel')
        self.stats_label.pack(side='right')
        
        # Devices frame
        devices_frame = ttk.LabelFrame(main_frame, text="Virtual Devices", padding=10)
        devices_frame.pack(fill='both', expand=True)
        
        # Create treeview for devices
        columns = ('ID', 'IP', 'RSSI', 'Role', 'Status', 'Health', 'Battery', 
                   'Server Role', 'Server Status', 'Last Update', 'Errors')
        self.device_tree = ttk.Treeview(devices_frame, columns=columns, show='headings', height=20)
        
        # Configure columns
        col_widths = {
            'ID': 100, 'IP': 120, 'RSSI': 60, 'Role': 80, 'Status': 80,
            'Health': 60, 'Battery': 60, 'Server Role': 90, 'Server Status': 90,
            'Last Update': 100, 'Errors': 60
        }
        
        for col in columns:
            self.device_tree.heading(col, text=col, command=lambda c=col: self.sort_treeview(c))
            self.device_tree.column(col, width=col_widths.get(col, 80), anchor='center')
        
        # Scrollbars
        v_scroll = ttk.Scrollbar(devices_frame, orient='vertical', command=self.device_tree.yview)
        h_scroll = ttk.Scrollbar(devices_frame, orient='horizontal', command=self.device_tree.xview)
        self.device_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        # Grid layout
        self.device_tree.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        
        devices_frame.grid_rowconfigure(0, weight=1)
        devices_frame.grid_columnconfigure(0, weight=1)
        
        # Configure row tags for colors
        self.device_tree.tag_configure('zombie', background='#ffcccc')
        self.device_tree.tag_configure('human', background='#ccffcc')
        self.device_tree.tag_configure('neutral', background='#f0f0f0')
        self.device_tree.tag_configure('error', background='#ffeecc')
        
        # Enable multiple selection
        self.device_tree.configure(selectmode='extended')
        
        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding=5)
        log_frame.pack(fill='x', pady=(10, 0))
        
        self.log_text = tk.Text(log_frame, height=5, wrap='word', state='disabled',
                                font=('Consolas', 9))
        log_scroll = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        self.log_text.pack(side='left', fill='both', expand=True)
        log_scroll.pack(side='right', fill='y')
        
    def create_devices(self, num_devices: int):
        """Create virtual devices"""
        for i in range(num_devices):
            device_id = f"ESP32_{i+1:03d}"
            ip = f"192.168.1.{100 + i}"
            rssi = random.randint(-80, -30)
            battery = random.randint(50, 100)
            comment = f"Virtual Device {i+1}"
            
            device = VirtualDevice(
                device_id=device_id,
                ip=ip,
                rssi=rssi,
                battery=battery,
                comment=comment
            )
            
            self.devices[device_id] = device
            
        self.refresh_device_list()
        self.log(f"Created {num_devices} virtual devices")
        
    def start_all_devices(self):
        """Start all device simulators"""
        if self.running:
            return
            
        self.running = True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.url_entry.config(state='disabled')
        
        for device_id, device in self.devices.items():
            simulator = DeviceSimulator(
                self.server_url, 
                device, 
                self.queue_device_update
            )
            self.simulators[device_id] = simulator
            simulator.start()
            
        self.status_label.config(text="Status: Running", style='Status.TLabel')
        self.log(f"Started {len(self.devices)} device simulators")
        
    def stop_all_devices(self):
        """Stop all device simulators"""
        if not self.running:
            return
            
        self.running = False
        
        for simulator in self.simulators.values():
            simulator.stop()
            
        self.simulators.clear()
        
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.url_entry.config(state='normal')
        
        self.status_label.config(text="Status: Stopped", style='Info.TLabel')
        self.log("Stopped all device simulators")
        
    def queue_device_update(self, device: VirtualDevice):
        """Queue a device update for UI processing"""
        with self.update_lock:
            self.pending_updates.append(device.device_id)
            
    def process_updates(self):
        """Process pending UI updates"""
        with self.update_lock:
            device_ids = list(set(self.pending_updates))
            self.pending_updates.clear()
            
        for device_id in device_ids:
            self.update_device_row(device_id)
            
        # Update stats
        self.update_stats()
        
        # Schedule next update
        self.root.after(200, self.process_updates)
        
    def update_device_row(self, device_id: str):
        """Update a single device row in the treeview"""
        device = self.devices.get(device_id)
        if not device:
            return
            
        # Find existing row
        for item in self.device_tree.get_children():
            if self.device_tree.item(item)['values'][0] == device_id:
                # Update existing row
                server_role = device.last_response.get('role', '-') if device.last_response else '-'
                server_status = device.last_response.get('status', '-') if device.last_response else '-'
                last_update = datetime.fromtimestamp(device.last_update).strftime('%H:%M:%S') if device.last_update else '-'
                
                values = (
                    device.device_id,
                    device.ip,
                    device.rssi,
                    device.role,
                    device.status,
                    device.health,
                    f"{device.battery}%",
                    server_role,
                    server_status,
                    last_update,
                    device.error_count
                )
                
                # Determine tag based on role
                tag = device.role if device.role in ['zombie', 'human', 'neutral'] else 'neutral'
                if device.error_count > 5:
                    tag = 'error'
                    
                self.device_tree.item(item, values=values, tags=(tag,))
                return
                
    def refresh_device_list(self):
        """Refresh the entire device list"""
        # Clear existing items
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
            
        # Add all devices
        for device_id, device in sorted(self.devices.items()):
            server_role = device.last_response.get('role', '-') if device.last_response else '-'
            server_status = device.last_response.get('status', '-') if device.last_response else '-'
            last_update = datetime.fromtimestamp(device.last_update).strftime('%H:%M:%S') if device.last_update else '-'
            
            values = (
                device.device_id,
                device.ip,
                device.rssi,
                device.role,
                device.status,
                device.health,
                f"{device.battery}%",
                server_role,
                server_status,
                last_update,
                device.error_count
            )
            
            tag = device.role if device.role in ['zombie', 'human', 'neutral'] else 'neutral'
            if device.error_count > 5:
                tag = 'error'
                
            self.device_tree.insert('', 'end', values=values, tags=(tag,))
            
        self.update_stats()
        
    def update_stats(self):
        """Update statistics display"""
        zombies = sum(1 for d in self.devices.values() if d.role == 'zombie')
        humans = sum(1 for d in self.devices.values() if d.role == 'human')
        neutral = sum(1 for d in self.devices.values() if d.role == 'neutral')
        errors = sum(d.error_count for d in self.devices.values())
        
        self.stats_label.config(
            text=f"🧟 Zombies: {zombies} | 👥 Humans: {humans} | ⚪ Neutral: {neutral} | ⚠️ Errors: {errors}"
        )
        
    def sort_treeview(self, col):
        """Sort treeview by column"""
        items = [(self.device_tree.set(item, col), item) for item in self.device_tree.get_children('')]
        
        # Try numeric sort for numeric columns
        try:
            items.sort(key=lambda x: float(x[0].replace('%', '').replace('-', '0')))
        except ValueError:
            items.sort()
            
        for index, (val, item) in enumerate(items):
            self.device_tree.move(item, '', index)
            
    def infect_selected(self):
        """Infect selected devices (human -> zombie)"""
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Please select devices to infect")
            return
            
        infected = 0
        for item in selected:
            device_id = self.device_tree.item(item)['values'][0]
            if device_id in self.simulators:
                self.simulators[device_id].simulate_infection()
                infected += 1
            elif device_id in self.devices:
                device = self.devices[device_id]
                if device.role == 'human':
                    device.role = 'zombie'
                    infected += 1
                    
        self.refresh_device_list()
        self.log(f"Infected {infected} devices")
        
    def heal_selected(self):
        """Heal selected devices"""
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Please select devices to heal")
            return
            
        healed = 0
        for item in selected:
            device_id = self.device_tree.item(item)['values'][0]
            if device_id in self.simulators:
                self.simulators[device_id].simulate_healing()
                healed += 1
            elif device_id in self.devices:
                device = self.devices[device_id]
                device.health = min(100, device.health + 25)
                healed += 1
                
        self.refresh_device_list()
        self.log(f"Healed {healed} devices")
        
    def random_infection(self):
        """Randomly infect one human"""
        humans = [d for d in self.devices.values() if d.role == 'human']
        if not humans:
            messagebox.showinfo("Info", "No humans to infect")
            return
            
        victim = random.choice(humans)
        if victim.device_id in self.simulators:
            self.simulators[victim.device_id].simulate_infection()
        else:
            victim.role = 'zombie'
            victim.health = max(0, victim.health - 25)
            
        self.refresh_device_list()
        self.log(f"Randomly infected device {victim.device_id}")
        
    def update_server_url(self):
        """Update the server URL"""
        new_url = self.url_var.get().rstrip('/')
        if new_url != self.server_url:
            self.server_url = new_url
            self.connection_label.config(text=f"Server: {self.server_url}")
            self.log(f"Updated server URL to: {self.server_url}")
            
    def log(self, message: str):
        """Add a message to the log"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.config(state='normal')
        self.log_text.insert('end', f"[{timestamp}] {message}\n")
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        
    def on_closing(self):
        """Handle window close"""
        if self.running:
            if messagebox.askyesno("Exit", "Devices are still running. Stop and exit?"):
                self.stop_all_devices()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Zombie Game Test Client - Simulates virtual ESP32 devices'
    )
    parser.add_argument(
        '-n', '--num-devices',
        type=int,
        default=10,
        help='Number of virtual devices to simulate (default: 10)'
    )
    parser.add_argument(
        '-s', '--server',
        type=str,
        default='http://127.0.0.1:5000',
        help='Server URL (default: http://127.0.0.1:5000)'
    )
    
    args = parser.parse_args()
    
    if args.num_devices < 1:
        print("Error: Number of devices must be at least 1")
        sys.exit(1)
    if args.num_devices > 100:
        print("Warning: Large number of devices may cause performance issues")
        
    print("=" * 60)
    print("🧪 ZOMBIE GAME - Test Client")
    print("=" * 60)
    print(f"Server URL: {args.server}")
    print(f"Virtual Devices: {args.num_devices}")
    print("=" * 60)
    print()
    
    # Create and run GUI
    root = tk.Tk()
    app = ZombieTestClientApp(root, args.server, args.num_devices)
    root.mainloop()


if __name__ == '__main__':
    main()