#!/usr/bin/env python3
"""
Zombie Game - Test Client
A GUI application that simulates multiple virtual ESP32 devices 
connecting to the Zombie Game server for testing purposes.

Features:
- Simulates N virtual ESP32 devices
- Tracks game duration and time remaining from server
- Simulates health degradation and role conversion (zombie <-> human)
- Manual role override controls
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
from dataclasses import dataclass
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


class GameState:
    """Tracks game state from server responses"""
    
    def __init__(self):
        self.status: str = "sleep"  # sleep, prepare, game, end
        self.game_duration: int = 15  # minutes (from server)
        self.game_timeout: int = 30  # seconds
        self.game_start_time: Optional[float] = None
        self.last_conversion_time: Optional[float] = None
        self.conversion_interval: float = 120.0  # 2 minutes between conversions
        self.health_damage_rate: int = 10  # health lost per cycle
        self._lock = threading.Lock()
        
    def update_from_response(self, response: dict):
        """Update game state from server response"""
        with self._lock:
            new_status = response.get('status', self.status)
            
            # Detect game start
            if new_status == 'game' and self.status != 'game':
                self.game_start_time = time.time()
                self.last_conversion_time = time.time()
                
            # Detect game end
            if new_status == 'end' and self.status == 'game':
                self.game_start_time = None
                
            self.status = new_status
            
            if 'game_duration' in response:
                self.game_duration = response['game_duration']
            if 'game_timeout' in response:
                self.game_timeout = response['game_timeout']
                
    def get_time_remaining(self) -> Optional[int]:
        """Get remaining game time in seconds, or None if not in game"""
        with self._lock:
            if self.status != 'game' or self.game_start_time is None:
                return None
                
            elapsed = time.time() - self.game_start_time
            total_seconds = self.game_duration * 60
            remaining = total_seconds - elapsed
            return max(0, int(remaining))
            
    def is_game_over(self) -> bool:
        """Check if game time has expired"""
        remaining = self.get_time_remaining()
        return remaining is not None and remaining <= 0
        
    def should_do_conversion(self) -> bool:
        """Check if it's time for a health/conversion cycle"""
        with self._lock:
            if self.status != 'game':
                return False
            if self.last_conversion_time is None:
                return False
                
            elapsed = time.time() - self.last_conversion_time
            return elapsed >= self.conversion_interval
            
    def mark_conversion_done(self):
        """Mark that a conversion cycle was performed"""
        with self._lock:
            self.last_conversion_time = time.time()


class DeviceSimulator:
    """Manages virtual device communication with server"""
    
    def __init__(self, server_url: str, device: VirtualDevice, 
                 game_state: GameState, update_callback):
        self.server_url = server_url
        self.device = device
        self.game_state = game_state
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
            
            # Update game state from response
            self.game_state.update_from_response(resp_data)
            
            # Update device state from server response
            if 'role' in resp_data:
                self.device.role = resp_data['role']
            if 'status' in resp_data:
                self.device.status = resp_data['status']
        else:
            self.device.error_count += 1


