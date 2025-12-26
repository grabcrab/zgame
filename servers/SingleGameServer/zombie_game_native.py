
#!/usr/bin/env python3
"""
Zombie Game - Native Windows GUI Application
A monolith desktop application with native GUI that runs the ESP32 game server.
No web interface - pure Windows GUI using tkinter.
"""

# =============================================================================
# VERSION: Update this version number every time you modify this code!
# =============================================================================
VERSION = "1.3.5"

import tkinter as tk
from tkinter import ttk, messagebox, font
import json
import random
import time
import threading
import logging
import socket
import sys
import atexit
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000
LOCK_PORT = 47201  # Port used for single instance lock
DEFAULT_HUMAN_PERCENTAGE = 50
DEFAULT_GAME_TIMEOUT = 30
DEFAULT_GAME_DURATION = 15
DEFAULT_NUM_GAMERS = 16
SETTINGS_FILE = 'zombie_game_settings.json'


# ============== Single Instance Lock ==============
class SingleInstance:
    """
    Ensures only one instance of the application runs at a time.
    Uses a socket-based lock which is automatically released when the process exits.
    """
    def __init__(self, port=LOCK_PORT):
        self.port = port
        self.lock_socket = None
    
    def acquire(self):
        """
        Try to acquire the single instance lock.
        Returns True if successful, False if another instance is running.
        """
        try:
            self.lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            self.lock_socket.bind(('127.0.0.1', self.port))
            self.lock_socket.listen(1)
            # Register cleanup on exit
            atexit.register(self.release)
            return True
        except socket.error:
            # Port is already in use - another instance is running
            return False
    
    def release(self):
        """Release the single instance lock."""
        if self.lock_socket:
            try:
                self.lock_socket.close()
            except:
                pass
            self.lock_socket = None


# Flask app for API
app = Flask(__name__)
app.config['SECRET_KEY'] = 'zombie-game-secret-key'

# Game state
devices = {}
game_state = {
    'status': 'sleep',
    'human_percentage': DEFAULT_HUMAN_PERCENTAGE,
    'game_timeout': DEFAULT_GAME_TIMEOUT,
    'game_duration': DEFAULT_GAME_DURATION,
    'num_gamers': DEFAULT_NUM_GAMERS,
    'game_start_time': None,
    'countdown_end_time': None,  # When countdown ends and actual game starts
    'zombies': [],
    'humans': []
}
devices_lock = threading.Lock()


def assign_roles():
    """Assign roles to devices based on human percentage"""
    with devices_lock:
        device_list = list(devices.keys())
        if not device_list:
            return
        
        total_devices = len(device_list)
        num_humans = max(1, int(total_devices * game_state['human_percentage'] / 100))
        
        random.shuffle(device_list)
        selected_humans = device_list[:num_humans]
        
        game_state['humans'] = []
        game_state['zombies'] = []
        
        for device_id in device_list:
            if device_id in selected_humans:
                devices[device_id]['role'] = 'human'
                game_state['humans'].append(device_id)
            else:
                devices[device_id]['role'] = 'zombie'
                game_state['zombies'].append(device_id)
        
        logger.debug(f"Assigned roles: {num_humans} humans, {total_devices - num_humans} zombies")


# Flask API endpoint
@app.route('/api/device', methods=['GET'])
def device_update():
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
        if game_state['status'] == 'game' and data['role'] in ['human', 'zombie']:
            role = data['role']
            if data['id'] in game_state['humans'] and role == 'zombie':
                game_state['humans'].remove(data['id'])
                game_state['zombies'].append(data['id'])
            elif data['id'] in game_state['zombies'] and role == 'human':
                game_state['zombies'].remove(data['id'])
                game_state['humans'].append(data['id'])
        else:
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

    response = {
        'role': devices[data['id']]['role'],
        'status': game_state['status'],
        'game_timeout': game_state['game_timeout'],
        'game_duration': game_state['game_duration']
    }
    
    # Calculate remaining seconds for game_duration during countdown or game
    if game_state['status'] == 'countdown' and game_state['countdown_end_time']:
        # During countdown, return countdown seconds remaining
        countdown_remaining = (game_state['countdown_end_time'] - datetime.now()).total_seconds()
        response['game_duration'] = max(0, int(countdown_remaining))
    elif game_state['status'] == 'game' and game_state['game_start_time']:
        # During game, return game seconds remaining
        elapsed = (datetime.now() - game_state['game_start_time']).total_seconds()
        total_duration_seconds = game_state['game_duration'] * 60
        remaining = total_duration_seconds - elapsed
        response['game_duration'] = max(0, int(remaining))
    
    # When game is ended, override role with winner information
    if game_state['status'] == 'end':
        zombie_count = len(game_state['zombies'])
        human_count = len(game_state['humans'])
        if zombie_count > human_count:
            response['role'] = 'zwin'
        elif human_count > zombie_count:
            response['role'] = 'hwin'
        else:
            response['role'] = 'draw'
    
    return jsonify(response)


class FlaskThread(threading.Thread):
    """Background thread to run Flask server"""
    def __init__(self, host, port):
        super().__init__()
        self.daemon = True
        self.host = host
        self.port = port
        
    def run(self):
        logger.info(f"Starting Flask server on http://{self.host}:{self.port}")
        app.run(host=self.host, port=self.port, debug=False, use_reloader=False)


