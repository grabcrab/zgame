#!/usr/bin/env python3
"""
LED Pattern Editor for ESP32
A visual editor for LED strip patterns with MP3 playback support.

Usage: python led_pattern_editor.py [sync_files_directory]

The sync_files directory should contain:
- val.json (the pattern file)
- MP3 files referenced in the patterns
"""

import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
import json
import os
import sys
import threading
import time
import subprocess

# Audio backend detection - try multiple options
AUDIO_BACKEND = None
AUDIO_ERROR_MSG = ""

# Try pygame first
try:
    import pygame
    pygame.mixer.init()
    AUDIO_BACKEND = "pygame"
except ImportError:
    pass
except Exception as e:
    AUDIO_ERROR_MSG = f"pygame init failed: {e}"

# Try playsound if pygame not available
if not AUDIO_BACKEND:
    try:
        from playsound import playsound
        AUDIO_BACKEND = "playsound"
    except ImportError:
        pass

# On Windows, we can use the system's default media player as fallback
if not AUDIO_BACKEND and sys.platform == 'win32':
    AUDIO_BACKEND = "windows_system"

if not AUDIO_BACKEND:
    print("Warning: No audio backend available.")
    print("Install one of these for audio playback:")
    print("  pip install playsound")
    print("  pip install pygame")