class ZombieTestClientApp:
    """Main GUI Application for Test Client"""
    
    def __init__(self, root, server_url: str, num_devices: int):
        self.root = root
        self.server_url = server_url.rstrip('/')
        self.num_devices = num_devices
        
        self.root.title(f"Zombie Game - Test Client ({num_devices} devices)")
        self.root.geometry("1300x850")
        self.root.minsize(1100, 700)
        
        # Game state
        self.game_state = GameState()
        
        # Device management
        self.devices: Dict[str, VirtualDevice] = {}
        self.simulators: Dict[str, DeviceSimulator] = {}
        self.running = False
        
        # UI update queue
        self.pending_updates = []
        self.update_lock = threading.Lock()
        
        # Game ended flag
        self.game_ended_shown = False
        
        # Setup UI
        self.setup_styles()
        self.create_ui()
        
        # Create virtual devices
        self.create_devices(num_devices)
        
        # Setup close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start UI update loop
        self.root.after(100, self.process_updates)
        
        # Start timer update loop
        self.root.after(1000, self.update_timer_display)
        
        # Start conversion simulation loop
        self.root.after(5000, self.check_conversion_cycle)
        
    def setup_styles(self):
        """Setup ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('Title.TLabel', font=('Arial', 18, 'bold'), foreground='#2c3e50')
        style.configure('Header.TLabel', font=('Arial', 14, 'bold'), foreground='#34495e')
        style.configure('Info.TLabel', font=('Arial', 10), foreground='#7f8c8d')
        style.configure('Status.TLabel', font=('Arial', 11), foreground='#27ae60')
        style.configure('Error.TLabel', font=('Arial', 11), foreground='#e74c3c')
        style.configure('Timer.TLabel', font=('Arial', 24, 'bold'), foreground='#2980b9')
        style.configure('TimerWarning.TLabel', font=('Arial', 24, 'bold'), foreground='#e74c3c')
        style.configure('GameStatus.TLabel', font=('Arial', 12, 'bold'), foreground='#8e44ad')
        
        style.configure('Start.TButton', font=('Arial', 11, 'bold'), padding=8)
        style.configure('Stop.TButton', font=('Arial', 11, 'bold'), padding=8)
        style.configure('Action.TButton', font=('Arial', 10), padding=5)
        style.configure('Zombie.TButton', font=('Arial', 10, 'bold'), padding=5)
        style.configure('Human.TButton', font=('Arial', 10, 'bold'), padding=5)
        
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
        
        # Game status frame
        game_frame = ttk.LabelFrame(main_frame, text="Game Status", padding=10)
        game_frame.pack(fill='x', pady=(0, 10))
        
        game_info_frame = ttk.Frame(game_frame)
        game_info_frame.pack(fill='x')
        
        # Left side - game state info
        left_game = ttk.Frame(game_info_frame)
        left_game.pack(side='left', fill='x', expand=True)
        
        self.game_status_label = ttk.Label(left_game, text="Game Status: SLEEP", 
                                           style='GameStatus.TLabel')
        self.game_status_label.pack(anchor='w')
        
        self.game_duration_label = ttk.Label(left_game, text="Duration: -- min", 
                                             style='Info.TLabel')
        self.game_duration_label.pack(anchor='w')
        
        # Right side - timer
        right_game = ttk.Frame(game_info_frame)
        right_game.pack(side='right')
        
        ttk.Label(right_game, text="Time Remaining:", style='Info.TLabel').pack()
        self.timer_label = ttk.Label(right_game, text="--:--", style='Timer.TLabel')
        self.timer_label.pack()
        
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
        
        ttk.Button(btn_frame, text="🧟 To Zombie Selected", 
                  command=self.convert_to_zombie,
                  style='Zombie.TButton').pack(side='left', padx=5)
        
        ttk.Button(btn_frame, text="👥 To Human Selected", 
                  command=self.convert_to_human,
                  style='Human.TButton').pack(side='left', padx=5)
        
        ttk.Separator(btn_frame, orient='vertical').pack(side='left', fill='y', padx=15)
        
        ttk.Button(btn_frame, text="🔄 Refresh", 
                  command=self.refresh_device_list,
                  style='Action.TButton').pack(side='left', padx=5)
        
        # Simulation settings frame
        sim_frame = ttk.Frame(control_frame)
        sim_frame.pack(fill='x', pady=5)
        
        ttk.Label(sim_frame, text="Conversion Interval (sec):").pack(side='left')
        self.conversion_interval_var = tk.IntVar(value=120)
        conversion_spin = ttk.Spinbox(sim_frame, from_=30, to=300, width=8,
                                       textvariable=self.conversion_interval_var,
                                       command=self.update_conversion_interval)
        conversion_spin.pack(side='left', padx=5)
        
        ttk.Label(sim_frame, text="Health Damage:").pack(side='left', padx=(20, 0))
        self.health_damage_var = tk.IntVar(value=10)
        damage_spin = ttk.Spinbox(sim_frame, from_=5, to=50, width=8,
                                   textvariable=self.health_damage_var,
                                   command=self.update_health_damage)
        damage_spin.pack(side='left', padx=5)
        
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
        self.device_tree = ttk.Treeview(devices_frame, columns=columns, show='headings', height=18)
        
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
        self.device_tree.tag_configure('low_health', background='#ffe0b3')
        
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
        self.game_ended_shown = False
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.url_entry.config(state='disabled')
        
        for device_id, device in self.devices.items():
            simulator = DeviceSimulator(
                self.server_url, 
                device,
                self.game_state,
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
        
        # Update game status display
        self.update_game_status_display()
        
        # Schedule next update
        self.root.after(200, self.process_updates)
        
    def update_timer_display(self):
        """Update the timer display"""
        remaining = self.game_state.get_time_remaining()
        
        if remaining is not None:
            minutes = remaining // 60
            seconds = remaining % 60
            time_str = f"{minutes:02d}:{seconds:02d}"
            self.timer_label.config(text=time_str)
            
            # Change color when time is low
            if remaining < 60:
                self.timer_label.config(style='TimerWarning.TLabel')
            else:
                self.timer_label.config(style='Timer.TLabel')
                
            # Check for game end
            if remaining <= 0 and not self.game_ended_shown:
                self.handle_game_end()
        else:
            self.timer_label.config(text="--:--", style='Timer.TLabel')
            
        # Schedule next update
        self.root.after(1000, self.update_timer_display)
        
    def update_game_status_display(self):
        """Update game status labels"""
        status_map = {
            'sleep': 'SLEEP 💤',
            'prepare': 'PREPARE 🎯',
            'game': 'GAME IN PROGRESS 🎮',
            'end': 'GAME ENDED 🏁'
        }
        
        status_text = status_map.get(self.game_state.status, self.game_state.status.upper())
        self.game_status_label.config(text=f"Game Status: {status_text}")
        self.game_duration_label.config(text=f"Duration: {self.game_state.game_duration} min")
        
    def check_conversion_cycle(self):
        """Check if it's time to do health damage and conversions"""
        if self.running and self.game_state.status == 'game':
            if self.game_state.should_do_conversion():
                self.perform_conversion_cycle()
                self.game_state.mark_conversion_done()
                
        # Schedule next check
        self.root.after(5000, self.check_conversion_cycle)
        
    def perform_conversion_cycle(self):
        """Perform health damage and role conversions"""
        damage = self.health_damage_var.get()
        converted_to_zombie = 0
        converted_to_human = 0
        
        # Get current zombies and humans
        zombies = [d for d in self.devices.values() if d.role == 'zombie']
        humans = [d for d in self.devices.values() if d.role == 'human']
        
        if not zombies and not humans:
            return
            
        # Randomly select some devices to take damage
        # Humans are damaged by zombies, zombies are damaged by humans
        # The more of the opposite type, the more damage
        
        # Damage some humans (simulating zombie attacks)
        if humans and zombies:
            num_to_damage = max(1, len(humans) // 3)
            victims = random.sample(humans, min(num_to_damage, len(humans)))
            
            for device in victims:
                device.health = max(0, device.health - damage)
                if device.health <= 0:
                    device.role = 'zombie'
                    device.health = 100
                    converted_to_zombie += 1
                    
        # Damage some zombies (simulating human defense)
        if zombies and humans:
            num_to_damage = max(1, len(zombies) // 4)
            victims = random.sample(zombies, min(num_to_damage, len(zombies)))
            
            for device in victims:
                device.health = max(0, device.health - damage)
                if device.health <= 0:
                    device.role = 'human'
                    device.health = 100
                    converted_to_human += 1
                    
        # Log conversions
        if converted_to_zombie > 0 or converted_to_human > 0:
            self.log(f"⚔️ Combat: {converted_to_zombie} humans → zombies, "
                    f"{converted_to_human} zombies → humans")
            
        self.refresh_device_list()
        
    def handle_game_end(self):
        """Handle game time expiration"""
        self.game_ended_shown = True
        
        # Count final results
        zombies = sum(1 for d in self.devices.values() if d.role == 'zombie')
        humans = sum(1 for d in self.devices.values() if d.role == 'human')
        
        if zombies > humans:
            winner = "🧟 ZOMBIES WIN!"
        elif humans > zombies:
            winner = "👥 HUMANS WIN!"
        else:
            winner = "⚖️ IT'S A TIE!"
            
        self.log(f"🏁 GAME ENDED! Final: Zombies={zombies}, Humans={humans}. {winner}")
        
        messagebox.showinfo(
            "Game Ended",
            f"Time's up!\n\n"
            f"Final Results:\n"
            f"🧟 Zombies: {zombies}\n"
            f"👥 Humans: {humans}\n\n"
            f"{winner}"
        )
        
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
                
                # Determine tag based on role and health
                if device.error_count > 5:
                    tag = 'error'
                elif device.health <= 30 and device.role in ['zombie', 'human']:
                    tag = 'low_health'
                elif device.role in ['zombie', 'human', 'neutral']:
                    tag = device.role
                else:
                    tag = 'neutral'
                    
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
            
            # Determine tag based on role and health
            if device.error_count > 5:
                tag = 'error'
            elif device.health <= 30 and device.role in ['zombie', 'human']:
                tag = 'low_health'
            elif device.role in ['zombie', 'human', 'neutral']:
                tag = device.role
            else:
                tag = 'neutral'
                
            self.device_tree.insert('', 'end', values=values, tags=(tag,))
            
        self.update_stats()
        
    def update_stats(self):
        """Update statistics display"""
        zombies = sum(1 for d in self.devices.values() if d.role == 'zombie')
        humans = sum(1 for d in self.devices.values() if d.role == 'human')
        neutral = sum(1 for d in self.devices.values() if d.role == 'neutral')
        low_health = sum(1 for d in self.devices.values() 
                        if d.health <= 30 and d.role in ['zombie', 'human'])
        errors = sum(d.error_count for d in self.devices.values())
        
        self.stats_label.config(
            text=f"🧟 Zombies: {zombies} | 👥 Humans: {humans} | "
                 f"⚪ Neutral: {neutral} | ⚠️ Low HP: {low_health} | ❌ Errors: {errors}"
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
            
    def convert_to_zombie(self):
        """Convert selected devices to zombies"""
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Please select devices to convert")
            return
            
        converted = 0
        for item in selected:
            device_id = self.device_tree.item(item)['values'][0]
            device = self.devices.get(device_id)
            if device and device.role != 'zombie':
                device.role = 'zombie'
                device.health = 100
                converted += 1
                    
        self.refresh_device_list()
        self.log(f"🧟 Manually converted {converted} devices to ZOMBIE")
        
    def convert_to_human(self):
        """Convert selected devices to humans"""
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Please select devices to convert")
            return
            
        converted = 0
        for item in selected:
            device_id = self.device_tree.item(item)['values'][0]
            device = self.devices.get(device_id)
            if device and device.role != 'human':
                device.role = 'human'
                device.health = 100
                converted += 1
                    
        self.refresh_device_list()
        self.log(f"👥 Manually converted {converted} devices to HUMAN")
        
    def update_conversion_interval(self):
        """Update the conversion interval"""
        self.game_state.conversion_interval = float(self.conversion_interval_var.get())
        self.log(f"Updated conversion interval to {self.conversion_interval_var.get()}s")
        
    def update_health_damage(self):
        """Update the health damage rate"""
        self.game_state.health_damage_rate = self.health_damage_var.get()
        self.log(f"Updated health damage to {self.health_damage_var.get()}")
        
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