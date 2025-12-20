#!/usr/bin/env python3
"""
Zombie Game - Native Windows GUI Application
A monolith desktop application with native GUI that runs the ESP32 game server.
No web interface - pure Windows GUI using tkinter.
"""

import tkinter as tk
from tkinter import ttk, messagebox, font
import json
import random
import time
import threading
import logging
import socket
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
DEFAULT_HUMAN_PERCENTAGE = 50
DEFAULT_GAME_TIMEOUT = 30
DEFAULT_GAME_DURATION = 15

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
    'game_start_time': None,
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
        
        style.configure('Primary.TButton', font=('Arial', 12, 'bold'), padding=10)
        style.configure('Success.TButton', font=('Arial', 11), padding=8)
        style.configure('Danger.TButton', font=('Arial', 11), padding=8)
        
    def clear_screen(self):
        """Clear current screen"""
        for widget in self.root.winfo_children():
            widget.destroy()
            
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
        title.pack(pady=(0, 30))
        
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
        enter_btn = ttk.Button(main_frame, text="START GAME SETUP", 
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
        
        # Title
        title = ttk.Label(main_frame, text="Game Preparation", style='Header.TLabel')
        title.pack(pady=(0, 10))
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Game Settings", padding=15)
        settings_frame.pack(fill='x', padx=20, pady=10)
        
        # Human percentage
        ttk.Label(settings_frame, text="Human Percentage (25-75%):").grid(row=0, column=0, sticky='w', pady=5)
        self.human_pct_var = tk.IntVar(value=game_state['human_percentage'])
        human_spin = ttk.Spinbox(settings_frame, from_=25, to=75, textvariable=self.human_pct_var, width=10)
        human_spin.grid(row=0, column=1, padx=10, pady=5)
        
        # Game timeout
        ttk.Label(settings_frame, text="Game Timeout (seconds):").grid(row=1, column=0, sticky='w', pady=5)
        self.timeout_var = tk.IntVar(value=game_state['game_timeout'])
        timeout_spin = ttk.Spinbox(settings_frame, from_=10, to=120, textvariable=self.timeout_var, width=10)
        timeout_spin.grid(row=1, column=1, padx=10, pady=5)
        
        # Game duration
        ttk.Label(settings_frame, text="Game Duration (minutes):").grid(row=2, column=0, sticky='w', pady=5)
        self.duration_var = tk.IntVar(value=game_state['game_duration'])
        duration_spin = ttk.Spinbox(settings_frame, from_=1, to=60, textvariable=self.duration_var, width=10)
        duration_spin.grid(row=2, column=1, padx=10, pady=5)
        
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
        
        # Update devices display
        self.update_device_list()
        
        # Start auto-refresh
        self.prepare_refresh_job = self.root.after(5000, self.refresh_prepare_screen)
        
        # Buttons frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Start Game", command=self.start_game,
                  style='Success.TButton').pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Back to Main", command=self.show_main_screen,
                  style='Primary.TButton').pack(side='left', padx=5)
        
    def refresh_prepare_screen(self):
        """Refresh prepare screen data"""
        if self.current_screen == 'prepare':
            self.update_device_list()
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
    
    def sort_treeview(self, col):
        """Sort treeview by column"""
        items = [(self.device_tree.set(item, col), item) for item in self.device_tree.get_children('')]
        items.sort()
        for index, (val, item) in enumerate(items):
            self.device_tree.move(item, '', index)
    
    def start_game(self):
        """Start the game"""
        # Update game state
        game_state['human_percentage'] = self.human_pct_var.get()
        game_state['game_timeout'] = self.timeout_var.get()
        game_state['game_duration'] = self.duration_var.get()
        
        # Assign roles
        assign_roles()
        
        # Cancel prepare refresh
        if hasattr(self, 'prepare_refresh_job'):
            self.root.after_cancel(self.prepare_refresh_job)
        
        # Show game screen
        self.show_game_screen()
    
    def show_game_screen(self):
        """Game in progress screen"""
        self.clear_screen()
        self.current_screen = 'game'
        
        # Set game state
        with devices_lock:
            game_state['status'] = 'game'
            if game_state['game_start_time'] is None:
                game_state['game_start_time'] = datetime.now()
            
            for device in devices.values():
                device['status'] = 'game'
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(expand=True, fill='both')
        
        # Title and timer frame
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill='x', pady=(0, 10))
        
        title = ttk.Label(header_frame, text="Game In Progress", style='Header.TLabel')
        title.pack(side='left')
        
        self.timer_label = ttk.Label(header_frame, text="00:00:00", style='Title.TLabel')
        self.timer_label.pack(side='right')
        
        # Create notebook for teams
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True, pady=10)
        
        # Zombies tab
        zombies_frame = ttk.Frame(notebook)
        notebook.add(zombies_frame, text='Zombies')
        
        columns = ('ID', 'IP', 'RSSI', 'Health', 'Battery', 'Comment')
        self.zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.zombies_tree.heading(col, text=col)
            self.zombies_tree.column(col, width=120)
        
        zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=self.zombies_tree.yview)
        self.zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
        self.zombies_tree.pack(side='left', fill='both', expand=True)
        zombies_scroll.pack(side='right', fill='y')
        
        # Humans tab
        humans_frame = ttk.Frame(notebook)
        notebook.add(humans_frame, text='Humans')
        
        self.humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.humans_tree.heading(col, text=col)
            self.humans_tree.column(col, width=120)
        
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
        
        ttk.Button(btn_frame, text="Add 1 Minute", command=self.add_minute,
                  style='Success.TButton').pack(side='left', padx=5)
        ttk.Button(btn_frame, text="End Game", command=self.confirm_end_game,
                  style='Danger.TButton').pack(side='left', padx=5)
    
    def update_game_teams(self):
        """Update zombies and humans lists"""
        # Clear existing items
        for item in self.zombies_tree.get_children():
            self.zombies_tree.delete(item)
        for item in self.humans_tree.get_children():
            self.humans_tree.delete(item)
        
        # Add devices to respective teams
        with devices_lock:
            for dev_id in game_state['zombies']:
                if dev_id in devices:
                    device = devices[dev_id]
                    self.zombies_tree.insert('', 'end', values=(
                        device['id'],
                        device['ip'],
                        device['rssi'],
                        device['health'],
                        f"{device['battery']}%",
                        device['comment']
                    ))
            
            for dev_id in game_state['humans']:
                if dev_id in devices:
                    device = devices[dev_id]
                    self.humans_tree.insert('', 'end', values=(
                        device['id'],
                        device['ip'],
                        device['rssi'],
                        device['health'],
                        f"{device['battery']}%",
                        device['comment']
                    ))
        
        # Update tab titles with counts
        zombie_count = len(self.zombies_tree.get_children())
        human_count = len(self.humans_tree.get_children())
        
        # Find notebook and update tab text
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Notebook):
                        child.tab(0, text=f'Zombies ({zombie_count})')
                        child.tab(1, text=f'Humans ({human_count})')
    
    def update_timer(self):
        """Update game timer"""
        if self.current_screen == 'game' and game_state['game_start_time']:
            elapsed = datetime.now() - game_state['game_start_time']
            duration = timedelta(minutes=game_state['game_duration'])
            remaining = duration - elapsed
            
            if remaining.total_seconds() > 0:
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.timer_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                self.root.after(1000, self.update_timer)
            else:
                self.timer_label.config(text="00:00:00")
    
    def refresh_game_screen(self):
        """Refresh game screen data"""
        if self.current_screen == 'game':
            self.update_game_teams()
            self.game_refresh_job = self.root.after(5000, self.refresh_game_screen)
    
    def add_minute(self):
        """Add one minute to game duration"""
        with devices_lock:
            game_state['game_duration'] += 1
        logger.info("Added 1 minute to game duration")
    
    def confirm_end_game(self):
        """Confirm and end game"""
        if messagebox.askyesno("End Game", "Are you sure you want to end the game?"):
            # Cancel game refresh
            if hasattr(self, 'game_refresh_job'):
                self.root.after_cancel(self.game_refresh_job)
            self.show_end_screen()
    
    def show_end_screen(self):
        """Game end screen"""
        self.clear_screen()
        self.current_screen = 'end'
        
        # Set status
        with devices_lock:
            game_state['status'] = 'end'
            for device in devices.values():
                device['status'] = 'end'
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(expand=True, fill='both')
        
        # Title
        title = ttk.Label(main_frame, text="Game Ended", style='Header.TLabel')
        title.pack(pady=(0, 10))
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Final Results", padding=10)
        results_frame.pack(fill='x', padx=20, pady=10)
        
        with devices_lock:
            zombie_count = len(game_state['zombies'])
            human_count = len(game_state['humans'])
        
        result_text = f"Zombies: {zombie_count} | Humans: {human_count}"
        if zombie_count > human_count:
            winner = "ZOMBIES WIN! 🧟"
        elif human_count > zombie_count:
            winner = "HUMANS WIN! 👥"
        else:
            winner = "TIE! ⚖️"
        
        ttk.Label(results_frame, text=result_text, style='Status.TLabel').pack(pady=5)
        ttk.Label(results_frame, text=winner, style='Title.TLabel').pack(pady=10)
        
        # Create notebook for final teams
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True, pady=10)
        
        # Zombies tab
        zombies_frame = ttk.Frame(notebook)
        notebook.add(zombies_frame, text=f'Zombies ({zombie_count})')
        
        columns = ('ID', 'IP', 'RSSI', 'Health', 'Battery', 'Comment')
        zombies_tree = ttk.Treeview(zombies_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            zombies_tree.heading(col, text=col)
            zombies_tree.column(col, width=120)
        
        zombies_scroll = ttk.Scrollbar(zombies_frame, orient='vertical', command=zombies_tree.yview)
        zombies_tree.configure(yscrollcommand=zombies_scroll.set)
        
        zombies_tree.pack(side='left', fill='both', expand=True)
        zombies_scroll.pack(side='right', fill='y')
        
        # Humans tab
        humans_frame = ttk.Frame(notebook)
        notebook.add(humans_frame, text=f'Humans ({human_count})')
        
        humans_tree = ttk.Treeview(humans_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            humans_tree.heading(col, text=col)
            humans_tree.column(col, width=120)
        
        humans_scroll = ttk.Scrollbar(humans_frame, orient='vertical', command=humans_tree.yview)
        humans_tree.configure(yscrollcommand=humans_scroll.set)
        
        humans_tree.pack(side='left', fill='both', expand=True)
        humans_scroll.pack(side='right', fill='y')
        
        # Populate final team lists
        with devices_lock:
            for dev_id in game_state['zombies']:
                if dev_id in devices:
                    device = devices[dev_id]
                    zombies_tree.insert('', 'end', values=(
                        device['id'],
                        device['ip'],
                        device['rssi'],
                        device['health'],
                        f"{device['battery']}%",
                        device['comment']
                    ))
            
            for dev_id in game_state['humans']:
                if dev_id in devices:
                    device = devices[dev_id]
                    humans_tree.insert('', 'end', values=(
                        device['id'],
                        device['ip'],
                        device['rssi'],
                        device['health'],
                        f"{device['battery']}%",
                        device['comment']
                    ))
        
        # Finish button
        ttk.Button(main_frame, text="Finish and Return to Main", 
                  command=self.confirm_finish,
                  style='Primary.TButton').pack(pady=20)
    
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