class ZombieGameApp:
    """Main GUI Application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Zombie Game - Server Control")
        self.root.geometry("1200x700")
        
        # Prevent window from being resized too small
        self.root.minsize(1000, 600)
        
        # Configure styles
        self.setup_styles()
        
        # Load saved settings
        self.load_settings()
        
        # Current screen
        self.current_screen = None
        
        # Start with main screen
        self.show_main_screen()
        
        # Setup close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def setup_styles(self):
        """Setup ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure('Title.TLabel', font=('Arial', 24, 'bold'), foreground='#2c3e50')
        style.configure('Header.TLabel', font=('Arial', 16, 'bold'), foreground='#34495e')
        style.configure('Info.TLabel', font=('Arial', 10), foreground='#7f8c8d')
        style.configure('Status.TLabel', font=('Arial', 12), foreground='#27ae60')
        style.configure('Stats.TLabel', font=('Arial', 11, 'bold'), foreground='#2c3e50')
        
        style.configure('Primary.TButton', font=('Arial', 12, 'bold'), padding=10)
        style.configure('Success.TButton', font=('Arial', 11), padding=8)
        style.configure('Danger.TButton', font=('Arial', 11), padding=8)
        style.configure('Secondary.TButton', font=('Arial', 10), padding=6)
        
        # Colored buttons for game controls
        style.configure('AddTime.TButton', font=('Arial', 11, 'bold'), padding=8, 
                       foreground='white', background='#27ae60')
        style.map('AddTime.TButton', background=[('active', '#2ecc71')])
        
        style.configure('SubtractTime.TButton', font=('Arial', 11, 'bold'), padding=8,
                       foreground='white', background='#f39c12')
        style.map('SubtractTime.TButton', background=[('active', '#f1c40f')])
        
        style.configure('EndGame.TButton', font=('Arial', 11, 'bold'), padding=8,
                       foreground='white', background='#e74c3c')
        style.map('EndGame.TButton', background=[('active', '#c0392b')])
        
    def clear_screen(self):
        """Clear current screen"""
        for widget in self.root.winfo_children():
            widget.destroy()
    
    def load_settings(self):
        """Load game settings from file"""
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                game_state['human_percentage'] = settings.get('human_percentage', DEFAULT_HUMAN_PERCENTAGE)
                game_state['game_timeout'] = settings.get('game_timeout', DEFAULT_GAME_TIMEOUT)
                game_state['game_duration'] = settings.get('game_duration', DEFAULT_GAME_DURATION)
                game_state['num_gamers'] = settings.get('num_gamers', DEFAULT_NUM_GAMERS)
                logger.info(f"Settings loaded from {SETTINGS_FILE}")
        except FileNotFoundError:
            logger.info("No settings file found, using defaults")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    
    def save_settings(self):
        """Save game settings to file"""
        try:
            settings = {
                'human_percentage': game_state['human_percentage'],
                'game_timeout': game_state['game_timeout'],
                'game_duration': game_state['game_duration'],
                'num_gamers': game_state['num_gamers']
            }
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            logger.info(f"Settings saved to {SETTINGS_FILE}")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            
    def show_main_screen(self):
        """Main/Sleep screen"""
        self.clear_screen()
        self.current_screen = 'main'
        
        # Reset game state
        with devices_lock:
            game_state['status'] = 'sleep'
            game_state['humans'] = []
            game_state['zombies'] = []
            game_state['game_start_time'] = None
            for device in devices.values():
                device['status'] = 'sleep'
                device['role'] = 'neutral'
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=50)
        main_frame.pack(expand=True, fill='both')
        
        # Title
        title = ttk.Label(main_frame, text="🧟 ZOMBIE GAME", style='Title.TLabel')
        title.pack(pady=(0, 5))
        
        # Version
        version_label = ttk.Label(main_frame, text=f"Version {VERSION}", style='Info.TLabel')
        version_label.pack(pady=(0, 25))
        
        # Server info
        local_ip = self.get_local_ip()
        info_text = f"Server Running\nLocal: 127.0.0.1:{SERVER_PORT}\nNetwork: {local_ip}:{SERVER_PORT}"
        info_label = ttk.Label(main_frame, text=info_text, style='Status.TLabel', justify='center')
        info_label.pack(pady=20)
        
        # ESP32 info
        esp_info = f"ESP32 Connection:\nhttp://{local_ip}:{SERVER_PORT}/api/device"
        esp_label = ttk.Label(main_frame, text=esp_info, style='Info.TLabel', justify='center')
        esp_label.pack(pady=10)
        
        # Enter button
        enter_btn = ttk.Button(main_frame, text="START GAME", 
                               command=self.show_prepare_screen,
                               style='Primary.TButton')
        enter_btn.pack(pady=30, ipadx=20)
        
    def show_prepare_screen(self):
        """Preparation screen"""
        self.clear_screen()
        self.current_screen = 'prepare'
        
        # Set status
        with devices_lock:
            game_state['status'] = 'prepare'
            for device in devices.values():
                device['status'] = 'prepare'
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(expand=True, fill='both')
        
        # Title row with Back button on right
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill='x', pady=(0, 10))
        
        # Empty label for left side balance
        ttk.Label(title_frame, text="").pack(side='left', expand=True)
        
        # Title (centered)
        title = ttk.Label(title_frame, text="Game Preparation", style='Header.TLabel')
        title.pack(side='left')
        
        # Buttons frame on the right (Clear List and Back to Main)
        back_frame = ttk.Frame(title_frame)
        back_frame.pack(side='left', expand=True)
        # Inner frame to hold buttons on the right
        buttons_inner = ttk.Frame(back_frame)
        buttons_inner.pack(side='right')
        # Clear List button (left of Back to Main)
        ttk.Button(buttons_inner, text="Clear List", command=self.confirm_clear_list,
                  style='Secondary.TButton').pack(side='left', padx=(0, 5))
        # Back to Main button (right corner, non-bold, with confirmation)
        ttk.Button(buttons_inner, text="Back to Main", command=self.confirm_back_to_main,
                  style='Secondary.TButton').pack(side='left')
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Game Settings", padding=15)
        settings_frame.pack(fill='x', padx=20, pady=10)
        
        # Number of Players
        ttk.Label(settings_frame, text="Number of Players:").grid(row=0, column=0, sticky='w', pady=5)
        self.num_gamers_var = tk.IntVar(value=game_state['num_gamers'])
        num_gamers_spin = ttk.Spinbox(settings_frame, from_=1, to=100, textvariable=self.num_gamers_var, width=10)
        num_gamers_spin.grid(row=0, column=1, padx=10, pady=5)
        
        # Human percentage
        ttk.Label(settings_frame, text="Human Percentage (25-75%):").grid(row=1, column=0, sticky='w', pady=5)
        self.human_pct_var = tk.IntVar(value=game_state['human_percentage'])
        human_spin = ttk.Spinbox(settings_frame, from_=25, to=75, textvariable=self.human_pct_var, width=10)
        human_spin.grid(row=1, column=1, padx=10, pady=5)
        
        # Game timeout
        ttk.Label(settings_frame, text="Game Timeout (seconds):").grid(row=2, column=0, sticky='w', pady=5)
        self.timeout_var = tk.IntVar(value=game_state['game_timeout'])
        timeout_spin = ttk.Spinbox(settings_frame, from_=10, to=120, textvariable=self.timeout_var, width=10)
        timeout_spin.grid(row=2, column=1, padx=10, pady=5)
        
        # Game duration
        ttk.Label(settings_frame, text="Game Duration (minutes):").grid(row=3, column=0, sticky='w', pady=5)
        self.duration_var = tk.IntVar(value=game_state['game_duration'])
        duration_spin = ttk.Spinbox(settings_frame, from_=1, to=60, textvariable=self.duration_var, width=10)
        duration_spin.grid(row=3, column=1, padx=10, pady=5)
        
        # Add trace callbacks to save settings on every change
        self.num_gamers_var.trace_add('write', self.on_setting_changed)
        self.human_pct_var.trace_add('write', self.on_setting_changed)
        self.timeout_var.trace_add('write', self.on_setting_changed)
        self.duration_var.trace_add('write', self.on_setting_changed)
        
        # Devices frame
        devices_frame = ttk.LabelFrame(main_frame, text="Connected Devices", padding=10)
        devices_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Create treeview for devices
        columns = ('ID', 'IP', 'RSSI', 'Role', 'Status', 'Health', 'Battery', 'Comment')
        self.device_tree = ttk.Treeview(devices_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.device_tree.heading(col, text=col, command=lambda c=col: self.sort_treeview(c))
            self.device_tree.column(col, width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(devices_frame, orient='vertical', command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)
        
        self.device_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Buttons frame (centered)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        
        # Continue button (disabled until enough devices)
        self.continue_btn = ttk.Button(btn_frame, text="Waiting devices...", command=self.confirm_continue,
                  style='Success.TButton', state='disabled')
        self.continue_btn.pack()
        
        # Update devices display and button state
        self.update_device_list()
        
        # Start auto-refresh
        self.prepare_refresh_job = self.root.after(5000, self.refresh_prepare_screen)
    
    def on_setting_changed(self, *args):
        """Called when any setting is changed - saves settings immediately"""
        try:
            # Update game state with current values
            game_state['num_gamers'] = self.num_gamers_var.get()
            game_state['human_percentage'] = self.human_pct_var.get()
            game_state['game_timeout'] = self.timeout_var.get()
            game_state['game_duration'] = self.duration_var.get()
            # Save to file
            self.save_settings()
            # Update continue button (in case num_gamers changed)
            if hasattr(self, 'continue_btn'):
                self.update_continue_button()
        except tk.TclError:
            # Ignore errors during widget destruction or invalid values
            pass
    
    def confirm_back_to_main(self):
        """Confirm before going back to main screen"""
        if messagebox.askyesno("Confirm", "Are you sure you want to go back to the main screen?"):
            # Cancel prepare refresh
            if hasattr(self, 'prepare_refresh_job'):
                self.root.after_cancel(self.prepare_refresh_job)
            self.show_main_screen()
    
    def confirm_clear_list(self):
        """Confirm before clearing the device list"""
        if messagebox.askyesno("Confirm", "Are you sure you want to clear all connected devices?"):
            with devices_lock:
                devices.clear()
                game_state['humans'] = []
                game_state['zombies'] = []
            self.update_device_list()
    
    def confirm_continue(self):
        """Confirm before continuing to distribution screen"""
        if messagebox.askyesno("Confirm", "Continue to player distribution?"):
            # Cancel prepare refresh
            if hasattr(self, 'prepare_refresh_job'):
                self.root.after_cancel(self.prepare_refresh_job)
            self.show_distribution_screen()
    
    def update_continue_button(self):
        """Update Continue button state based on device count"""
        with devices_lock:
            device_count = len(devices)
        required = self.num_gamers_var.get()
        
        if device_count >= required:
            self.continue_btn.config(text="Continue", state='normal')
        else:
            self.continue_btn.config(text=f"Waiting devices... ({device_count}/{required})", state='disabled')
        
    def refresh_prepare_screen(self):
        """Refresh prepare screen data"""
        if self.current_screen == 'prepare':
            self.update_device_list()
            self.update_continue_button()
            self.prepare_refresh_job = self.root.after(5000, self.refresh_prepare_screen)
    
    def update_device_list(self):
        """Update device list in treeview"""
        # Clear existing items
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        
        # Add devices
        with devices_lock:
            sorted_devices = sorted(devices.values(), key=lambda x: x['id'])
            for device in sorted_devices:
                self.device_tree.insert('', 'end', values=(
                    device['id'],
                    device['ip'],
                    device['rssi'],
                    device['role'],
                    device['status'],
                    device['health'],
                    f"{device['battery']}%",
                    device['comment']
                ))
        
        # Update continue button state
        if hasattr(self, 'continue_btn'):
            self.update_continue_button()
    
    def sort_treeview(self, col):
        """Sort treeview by column"""
        items = [(self.device_tree.set(item, col), item) for item in self.device_tree.get_children('')]
        items.sort()
        for index, (val, item) in enumerate(items):
            self.device_tree.move(item, '', index)
    
    def show_distribution_screen(self):
        """Player distribution screen - assign zombies and humans"""
        self.clear_screen()
        self.current_screen = 'distribution'
        
        # Set status - but keep roles as neutral until Start is pressed
        with devices_lock:
            game_state['status'] = 'distribution'
            for device in devices.values():
                device['status'] = 'distribution'
                device['role'] = 'neutral'  # Keep neutral until Start is pressed
        
        # Assign initial roles based on percentage (for display purposes only, not sent to devices yet)
        self.assign_distribution_roles()
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(expand=True, fill='both')
        
        # Title (centered)
        title = ttk.Label(main_frame, text="Players Distribution", style='Header.TLabel')
        title.pack(pady=(0, 10), anchor='center')
        
        # Lists container
        lists_frame = ttk.Frame(main_frame)
        lists_frame.pack(fill='both', expand=True, pady=10)
        
        # Configure grid weights for equal distribution
        lists_frame.columnconfigure(0, weight=1)
        lists_frame.columnconfigure(1, weight=0)
        lists_frame.columnconfigure(2, weight=1)
        lists_frame.rowconfigure(0, weight=1)
        
        # Zombies list (left side)
        zombies_frame = ttk.LabelFrame(lists_frame, text="Zombies", padding=10)
        zombies_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        columns = ('ID', 'Comment')
        self.dist_zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=15)
        self.dist_zombies_tree.heading('ID', text='ID')
        self.dist_zombies_tree.heading('Comment', text='Comment')
        self.dist_zombies_tree.column('ID', width=150)
        self.dist_zombies_tree.column('Comment', width=150)
        
        zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=self.dist_zombies_tree.yview)
        self.dist_zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
        self.dist_zombies_tree.pack(side='left', fill='both', expand=True)
        zombies_scroll.pack(side='right', fill='y')
        
        # Middle buttons frame
        middle_frame = ttk.Frame(lists_frame)
        middle_frame.grid(row=0, column=1, padx=10)
        
        # Move to Humans button (right arrow)
        ttk.Button(middle_frame, text="→\nTo Human", command=self.move_to_human,
                  style='Secondary.TButton').pack(pady=5)
        
        # Move to Zombies button (left arrow)
        ttk.Button(middle_frame, text="←\nTo Zombie", command=self.move_to_zombie,
                  style='Secondary.TButton').pack(pady=5)
        
        # Humans list (right side)
        humans_frame = ttk.LabelFrame(lists_frame, text="Humans", padding=10)
        humans_frame.grid(row=0, column=2, sticky='nsew', padx=(5, 0))
        
        self.dist_humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=15)
        self.dist_humans_tree.heading('ID', text='ID')
        self.dist_humans_tree.heading('Comment', text='Comment')
        self.dist_humans_tree.column('ID', width=150)
        self.dist_humans_tree.column('Comment', width=150)
        
        humans_scroll = ttk.Scrollbar(humans_frame, orient='vertical', command=self.dist_humans_tree.yview)
        self.dist_humans_tree.configure(yscrollcommand=humans_scroll.set)
        
        self.dist_humans_tree.pack(side='left', fill='both', expand=True)
        humans_scroll.pack(side='right', fill='y')
        
        # Populate the lists
        self.update_distribution_lists()
        
        # Buttons frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=10)
        
        # Back button (left side)
        ttk.Button(btn_frame, text="Back", command=self.confirm_back_to_prepare,
                  style='Secondary.TButton').pack(side='left')
        
        # Start button (center)
        ttk.Button(btn_frame, text="Start!", command=self.confirm_start_game,
                  style='Primary.TButton').pack(expand=True)
    
    def update_distribution_lists(self):
        """Update the distribution lists with current assignments"""
        # Clear existing items
        for item in self.dist_zombies_tree.get_children():
            self.dist_zombies_tree.delete(item)
        for item in self.dist_humans_tree.get_children():
            self.dist_humans_tree.delete(item)
        
        # Populate lists (sorted by ID)
        with devices_lock:
            # Sort zombies by ID
            sorted_zombies = sorted(game_state['zombies'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
            for dev_id in sorted_zombies:
                if dev_id in devices:
                    device = devices[dev_id]
                    self.dist_zombies_tree.insert('', 'end', iid=dev_id, values=(
                        device['id'],
                        device['comment']
                    ))
            
            # Sort humans by ID
            sorted_humans = sorted(game_state['humans'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
            for dev_id in sorted_humans:
                if dev_id in devices:
                    device = devices[dev_id]
                    self.dist_humans_tree.insert('', 'end', iid=dev_id, values=(
                        device['id'],
                        device['comment']
                    ))
    
    def move_to_human(self):
        """Move selected zombie to humans list"""
        selected = self.dist_zombies_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a player from the Zombies list.")
            return
        
        # Check if this would empty the Zombies list
        with devices_lock:
            if len(game_state['zombies']) <= len(selected):
                messagebox.showerror("Cannot Move", "Cannot move all players. There must be at least one Zombie.")
                return
            
            for dev_id in selected:
                if dev_id in game_state['zombies']:
                    game_state['zombies'].remove(dev_id)
                    game_state['humans'].append(dev_id)
                    # Don't change device role yet - keep neutral until Start is pressed
        
        self.update_distribution_lists()
    
    def move_to_zombie(self):
        """Move selected human to zombies list"""
        selected = self.dist_humans_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a player from the Humans list.")
            return
        
        # Check if this would empty the Humans list
        with devices_lock:
            if len(game_state['humans']) <= len(selected):
                messagebox.showerror("Cannot Move", "Cannot move all players. There must be at least one Human.")
                return
            
            for dev_id in selected:
                if dev_id in game_state['humans']:
                    game_state['humans'].remove(dev_id)
                    game_state['zombies'].append(dev_id)
                    # Don't change device role yet - keep neutral until Start is pressed
        
        self.update_distribution_lists()
    
    def confirm_back_to_prepare(self):
        """Confirm before going back to preparation screen"""
        if messagebox.askyesno("Confirm", "Go back to preparation screen? Current distribution will be lost."):
            self.show_prepare_screen()
    
    def assign_distribution_roles(self):
        """Assign roles for distribution display only (devices stay neutral until Start)"""
        with devices_lock:
            device_list = list(devices.keys())
            if not device_list:
                return
            
            total_devices = len(device_list)
            num_humans = max(1, int(total_devices * game_state['human_percentage'] / 100))
            
            random.shuffle(device_list)
            selected_humans = device_list[:num_humans]
            
            game_state['humans'] = []
            game_state['zombies'] = []
            
            for device_id in device_list:
                if device_id in selected_humans:
                    game_state['humans'].append(device_id)
                else:
                    game_state['zombies'].append(device_id)
                # Note: device['role'] stays 'neutral' - not changed here
    
    def confirm_start_game(self):
        """Confirm before starting the game"""
        if messagebox.askyesno("Confirm", "Start the game with current distribution?"):
            self.start_game()
    
    def start_game(self):
        """Start the game"""
        # Cancel prepare refresh if still active
        if hasattr(self, 'prepare_refresh_job'):
            self.root.after_cancel(self.prepare_refresh_job)
        
        # NOW assign the actual roles to devices (they were neutral until this point)
        with devices_lock:
            for dev_id in game_state['humans']:
                if dev_id in devices:
                    devices[dev_id]['role'] = 'human'
            for dev_id in game_state['zombies']:
                if dev_id in devices:
                    devices[dev_id]['role'] = 'zombie'
        
        # Show game screen
        self.show_game_screen()
    
    def show_game_screen(self):
        """Game in progress screen"""
        self.clear_screen()
        self.current_screen = 'game'
        
        # Set game state - start with countdown phase
        with devices_lock:
            game_state['status'] = 'countdown'
            game_state['countdown_end_time'] = datetime.now() + timedelta(seconds=game_state['game_timeout'])
            game_state['game_start_time'] = None  # Will be set when countdown ends
            
            for device in devices.values():
                device['status'] = 'countdown'
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(expand=True, fill='both')
        
        # Title and timer frame
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill='x', pady=(0, 10))
        
        self.game_title_label = ttk.Label(header_frame, text="Countdown", style='Header.TLabel')
        self.game_title_label.pack(side='left')
        
        self.timer_label = ttk.Label(header_frame, text="00:00:00", style='Title.TLabel')
        self.timer_label.pack(side='right')
        
        # Statistics frame
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill='x', pady=(0, 10))
        
        # Zombies stats (left)
        self.zombies_stats_label = ttk.Label(stats_frame, text="Zombies: 0 players, Total Health: 0", style='Stats.TLabel')
        self.zombies_stats_label.pack(side='left', padx=20)
        
        # Humans stats (right)
        self.humans_stats_label = ttk.Label(stats_frame, text="Humans: 0 players, Total Health: 0", style='Stats.TLabel')
        self.humans_stats_label.pack(side='right', padx=20)
        
        # Lists container (side by side)
        lists_frame = ttk.Frame(main_frame)
        lists_frame.pack(fill='both', expand=True, pady=10)
        
        # Configure grid weights for equal distribution
        lists_frame.columnconfigure(0, weight=1)
        lists_frame.columnconfigure(1, weight=1)
        lists_frame.rowconfigure(0, weight=1)
        
        # Zombies list (left side)
        zombies_frame = ttk.LabelFrame(lists_frame, text="Zombies", padding=10)
        zombies_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        columns = ('ID', 'Health', 'Battery', 'RSSI', 'Comment')
        self.zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=15)
        
        # Set column headings and widths
        self.zombies_tree.heading('ID', text='ID')
        self.zombies_tree.heading('Health', text='Health')
        self.zombies_tree.heading('Battery', text='Battery')
        self.zombies_tree.heading('RSSI', text='RSSI')
        self.zombies_tree.heading('Comment', text='Comment')
        
        self.zombies_tree.column('ID', width=150, minwidth=100)
        self.zombies_tree.column('Health', width=60, minwidth=50)
        self.zombies_tree.column('Battery', width=60, minwidth=50)
        self.zombies_tree.column('RSSI', width=50, minwidth=40)
        self.zombies_tree.column('Comment', width=150, minwidth=100)
        
        zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=self.zombies_tree.yview)
        self.zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
        self.zombies_tree.pack(side='left', fill='both', expand=True)
        zombies_scroll.pack(side='right', fill='y')
        
        # Humans list (right side)
        humans_frame = ttk.LabelFrame(lists_frame, text="Humans", padding=10)
        humans_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        self.humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=15)
        
        # Set column headings and widths
        self.humans_tree.heading('ID', text='ID')
        self.humans_tree.heading('Health', text='Health')
        self.humans_tree.heading('Battery', text='Battery')
        self.humans_tree.heading('RSSI', text='RSSI')
        self.humans_tree.heading('Comment', text='Comment')
        
        self.humans_tree.column('ID', width=150, minwidth=100)
        self.humans_tree.column('Health', width=60, minwidth=50)
        self.humans_tree.column('Battery', width=60, minwidth=50)
        self.humans_tree.column('RSSI', width=50, minwidth=40)
        self.humans_tree.column('Comment', width=150, minwidth=100)
        
        humans_scroll = ttk.Scrollbar(humans_frame, orient='vertical', command=self.humans_tree.yview)
        self.humans_tree.configure(yscrollcommand=humans_scroll.set)
        
        self.humans_tree.pack(side='left', fill='both', expand=True)
        humans_scroll.pack(side='right', fill='y')
        
        # Update team lists
        self.update_game_teams()
        
        # Start timer and auto-refresh
        self.update_timer()
        self.game_refresh_job = self.root.after(5000, self.refresh_game_screen)
        
        # Buttons frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="-1 Minute", command=self.confirm_subtract_minute,
                  style='SubtractTime.TButton').pack(side='left', padx=10)
        ttk.Button(btn_frame, text="+1 Minute", command=self.confirm_add_minute,
                  style='AddTime.TButton').pack(side='left', padx=10)
        ttk.Button(btn_frame, text="End Game", command=self.confirm_end_game,
                  style='EndGame.TButton').pack(side='left', padx=10)
    
    def update_game_teams(self):
        """Update zombies and humans lists with statistics"""
        # Clear existing items
        for item in self.zombies_tree.get_children():
            self.zombies_tree.delete(item)
        for item in self.humans_tree.get_children():
            self.humans_tree.delete(item)
        
        # Track statistics
        zombie_count = 0
        zombie_total_health = 0
        human_count = 0
        human_total_health = 0
        
        # Add devices to respective teams (sorted by ID)
        with devices_lock:
            # Sort and add zombies
            sorted_zombies = sorted(game_state['zombies'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
            for dev_id in sorted_zombies:
                if dev_id in devices:
                    device = devices[dev_id]
                    self.zombies_tree.insert('', 'end', values=(
                        device['id'],
                        device['health'],
                        f"{device['battery']}%",
                        device['rssi'],
                        device['comment']
                    ))
                    zombie_count += 1
                    try:
                        zombie_total_health += int(device['health'])
                    except (ValueError, TypeError):
                        pass
            
            # Sort and add humans
            sorted_humans = sorted(game_state['humans'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
            for dev_id in sorted_humans:
                if dev_id in devices:
                    device = devices[dev_id]
                    self.humans_tree.insert('', 'end', values=(
                        device['id'],
                        device['health'],
                        f"{device['battery']}%",
                        device['rssi'],
                        device['comment']
                    ))
                    human_count += 1
                    try:
                        human_total_health += int(device['health'])
                    except (ValueError, TypeError):
                        pass
        
        # Update statistics labels
        if hasattr(self, 'zombies_stats_label'):
            self.zombies_stats_label.config(text=f"Zombies: {zombie_count} players, Total Health: {zombie_total_health}")
        if hasattr(self, 'humans_stats_label'):
            self.humans_stats_label.config(text=f"Humans: {human_count} players, Total Health: {human_total_health}")
    
    def update_timer(self):
        """Update game timer - handles both countdown and game phases"""
        if self.current_screen != 'game':
            return
            
        with devices_lock:
            status = game_state['status']
            countdown_end = game_state['countdown_end_time']
            game_start = game_state['game_start_time']
            duration_minutes = game_state['game_duration']
        
        if status == 'countdown' and countdown_end:
            # Countdown phase
            remaining = (countdown_end - datetime.now()).total_seconds()
            
            if remaining > 0:
                # Still counting down
                minutes, seconds = divmod(int(remaining), 60)
                self.timer_label.config(text=f"00:{minutes:02d}:{seconds:02d}")
                self.root.after(1000, self.update_timer)
            else:
                # Countdown finished - start the actual game
                self.timer_label.config(text="00:00:00")
                with devices_lock:
                    game_state['status'] = 'game'
                    game_state['game_start_time'] = datetime.now()
                    for device in devices.values():
                        device['status'] = 'game'
                
                # Update title to show game in progress
                if hasattr(self, 'game_title_label'):
                    self.game_title_label.config(text="Game In Progress")
                
                # Continue with game timer
                self.root.after(1000, self.update_timer)
                
        elif status == 'game' and game_start:
            # Game phase
            elapsed = datetime.now() - game_start
            duration = timedelta(minutes=duration_minutes)
            remaining = duration - elapsed
            
            if remaining.total_seconds() > 0:
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.timer_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                self.root.after(1000, self.update_timer)
            else:
                self.timer_label.config(text="00:00:00")
                # Time is up - end the game
                self.end_game_time_up()
    
    def refresh_game_screen(self):
        """Refresh game screen data"""
        if self.current_screen == 'game':
            self.update_game_teams()
            
            # Only check for win conditions during actual game (not countdown)
            if game_state['status'] == 'game':
                with devices_lock:
                    zombie_count = len(game_state['zombies'])
                    human_count = len(game_state['humans'])
                
                if zombie_count == 0:
                    # All zombies eliminated - humans win
                    self.end_game_team_won("Humans")
                    return
                elif human_count == 0:
                    # All humans converted - zombies win
                    self.end_game_team_won("Zombies")
                    return
            
            self.game_refresh_job = self.root.after(5000, self.refresh_game_screen)
    
    def end_game_time_up(self):
        """End game due to time running out"""
        # Cancel game refresh
        if hasattr(self, 'game_refresh_job'):
            self.root.after_cancel(self.game_refresh_job)
        
        # Set end status BEFORE showing notification (so devices get winner info immediately)
        with devices_lock:
            game_state['status'] = 'end'
            for device in devices.values():
                device['status'] = 'end'
            zombie_count = len(game_state['zombies'])
            human_count = len(game_state['humans'])
        
        # Determine winner message
        if zombie_count > human_count:
            result = "Time's up!\n\n🧟 Zombies won! 🧟"
        elif human_count > zombie_count:
            result = "Time's up!\n\n👥 Humans won! 👥"
        else:
            result = "Time's up!\n\n⚖️ It's a tie! ⚖️"
        
        messagebox.showinfo("Game Over", result)
        self.show_end_screen()
    
    def end_game_team_won(self, winning_team):
        """End game due to one team winning"""
        # Cancel game refresh
        if hasattr(self, 'game_refresh_job'):
            self.root.after_cancel(self.game_refresh_job)
        
        # Set end status BEFORE showing notification (so devices get winner info immediately)
        with devices_lock:
            game_state['status'] = 'end'
            for device in devices.values():
                device['status'] = 'end'
        
        if winning_team == "Zombies":
            result = "🧟 Zombies won! 🧟\n\nAll humans have been converted!"
        else:
            result = "👥 Humans won! 👥\n\nAll zombies have been eliminated!"
        
        messagebox.showinfo("Game Over", result)
        self.show_end_screen()
    
    def confirm_add_minute(self):
        """Confirm before adding a minute"""
        if messagebox.askyesno("Confirm", "Add 1 minute to game time?"):
            self.add_minute()
    
    def confirm_subtract_minute(self):
        """Confirm before subtracting a minute"""
        if messagebox.askyesno("Confirm", "Subtract 1 minute from game time?"):
            self.subtract_minute()
    
    def add_minute(self):
        """Add one minute to game duration"""
        with devices_lock:
            game_state['game_duration'] += 1
        logger.info("Added 1 minute to game duration")
    
    def subtract_minute(self):
        """Subtract one minute from game duration"""
        with devices_lock:
            if game_state['game_duration'] > 1:
                game_state['game_duration'] -= 1
                logger.info("Subtracted 1 minute from game duration")
            else:
                logger.warning("Cannot subtract minute - duration already at minimum")
    
    def confirm_end_game(self):
        """Double confirm and end game"""
        if messagebox.askyesno("End Game", "Are you sure you want to end the game?"):
            # Second confirmation
            if messagebox.askyesno("Confirm End Game", "This action cannot be undone.\n\nAre you REALLY sure you want to end the game?"):
                # Cancel game refresh
                if hasattr(self, 'game_refresh_job'):
                    self.root.after_cancel(self.game_refresh_job)
                
                # Set end status BEFORE showing end screen (so devices get winner info immediately)
                with devices_lock:
                    game_state['status'] = 'end'
                    for device in devices.values():
                        device['status'] = 'end'
                
                self.show_end_screen()
    
    def show_end_screen(self):
        """Game end screen"""
        self.clear_screen()
        self.current_screen = 'end'
        
        # Status is already set to 'end' before this method is called
        # (in end_game_time_up, end_game_team_won, or confirm_end_game)
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(expand=True, fill='both')
        
        # Title (centered)
        title = ttk.Label(main_frame, text="Game Ended", style='Header.TLabel')
        title.pack(pady=(0, 10), anchor='center')
        
        # Winner announcement
        with devices_lock:
            zombie_count = len(game_state['zombies'])
            human_count = len(game_state['humans'])
        
        if zombie_count > human_count:
            winner = "🧟 ZOMBIES WIN! 🧟"
        elif human_count > zombie_count:
            winner = "👥 HUMANS WIN! 👥"
        else:
            winner = "⚖️ TIE! ⚖️"
        
        winner_label = ttk.Label(main_frame, text=winner, style='Title.TLabel')
        winner_label.pack(pady=(0, 10), anchor='center')
        
        # Statistics frame
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill='x', pady=(0, 10))
        
        # Calculate total health
        zombie_total_health = 0
        human_total_health = 0
        with devices_lock:
            for dev_id in game_state['zombies']:
                if dev_id in devices:
                    try:
                        zombie_total_health += int(devices[dev_id]['health'])
                    except (ValueError, TypeError):
                        pass
            for dev_id in game_state['humans']:
                if dev_id in devices:
                    try:
                        human_total_health += int(devices[dev_id]['health'])
                    except (ValueError, TypeError):
                        pass
        
        # Zombies stats (left)
        zombies_stats_label = ttk.Label(stats_frame, 
            text=f"Zombies: {zombie_count} players, Total Health: {zombie_total_health}", 
            style='Stats.TLabel')
        zombies_stats_label.pack(side='left', padx=20)
        
        # Humans stats (right)
        humans_stats_label = ttk.Label(stats_frame, 
            text=f"Humans: {human_count} players, Total Health: {human_total_health}", 
            style='Stats.TLabel')
        humans_stats_label.pack(side='right', padx=20)
        
        # Lists container (side by side)
        lists_frame = ttk.Frame(main_frame)
        lists_frame.pack(fill='both', expand=True, pady=10)
        
        # Configure grid weights for equal distribution
        lists_frame.columnconfigure(0, weight=1)
        lists_frame.columnconfigure(1, weight=1)
        lists_frame.rowconfigure(0, weight=1)
        
        # Zombies list (left side)
        zombies_frame = ttk.LabelFrame(lists_frame, text="Zombies", padding=10)
        zombies_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
        columns = ('ID', 'Health', 'Battery', 'RSSI', 'Comment')
        zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=12)
        
        # Set column headings and widths
        zombies_tree.heading('ID', text='ID')
        zombies_tree.heading('Health', text='Health')
        zombies_tree.heading('Battery', text='Battery')
        zombies_tree.heading('RSSI', text='RSSI')
        zombies_tree.heading('Comment', text='Comment')
        
        zombies_tree.column('ID', width=150, minwidth=100)
        zombies_tree.column('Health', width=60, minwidth=50)
        zombies_tree.column('Battery', width=60, minwidth=50)
        zombies_tree.column('RSSI', width=50, minwidth=40)
        zombies_tree.column('Comment', width=150, minwidth=100)
        
        zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=zombies_tree.yview)
        zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
        zombies_tree.pack(side='left', fill='both', expand=True)
        zombies_scroll.pack(side='right', fill='y')
        
        # Humans list (right side)
        humans_frame = ttk.LabelFrame(lists_frame, text="Humans", padding=10)
        humans_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=12)
        
        # Set column headings and widths
        humans_tree.heading('ID', text='ID')
        humans_tree.heading('Health', text='Health')
        humans_tree.heading('Battery', text='Battery')
        humans_tree.heading('RSSI', text='RSSI')
        humans_tree.heading('Comment', text='Comment')
        
        humans_tree.column('ID', width=150, minwidth=100)
        humans_tree.column('Health', width=60, minwidth=50)
        humans_tree.column('Battery', width=60, minwidth=50)
        humans_tree.column('RSSI', width=50, minwidth=40)
        humans_tree.column('Comment', width=150, minwidth=100)
        
        humans_scroll = ttk.Scrollbar(humans_frame, orient='vertical', command=humans_tree.yview)
        humans_tree.configure(yscrollcommand=humans_scroll.set)
        
        humans_tree.pack(side='left', fill='both', expand=True)
        humans_scroll.pack(side='right', fill='y')
        
        # Populate final team lists (sorted by ID)
        with devices_lock:
            sorted_zombies = sorted(game_state['zombies'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
            for dev_id in sorted_zombies:
                if dev_id in devices:
                    device = devices[dev_id]
                    zombies_tree.insert('', 'end', values=(
                        device['id'],
                        device['health'],
                        f"{device['battery']}%",
                        device['rssi'],
                        device['comment']
                    ))
            
            sorted_humans = sorted(game_state['humans'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
            for dev_id in sorted_humans:
                if dev_id in devices:
                    device = devices[dev_id]
                    humans_tree.insert('', 'end', values=(
                        device['id'],
                        device['health'],
                        f"{device['battery']}%",
                        device['rssi'],
                        device['comment']
                    ))
        
        # Finish button (centered)
        ttk.Button(main_frame, text="Finish and Return to Main", 
                  command=self.confirm_finish,
                  style='Primary.TButton').pack(pady=20, anchor='center')
    
    def confirm_finish(self):
        """Confirm and return to main screen"""
        if messagebox.askyesno("Finish", "Return to main screen?"):
            self.show_main_screen()
    
    def get_local_ip(self):
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "127.0.0.1"
    
    def on_closing(self):
        """Handle window close"""
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.root.destroy()


def main():
    """Main application entry point"""
    # Check for single instance
    instance_lock = SingleInstance()
    
    if not instance_lock.acquire():
        # Another instance is already running
        # Show error message
        try:
            temp_root = tk.Tk()
            temp_root.withdraw()
            messagebox.showwarning(
                "Already Running",
                "Zombie Game Server is already running.\n\n"
                "Check your system tray or taskbar for the existing instance."
            )
            temp_root.destroy()
        except:
            print("Error: Zombie Game Server is already running.")
        
        sys.exit(1)
    
    # Start Flask server in background
    flask_thread = FlaskThread(SERVER_HOST, SERVER_PORT)
    flask_thread.start()
    
    # Give Flask a moment to start
    time.sleep(1)
    
    # Get local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"
    
    print("=" * 70)
    print("🎮 ZOMBIE GAME - Native GUI Application")
    print("=" * 70)
    print(f"\n✓ Server running on: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"✓ Local IP: {local_ip}")
    print(f"✓ ESP32 endpoint: http://{local_ip}:{SERVER_PORT}/api/device")
    print("\n" + "=" * 70)
    print("GUI window will open now...")
    print("=" * 70)
    print()
    
    # Create and run GUI
    root = tk.Tk()
    app = ZombieGameApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()

# #!/usr/bin/env python3
# """
# Zombie Game - Native Windows GUI Application
# A monolith desktop application with native GUI that runs the ESP32 game server.
# No web interface - pure Windows GUI using tkinter.
# """

# # =============================================================================
# # VERSION: Update this version number every time you modify this code!
# # =============================================================================
# VERSION = "1.3.4"

# import tkinter as tk
# from tkinter import ttk, messagebox, font
# import json
# import random
# import time
# import threading
# import logging
# import socket
# import sys
# import atexit
# from datetime import datetime, timedelta
# from flask import Flask, request, jsonify

# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
# logger = logging.getLogger(__name__)

# # Configuration
# SERVER_HOST = '0.0.0.0'
# SERVER_PORT = 5000
# LOCK_PORT = 47201  # Port used for single instance lock
# DEFAULT_HUMAN_PERCENTAGE = 50
# DEFAULT_GAME_TIMEOUT = 30
# DEFAULT_GAME_DURATION = 15
# DEFAULT_NUM_GAMERS = 16
# SETTINGS_FILE = 'zombie_game_settings.json'


# # ============== Single Instance Lock ==============
# class SingleInstance:
#     """
#     Ensures only one instance of the application runs at a time.
#     Uses a socket-based lock which is automatically released when the process exits.
#     """
#     def __init__(self, port=LOCK_PORT):
#         self.port = port
#         self.lock_socket = None
    
#     def acquire(self):
#         """
#         Try to acquire the single instance lock.
#         Returns True if successful, False if another instance is running.
#         """
#         try:
#             self.lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             self.lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
#             self.lock_socket.bind(('127.0.0.1', self.port))
#             self.lock_socket.listen(1)
#             # Register cleanup on exit
#             atexit.register(self.release)
#             return True
#         except socket.error:
#             # Port is already in use - another instance is running
#             return False
    
#     def release(self):
#         """Release the single instance lock."""
#         if self.lock_socket:
#             try:
#                 self.lock_socket.close()
#             except:
#                 pass
#             self.lock_socket = None


# # Flask app for API
# app = Flask(__name__)
# app.config['SECRET_KEY'] = 'zombie-game-secret-key'

# # Game state
# devices = {}
# game_state = {
#     'status': 'sleep',
#     'human_percentage': DEFAULT_HUMAN_PERCENTAGE,
#     'game_timeout': DEFAULT_GAME_TIMEOUT,
#     'game_duration': DEFAULT_GAME_DURATION,
#     'num_gamers': DEFAULT_NUM_GAMERS,
#     'game_start_time': None,
#     'zombies': [],
#     'humans': []
# }
# devices_lock = threading.Lock()


# def assign_roles():
#     """Assign roles to devices based on human percentage"""
#     with devices_lock:
#         device_list = list(devices.keys())
#         if not device_list:
#             return
        
#         total_devices = len(device_list)
#         num_humans = max(1, int(total_devices * game_state['human_percentage'] / 100))
        
#         random.shuffle(device_list)
#         selected_humans = device_list[:num_humans]
        
#         game_state['humans'] = []
#         game_state['zombies'] = []
        
#         for device_id in device_list:
#             if device_id in selected_humans:
#                 devices[device_id]['role'] = 'human'
#                 game_state['humans'].append(device_id)
#             else:
#                 devices[device_id]['role'] = 'zombie'
#                 game_state['zombies'].append(device_id)
        
#         logger.debug(f"Assigned roles: {num_humans} humans, {total_devices - num_humans} zombies")


# # Flask API endpoint
# @app.route('/api/device', methods=['GET'])
# def device_update():
#     data_str = request.args.get('data')
#     if not data_str:
#         return jsonify({'error': 'No data provided'}), 400

#     try:
#         data = json.loads(data_str)
#     except json.JSONDecodeError:
#         return jsonify({'error': 'Invalid JSON format'}), 400

#     if not all(key in data for key in ['id', 'ip', 'rssi', 'role', 'status', 'health', 'battery', 'comment']):
#         return jsonify({'error': 'Missing required fields'}), 400

#     with devices_lock:
#         if game_state['status'] == 'game' and data['role'] in ['human', 'zombie']:
#             role = data['role']
#             if data['id'] in game_state['humans'] and role == 'zombie':
#                 game_state['humans'].remove(data['id'])
#                 game_state['zombies'].append(data['id'])
#             elif data['id'] in game_state['zombies'] and role == 'human':
#                 game_state['zombies'].remove(data['id'])
#                 game_state['humans'].append(data['id'])
#         else:
#             if game_state['status'] == 'sleep':
#                 role = 'neutral'
#             else:
#                 role = devices.get(data['id'], {}).get('role', 'neutral')

#         devices[data['id']] = {
#             'id': data['id'],
#             'ip': data['ip'],
#             'rssi': data['rssi'],
#             'role': role,
#             'status': data['status'],
#             'health': data['health'],
#             'battery': data['battery'],
#             'comment': data['comment'],
#             'last_updated': time.time()
#         }

#     response = {
#         'role': devices[data['id']]['role'],
#         'status': game_state['status'],
#         'game_timeout': game_state['game_timeout'],
#         'game_duration': game_state['game_duration']
#     }
    
#     # When game is ended, override role with winner information
#     if game_state['status'] == 'end':
#         zombie_count = len(game_state['zombies'])
#         human_count = len(game_state['humans'])
#         if zombie_count > human_count:
#             response['role'] = 'zwin'
#         elif human_count > zombie_count:
#             response['role'] = 'hwin'
#         else:
#             response['role'] = 'draw'
    
#     return jsonify(response)


# class FlaskThread(threading.Thread):
#     """Background thread to run Flask server"""
#     def __init__(self, host, port):
#         super().__init__()
#         self.daemon = True
#         self.host = host
#         self.port = port
        
#     def run(self):
#         logger.info(f"Starting Flask server on http://{self.host}:{self.port}")
#         app.run(host=self.host, port=self.port, debug=False, use_reloader=False)


# class ZombieGameApp:
#     """Main GUI Application"""
    
#     def __init__(self, root):
#         self.root = root
#         self.root.title("Zombie Game - Server Control")
#         self.root.geometry("1200x700")
        
#         # Prevent window from being resized too small
#         self.root.minsize(1000, 600)
        
#         # Configure styles
#         self.setup_styles()
        
#         # Load saved settings
#         self.load_settings()
        
#         # Current screen
#         self.current_screen = None
        
#         # Start with main screen
#         self.show_main_screen()
        
#         # Setup close handler
#         self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
#     def setup_styles(self):
#         """Setup ttk styles"""
#         style = ttk.Style()
#         style.theme_use('clam')
        
#         # Configure colors
#         style.configure('Title.TLabel', font=('Arial', 24, 'bold'), foreground='#2c3e50')
#         style.configure('Header.TLabel', font=('Arial', 16, 'bold'), foreground='#34495e')
#         style.configure('Info.TLabel', font=('Arial', 10), foreground='#7f8c8d')
#         style.configure('Status.TLabel', font=('Arial', 12), foreground='#27ae60')
#         style.configure('Stats.TLabel', font=('Arial', 11, 'bold'), foreground='#2c3e50')
        
#         style.configure('Primary.TButton', font=('Arial', 12, 'bold'), padding=10)
#         style.configure('Success.TButton', font=('Arial', 11), padding=8)
#         style.configure('Danger.TButton', font=('Arial', 11), padding=8)
#         style.configure('Secondary.TButton', font=('Arial', 10), padding=6)
        
#         # Colored buttons for game controls
#         style.configure('AddTime.TButton', font=('Arial', 11, 'bold'), padding=8, 
#                        foreground='white', background='#27ae60')
#         style.map('AddTime.TButton', background=[('active', '#2ecc71')])
        
#         style.configure('SubtractTime.TButton', font=('Arial', 11, 'bold'), padding=8,
#                        foreground='white', background='#f39c12')
#         style.map('SubtractTime.TButton', background=[('active', '#f1c40f')])
        
#         style.configure('EndGame.TButton', font=('Arial', 11, 'bold'), padding=8,
#                        foreground='white', background='#e74c3c')
#         style.map('EndGame.TButton', background=[('active', '#c0392b')])
        
#     def clear_screen(self):
#         """Clear current screen"""
#         for widget in self.root.winfo_children():
#             widget.destroy()
    
#     def load_settings(self):
#         """Load game settings from file"""
#         try:
#             with open(SETTINGS_FILE, 'r') as f:
#                 settings = json.load(f)
#                 game_state['human_percentage'] = settings.get('human_percentage', DEFAULT_HUMAN_PERCENTAGE)
#                 game_state['game_timeout'] = settings.get('game_timeout', DEFAULT_GAME_TIMEOUT)
#                 game_state['game_duration'] = settings.get('game_duration', DEFAULT_GAME_DURATION)
#                 game_state['num_gamers'] = settings.get('num_gamers', DEFAULT_NUM_GAMERS)
#                 logger.info(f"Settings loaded from {SETTINGS_FILE}")
#         except FileNotFoundError:
#             logger.info("No settings file found, using defaults")
#         except Exception as e:
#             logger.error(f"Error loading settings: {e}")
    
#     def save_settings(self):
#         """Save game settings to file"""
#         try:
#             settings = {
#                 'human_percentage': game_state['human_percentage'],
#                 'game_timeout': game_state['game_timeout'],
#                 'game_duration': game_state['game_duration'],
#                 'num_gamers': game_state['num_gamers']
#             }
#             with open(SETTINGS_FILE, 'w') as f:
#                 json.dump(settings, f, indent=2)
#             logger.info(f"Settings saved to {SETTINGS_FILE}")
#         except Exception as e:
#             logger.error(f"Error saving settings: {e}")
            
#     def show_main_screen(self):
#         """Main/Sleep screen"""
#         self.clear_screen()
#         self.current_screen = 'main'
        
#         # Reset game state
#         with devices_lock:
#             game_state['status'] = 'sleep'
#             game_state['humans'] = []
#             game_state['zombies'] = []
#             game_state['game_start_time'] = None
#             for device in devices.values():
#                 device['status'] = 'sleep'
#                 device['role'] = 'neutral'
        
#         # Main container
#         main_frame = ttk.Frame(self.root, padding=50)
#         main_frame.pack(expand=True, fill='both')
        
#         # Title
#         title = ttk.Label(main_frame, text="🧟 ZOMBIE GAME", style='Title.TLabel')
#         title.pack(pady=(0, 5))
        
#         # Version
#         version_label = ttk.Label(main_frame, text=f"Version {VERSION}", style='Info.TLabel')
#         version_label.pack(pady=(0, 25))
        
#         # Server info
#         local_ip = self.get_local_ip()
#         info_text = f"Server Running\nLocal: 127.0.0.1:{SERVER_PORT}\nNetwork: {local_ip}:{SERVER_PORT}"
#         info_label = ttk.Label(main_frame, text=info_text, style='Status.TLabel', justify='center')
#         info_label.pack(pady=20)
        
#         # ESP32 info
#         esp_info = f"ESP32 Connection:\nhttp://{local_ip}:{SERVER_PORT}/api/device"
#         esp_label = ttk.Label(main_frame, text=esp_info, style='Info.TLabel', justify='center')
#         esp_label.pack(pady=10)
        
#         # Enter button
#         enter_btn = ttk.Button(main_frame, text="START GAME", 
#                                command=self.show_prepare_screen,
#                                style='Primary.TButton')
#         enter_btn.pack(pady=30, ipadx=20)
        
#     def show_prepare_screen(self):
#         """Preparation screen"""
#         self.clear_screen()
#         self.current_screen = 'prepare'
        
#         # Set status
#         with devices_lock:
#             game_state['status'] = 'prepare'
#             for device in devices.values():
#                 device['status'] = 'prepare'
        
#         # Main container
#         main_frame = ttk.Frame(self.root, padding=20)
#         main_frame.pack(expand=True, fill='both')
        
#         # Title row with Back button on right
#         title_frame = ttk.Frame(main_frame)
#         title_frame.pack(fill='x', pady=(0, 10))
        
#         # Empty label for left side balance
#         ttk.Label(title_frame, text="").pack(side='left', expand=True)
        
#         # Title (centered)
#         title = ttk.Label(title_frame, text="Game Preparation", style='Header.TLabel')
#         title.pack(side='left')
        
#         # Buttons frame on the right (Clear List and Back to Main)
#         back_frame = ttk.Frame(title_frame)
#         back_frame.pack(side='left', expand=True)
#         # Inner frame to hold buttons on the right
#         buttons_inner = ttk.Frame(back_frame)
#         buttons_inner.pack(side='right')
#         # Clear List button (left of Back to Main)
#         ttk.Button(buttons_inner, text="Clear List", command=self.confirm_clear_list,
#                   style='Secondary.TButton').pack(side='left', padx=(0, 5))
#         # Back to Main button (right corner, non-bold, with confirmation)
#         ttk.Button(buttons_inner, text="Back to Main", command=self.confirm_back_to_main,
#                   style='Secondary.TButton').pack(side='left')
        
#         # Settings frame
#         settings_frame = ttk.LabelFrame(main_frame, text="Game Settings", padding=15)
#         settings_frame.pack(fill='x', padx=20, pady=10)
        
#         # Number of Players
#         ttk.Label(settings_frame, text="Number of Players:").grid(row=0, column=0, sticky='w', pady=5)
#         self.num_gamers_var = tk.IntVar(value=game_state['num_gamers'])
#         num_gamers_spin = ttk.Spinbox(settings_frame, from_=1, to=100, textvariable=self.num_gamers_var, width=10)
#         num_gamers_spin.grid(row=0, column=1, padx=10, pady=5)
        
#         # Human percentage
#         ttk.Label(settings_frame, text="Human Percentage (25-75%):").grid(row=1, column=0, sticky='w', pady=5)
#         self.human_pct_var = tk.IntVar(value=game_state['human_percentage'])
#         human_spin = ttk.Spinbox(settings_frame, from_=25, to=75, textvariable=self.human_pct_var, width=10)
#         human_spin.grid(row=1, column=1, padx=10, pady=5)
        
#         # Game timeout
#         ttk.Label(settings_frame, text="Game Timeout (seconds):").grid(row=2, column=0, sticky='w', pady=5)
#         self.timeout_var = tk.IntVar(value=game_state['game_timeout'])
#         timeout_spin = ttk.Spinbox(settings_frame, from_=10, to=120, textvariable=self.timeout_var, width=10)
#         timeout_spin.grid(row=2, column=1, padx=10, pady=5)
        
#         # Game duration
#         ttk.Label(settings_frame, text="Game Duration (minutes):").grid(row=3, column=0, sticky='w', pady=5)
#         self.duration_var = tk.IntVar(value=game_state['game_duration'])
#         duration_spin = ttk.Spinbox(settings_frame, from_=1, to=60, textvariable=self.duration_var, width=10)
#         duration_spin.grid(row=3, column=1, padx=10, pady=5)
        
#         # Add trace callbacks to save settings on every change
#         self.num_gamers_var.trace_add('write', self.on_setting_changed)
#         self.human_pct_var.trace_add('write', self.on_setting_changed)
#         self.timeout_var.trace_add('write', self.on_setting_changed)
#         self.duration_var.trace_add('write', self.on_setting_changed)
        
#         # Devices frame
#         devices_frame = ttk.LabelFrame(main_frame, text="Connected Devices", padding=10)
#         devices_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
#         # Create treeview for devices
#         columns = ('ID', 'IP', 'RSSI', 'Role', 'Status', 'Health', 'Battery', 'Comment')
#         self.device_tree = ttk.Treeview(devices_frame, columns=columns, show='headings', height=10)
        
#         for col in columns:
#             self.device_tree.heading(col, text=col, command=lambda c=col: self.sort_treeview(c))
#             self.device_tree.column(col, width=100)
        
#         # Scrollbar
#         scrollbar = ttk.Scrollbar(devices_frame, orient='vertical', command=self.device_tree.yview)
#         self.device_tree.configure(yscrollcommand=scrollbar.set)
        
#         self.device_tree.pack(side='left', fill='both', expand=True)
#         scrollbar.pack(side='right', fill='y')
        
#         # Buttons frame (centered)
#         btn_frame = ttk.Frame(main_frame)
#         btn_frame.pack(pady=10)
        
#         # Continue button (disabled until enough devices)
#         self.continue_btn = ttk.Button(btn_frame, text="Waiting devices...", command=self.confirm_continue,
#                   style='Success.TButton', state='disabled')
#         self.continue_btn.pack()
        
#         # Update devices display and button state
#         self.update_device_list()
        
#         # Start auto-refresh
#         self.prepare_refresh_job = self.root.after(5000, self.refresh_prepare_screen)
    
#     def on_setting_changed(self, *args):
#         """Called when any setting is changed - saves settings immediately"""
#         try:
#             # Update game state with current values
#             game_state['num_gamers'] = self.num_gamers_var.get()
#             game_state['human_percentage'] = self.human_pct_var.get()
#             game_state['game_timeout'] = self.timeout_var.get()
#             game_state['game_duration'] = self.duration_var.get()
#             # Save to file
#             self.save_settings()
#             # Update continue button (in case num_gamers changed)
#             if hasattr(self, 'continue_btn'):
#                 self.update_continue_button()
#         except tk.TclError:
#             # Ignore errors during widget destruction or invalid values
#             pass
    
#     def confirm_back_to_main(self):
#         """Confirm before going back to main screen"""
#         if messagebox.askyesno("Confirm", "Are you sure you want to go back to the main screen?"):
#             # Cancel prepare refresh
#             if hasattr(self, 'prepare_refresh_job'):
#                 self.root.after_cancel(self.prepare_refresh_job)
#             self.show_main_screen()
    
#     def confirm_clear_list(self):
#         """Confirm before clearing the device list"""
#         if messagebox.askyesno("Confirm", "Are you sure you want to clear all connected devices?"):
#             with devices_lock:
#                 devices.clear()
#                 game_state['humans'] = []
#                 game_state['zombies'] = []
#             self.update_device_list()
    
#     def confirm_continue(self):
#         """Confirm before continuing to distribution screen"""
#         if messagebox.askyesno("Confirm", "Continue to player distribution?"):
#             # Cancel prepare refresh
#             if hasattr(self, 'prepare_refresh_job'):
#                 self.root.after_cancel(self.prepare_refresh_job)
#             self.show_distribution_screen()
    
#     def update_continue_button(self):
#         """Update Continue button state based on device count"""
#         with devices_lock:
#             device_count = len(devices)
#         required = self.num_gamers_var.get()
        
#         if device_count >= required:
#             self.continue_btn.config(text="Continue", state='normal')
#         else:
#             self.continue_btn.config(text=f"Waiting devices... ({device_count}/{required})", state='disabled')
        
#     def refresh_prepare_screen(self):
#         """Refresh prepare screen data"""
#         if self.current_screen == 'prepare':
#             self.update_device_list()
#             self.update_continue_button()
#             self.prepare_refresh_job = self.root.after(5000, self.refresh_prepare_screen)
    
#     def update_device_list(self):
#         """Update device list in treeview"""
#         # Clear existing items
#         for item in self.device_tree.get_children():
#             self.device_tree.delete(item)
        
#         # Add devices
#         with devices_lock:
#             sorted_devices = sorted(devices.values(), key=lambda x: x['id'])
#             for device in sorted_devices:
#                 self.device_tree.insert('', 'end', values=(
#                     device['id'],
#                     device['ip'],
#                     device['rssi'],
#                     device['role'],
#                     device['status'],
#                     device['health'],
#                     f"{device['battery']}%",
#                     device['comment']
#                 ))
        
#         # Update continue button state
#         if hasattr(self, 'continue_btn'):
#             self.update_continue_button()
    
#     def sort_treeview(self, col):
#         """Sort treeview by column"""
#         items = [(self.device_tree.set(item, col), item) for item in self.device_tree.get_children('')]
#         items.sort()
#         for index, (val, item) in enumerate(items):
#             self.device_tree.move(item, '', index)
    
#     def show_distribution_screen(self):
#         """Player distribution screen - assign zombies and humans"""
#         self.clear_screen()
#         self.current_screen = 'distribution'
        
#         # Set status - but keep roles as neutral until Start is pressed
#         with devices_lock:
#             game_state['status'] = 'distribution'
#             for device in devices.values():
#                 device['status'] = 'distribution'
#                 device['role'] = 'neutral'  # Keep neutral until Start is pressed
        
#         # Assign initial roles based on percentage (for display purposes only, not sent to devices yet)
#         self.assign_distribution_roles()
        
#         # Main container
#         main_frame = ttk.Frame(self.root, padding=20)
#         main_frame.pack(expand=True, fill='both')
        
#         # Title (centered)
#         title = ttk.Label(main_frame, text="Players Distribution", style='Header.TLabel')
#         title.pack(pady=(0, 10), anchor='center')
        
#         # Lists container
#         lists_frame = ttk.Frame(main_frame)
#         lists_frame.pack(fill='both', expand=True, pady=10)
        
#         # Configure grid weights for equal distribution
#         lists_frame.columnconfigure(0, weight=1)
#         lists_frame.columnconfigure(1, weight=0)
#         lists_frame.columnconfigure(2, weight=1)
#         lists_frame.rowconfigure(0, weight=1)
        
#         # Zombies list (left side)
#         zombies_frame = ttk.LabelFrame(lists_frame, text="Zombies", padding=10)
#         zombies_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
#         columns = ('ID', 'Comment')
#         self.dist_zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=15)
#         self.dist_zombies_tree.heading('ID', text='ID')
#         self.dist_zombies_tree.heading('Comment', text='Comment')
#         self.dist_zombies_tree.column('ID', width=150)
#         self.dist_zombies_tree.column('Comment', width=150)
        
#         zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=self.dist_zombies_tree.yview)
#         self.dist_zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
#         self.dist_zombies_tree.pack(side='left', fill='both', expand=True)
#         zombies_scroll.pack(side='right', fill='y')
        
#         # Middle buttons frame
#         middle_frame = ttk.Frame(lists_frame)
#         middle_frame.grid(row=0, column=1, padx=10)
        
#         # Move to Humans button (right arrow)
#         ttk.Button(middle_frame, text="→\nTo Human", command=self.move_to_human,
#                   style='Secondary.TButton').pack(pady=5)
        
#         # Move to Zombies button (left arrow)
#         ttk.Button(middle_frame, text="←\nTo Zombie", command=self.move_to_zombie,
#                   style='Secondary.TButton').pack(pady=5)
        
#         # Humans list (right side)
#         humans_frame = ttk.LabelFrame(lists_frame, text="Humans", padding=10)
#         humans_frame.grid(row=0, column=2, sticky='nsew', padx=(5, 0))
        
#         self.dist_humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=15)
#         self.dist_humans_tree.heading('ID', text='ID')
#         self.dist_humans_tree.heading('Comment', text='Comment')
#         self.dist_humans_tree.column('ID', width=150)
#         self.dist_humans_tree.column('Comment', width=150)
        
#         humans_scroll = ttk.Scrollbar(humans_frame, orient='vertical', command=self.dist_humans_tree.yview)
#         self.dist_humans_tree.configure(yscrollcommand=humans_scroll.set)
        
#         self.dist_humans_tree.pack(side='left', fill='both', expand=True)
#         humans_scroll.pack(side='right', fill='y')
        
#         # Populate the lists
#         self.update_distribution_lists()
        
#         # Buttons frame
#         btn_frame = ttk.Frame(main_frame)
#         btn_frame.pack(fill='x', pady=10)
        
#         # Back button (left side)
#         ttk.Button(btn_frame, text="Back", command=self.confirm_back_to_prepare,
#                   style='Secondary.TButton').pack(side='left')
        
#         # Start button (center)
#         ttk.Button(btn_frame, text="Start!", command=self.confirm_start_game,
#                   style='Primary.TButton').pack(expand=True)
    
#     def update_distribution_lists(self):
#         """Update the distribution lists with current assignments"""
#         # Clear existing items
#         for item in self.dist_zombies_tree.get_children():
#             self.dist_zombies_tree.delete(item)
#         for item in self.dist_humans_tree.get_children():
#             self.dist_humans_tree.delete(item)
        
#         # Populate lists (sorted by ID)
#         with devices_lock:
#             # Sort zombies by ID
#             sorted_zombies = sorted(game_state['zombies'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
#             for dev_id in sorted_zombies:
#                 if dev_id in devices:
#                     device = devices[dev_id]
#                     self.dist_zombies_tree.insert('', 'end', iid=dev_id, values=(
#                         device['id'],
#                         device['comment']
#                     ))
            
#             # Sort humans by ID
#             sorted_humans = sorted(game_state['humans'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
#             for dev_id in sorted_humans:
#                 if dev_id in devices:
#                     device = devices[dev_id]
#                     self.dist_humans_tree.insert('', 'end', iid=dev_id, values=(
#                         device['id'],
#                         device['comment']
#                     ))
    
#     def move_to_human(self):
#         """Move selected zombie to humans list"""
#         selected = self.dist_zombies_tree.selection()
#         if not selected:
#             messagebox.showwarning("No Selection", "Please select a player from the Zombies list.")
#             return
        
#         # Check if this would empty the Zombies list
#         with devices_lock:
#             if len(game_state['zombies']) <= len(selected):
#                 messagebox.showerror("Cannot Move", "Cannot move all players. There must be at least one Zombie.")
#                 return
            
#             for dev_id in selected:
#                 if dev_id in game_state['zombies']:
#                     game_state['zombies'].remove(dev_id)
#                     game_state['humans'].append(dev_id)
#                     # Don't change device role yet - keep neutral until Start is pressed
        
#         self.update_distribution_lists()
    
#     def move_to_zombie(self):
#         """Move selected human to zombies list"""
#         selected = self.dist_humans_tree.selection()
#         if not selected:
#             messagebox.showwarning("No Selection", "Please select a player from the Humans list.")
#             return
        
#         # Check if this would empty the Humans list
#         with devices_lock:
#             if len(game_state['humans']) <= len(selected):
#                 messagebox.showerror("Cannot Move", "Cannot move all players. There must be at least one Human.")
#                 return
            
#             for dev_id in selected:
#                 if dev_id in game_state['humans']:
#                     game_state['humans'].remove(dev_id)
#                     game_state['zombies'].append(dev_id)
#                     # Don't change device role yet - keep neutral until Start is pressed
        
#         self.update_distribution_lists()
    
#     def confirm_back_to_prepare(self):
#         """Confirm before going back to preparation screen"""
#         if messagebox.askyesno("Confirm", "Go back to preparation screen? Current distribution will be lost."):
#             self.show_prepare_screen()
    
#     def assign_distribution_roles(self):
#         """Assign roles for distribution display only (devices stay neutral until Start)"""
#         with devices_lock:
#             device_list = list(devices.keys())
#             if not device_list:
#                 return
            
#             total_devices = len(device_list)
#             num_humans = max(1, int(total_devices * game_state['human_percentage'] / 100))
            
#             random.shuffle(device_list)
#             selected_humans = device_list[:num_humans]
            
#             game_state['humans'] = []
#             game_state['zombies'] = []
            
#             for device_id in device_list:
#                 if device_id in selected_humans:
#                     game_state['humans'].append(device_id)
#                 else:
#                     game_state['zombies'].append(device_id)
#                 # Note: device['role'] stays 'neutral' - not changed here
    
#     def confirm_start_game(self):
#         """Confirm before starting the game"""
#         if messagebox.askyesno("Confirm", "Start the game with current distribution?"):
#             self.start_game()
    
#     def start_game(self):
#         """Start the game"""
#         # Cancel prepare refresh if still active
#         if hasattr(self, 'prepare_refresh_job'):
#             self.root.after_cancel(self.prepare_refresh_job)
        
#         # NOW assign the actual roles to devices (they were neutral until this point)
#         with devices_lock:
#             for dev_id in game_state['humans']:
#                 if dev_id in devices:
#                     devices[dev_id]['role'] = 'human'
#             for dev_id in game_state['zombies']:
#                 if dev_id in devices:
#                     devices[dev_id]['role'] = 'zombie'
        
#         # Show game screen
#         self.show_game_screen()
    
#     def show_game_screen(self):
#         """Game in progress screen"""
#         self.clear_screen()
#         self.current_screen = 'game'
        
#         # Set game state
#         with devices_lock:
#             game_state['status'] = 'game'
#             if game_state['game_start_time'] is None:
#                 game_state['game_start_time'] = datetime.now()
            
#             for device in devices.values():
#                 device['status'] = 'game'
        
#         # Main container
#         main_frame = ttk.Frame(self.root, padding=20)
#         main_frame.pack(expand=True, fill='both')
        
#         # Title and timer frame
#         header_frame = ttk.Frame(main_frame)
#         header_frame.pack(fill='x', pady=(0, 10))
        
#         title = ttk.Label(header_frame, text="Game In Progress", style='Header.TLabel')
#         title.pack(side='left')
        
#         self.timer_label = ttk.Label(header_frame, text="00:00:00", style='Title.TLabel')
#         self.timer_label.pack(side='right')
        
#         # Statistics frame
#         stats_frame = ttk.Frame(main_frame)
#         stats_frame.pack(fill='x', pady=(0, 10))
        
#         # Zombies stats (left)
#         self.zombies_stats_label = ttk.Label(stats_frame, text="Zombies: 0 players, Total Health: 0", style='Stats.TLabel')
#         self.zombies_stats_label.pack(side='left', padx=20)
        
#         # Humans stats (right)
#         self.humans_stats_label = ttk.Label(stats_frame, text="Humans: 0 players, Total Health: 0", style='Stats.TLabel')
#         self.humans_stats_label.pack(side='right', padx=20)
        
#         # Lists container (side by side)
#         lists_frame = ttk.Frame(main_frame)
#         lists_frame.pack(fill='both', expand=True, pady=10)
        
#         # Configure grid weights for equal distribution
#         lists_frame.columnconfigure(0, weight=1)
#         lists_frame.columnconfigure(1, weight=1)
#         lists_frame.rowconfigure(0, weight=1)
        
#         # Zombies list (left side)
#         zombies_frame = ttk.LabelFrame(lists_frame, text="Zombies", padding=10)
#         zombies_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
#         columns = ('ID', 'Health', 'Battery', 'RSSI', 'Comment')
#         self.zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=15)
        
#         # Set column headings and widths
#         self.zombies_tree.heading('ID', text='ID')
#         self.zombies_tree.heading('Health', text='Health')
#         self.zombies_tree.heading('Battery', text='Battery')
#         self.zombies_tree.heading('RSSI', text='RSSI')
#         self.zombies_tree.heading('Comment', text='Comment')
        
#         self.zombies_tree.column('ID', width=150, minwidth=100)
#         self.zombies_tree.column('Health', width=60, minwidth=50)
#         self.zombies_tree.column('Battery', width=60, minwidth=50)
#         self.zombies_tree.column('RSSI', width=50, minwidth=40)
#         self.zombies_tree.column('Comment', width=150, minwidth=100)
        
#         zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=self.zombies_tree.yview)
#         self.zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
#         self.zombies_tree.pack(side='left', fill='both', expand=True)
#         zombies_scroll.pack(side='right', fill='y')
        
#         # Humans list (right side)
#         humans_frame = ttk.LabelFrame(lists_frame, text="Humans", padding=10)
#         humans_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
#         self.humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=15)
        
#         # Set column headings and widths
#         self.humans_tree.heading('ID', text='ID')
#         self.humans_tree.heading('Health', text='Health')
#         self.humans_tree.heading('Battery', text='Battery')
#         self.humans_tree.heading('RSSI', text='RSSI')
#         self.humans_tree.heading('Comment', text='Comment')
        
#         self.humans_tree.column('ID', width=150, minwidth=100)
#         self.humans_tree.column('Health', width=60, minwidth=50)
#         self.humans_tree.column('Battery', width=60, minwidth=50)
#         self.humans_tree.column('RSSI', width=50, minwidth=40)
#         self.humans_tree.column('Comment', width=150, minwidth=100)
        
#         humans_scroll = ttk.Scrollbar(humans_frame, orient='vertical', command=self.humans_tree.yview)
#         self.humans_tree.configure(yscrollcommand=humans_scroll.set)
        
#         self.humans_tree.pack(side='left', fill='both', expand=True)
#         humans_scroll.pack(side='right', fill='y')
        
#         # Update team lists
#         self.update_game_teams()
        
#         # Start timer and auto-refresh
#         self.update_timer()
#         self.game_refresh_job = self.root.after(5000, self.refresh_game_screen)
        
#         # Buttons frame
#         btn_frame = ttk.Frame(main_frame)
#         btn_frame.pack(pady=10)
        
#         ttk.Button(btn_frame, text="-1 Minute", command=self.confirm_subtract_minute,
#                   style='SubtractTime.TButton').pack(side='left', padx=10)
#         ttk.Button(btn_frame, text="+1 Minute", command=self.confirm_add_minute,
#                   style='AddTime.TButton').pack(side='left', padx=10)
#         ttk.Button(btn_frame, text="End Game", command=self.confirm_end_game,
#                   style='EndGame.TButton').pack(side='left', padx=10)
    
#     def update_game_teams(self):
#         """Update zombies and humans lists with statistics"""
#         # Clear existing items
#         for item in self.zombies_tree.get_children():
#             self.zombies_tree.delete(item)
#         for item in self.humans_tree.get_children():
#             self.humans_tree.delete(item)
        
#         # Track statistics
#         zombie_count = 0
#         zombie_total_health = 0
#         human_count = 0
#         human_total_health = 0
        
#         # Add devices to respective teams (sorted by ID)
#         with devices_lock:
#             # Sort and add zombies
#             sorted_zombies = sorted(game_state['zombies'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
#             for dev_id in sorted_zombies:
#                 if dev_id in devices:
#                     device = devices[dev_id]
#                     self.zombies_tree.insert('', 'end', values=(
#                         device['id'],
#                         device['health'],
#                         f"{device['battery']}%",
#                         device['rssi'],
#                         device['comment']
#                     ))
#                     zombie_count += 1
#                     try:
#                         zombie_total_health += int(device['health'])
#                     except (ValueError, TypeError):
#                         pass
            
#             # Sort and add humans
#             sorted_humans = sorted(game_state['humans'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
#             for dev_id in sorted_humans:
#                 if dev_id in devices:
#                     device = devices[dev_id]
#                     self.humans_tree.insert('', 'end', values=(
#                         device['id'],
#                         device['health'],
#                         f"{device['battery']}%",
#                         device['rssi'],
#                         device['comment']
#                     ))
#                     human_count += 1
#                     try:
#                         human_total_health += int(device['health'])
#                     except (ValueError, TypeError):
#                         pass
        
#         # Update statistics labels
#         if hasattr(self, 'zombies_stats_label'):
#             self.zombies_stats_label.config(text=f"Zombies: {zombie_count} players, Total Health: {zombie_total_health}")
#         if hasattr(self, 'humans_stats_label'):
#             self.humans_stats_label.config(text=f"Humans: {human_count} players, Total Health: {human_total_health}")
    
#     def update_timer(self):
#         """Update game timer"""
#         if self.current_screen == 'game' and game_state['game_start_time']:
#             elapsed = datetime.now() - game_state['game_start_time']
#             duration = timedelta(minutes=game_state['game_duration'])
#             remaining = duration - elapsed
            
#             if remaining.total_seconds() > 0:
#                 hours, remainder = divmod(int(remaining.total_seconds()), 3600)
#                 minutes, seconds = divmod(remainder, 60)
#                 self.timer_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
#                 self.root.after(1000, self.update_timer)
#             else:
#                 self.timer_label.config(text="00:00:00")
#                 # Time is up - end the game
#                 self.end_game_time_up()
    
#     def refresh_game_screen(self):
#         """Refresh game screen data"""
#         if self.current_screen == 'game':
#             self.update_game_teams()
            
#             # Check for win conditions
#             with devices_lock:
#                 zombie_count = len(game_state['zombies'])
#                 human_count = len(game_state['humans'])
            
#             if zombie_count == 0:
#                 # All zombies eliminated - humans win
#                 self.end_game_team_won("Humans")
#                 return
#             elif human_count == 0:
#                 # All humans converted - zombies win
#                 self.end_game_team_won("Zombies")
#                 return
            
#             self.game_refresh_job = self.root.after(5000, self.refresh_game_screen)
    
#     def end_game_time_up(self):
#         """End game due to time running out"""
#         # Cancel game refresh
#         if hasattr(self, 'game_refresh_job'):
#             self.root.after_cancel(self.game_refresh_job)
        
#         # Determine winner based on counts
#         with devices_lock:
#             zombie_count = len(game_state['zombies'])
#             human_count = len(game_state['humans'])
        
#         if zombie_count > human_count:
#             result = "Time's up!\n\n🧟 Zombies won! 🧟"
#         elif human_count > zombie_count:
#             result = "Time's up!\n\n👥 Humans won! 👥"
#         else:
#             result = "Time's up!\n\n⚖️ It's a tie! ⚖️"
        
#         messagebox.showinfo("Game Over", result)
#         self.show_end_screen()
    
#     def end_game_team_won(self, winning_team):
#         """End game due to one team winning"""
#         # Cancel game refresh
#         if hasattr(self, 'game_refresh_job'):
#             self.root.after_cancel(self.game_refresh_job)
        
#         if winning_team == "Zombies":
#             result = "🧟 Zombies won! 🧟\n\nAll humans have been converted!"
#         else:
#             result = "👥 Humans won! 👥\n\nAll zombies have been eliminated!"
        
#         messagebox.showinfo("Game Over", result)
#         self.show_end_screen()
    
#     def confirm_add_minute(self):
#         """Confirm before adding a minute"""
#         if messagebox.askyesno("Confirm", "Add 1 minute to game time?"):
#             self.add_minute()
    
#     def confirm_subtract_minute(self):
#         """Confirm before subtracting a minute"""
#         if messagebox.askyesno("Confirm", "Subtract 1 minute from game time?"):
#             self.subtract_minute()
    
#     def add_minute(self):
#         """Add one minute to game duration"""
#         with devices_lock:
#             game_state['game_duration'] += 1
#         logger.info("Added 1 minute to game duration")
    
#     def subtract_minute(self):
#         """Subtract one minute from game duration"""
#         with devices_lock:
#             if game_state['game_duration'] > 1:
#                 game_state['game_duration'] -= 1
#                 logger.info("Subtracted 1 minute from game duration")
#             else:
#                 logger.warning("Cannot subtract minute - duration already at minimum")
    
#     def confirm_end_game(self):
#         """Double confirm and end game"""
#         if messagebox.askyesno("End Game", "Are you sure you want to end the game?"):
#             # Second confirmation
#             if messagebox.askyesno("Confirm End Game", "This action cannot be undone.\n\nAre you REALLY sure you want to end the game?"):
#                 # Cancel game refresh
#                 if hasattr(self, 'game_refresh_job'):
#                     self.root.after_cancel(self.game_refresh_job)
#                 self.show_end_screen()
    
#     def show_end_screen(self):
#         """Game end screen"""
#         self.clear_screen()
#         self.current_screen = 'end'
        
#         # Set status
#         with devices_lock:
#             game_state['status'] = 'end'
#             for device in devices.values():
#                 device['status'] = 'end'
        
#         # Main container
#         main_frame = ttk.Frame(self.root, padding=20)
#         main_frame.pack(expand=True, fill='both')
        
#         # Title (centered)
#         title = ttk.Label(main_frame, text="Game Ended", style='Header.TLabel')
#         title.pack(pady=(0, 10), anchor='center')
        
#         # Winner announcement
#         with devices_lock:
#             zombie_count = len(game_state['zombies'])
#             human_count = len(game_state['humans'])
        
#         if zombie_count > human_count:
#             winner = "🧟 ZOMBIES WIN! 🧟"
#         elif human_count > zombie_count:
#             winner = "👥 HUMANS WIN! 👥"
#         else:
#             winner = "⚖️ TIE! ⚖️"
        
#         winner_label = ttk.Label(main_frame, text=winner, style='Title.TLabel')
#         winner_label.pack(pady=(0, 10), anchor='center')
        
#         # Statistics frame
#         stats_frame = ttk.Frame(main_frame)
#         stats_frame.pack(fill='x', pady=(0, 10))
        
#         # Calculate total health
#         zombie_total_health = 0
#         human_total_health = 0
#         with devices_lock:
#             for dev_id in game_state['zombies']:
#                 if dev_id in devices:
#                     try:
#                         zombie_total_health += int(devices[dev_id]['health'])
#                     except (ValueError, TypeError):
#                         pass
#             for dev_id in game_state['humans']:
#                 if dev_id in devices:
#                     try:
#                         human_total_health += int(devices[dev_id]['health'])
#                     except (ValueError, TypeError):
#                         pass
        
#         # Zombies stats (left)
#         zombies_stats_label = ttk.Label(stats_frame, 
#             text=f"Zombies: {zombie_count} players, Total Health: {zombie_total_health}", 
#             style='Stats.TLabel')
#         zombies_stats_label.pack(side='left', padx=20)
        
#         # Humans stats (right)
#         humans_stats_label = ttk.Label(stats_frame, 
#             text=f"Humans: {human_count} players, Total Health: {human_total_health}", 
#             style='Stats.TLabel')
#         humans_stats_label.pack(side='right', padx=20)
        
#         # Lists container (side by side)
#         lists_frame = ttk.Frame(main_frame)
#         lists_frame.pack(fill='both', expand=True, pady=10)
        
#         # Configure grid weights for equal distribution
#         lists_frame.columnconfigure(0, weight=1)
#         lists_frame.columnconfigure(1, weight=1)
#         lists_frame.rowconfigure(0, weight=1)
        
#         # Zombies list (left side)
#         zombies_frame = ttk.LabelFrame(lists_frame, text="Zombies", padding=10)
#         zombies_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        
#         columns = ('ID', 'Health', 'Battery', 'RSSI', 'Comment')
#         zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=12)
        
#         # Set column headings and widths
#         zombies_tree.heading('ID', text='ID')
#         zombies_tree.heading('Health', text='Health')
#         zombies_tree.heading('Battery', text='Battery')
#         zombies_tree.heading('RSSI', text='RSSI')
#         zombies_tree.heading('Comment', text='Comment')
        
#         zombies_tree.column('ID', width=150, minwidth=100)
#         zombies_tree.column('Health', width=60, minwidth=50)
#         zombies_tree.column('Battery', width=60, minwidth=50)
#         zombies_tree.column('RSSI', width=50, minwidth=40)
#         zombies_tree.column('Comment', width=150, minwidth=100)
        
#         zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=zombies_tree.yview)
#         zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
#         zombies_tree.pack(side='left', fill='both', expand=True)
#         zombies_scroll.pack(side='right', fill='y')
        
#         # Humans list (right side)
#         humans_frame = ttk.LabelFrame(lists_frame, text="Humans", padding=10)
#         humans_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
#         humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=12)
        
#         # Set column headings and widths
#         humans_tree.heading('ID', text='ID')
#         humans_tree.heading('Health', text='Health')
#         humans_tree.heading('Battery', text='Battery')
#         humans_tree.heading('RSSI', text='RSSI')
#         humans_tree.heading('Comment', text='Comment')
        
#         humans_tree.column('ID', width=150, minwidth=100)
#         humans_tree.column('Health', width=60, minwidth=50)
#         humans_tree.column('Battery', width=60, minwidth=50)
#         humans_tree.column('RSSI', width=50, minwidth=40)
#         humans_tree.column('Comment', width=150, minwidth=100)
        
#         humans_scroll = ttk.Scrollbar(humans_frame, orient='vertical', command=humans_tree.yview)
#         humans_tree.configure(yscrollcommand=humans_scroll.set)
        
#         humans_tree.pack(side='left', fill='both', expand=True)
#         humans_scroll.pack(side='right', fill='y')
        
#         # Populate final team lists (sorted by ID)
#         with devices_lock:
#             sorted_zombies = sorted(game_state['zombies'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
#             for dev_id in sorted_zombies:
#                 if dev_id in devices:
#                     device = devices[dev_id]
#                     zombies_tree.insert('', 'end', values=(
#                         device['id'],
#                         device['health'],
#                         f"{device['battery']}%",
#                         device['rssi'],
#                         device['comment']
#                     ))
            
#             sorted_humans = sorted(game_state['humans'], key=lambda dev_id: devices.get(dev_id, {}).get('id', dev_id))
#             for dev_id in sorted_humans:
#                 if dev_id in devices:
#                     device = devices[dev_id]
#                     humans_tree.insert('', 'end', values=(
#                         device['id'],
#                         device['health'],
#                         f"{device['battery']}%",
#                         device['rssi'],
#                         device['comment']
#                     ))
        
#         # Finish button (centered)
#         ttk.Button(main_frame, text="Finish and Return to Main", 
#                   command=self.confirm_finish,
#                   style='Primary.TButton').pack(pady=20, anchor='center')
    
#     def confirm_finish(self):
#         """Confirm and return to main screen"""
#         if messagebox.askyesno("Finish", "Return to main screen?"):
#             self.show_main_screen()
    
#     def get_local_ip(self):
#         """Get local IP address"""
#         try:
#             s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#             s.connect(("8.8.8.8", 80))
#             local_ip = s.getsockname()[0]
#             s.close()
#             return local_ip
#         except Exception:
#             return "127.0.0.1"
    
#     def on_closing(self):
#         """Handle window close"""
#         if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
#             self.root.destroy()


# def main():
#     """Main application entry point"""
#     # Check for single instance
#     instance_lock = SingleInstance()
    
#     if not instance_lock.acquire():
#         # Another instance is already running
#         # Show error message
#         try:
#             temp_root = tk.Tk()
#             temp_root.withdraw()
#             messagebox.showwarning(
#                 "Already Running",
#                 "Zombie Game Server is already running.\n\n"
#                 "Check your system tray or taskbar for the existing instance."
#             )
#             temp_root.destroy()
#         except:
#             print("Error: Zombie Game Server is already running.")
        
#         sys.exit(1)
    
#     # Start Flask server in background
#     flask_thread = FlaskThread(SERVER_HOST, SERVER_PORT)
#     flask_thread.start()
    
#     # Give Flask a moment to start
#     time.sleep(1)
    
#     # Get local IP
#     try:
#         s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#         s.connect(("8.8.8.8", 80))
#         local_ip = s.getsockname()[0]
#         s.close()
#     except Exception:
#         local_ip = "127.0.0.1"
    
#     print("=" * 70)
#     print("🎮 ZOMBIE GAME - Native GUI Application")
#     print("=" * 70)
#     print(f"\n✓ Server running on: http://{SERVER_HOST}:{SERVER_PORT}")
#     print(f"✓ Local IP: {local_ip}")
#     print(f"✓ ESP32 endpoint: http://{local_ip}:{SERVER_PORT}/api/device")
#     print("\n" + "=" * 70)
#     print("GUI window will open now...")
#     print("=" * 70)
#     print()
    
#     # Create and run GUI
#     root = tk.Tk()
#     app = ZombieGameApp(root)
#     root.mainloop()


# if __name__ == '__main__':
#     main()