class AudioPlayer:
    """Cross-platform audio player with multiple backend support"""
    
    def __init__(self):
        self.current_process = None
        self.is_playing = False
        self.current_file = None
        self.loop = False
        self.loop_thread = None
        self.stop_flag = False
    
    def play(self, filepath, loop=False):
        """Play an audio file, optionally looping"""
        self.stop()  # Stop any currently playing audio
        
        if not os.path.exists(filepath):
            return False, f"File not found: {filepath}"
        
        self.current_file = filepath
        self.loop = loop
        self.stop_flag = False
        
        if AUDIO_BACKEND == "pygame":
            return self._play_pygame(filepath, loop)
        elif AUDIO_BACKEND == "playsound":
            return self._play_playsound(filepath, loop)
        elif AUDIO_BACKEND == "windows_system":
            return self._play_windows_system(filepath, loop)
        else:
            return False, "No audio backend available.\n\nInstall with: pip install playsound"
    
    def _play_pygame(self, filepath, loop=False):
        """Play using pygame"""
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.set_volume(1.0)
            # pygame supports loop: -1 means infinite loop
            loops = -1 if loop else 0
            pygame.mixer.music.play(loops=loops)
            self.is_playing = True
            return True, "Playing with pygame"
        except Exception as e:
            return False, f"Pygame error: {e}"
    
    def _play_playsound(self, filepath, loop=False):
        """Play using playsound in a separate thread"""
        try:
            def play_thread():
                try:
                    while not self.stop_flag:
                        playsound(filepath)
                        if not loop or self.stop_flag:
                            break
                except Exception as e:
                    print(f"Playsound error: {e}")
                finally:
                    self.is_playing = False
            
            self.is_playing = True
            self.loop_thread = threading.Thread(target=play_thread, daemon=True)
            self.loop_thread.start()
            return True, "Playing with playsound"
        except Exception as e:
            return False, f"Playsound error: {e}"
    
    def _play_windows_system(self, filepath, loop=False):
        """Play using Windows system"""
        try:
            def play_loop():
                while not self.stop_flag:
                    try:
                        # Use PowerShell MediaPlayer for better control
                        # Get audio duration and play
                        ps_script = f'''
                        Add-Type -AssemblyName PresentationCore
                        $mediaPlayer = New-Object System.Windows.Media.MediaPlayer
                        $mediaPlayer.Open([System.Uri]"{filepath}")
                        Start-Sleep -Milliseconds 500
                        $duration = $mediaPlayer.NaturalDuration.TimeSpan.TotalSeconds
                        if ($duration -eq 0) {{ $duration = 10 }}
                        $mediaPlayer.Play()
                        Start-Sleep -Seconds ([math]::Ceiling($duration) + 1)
                        $mediaPlayer.Close()
                        '''
                        process = subprocess.Popen(
                            ['powershell', '-Command', ps_script],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        self.current_process = process
                        process.wait()
                        
                        if not loop or self.stop_flag:
                            break
                    except Exception as e:
                        print(f"Windows playback error: {e}")
                        break
                
                self.is_playing = False
            
            self.is_playing = True
            self.loop_thread = threading.Thread(target=play_loop, daemon=True)
            self.loop_thread.start()
            return True, "Playing with Windows Media"
            
        except Exception as e:
            return False, f"Windows playback error: {e}"
    
    def stop(self):
        """Stop audio playback"""
        self.stop_flag = True
        self.is_playing = False
        self.loop = False
        
        if AUDIO_BACKEND == "pygame":
            try:
                pygame.mixer.music.stop()
            except:
                pass
        
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.kill()
            except:
                pass
            self.current_process = None
        
        self.current_file = None


# Global audio player instance
audio_player = AudioPlayer()


class ToolTip:
    """Tooltip widget for showing color hints on hover"""
    def __init__(self, widget, text_callback):
        self.widget = widget
        self.text_callback = text_callback
        self.tooltip_window = None
        self.widget.bind('<Enter>', self.show_tooltip)
        self.widget.bind('<Leave>', self.hide_tooltip)
        self.widget.bind('<Motion>', self.move_tooltip)
    
    def show_tooltip(self, event=None):
        if self.tooltip_window:
            return
        
        text = self.text_callback()
        if not text:
            return
        
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        # Create tooltip content
        frame = tk.Frame(tw, background="#ffffe0", relief=tk.SOLID, borderwidth=1)
        frame.pack()
        
        label = tk.Label(frame, text=text, background="#ffffe0", 
                        font=('Consolas', 10), justify=tk.LEFT, padx=5, pady=3)
        label.pack()
    
    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    def move_tooltip(self, event=None):
        if self.tooltip_window:
            x = self.widget.winfo_rootx() + event.x + 15
            y = self.widget.winfo_rooty() + event.y + 15
            self.tooltip_window.wm_geometry(f"+{x}+{y}")


class LEDPatternEditor:
    def __init__(self, root, sync_files_dir=None):
        self.root = root
        self.root.title("ESP32 LED Pattern Editor")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 700)
        
        # Data
        self.data = None
        self.sync_files_dir = None
        self.json_file_path = None
        self.current_pattern_index = 0
        self.playing = False
        self.play_thread = None
        self.modified = False
        
        # Available MP3 files
        self.available_mp3s = []
        
        # LED display settings
        self.led_size = 50
        self.led_spacing = 10
        
        # Setup UI
        self.setup_ui()
        self.setup_menu()
        
        # Bind keyboard shortcuts
        self.root.bind('<Control-s>', lambda e: self.save_file())
        self.root.bind('<Control-o>', lambda e: self.open_sync_folder())
        self.root.bind('<space>', lambda e: self.toggle_play())
        
        # If sync_files_dir provided, load it
        if sync_files_dir:
            self.load_sync_folder(sync_files_dir)
        
    def setup_menu(self):
        """Setup the menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open sync_files folder...", command=self.open_sync_folder, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        
        # Pattern menu
        pattern_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Pattern", menu=pattern_menu)
        pattern_menu.add_command(label="New Pattern", command=self.new_pattern)
        pattern_menu.add_command(label="Duplicate Pattern", command=self.duplicate_pattern)
        pattern_menu.add_command(label="Delete Pattern", command=self.delete_pattern)
        pattern_menu.add_separator()
        pattern_menu.add_command(label="Add Strip Frame", command=self.add_strip_frame)
        pattern_menu.add_command(label="Delete Strip Frame", command=self.delete_strip_frame)
        
    def setup_ui(self):
        """Setup the main UI"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - Pattern list
        left_frame = ttk.LabelFrame(main_frame, text="Patterns", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        
        # Pattern listbox with scrollbar
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.pattern_listbox = tk.Listbox(list_frame, width=20, height=25, 
                                          selectmode=tk.SINGLE, font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, 
                                  command=self.pattern_listbox.yview)
        self.pattern_listbox.config(yscrollcommand=scrollbar.set)
        
        self.pattern_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.pattern_listbox.bind('<<ListboxSelect>>', self.on_pattern_select)
        
        # Pattern buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(btn_frame, text="+", width=3, command=self.new_pattern).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Dup", width=4, command=self.duplicate_pattern).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Del", width=4, command=self.delete_pattern).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Up", width=3, command=self.move_pattern_up).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Dn", width=3, command=self.move_pattern_down).pack(side=tk.LEFT)
        
        # Right panel - Editor
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Top - Pattern properties
        props_frame = ttk.LabelFrame(right_frame, text="Pattern Properties", padding="5")
        props_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Row 1: Name and Circular
        row1 = ttk.Frame(props_frame)
        row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1, text="Name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(row1, textvariable=self.name_var, width=20)
        self.name_entry.pack(side=tk.LEFT, padx=(5, 20))
        self.name_var.trace('w', self.on_property_change)
        
        self.circular_var = tk.BooleanVar()
        ttk.Checkbutton(row1, text="Circular (Loop)", variable=self.circular_var,
                       command=self.on_property_change).pack(side=tk.LEFT)
        
        # Row 2: Sound settings
        row2 = ttk.Frame(props_frame)
        row2.pack(fill=tk.X, pady=2)
        
        self.play_sound_var = tk.BooleanVar()
        ttk.Checkbutton(row2, text="Play Sound", variable=self.play_sound_var,
                       command=self.on_property_change).pack(side=tk.LEFT)
        
        ttk.Label(row2, text="Sound File:").pack(side=tk.LEFT, padx=(20, 5))
        self.sound_file_var = tk.StringVar()
        self.sound_combo = ttk.Combobox(row2, textvariable=self.sound_file_var, width=25, state='readonly')
        self.sound_combo.pack(side=tk.LEFT)
        self.sound_combo.bind('<<ComboboxSelected>>', lambda e: self.on_property_change())
        
        ttk.Label(row2, text="Volume (0-25):").pack(side=tk.LEFT, padx=(20, 5))
        self.sound_level_var = tk.IntVar(value=0)
        self.sound_level_spin = ttk.Spinbox(row2, from_=0, to=25, width=5,
                                            textvariable=self.sound_level_var,
                                            command=self.on_property_change)
        self.sound_level_spin.pack(side=tk.LEFT)
        
        # Test sound button
        ttk.Button(row2, text="Test Sound", width=10, 
                  command=self.test_sound).pack(side=tk.LEFT, padx=(15, 0))
        
        # Middle - LED Preview and Controls
        preview_frame = ttk.LabelFrame(right_frame, text="LED Preview", padding="5")
        preview_frame.pack(fill=tk.X, pady=(0, 5))
        
        # LED Canvas
        self.led_canvas = tk.Canvas(preview_frame, height=80, bg='#1a1a1a')
        self.led_canvas.pack(fill=tk.X, pady=5)
        
        # Vibration indicator
        self.vibration_label = ttk.Label(preview_frame, text="Vibration: OFF", 
                                         font=('Arial', 10, 'bold'))
        self.vibration_label.pack()
        
        # Playback controls
        controls_frame = ttk.Frame(preview_frame)
        controls_frame.pack(fill=tk.X, pady=5)
        
        self.play_btn = ttk.Button(controls_frame, text="Play", command=self.toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(controls_frame, text="Stop", command=self.stop_play).pack(side=tk.LEFT, padx=5)
        
        self.frame_label = ttk.Label(controls_frame, text="Frame: 0/0")
        self.frame_label.pack(side=tk.LEFT, padx=20)
        
        self.time_label = ttk.Label(controls_frame, text="Duration: 0ms")
        self.time_label.pack(side=tk.LEFT, padx=20)
        
        # Bottom - Strip Editor
        editor_frame = ttk.LabelFrame(right_frame, text="Strip Frames Editor", padding="5")
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        # Strip list with scrollbar
        self.strip_canvas = tk.Canvas(editor_frame, bg='#2d2d2d')
        strip_scrollbar_y = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL, 
                                          command=self.strip_canvas.yview)
        strip_scrollbar_x = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL,
                                          command=self.strip_canvas.xview)
        
        self.strip_inner_frame = ttk.Frame(self.strip_canvas)
        
        self.strip_canvas.configure(yscrollcommand=strip_scrollbar_y.set,
                                    xscrollcommand=strip_scrollbar_x.set)
        
        strip_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        strip_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.strip_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.strip_window = self.strip_canvas.create_window((0, 0), window=self.strip_inner_frame, 
                                                            anchor=tk.NW)
        
        self.strip_inner_frame.bind('<Configure>', self.on_strip_frame_configure)
        self.strip_canvas.bind('<Configure>', self.on_canvas_configure)
        
        # Strip buttons
        strip_btn_frame = ttk.Frame(editor_frame)
        strip_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(strip_btn_frame, text="Add Frame", command=self.add_strip_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(strip_btn_frame, text="Delete Selected", command=self.delete_strip_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(strip_btn_frame, text="Duplicate Selected", command=self.duplicate_strip_frame).pack(side=tk.LEFT, padx=2)
        ttk.Button(strip_btn_frame, text="Move Up", command=self.move_strip_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(strip_btn_frame, text="Move Down", command=self.move_strip_down).pack(side=tk.LEFT, padx=2)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready - Open a sync_files folder to begin")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Initialize LED display
        self.draw_leds([['0x000000'] * 8 + ['0', '0']])
        
        # Track selected strip frame
        self.selected_strip_index = None
        self.strip_widgets = []
        
    def on_strip_frame_configure(self, event):
        """Update scroll region when strip frame changes"""
        self.strip_canvas.configure(scrollregion=self.strip_canvas.bbox('all'))
        
    def on_canvas_configure(self, event):
        """Update window width when canvas resizes"""
        self.strip_canvas.itemconfig(self.strip_window, width=event.width)

    def open_sync_folder(self):
        """Open a sync_files folder"""
        if self.modified:
            if not messagebox.askyesno("Unsaved Changes", 
                                       "You have unsaved changes. Continue?"):
                return
        
        folder = filedialog.askdirectory(title="Select sync_files folder")
        if folder:
            self.load_sync_folder(folder)
    
    def load_sync_folder(self, folder):
        """Load the sync_files folder"""
        # Check if val.json exists
        json_path = os.path.join(folder, 'val.json')
        if not os.path.exists(json_path):
            messagebox.showerror("Error", f"val.json not found in:\n{folder}")
            return
        
        # Load JSON
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load val.json:\n{e}")
            return
        
        self.sync_files_dir = folder
        self.json_file_path = json_path
        self.modified = False
        
        # Scan for MP3 files
        self.scan_mp3_files()
        
        # Update UI
        self.populate_pattern_list()
        self.update_sound_combo()
        
        # Select first pattern
        if self.data.get('PlayPatterns'):
            self.pattern_listbox.selection_set(0)
            self.on_pattern_select(None)
        
        self.status_var.set(f"Loaded: {folder}")
        self.update_title()
    
    def scan_mp3_files(self):
        """Scan sync_files folder for MP3 files"""
        self.available_mp3s = ['']  # Empty option for no sound
        
        if not self.sync_files_dir:
            return
        
        for filename in os.listdir(self.sync_files_dir):
            if filename.lower().endswith('.mp3'):
                # Store in ESP32 format: /filename.mp3
                self.available_mp3s.append('/' + filename)
        
        self.available_mp3s.sort()
    
    def update_sound_combo(self):
        """Update the sound file combobox with available MP3s"""
        self.sound_combo['values'] = self.available_mp3s
    
    def save_file(self):
        """Save the current file"""
        if not self.json_file_path:
            messagebox.showerror("Error", "No file loaded. Open a sync_files folder first.")
            return
            
        self.save_current_pattern()
        
        try:
            with open(self.json_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4)
            self.modified = False
            self.update_title()
            self.status_var.set(f"Saved: {self.json_file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")
            
    def populate_pattern_list(self):
        """Populate the pattern listbox"""
        self.pattern_listbox.delete(0, tk.END)
        
        if not self.data or 'PlayPatterns' not in self.data:
            return
            
        for pattern in self.data['PlayPatterns']:
            name = pattern.get('PatternName', 'Unnamed')
            self.pattern_listbox.insert(tk.END, name)
            
    def on_pattern_select(self, event):
        """Handle pattern selection"""
        selection = self.pattern_listbox.curselection()
        if not selection:
            return
            
        # Save current pattern before switching
        if self.current_pattern_index is not None and self.data:
            self.save_current_pattern()
            
        self.current_pattern_index = selection[0]
        self.load_pattern(self.current_pattern_index)
        
    def load_pattern(self, index):
        """Load a pattern into the editor"""
        if not self.data or index >= len(self.data['PlayPatterns']):
            return
            
        pattern = self.data['PlayPatterns'][index]
        
        # Update properties
        self.name_var.set(pattern.get('PatternName', ''))
        self.circular_var.set(pattern.get('Circular', False))
        self.play_sound_var.set(pattern.get('PlaySound', False))
        
        # Set sound file (ensure it's in the list)
        sound_file = pattern.get('SoundFile', '')
        if sound_file and sound_file not in self.available_mp3s:
            # File referenced but not found - show warning
            self.status_var.set(f"Warning: Sound file not found: {sound_file}")
        self.sound_file_var.set(sound_file)
        
        self.sound_level_var.set(pattern.get('SoundLevel', 0))
        
        # Load strips
        self.load_strips(pattern.get('Strips', []))
        
        # Update LED preview with first frame
        strips = pattern.get('Strips', [])
        if strips:
            self.draw_leds(strips)
            
    def save_current_pattern(self):
        """Save the current pattern from UI to data"""
        if not self.data or self.current_pattern_index is None:
            return
            
        if self.current_pattern_index >= len(self.data['PlayPatterns']):
            return
            
        pattern = self.data['PlayPatterns'][self.current_pattern_index]
        
        pattern['PatternName'] = self.name_var.get()
        pattern['Circular'] = self.circular_var.get()
        pattern['PlaySound'] = self.play_sound_var.get()
        pattern['SoundFile'] = self.sound_file_var.get()  # Already in /filename.mp3 format
        pattern['SoundLevel'] = self.sound_level_var.get()
        
        # Save strips from widgets
        strips = []
        for widget_data in self.strip_widgets:
            strip = []
            for i in range(8):
                color = widget_data['colors'][i].get()
                strip.append(color)
            strip.append(widget_data['duration'].get())
            strip.append(widget_data['vibration'].get())
            strips.append(strip)
            
        pattern['Strips'] = strips
        
        # Update listbox
        self.pattern_listbox.delete(self.current_pattern_index)
        self.pattern_listbox.insert(self.current_pattern_index, pattern['PatternName'])
        self.pattern_listbox.selection_set(self.current_pattern_index)
        
    def load_strips(self, strips):
        """Load strip frames into the editor"""
        # Clear existing widgets
        for widget in self.strip_inner_frame.winfo_children():
            widget.destroy()
        self.strip_widgets = []
        self.selected_strip_index = None
        
        for i, strip in enumerate(strips):
            self.add_strip_widget(i, strip)
            
    def add_strip_widget(self, index, strip_data=None):
        """Add a strip frame widget"""
        if strip_data is None:
            strip_data = ['0x000000'] * 8 + ['100', '0']
        
        # Use tk.Frame instead of ttk.Frame for better color control
        frame = tk.Frame(self.strip_inner_frame, relief=tk.RIDGE, borderwidth=2,
                        bg='#3d3d3d', highlightthickness=3, highlightbackground='#3d3d3d')
        frame.pack(fill=tk.X, pady=2, padx=2)
        
        # Store widget data
        widget_data = {
            'frame': frame,
            'colors': [],
            'buttons': [],
            'duration': tk.StringVar(value=strip_data[8] if len(strip_data) > 8 else '100'),
            'vibration': tk.StringVar(value=strip_data[9] if len(strip_data) > 9 else '0')
        }
        
        # Frame index label
        index_label = tk.Label(frame, text=f"#{index+1}", width=4, bg='#3d3d3d', fg='white',
                              font=('Arial', 10, 'bold'))
        index_label.pack(side=tk.LEFT, padx=2)
        widget_data['index_label'] = index_label
        
        # LED buttons container
        led_frame = tk.Frame(frame, bg='#3d3d3d')
        led_frame.pack(side=tk.LEFT, padx=5)
        widget_data['led_frame'] = led_frame
        
        for i in range(8):
            color_var = tk.StringVar(value=strip_data[i] if i < len(strip_data) else '0x000000')
            widget_data['colors'].append(color_var)
            
            # Get display color (brightened for visibility)
            display_color = self.get_display_color(color_var.get())
            
            btn = tk.Button(led_frame, width=4, height=2, 
                           bg=display_color,
                           activebackground=display_color,
                           command=lambda idx=len(self.strip_widgets), led=i: self.pick_color(idx, led))
            btn.pack(side=tk.LEFT, padx=1)
            widget_data['buttons'].append(btn)
            
            # Add tooltip showing color value
            ToolTip(btn, lambda cv=color_var: self.get_color_tooltip(cv.get()))
        
        # Duration label and entry with up/down buttons
        dur_label = tk.Label(frame, text="ms:", bg='#3d3d3d', fg='white')
        dur_label.pack(side=tk.LEFT, padx=(10, 2))
        widget_data['dur_label'] = dur_label
        
        # Down button
        dur_down_btn = tk.Button(frame, text="◀", width=2, bg='#555555', fg='white',
                                activebackground='#666666', activeforeground='white',
                                command=lambda idx=len(self.strip_widgets): self.adjust_duration(idx, -10))
        dur_down_btn.pack(side=tk.LEFT)
        widget_data['dur_down_btn'] = dur_down_btn
        
        dur_entry = tk.Entry(frame, textvariable=widget_data['duration'], width=6,
                            bg='#2d2d2d', fg='white', insertbackground='white', justify='center')
        dur_entry.pack(side=tk.LEFT)
        dur_entry.bind('<KeyRelease>', lambda e: self.mark_modified())
        widget_data['dur_entry'] = dur_entry
        
        # Up button
        dur_up_btn = tk.Button(frame, text="▶", width=2, bg='#555555', fg='white',
                              activebackground='#666666', activeforeground='white',
                              command=lambda idx=len(self.strip_widgets): self.adjust_duration(idx, 10))
        dur_up_btn.pack(side=tk.LEFT)
        widget_data['dur_up_btn'] = dur_up_btn
        
        # Vibration label and combobox
        vib_label = tk.Label(frame, text="Vib:", bg='#3d3d3d', fg='white')
        vib_label.pack(side=tk.LEFT, padx=(10, 2))
        widget_data['vib_label'] = vib_label
        
        vib_combo = ttk.Combobox(frame, textvariable=widget_data['vibration'], 
                                 values=['0', '1'], width=3, state='readonly')
        vib_combo.pack(side=tk.LEFT)
        vib_combo.bind('<<ComboboxSelected>>', lambda e: self.mark_modified())
        widget_data['vib_combo'] = vib_combo
        
        # Select button
        select_btn = tk.Button(frame, text="Select", width=6, bg='#555555', fg='white',
                              activebackground='#666666', activeforeground='white',
                              command=lambda idx=len(self.strip_widgets): self.select_strip(idx))
        select_btn.pack(side=tk.LEFT, padx=10)
        widget_data['select_btn'] = select_btn
        
        # Click to select (bind to frame and all child widgets)
        frame.bind('<Button-1>', lambda e, idx=len(self.strip_widgets): self.select_strip(idx))
        index_label.bind('<Button-1>', lambda e, idx=len(self.strip_widgets): self.select_strip(idx))
        led_frame.bind('<Button-1>', lambda e, idx=len(self.strip_widgets): self.select_strip(idx))
        dur_label.bind('<Button-1>', lambda e, idx=len(self.strip_widgets): self.select_strip(idx))
        vib_label.bind('<Button-1>', lambda e, idx=len(self.strip_widgets): self.select_strip(idx))
        
        self.strip_widgets.append(widget_data)
        
    def select_strip(self, index):
        """Select a strip frame"""
        # Deselect previous
        if self.selected_strip_index is not None and self.selected_strip_index < len(self.strip_widgets):
            self._style_strip_frame(self.selected_strip_index, selected=False)
            
        # Select new
        self.selected_strip_index = index
        self._style_strip_frame(index, selected=True)
        
        # Update preview
        colors = [w.get() for w in self.strip_widgets[index]['colors']]
        duration = self.strip_widgets[index]['duration'].get()
        vibration = self.strip_widgets[index]['vibration'].get()
        self.draw_leds([[*colors, duration, vibration]])
    
    def _style_strip_frame(self, index, selected=False):
        """Apply visual styling to a strip frame"""
        widget_data = self.strip_widgets[index]
        frame = widget_data['frame']
        
        if selected:
            # Selected: orange border, darker background
            bg_color = '#2a2a2a'
            border_color = '#ff8c00'  # Orange
            fg_color = '#ffffff'
            frame.configure(highlightbackground=border_color, highlightcolor=border_color,
                          bg=bg_color, relief=tk.SOLID)
        else:
            # Not selected: normal gray
            bg_color = '#3d3d3d'
            border_color = '#3d3d3d'
            fg_color = '#ffffff'
            frame.configure(highlightbackground=border_color, highlightcolor=border_color,
                          bg=bg_color, relief=tk.RIDGE)
        
        # Update child widget backgrounds
        if 'index_label' in widget_data:
            widget_data['index_label'].configure(bg=bg_color, fg=fg_color)
        if 'led_frame' in widget_data:
            widget_data['led_frame'].configure(bg=bg_color)
        if 'dur_label' in widget_data:
            widget_data['dur_label'].configure(bg=bg_color, fg=fg_color)
        if 'vib_label' in widget_data:
            widget_data['vib_label'].configure(bg=bg_color, fg=fg_color)
        if 'select_btn' in widget_data:
            if selected:
                widget_data['select_btn'].configure(bg='#ff8c00', fg='black',
                                                   activebackground='#ffa500')
            else:
                widget_data['select_btn'].configure(bg='#555555', fg='white',
                                                   activebackground='#666666')
    
    def adjust_duration(self, strip_index, delta):
        """Adjust duration value by delta (in ms)"""
        if strip_index >= len(self.strip_widgets):
            return
        
        widget_data = self.strip_widgets[strip_index]
        try:
            current = int(widget_data['duration'].get())
        except ValueError:
            current = 100
        
        # Calculate new value, minimum 10ms
        new_value = max(10, current + delta)
        widget_data['duration'].set(str(new_value))
        self.mark_modified()
        
    def pick_color(self, strip_index, led_index):
        """Open color picker for LED"""
        current = self.strip_widgets[strip_index]['colors'][led_index].get()
        initial = self.hex_to_rgb(current)
        
        color = colorchooser.askcolor(color=initial, title=f"Pick color for LED {led_index+1}")
        
        if color[0]:
            r, g, b = [int(c) for c in color[0]]
            hex_color = f"0x{r:02x}{g:02x}{b:02x}"
            
            self.strip_widgets[strip_index]['colors'][led_index].set(hex_color)
            
            # Use brightened color for display
            display_color = self.get_display_color(hex_color)
            self.strip_widgets[strip_index]['buttons'][led_index].configure(
                bg=display_color,
                activebackground=display_color
            )
            self.mark_modified()
            
            # Update preview if this strip is selected
            if self.selected_strip_index == strip_index:
                self.select_strip(strip_index)
                
    def hex_to_rgb(self, hex_str):
        """Convert hex string (0xRRGGBB) to RGB format (#RRGGBB)"""
        try:
            hex_str = hex_str.replace('0x', '').replace('#', '')
            if len(hex_str) == 6:
                return f"#{hex_str}"
            return "#000000"
        except:
            return "#000000"
    
    def get_display_color(self, hex_str):
        """Get a visible display color for buttons - brightens very dark colors"""
        try:
            hex_str = hex_str.replace('0x', '').replace('#', '')
            if len(hex_str) != 6:
                return "#000000"
            
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            
            # If it's pure black, keep it black
            if r == 0 and g == 0 and b == 0:
                return "#000000"
            
            # Calculate brightness (perceived luminance)
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            
            # If the color is very dark (but not black), brighten it for display
            # This makes colors like 0x001000 visible while preserving the hue
            if brightness < 40:
                # Scale up the color to be more visible
                max_val = max(r, g, b)
                if max_val > 0:
                    # Boost to at least 80 brightness in the dominant channel
                    scale = max(80 / max_val, 1)
                    r = min(255, int(r * scale))
                    g = min(255, int(g * scale))
                    b = min(255, int(b * scale))
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return "#000000"
    
    def get_color_tooltip(self, hex_str):
        """Generate tooltip text for a color value"""
        try:
            hex_str_clean = hex_str.replace('0x', '').replace('#', '')
            if len(hex_str_clean) != 6:
                return "Invalid color"
            
            r = int(hex_str_clean[0:2], 16)
            g = int(hex_str_clean[2:4], 16)
            b = int(hex_str_clean[4:6], 16)
            
            # Format the tooltip
            lines = [
                f"Color: {hex_str}",
                f"R: {r}  G: {g}  B: {b}"
            ]
            
            # Add color name hint for common colors
            if r == 0 and g == 0 and b == 0:
                lines.append("(Black/Off)")
            elif r == 255 and g == 0 and b == 0:
                lines.append("(Red)")
            elif r == 0 and g == 255 and b == 0:
                lines.append("(Green)")
            elif r == 0 and g == 0 and b == 255:
                lines.append("(Blue)")
            elif r == 255 and g == 255 and b == 0:
                lines.append("(Yellow)")
            elif r == 255 and g == 255 and b == 255:
                lines.append("(White)")
            elif r == g == b:
                lines.append("(Gray)")
            elif g > r and g > b:
                lines.append("(Green tint)")
            elif r > g and r > b:
                lines.append("(Red tint)")
            elif b > r and b > g:
                lines.append("(Blue tint)")
            
            return "\n".join(lines)
        except:
            return hex_str
            
    def draw_leds(self, strips, frame_index=0):
        """Draw LEDs on the canvas"""
        self.led_canvas.delete('all')
        
        if not strips or frame_index >= len(strips):
            return
            
        strip = strips[frame_index]
        canvas_width = self.led_canvas.winfo_width()
        if canvas_width < 10:
            canvas_width = 600
            
        total_width = 8 * self.led_size + 7 * self.led_spacing
        start_x = (canvas_width - total_width) // 2
        y = 15
        
        for i in range(8):
            if i < len(strip):
                color = self.hex_to_rgb(strip[i])
            else:
                color = "#000000"
                
            x = start_x + i * (self.led_size + self.led_spacing)
            
            # Draw LED glow effect
            glow_color = self.lighten_color(color, 0.3)
            self.led_canvas.create_oval(x-5, y-5, x+self.led_size+5, y+self.led_size+5,
                                        fill=glow_color, outline='')
            
            # Draw LED
            self.led_canvas.create_oval(x, y, x+self.led_size, y+self.led_size,
                                        fill=color, outline='#333333', width=2)
            
            # LED number
            self.led_canvas.create_text(x + self.led_size//2, y + self.led_size//2,
                                        text=str(i+1), fill='#666666', font=('Arial', 10))
            
        # Update frame info
        duration = strip[8] if len(strip) > 8 else '0'
        vibration = strip[9] if len(strip) > 9 else '0'
        
        self.frame_label.config(text=f"Frame: {frame_index+1}/{len(strips)}")
        self.time_label.config(text=f"Duration: {duration}ms")
        
        if vibration == '1':
            self.vibration_label.config(text="Vibration: ON", foreground='red')
        else:
            self.vibration_label.config(text="Vibration: OFF", foreground='gray')
            
    def lighten_color(self, color, factor=0.3):
        """Lighten a color for glow effect"""
        try:
            color = color.replace('#', '')
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            
            r = min(255, int(r + (255 - r) * factor))
            g = min(255, int(g + (255 - g) * factor))
            b = min(255, int(b + (255 - b) * factor))
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return "#333333"
            
    def toggle_play(self):
        """Toggle pattern playback"""
        if self.playing:
            self.stop_play()
        else:
            self.start_play()
            
    def start_play(self):
        """Start playing the current pattern"""
        if not self.data or self.current_pattern_index is None:
            return
            
        self.save_current_pattern()
        pattern = self.data['PlayPatterns'][self.current_pattern_index]
        strips = pattern.get('Strips', [])
        
        if not strips:
            return
            
        self.playing = True
        self.play_btn.config(text="Pause")
        
        circular = pattern.get('Circular', False)
        
        # Start sound if enabled (loop if circular)
        if pattern.get('PlaySound') and AUDIO_BACKEND:
            sound_file = pattern.get('SoundFile', '')
            if sound_file:
                self.play_sound(sound_file, pattern.get('SoundLevel', 5), loop=circular)
                
        # Start animation thread
        self.play_thread = threading.Thread(target=self.play_animation, 
                                            args=(strips, circular),
                                            daemon=True)
        self.play_thread.start()
        
    def stop_play(self):
        """Stop playing"""
        self.playing = False
        self.play_btn.config(text="Play")
        
        # Stop audio using the audio player
        audio_player.stop()
                
    def play_animation(self, strips, circular):
        """Animation thread"""
        frame = 0
        
        while self.playing:
            if frame >= len(strips):
                if circular:
                    frame = 0
                else:
                    self.playing = False
                    break
                    
            # Update UI from main thread
            self.root.after(0, lambda f=frame: self.draw_leds(strips, f))
            
            # Get duration
            try:
                duration = int(strips[frame][8]) / 1000  # Convert ms to seconds
            except:
                duration = 0.1
                
            time.sleep(duration)
            frame += 1
            
        # Reset button
        self.root.after(0, lambda: self.play_btn.config(text="Play"))
        
    def play_sound(self, sound_file, level, loop=False):
        """Play sound file from sync_files directory"""
        if not AUDIO_BACKEND:
            error_msg = "No audio backend available.\n\nInstall with:\n  pip install playsound"
            self.status_var.set("No audio backend available")
            messagebox.showwarning("Audio Unavailable", error_msg)
            return False
        
        if not self.sync_files_dir:
            self.status_var.set("No sync_files folder loaded")
            messagebox.showerror("Error", "No sync_files folder loaded")
            return False
        
        # Handle empty sound file
        if not sound_file or sound_file.strip() == '':
            self.status_var.set("No sound file specified")
            return False
        
        # Convert ESP32 path (/filename.mp3) to local path
        if sound_file.startswith('/'):
            filename = sound_file[1:]  # Remove leading slash
        else:
            filename = sound_file
        
        full_path = os.path.join(self.sync_files_dir, filename)
        
        # Check if file exists
        if not os.path.exists(full_path):
            error_msg = f"MP3 file not found:\n{full_path}\n\nMake sure the file exists in the sync_files folder."
            self.status_var.set(f"File not found: {filename}")
            messagebox.showerror("File Not Found", error_msg)
            return False
        
        # Check file size (basic validation)
        file_size = os.path.getsize(full_path)
        if file_size == 0:
            error_msg = f"MP3 file is empty:\n{full_path}"
            self.status_var.set(f"Empty file: {filename}")
            messagebox.showerror("Invalid File", error_msg)
            return False
        
        # Play using the audio player
        success, message = audio_player.play(full_path, loop=loop)
        
        loop_text = " [looping]" if loop else ""
        if success:
            self.status_var.set(f"Playing: {filename}{loop_text} ({AUDIO_BACKEND})")
            return True
        else:
            self.status_var.set(f"Error: {message}")
            messagebox.showerror("Playback Error", f"Failed to play:\n{full_path}\n\n{message}")
            return False
    
    def test_sound(self):
        """Test the currently selected sound file"""
        sound_file = self.sound_file_var.get()
        if not sound_file:
            messagebox.showinfo("Test Sound", "No sound file selected.\n\nSelect a sound file from the dropdown first.")
            return
        
        level = self.sound_level_var.get()
        self.play_sound(sound_file, level)
                
    def new_pattern(self):
        """Create a new pattern"""
        if not self.data:
            self.data = {'PlayPatterns': []}
            
        new_pattern = {
            'PatternName': f'NewPattern{len(self.data["PlayPatterns"])+1}',
            'Circular': False,
            'Strips': [['0x000000'] * 8 + ['100', '0']],
            'PlaySound': False,
            'SoundFile': '',
            'SoundLevel': 0
        }
        
        self.data['PlayPatterns'].append(new_pattern)
        self.populate_pattern_list()
        
        # Select the new pattern
        self.pattern_listbox.selection_clear(0, tk.END)
        self.pattern_listbox.selection_set(tk.END)
        self.on_pattern_select(None)
        self.mark_modified()
        
    def duplicate_pattern(self):
        """Duplicate the current pattern"""
        if not self.data or self.current_pattern_index is None:
            return
            
        self.save_current_pattern()
        
        import copy
        pattern = copy.deepcopy(self.data['PlayPatterns'][self.current_pattern_index])
        pattern['PatternName'] += '_copy'
        
        self.data['PlayPatterns'].append(pattern)
        self.populate_pattern_list()
        
        self.pattern_listbox.selection_clear(0, tk.END)
        self.pattern_listbox.selection_set(tk.END)
        self.on_pattern_select(None)
        self.mark_modified()
        
    def delete_pattern(self):
        """Delete the current pattern"""
        if not self.data or self.current_pattern_index is None:
            return
            
        if len(self.data['PlayPatterns']) <= 1:
            messagebox.showwarning("Warning", "Cannot delete the last pattern")
            return
            
        if not messagebox.askyesno("Confirm", "Delete this pattern?"):
            return
            
        del self.data['PlayPatterns'][self.current_pattern_index]
        self.populate_pattern_list()
        
        # Select previous or first
        new_index = max(0, self.current_pattern_index - 1)
        self.pattern_listbox.selection_set(new_index)
        self.on_pattern_select(None)
        self.mark_modified()
        
    def move_pattern_up(self):
        """Move pattern up in list"""
        if not self.data or self.current_pattern_index is None or self.current_pattern_index == 0:
            return
            
        self.save_current_pattern()
        idx = self.current_pattern_index
        self.data['PlayPatterns'][idx], self.data['PlayPatterns'][idx-1] = \
            self.data['PlayPatterns'][idx-1], self.data['PlayPatterns'][idx]
            
        self.populate_pattern_list()
        self.pattern_listbox.selection_set(idx - 1)
        self.current_pattern_index = idx - 1
        self.mark_modified()
        
    def move_pattern_down(self):
        """Move pattern down in list"""
        if not self.data or self.current_pattern_index is None:
            return
        if self.current_pattern_index >= len(self.data['PlayPatterns']) - 1:
            return
            
        self.save_current_pattern()
        idx = self.current_pattern_index
        self.data['PlayPatterns'][idx], self.data['PlayPatterns'][idx+1] = \
            self.data['PlayPatterns'][idx+1], self.data['PlayPatterns'][idx]
            
        self.populate_pattern_list()
        self.pattern_listbox.selection_set(idx + 1)
        self.current_pattern_index = idx + 1
        self.mark_modified()
        
    def add_strip_frame(self):
        """Add a new strip frame"""
        if not self.data or self.current_pattern_index is None:
            return
            
        # Add to UI
        new_index = len(self.strip_widgets)
        self.add_strip_widget(new_index)
        
        # Update scroll region
        self.strip_inner_frame.update_idletasks()
        self.strip_canvas.configure(scrollregion=self.strip_canvas.bbox('all'))
        
        self.mark_modified()
        
    def delete_strip_frame(self):
        """Delete selected strip frame"""
        if self.selected_strip_index is None or len(self.strip_widgets) <= 1:
            if len(self.strip_widgets) <= 1:
                messagebox.showwarning("Warning", "Cannot delete the last frame")
            return
            
        # Remove widget
        self.strip_widgets[self.selected_strip_index]['frame'].destroy()
        del self.strip_widgets[self.selected_strip_index]
        
        # Renumber frames
        self.renumber_strips()
        
        self.selected_strip_index = None
        self.mark_modified()
        
    def duplicate_strip_frame(self):
        """Duplicate selected strip frame"""
        if self.selected_strip_index is None:
            return
            
        # Get current data
        src = self.strip_widgets[self.selected_strip_index]
        strip_data = [c.get() for c in src['colors']] + [src['duration'].get(), src['vibration'].get()]
        
        # Add new
        new_index = len(self.strip_widgets)
        self.add_strip_widget(new_index, strip_data)
        
        self.strip_inner_frame.update_idletasks()
        self.strip_canvas.configure(scrollregion=self.strip_canvas.bbox('all'))
        
        self.mark_modified()
        
    def move_strip_up(self):
        """Move selected strip up"""
        if self.selected_strip_index is None or self.selected_strip_index == 0:
            return
            
        idx = self.selected_strip_index
        self.strip_widgets[idx], self.strip_widgets[idx-1] = \
            self.strip_widgets[idx-1], self.strip_widgets[idx]
            
        self.rebuild_strip_display()
        self.selected_strip_index = idx - 1
        self.strip_widgets[self.selected_strip_index]['frame'].configure(relief=tk.SOLID)
        self.mark_modified()
        
    def move_strip_down(self):
        """Move selected strip down"""
        if self.selected_strip_index is None or self.selected_strip_index >= len(self.strip_widgets) - 1:
            return
            
        idx = self.selected_strip_index
        self.strip_widgets[idx], self.strip_widgets[idx+1] = \
            self.strip_widgets[idx+1], self.strip_widgets[idx]
            
        self.rebuild_strip_display()
        self.selected_strip_index = idx + 1
        self.strip_widgets[self.selected_strip_index]['frame'].configure(relief=tk.SOLID)
        self.mark_modified()
        
    def rebuild_strip_display(self):
        """Rebuild strip display after reordering"""
        # Save current data
        strips_data = []
        for widget_data in self.strip_widgets:
            strip = [c.get() for c in widget_data['colors']] + \
                    [widget_data['duration'].get(), widget_data['vibration'].get()]
            strips_data.append(strip)
            
        # Clear and rebuild
        for widget in self.strip_inner_frame.winfo_children():
            widget.destroy()
        self.strip_widgets = []
        
        for i, strip in enumerate(strips_data):
            self.add_strip_widget(i, strip)
            
    def renumber_strips(self):
        """Renumber strip frames after deletion"""
        # Save all data
        strips_data = []
        for widget_data in self.strip_widgets:
            strip = [c.get() for c in widget_data['colors']] + \
                    [widget_data['duration'].get(), widget_data['vibration'].get()]
            strips_data.append(strip)
            
        # Clear and rebuild
        for widget in self.strip_inner_frame.winfo_children():
            widget.destroy()
        self.strip_widgets = []
        
        for i, strip in enumerate(strips_data):
            self.add_strip_widget(i, strip)
            
    def on_property_change(self, *args):
        """Handle property changes"""
        self.mark_modified()
        
    def mark_modified(self):
        """Mark document as modified"""
        self.modified = True
        self.update_title()
    
    def update_title(self):
        """Update window title"""
        title = "ESP32 LED Pattern Editor"
        if self.sync_files_dir:
            title += f" - {os.path.basename(self.sync_files_dir)}"
        if self.modified:
            title += " *"
        self.root.title(title)
        
    def on_close(self):
        """Handle window close"""
        if self.modified:
            result = messagebox.askyesnocancel("Unsaved Changes", 
                                               "Save changes before closing?")
            if result is None:  # Cancel
                return
            if result:  # Yes
                self.save_file()
                
        self.playing = False
        audio_player.stop()
        
        # Cleanup pygame if it was used
        if AUDIO_BACKEND == "pygame":
            try:
                pygame.mixer.quit()
            except:
                pass
        
        self.root.destroy()


def main():
    # Check command line arguments
    sync_dir = None
    if len(sys.argv) > 1:
        sync_dir = sys.argv[1]
        if not os.path.isdir(sync_dir):
            print(f"Error: Directory not found: {sync_dir}")
            print("Usage: python led_pattern_editor.py [sync_files_directory]")
            sys.exit(1)
    
    root = tk.Tk()
    app = LEDPatternEditor(root, sync_dir)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == '__main__':
    main()