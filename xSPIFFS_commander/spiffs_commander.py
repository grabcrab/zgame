#!/usr/bin/env python3
"""
ESP32 SPIFFS Manager GUI
Windows GUI application for managing ESP32 SPIFFS filesystem
"""
VERSION = "v.027"  #  <── incremented on every program update

import os
import json
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import csv
from pathlib import Path
import serial.tools.list_ports
import threading
from datetime import datetime

# ------------------------------------------------------------------
#  Main application class
# ------------------------------------------------------------------
class ESP32SPIFFSManager:
    def __init__(self, root):
        self.root = root
        self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        # Configuration
        self.config_file = "spiffs_config.json"
        self.load_config()

        # keep chip variable even though the UI element is hidden
        self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

        # --------------------------------------------------------------
        #  SPIFFS partition information (now loaded from ESP32)
        # --------------------------------------------------------------
        self.spiffs_partitions = []          # list of dicts: {name, offset, size}
        self.current_spiffs_index = 0       # index inside self.spiffs_partitions

        # State variables
        self.connected = False
        self.current_files = {}       # filename → content (text content or empty for non‑text)
        self.selected_file = None     # filename currently in editor
        self.spiffs_downloaded = False
        self.editor_modified = False  # True while editor has unsaved changes

        # Define which extensions are editable in the text editor
        self.text_extensions = {
            '.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'
        }

        # Create GUI
        self.create_widgets()
        self.scan_ports()

        # Ask on unsaved changes when user closes window
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

        # Check required files on startup
        self.check_dependencies()

    # ------------------------------------------------------------------
    #  NEW:  generic "ask unsaved" helper  (returns True = proceed, False = abort)
    # ------------------------------------------------------------------
    def ask_unsaved_changes(self, action: str = "switch file"):
        """Return True if the caller may continue, False if user chose Cancel."""
        if not self.editor_modified:
            return True

        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f'File "{self.selected_file}" has unsaved changes.\n\n'
            f'Save before {action}?',
            default=messagebox.YES
        )
        if answer is True:          # Save
            self.save_current_file()
            return True
        elif answer is False:       # Discard
            return True
        else:                       # Cancel
            return False

    # ------------------------------------------------------------------
    #  Small helpers (unchanged)
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_int(value):
        """Return int whether value is already int or decimal/hex string."""
        if isinstance(value, int):
            return value
        return int(value, 0)          # 0 → auto-detect base (handles 0x...)

    def load_config(self):
        default_config = {
            "spiffs_offset": 6750208,  # 0x670000
            "spiffs_size": 1572864,    # 0x180000
            "esp32_chip": "esp32-s3",
            "baud_rate": "921600",
            "last_port": ""
        }
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                for key, value in default_config.items():
                    if key not in self.config:
                        self.config[key] = value
            else:
                self.config = default_config
                self.save_config()
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = default_config
            self.save_config()

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def format_value_for_display(self, value):
        if isinstance(value, int):
            return f"0x{value:X}"
        return str(value)

    def parse_value_from_input(self, value_str):
        value_str = value_str.strip()
        if value_str.lower().startswith('0x'):
            return int(value_str, 16)
        else:
            return int(value_str)

    def validate_config_input(self, value_str, field_name):
        try:
            return self.parse_value_from_input(value_str)
        except ValueError:
            messagebox.showerror("Invalid Input",
                               f"Invalid {field_name} value: {value_str}\n"
                               f"Please enter a decimal number or hex value (0x...)")
            return None

    # ------------------------------------------------------------------
    #  NEW:  Read partition table from ESP32
    # ------------------------------------------------------------------
    def read_partition_table_from_esp32(self):
        """Read and parse partition table from connected ESP32"""
        esp = None
        try:
            import esptool

            port = self.get_selected_port()
            if not port:
                raise Exception("No COM port selected")

            print(f"Connecting to ESP32 on port {port}...")

            # Connect to ESP32
            esp = esptool.get_default_connected_device(
                serial_list=[port],
                port=port,
                connect_attempts=7,
                initial_baud=115200
            )

            if not esp:
                raise Exception("Failed to connect to ESP32")

            # Detect chip model and extract base chip type
            chip_description = esp.get_chip_description()
            print(f"Chip detected: {chip_description}")
            chip_model = self.extract_chip_model(chip_description)
            print(f"Extracted chip model: {chip_model}")
            self.chip_var.set(chip_model)
            self.config["esp32_chip"] = chip_model
            self.save_config()
            self.chip_display_var.set(chip_description)

            # Read partition table
            PARTITION_TABLE_OFFSET = 0x8000
            PARTITION_TABLE_SIZE = 0xC00  # 3KB

            print(f"Reading partition table from offset 0x{PARTITION_TABLE_OFFSET:X}...")
            esp = esp.run_stub()
            partition_data = esp.read_flash(PARTITION_TABLE_OFFSET, PARTITION_TABLE_SIZE)
            print(f"Successfully read {len(partition_data)} bytes of partition table")

            # Parse partition table
            partitions = self.parse_partition_table(partition_data)
            print(f"Parsed {len(partitions)} partitions from table")

            # Filter only SPIFFS partitions
            spiffs_partitions = []
            for p in partitions:
                if p['subtype'].lower() == 'spiffs':
                    # Convert hex strings to integers
                    offset = int(p['offset'], 0) if isinstance(p['offset'], str) else p['offset']
                    size = int(p['size'], 0) if isinstance(p['size'], str) else p['size']
                    spiffs_partitions.append({
                        "name": p['name'],
                        "offset": offset,
                        "size": size
                    })
                    print(f"Found SPIFFS partition: {p['name']} at 0x{offset:X}, size 0x{size:X}")

            if not spiffs_partitions:
                raise Exception("No SPIFFS partitions found in partition table")

            return spiffs_partitions

        except ImportError:
            raise Exception("esptool library not found. Please install it: pip install esptool")
        except Exception as e:
            raise Exception(f"Failed to read partition table: {str(e)}")
        finally:
            # Ensure the connection is properly closed
            if esp is not None:
                try:
                    esp._port.close()
                    print("ESP32 connection closed successfully")
                except Exception as e:
                    print(f"Error closing ESP32 connection: {e}")

    def extract_chip_model(self, chip_description):
        """Extract base chip model from full chip description"""
        # Common ESP32 chip models
        chip_models = ['esp32-s2', 'esp32-s3', 'esp32-c3', 'esp32-c6', 'esp32']

        # Convert to lowercase for comparison
        desc_lower = chip_description.lower()

        # Check for specific chip models
        for model in chip_models:
            if model in desc_lower:
                return model

        # Default fallback
        return 'esp32'

    def parse_partition_table(self, data):
        """Parse binary partition table data"""
        partitions = []
        offset = 0

        # MD5 hash is at the end, partition entries are 32 bytes each
        while offset < len(data) - 32:
            entry = data[offset:offset + 32]

            # Check for end marker (all 0xFF) or empty entry
            if entry[0:2] == b'\xFF\xFF' or entry[0:2] == b'\x00\x00':
                break

            # Magic byte check (0xAA, 0x50)
            if entry[0] != 0xAA or entry[1] != 0x50:
                offset += 32
                continue

            # Parse partition entry
            p_type = entry[2]
            p_subtype = entry[3]
            p_offset = int.from_bytes(entry[4:8], 'little')
            p_size = int.from_bytes(entry[8:12], 'little')

            # Name is null‑terminated string
            name_bytes = entry[12:28]
            name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='ignore')

            flags = int.from_bytes(entry[28:32], 'little')

            # Type and subtype mapping
            type_str = self.get_partition_type(p_type)
            subtype_str = self.get_partition_subtype(p_type, p_subtype)

            partitions.append({
                'name': name,
                'type': type_str,
                'subtype': subtype_str,
                'offset': f"0x{p_offset:X}",
                'size': f"0x{p_size:X}",
                'flags': f"0x{flags:X}"
            })

            offset += 32

        return partitions

    def get_partition_type(self, p_type):
        """Convert partition type byte to string"""
        types = {
            0x00: 'app',
            0x01: 'data',
        }
        return types.get(p_type, f'0x{p_type:02X}')

    def get_partition_subtype(self, p_type, p_subtype):
        """Convert partition subtype to string"""
        if p_type == 0x00:  # app
            subtypes = {
                0x00: 'factory',
                0x10: 'ota_0',
                0x11: 'ota_1',
                0x12: 'ota_2',
                0x13: 'ota_3',
                0x20: 'test',
            }
        elif p_type == 0x01:  # data
            subtypes = {
                0x00: 'ota',
                0x01: 'phy',
                0x02: 'nvs',
                0x03: 'coredump',
                0x04: 'nvs_keys',
                0x05: 'efuse',
                0x80: 'esphttpd',
                0x81: 'fat',
                0x82: 'spiffs',
            }
        else:
            return f'0x{p_subtype:02X}'

        return subtypes.get(p_subtype, f'0x{p_subtype:02X}')

    # ------------------------------------------------------------------
    #  GUI creation (modified layout)
    # ------------------------------------------------------------------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(3, weight=1)

        # ---------------- Connection frame ----------------
        conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
        conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        conn_frame.columnconfigure(1, weight=1)

        ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
        self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

        self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
        self.scan_btn.grid(row=0, column=2, padx=(0, 5))

        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
        self.connect_btn.grid(row=0, column=3, padx=(0, 10))

        # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

        # ---------------- SPIFFS Configuration frame ----------------
        spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
        spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # ----- Partition selector (wider) -----
        ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.partition_var = tk.StringVar()
        self.partition_combo = ttk.Combobox(
            spiffs_frame,
            textvariable=self.partition_var,
            state="readonly",
            width=40,                # made wider as requested
        )
        partition_names = [
            f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
        ]
        self.partition_combo['values'] = partition_names
        if partition_names:  # Only set current if there are partitions
            self.partition_combo.current(self.current_spiffs_index)
        self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)
        self.partition_combo.state(['disabled'])          # locked until download

        # ----- Offset (read‑only) -----
        ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.offset_var = tk.StringVar()
        self.offset_entry = ttk.Entry(
            spiffs_frame,
            textvariable=self.offset_var,
            width=15,
            state="readonly"
        )
        self.offset_entry.grid(row=0, column=3, padx=(0, 10))
        self.offset_entry.state(['disabled'])

        # ----- Size (read‑only) -----
        ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        self.size_var = tk.StringVar()
        self.size_entry = ttk.Entry(
            spiffs_frame,
            textvariable=self.size_var,
            width=15,
            state="readonly"
        )
        self.size_entry.grid(row=0, column=5, padx=(0, 10))
        self.size_entry.state(['disabled'])

        # ----- Chip (read‑only, shown after connection) -----
        ttk.Label(spiffs_frame, text="Chip:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
        self.chip_display_var = tk.StringVar()
        self.chip_display_entry = ttk.Entry(
            spiffs_frame,
            textvariable=self.chip_display_var,
            width=12,
            state="readonly"
        )
        self.chip_display_entry.grid(row=0, column=7, padx=(0, 10))
        self.chip_display_entry.state(['disabled'])

        # Initialise the displayed values (empty at start)
        self.update_spiffs_fields()

        # Hide the now‑redundant "Save Config" button (kept for layout)
        self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
        self.save_config_btn.grid(row=0, column=8, padx=(10, 0))
        self.save_config_btn.grid_remove()          # completely hide it

        # ---------------- Action frame ----------------
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

        self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
        self.action_btn.grid(row=0, column=0, padx=(0, 10))
        self.action_btn.config(state="disabled")

        self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
        self.progress.grid(row=0, column=1, padx=(10, 0))

        # ---------------- Content frame ----------------
        content_frame = ttk.Frame(main_frame)
        content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        content_frame.columnconfigure(1, weight=2)
        content_frame.rowconfigure(0, weight=1)

        # File list
        file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
        file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        file_frame.columnconfigure(0, weight=1)
        file_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(file_frame)
        list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.file_listbox.config(yscrollcommand=file_scrollbar.set)

        file_btn_frame = ttk.Frame(file_frame)
        file_btn_frame.grid(row=1, column=0, pady=(5, 0))

        self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
        self.add_file_btn.grid(row=0, column=0, padx=(0, 5))
        self.add_file_btn.config(state="disabled")   # enabled only after download

        self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
        self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
        self.save_file_btn.config(state="disabled")

        self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
        self.delete_file_btn.grid(row=0, column=2)
        self.delete_file_btn.config(state="disabled")

        # Editor
        editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
        editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        self.content_editor = scrolledtext.ScrolledText(
            editor_frame,
            wrap=tk.WORD,
            width=50,
            height=20,
            state="normal"
        )
        self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.content_editor.bind('<KeyRelease>', self.on_content_changed)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

    # ------------------------------------------------------------------
    #  Dependency / connection / scan helpers (unchanged)
    # ------------------------------------------------------------------
    def check_dependencies(self):
        required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
        missing_files = []
        for file in required_files:
            if not os.path.exists(file):
                missing_files.append(file)
        if missing_files:
            message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
            message += "\n\nPlease ensure these files are in the application directory."
            messagebox.showerror("Missing Dependencies", message)
            self.status_var.set("Missing dependencies")
            return False
        try:
            import serial.tools.list_ports
        except ImportError:
            messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
            self.status_var.set("Missing pyserial")
            return False
        self.status_var.set("Dependencies OK")
        return True

    def scan_ports(self):
        ports = serial.tools.list_ports.comports()
        port_list = []
        for port in ports:
            description = port.description if port.description != 'n/a' else 'Unknown device'
            port_display = f"{port.device} - {description}"
            port_list.append(port_display)
        self.port_combo['values'] = port_list
        if self.config.get("last_port"):
            for port_display in port_list:
                if port_display.startswith(self.config["last_port"] + " "):
                    self.port_var.set(port_display)
                    break
        elif port_list:
            self.port_var.set(port_list[0])
        self.status_var.set(f"Found {len(port_list)} COM ports")

    def get_selected_port(self):
        port_display = self.port_var.get()
        if not port_display:
            return ""
        return port_display.split(" - ")[0]

    # ------------------------------------------------------------------
    #  NEW:  on disconnect reset button to initial state + clear file list & editor
    # ------------------------------------------------------------------
    def toggle_connection(self):
        if not self.connected:
            if not self.port_var.get():
                messagebox.showerror("Error", "Please select a COM port")
                return

            try:
                # Read partition table from ESP32
                self.status_var.set("Reading partition table...")
                self.root.update()

                spiffs_partitions = self.read_partition_table_from_esp32()

                # Update internal state with new partitions
                self.spiffs_partitions = spiffs_partitions
                self.current_spiffs_index = 0

                # Update UI with new partition data
                self.update_partition_combo()

                # Connection considered successful
                self.connected = True
                self.connect_btn.config(text="Disconnect")
                self.action_btn.config(state="normal")

                # Enable partition combo when connected
                self.partition_combo.state(['!disabled'])

                self.config["last_port"] = self.get_selected_port()
                self.save_config()
                self.status_var.set(f"Connected to {self.get_selected_port()} ({self.chip_var.get()})")

            except Exception as e:
                messagebox.showerror("Connection Error", f"Could not read partition table:\n{e}")
                self.status_var.set("Connection failed")
                return

        else:
            # ---------- disconnect ----------
            self.connected = False
            self.connect_btn.config(text="Connect")
            self.action_btn.config(state="disabled")
            # reset big button to initial download state
            self.spiffs_downloaded = False
            self.action_btn.config(text="Download SPIFFS")
            # clear file list and editor
            self.file_listbox.delete(0, tk.END)
            self.content_editor.delete(1.0, tk.END)
            self.current_files.clear()
            self.selected_file = None
            self.editor_modified = False
            self.save_file_btn.config(state="disabled")
            self.delete_file_btn.config(state="disabled")
            self.add_file_btn.config(state="disabled")
            # unlock COM port UI
            self.port_combo.state(['!disabled'])
            self.scan_btn.state(['!disabled'])
            # clear partition UI
            self.partition_combo.state(['disabled'])  # disable when disconnected
            self.offset_entry.state(['disabled'])
            self.size_entry.state(['disabled'])
            self.chip_display_var.set("")
            self.chip_display_entry.state(['disabled'])
            self.status_var.set("Disconnected")

    def update_partition_combo(self):
        """Update the partition combo box with current partitions"""
        partition_names = [
            f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
        ]
        self.partition_combo['values'] = partition_names
        if partition_names:  # Only set current if there are partitions
            self.partition_combo.current(self.current_spiffs_index)
        self.update_spiffs_fields()

    # ------------------------------------------------------------------
    #  NEW:  Called when the user changes the selected partition
    # ------------------------------------------------------------------
    def on_partition_selected(self, event=None):
        """Update offset/size fields to reflect the newly selected partition."""
        try:
            self.current_spiffs_index = self.partition_combo.current()
            self.update_spiffs_fields()
        except Exception:
            pass   # defensive – should never happen

    def update_spiffs_fields(self):
        """Write the offset and size of the currently selected partition to the UI."""
        if not self.spiffs_partitions:
            self.offset_var.set("")
            self.size_var.set("")
            return
        part = self.spiffs_partitions[self.current_spiffs_index]
        self.offset_var.set(self.format_value_for_display(part['offset']))
        self.size_var.set(self.format_value_for_display(part['size']))

    def save_spiffs_config(self):
        # The configuration is now derived from ESP32 partition table
        messagebox.showinfo(
            "Info",
            "SPIFFS partitions are read directly from the connected ESP32.\n"
            "No configuration file is used."
        )

    def perform_action(self):
        if not self.connected:
            messagebox.showerror("Error", "Not connected to ESP32")
            return
        if not self.spiffs_downloaded:
            self.download_spiffs()
        else:
            # ---- ask for confirmation before upload ----
            if not messagebox.askyesno("Confirm Upload",
                                       "Are you sure you want to upload the SPIFFS image to the ESP32?"):
                return
            # ---- ask for unsaved before upload ----
            if not self.ask_unsaved_changes("uploading"):
                return
            self.upload_spiffs()

    def download_spiffs(self):
        def download_worker():
            try:
                self.progress.start()
                self.action_btn.config(state="disabled")
                self.status_var.set("Downloading SPIFFS...")

                # Use the values from the selected partition
                part = self.spiffs_partitions[self.current_spiffs_index]
                offset_val = part['offset']
                size_val   = part['size']

                offset_hex = f"0x{offset_val:X}"
                size_dec   = str(size_val)

                cmd = [
                    "esptool.exe",
                    "--chip", self.chip_var.get(),
                    "--port", self.get_selected_port(),
                    "--baud", self.config["baud_rate"],
                    "read_flash", offset_hex, size_dec,
                    "spiffs_dump.bin"
                ]

                print(f"Executing command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                print(f"esptool return code: {result.returncode}")
                if result.stdout:
                    print(f"esptool stdout: {result.stdout}")
                if result.stderr:
                    print(f"esptool stderr: {result.stderr}")

                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    raise Exception(f"Failed to read flash: {error_msg}")

                data_dir = Path("data")
                data_dir.mkdir(exist_ok=True)
                for file in data_dir.glob("*"):
                    if file.is_file():
                        file.unlink()

                cmd = [
                    "mkspiffs_espressif32_arduino.exe",
                    "-u", "data",
                    "spiffs_dump.bin"
                ]

                print(f"Executing command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                print(f"mkspiffs return code: {result.returncode}")
                if result.stdout:
                    print(f"mkspiffs stdout: {result.stdout}")
                if result.stderr:
                    print(f"mkspiffs stderr: {result.stderr}")

                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    raise Exception(f"Failed to extract SPIFFS: {error_msg}")

                self.root.after(0, self.download_complete)

            except Exception as e:
                error_msg = str(e)
                print(f"Download error: {error_msg}")
                self.root.after(0, lambda msg=error_msg: self.download_error(msg))

        thread = threading.Thread(target=download_worker)
        thread.daemon = True
        thread.start()

    def download_complete(self):
        self.progress.stop()
        self.action_btn.config(state="normal", text="Upload SPIFFS")
        self.spiffs_downloaded = True
        self.status_var.set("SPIFFS downloaded successfully")
        self.load_files()
        # Enable partition UI now that we have data
        self.partition_combo.state(['!disabled'])
        self.offset_entry.state(['!disabled'])
        self.size_entry.state(['!disabled'])
        self.add_file_btn.config(state="normal")
        messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

    def download_error(self, error_msg):
        self.progress.stop()
        self.action_btn.config(state="normal")
        self.status_var.set("Download failed")
        messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

    def upload_spiffs(self):
        def upload_worker():
            try:
                self.progress.start()
                self.action_btn.config(state="disabled")
                self.status_var.set("Creating SPIFFS image...")

                spiffs_dir = Path("spiffs")
                spiffs_dir.mkdir(exist_ok=True)

                # Use the values from the selected partition
                part = self.spiffs_partitions[self.current_spiffs_index]
                size_val   = part['size']
                offset_val = part['offset']

                cmd = [
                    "mkspiffs_espressif32_arduino.exe",
                    "-c", "data",
                    "-p", "256",
                    "-b", "4096",
                    "-s", str(size_val),
                    "spiffs/data.bin"
                ]

                print(f"Executing command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                print(f"mkspiffs create return code: {result.returncode}")
                if result.stdout:
                    print(f"mkspiffs create stdout: {result.stdout}")
                if result.stderr:
                    print(f"mkspiffs create stderr: {result.stderr}")

                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    raise Exception(f"Failed to create SPIFFS image: {error_msg}")

                self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

                offset_hex = f"0x{offset_val:X}"
                cmd = [
                    "esptool.exe",
                    "--chip", self.chip_var.get(),
                    "--port", self.get_selected_port(),
                    "--baud", self.config["baud_rate"],
                    "--before", "default_reset",
                    "--after", "hard_reset",
                    "write_flash", "-z",
                    "--flash_mode", "dio",
                    "--flash_size", "detect",
                    offset_hex, "spiffs/data.bin"
                ]

                print(f"Executing command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                print(f"esptool write return code: {result.returncode}")
                if result.stdout:
                    print(f"esptool write stdout: {result.stdout}")
                if result.stderr:
                    print(f"esptool write stderr: {result.stderr}")

                if result.returncode != 0:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    raise Exception(f"Failed to upload SPIFFS: {error_msg}")

                self.root.after(0, self.upload_complete)

            except Exception as e:
                error_msg = str(e)
                print(f"Upload error: {error_msg}")
                self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

        thread = threading.Thread(target=upload_worker)
        thread.daemon = True
        thread.start()

    def upload_complete(self):
        self.progress.stop()
        self.action_btn.config(state="normal")
        self.status_var.set("SPIFFS uploaded successfully")
        messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

    def upload_error(self, error_msg):
        self.progress.stop()
        self.action_btn.config(state="normal")
        self.status_var.set("Upload failed")
        messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

    # ------------------------------------------------------------------
    #  File management (adjusted for editor_modified flag, full file list)
    # ------------------------------------------------------------------
    def load_files(self):
        self.current_files = {}
        self.file_listbox.delete(0, tk.END)
        data_dir = Path("data")
        if not data_dir.exists():
            return
        # we now list *all* files; only read as text when possible
        file_paths = list(data_dir.iterdir())

        print(f"Loading {len(file_paths)} files from data directory")

        for file_path in file_paths:
            if file_path.is_file():
                filename = file_path.name
                try:
                    if file_path.suffix.lower() in self.text_extensions:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        print(f"Loaded text file: {filename} ({len(content)} chars)")
                    else:
                        # binary or unknown – keep empty placeholder
                        content = ""
                        print(f"Loaded binary file: {filename} (empty content)")
                    self.current_files[filename] = content
                    self.file_listbox.insert(tk.END, filename)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
                    self.current_files[filename] = f"[Error reading file: {e}]"
                    self.file_listbox.insert(tk.END, filename)

        # keep add‑file button enabled after a successful download
        if self.spiffs_downloaded:
            self.add_file_btn.config(state="normal")

        # Select the first file if there are any files
        if self.current_files:
            first_filename = list(self.current_files.keys())[0]
            print(f"Selecting first file: {first_filename}")
            self.file_listbox.selection_set(0)
            self.on_file_select()
        else:
            print("No files found in data directory")

    # NEW:  ask unsaved when changing file selection
    def on_file_select(self, event=None):
        selection = self.file_listbox.curselection()
        if not selection:
            return
        if not self.ask_unsaved_changes("switching file"):
            # restore previous selection
            idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
            self.file_listbox.selection_clear(0, tk.END)
            self.file_listbox.selection_set(idx)
            return

        filename = self.file_listbox.get(selection[0])
        print(f"Selected file: {filename}")
        if filename in self.current_files:
            self.selected_file = filename
            # Determine if this file type is editable
            if filename.lower().endswith(tuple(self.text_extensions)):
                # Editable text file
                content = self.current_files[filename]
                self.content_editor.config(state="normal")
                self.content_editor.delete(1.0, tk.END)
                self.content_editor.insert(1.0, content)
                self.editor_modified = False
                self.save_file_btn.config(state="disabled")
                self.delete_file_btn.config(state="normal")
            else:
                # Not editable – show notice and disable editing
                notice = "File type not supported for editing."
                self.content_editor.config(state="normal")
                self.content_editor.delete(1.0, tk.END)
                self.content_editor.insert(1.0, notice)
                self.content_editor.config(state="disabled")
                self.editor_modified = False
                self.save_file_btn.config(state="disabled")
                self.delete_file_btn.config(state="normal")

    def on_content_changed(self, event=None):
        if self.selected_file and self.content_editor['state'] == 'normal':
            self.editor_modified = True
            self.save_file_btn.config(state="normal")

    def save_current_file(self):
        if not self.selected_file:
            return
        if not self.selected_file.lower().endswith(tuple(self.text_extensions)):
            messagebox.showerror("Error", "Cannot save this file type (read‑only).")
            return
        content = self.content_editor.get(1.0, tk.END).rstrip()
        self.current_files[self.selected_file] = content
        try:
            data_dir = Path("data")
            data_dir.mkdir(exist_ok=True)
            file_path = data_dir / self.selected_file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.editor_modified = False
            self.save_file_btn.config(state="disabled")
            self.status_var.set(f"Saved {self.selected_file}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

    # ------------------------------------------------------------------
    #  NEW:  Simple Add‑File that selects an existing file from the host
    # ------------------------------------------------------------------
    def add_file(self):
        src_path = filedialog.askopenfilename(title="Select file to add")
        if not src_path:
            return

        filename = os.path.basename(src_path)
        if filename in self.current_files:
            messagebox.showerror("Error", f'File "{filename}" already exists in the SPIFFS.')
            return

        try:
            with open(src_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"Could not read selected file:\n{e}")
            return

        # Register in internal structures and write to disk
        self.current_files[filename] = content
        self.file_listbox.insert(tk.END, filename)

        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        dest_path = data_dir / filename
        try:
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy file to data folder:\n{e}")
            return

        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(tk.END)
        self.on_file_select()

    def delete_file(self):
        if not self.selected_file:
            return
        result = messagebox.askyesno("Confirm Delete",
                                   f"Are you sure you want to delete {self.selected_file}?")
        if not result:
            return
        del self.current_files[self.selected_file]
        selection = self.file_listbox.curselection()
        if selection:
            self.file_listbox.delete(selection[0])
        try:
            file_path = Path("data") / self.selected_file
            if file_path.is_file():
                file_path.unlink()
        except Exception as e:
            print(f"Error deleting file: {e}")
        self.content_editor.delete(1.0, tk.END)
        self.selected_file = None
        self.editor_modified = False
        self.save_file_btn.config(state="disabled")
        self.delete_file_btn.config(state="disabled")
        self.content_editor.config(state="normal")   # re‑enable for next selection

    # ------------------------------------------------------------------
    #  Application close handler
    # ------------------------------------------------------------------
    def on_app_closing(self):
        if self.ask_unsaved_changes("closing the application"):
            self.root.destroy()


# ----------------------------------------------------------------------
#  Entry-point
# ----------------------------------------------------------------------
def main():
    import tkinter.simpledialog
    tk.simpledialog = tkinter.simpledialog
    root = tk.Tk()
    ESP32SPIFFSManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()


# #!/usr/bin/env python3
# """
# ESP32 SPIFFS Manager GUI
# Windows GUI application for managing ESP32 SPIFFS filesystem
# """
# VERSION = "v.025"  #  <── incremented on every program update

# import os
# import json
# import subprocess
# import sys
# import tkinter as tk
# from tkinter import ttk, messagebox, scrolledtext, filedialog
# import csv
# from pathlib import Path
# import serial.tools.list_ports
# import threading
# from datetime import datetime

# # ------------------------------------------------------------------
# #  Main application class
# # ------------------------------------------------------------------
# class ESP32SPIFFSManager:
#     def __init__(self, root):
#         self.root = root
#         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
#         self.root.geometry("1000x700")
#         self.root.minsize(800, 600)

#         # Configuration
#         self.config_file = "spiffs_config.json"
#         self.load_config()

#         # keep chip variable even though the UI element is hidden
#         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

#         # --------------------------------------------------------------
#         #  SPIFFS partition information (now loaded from ESP32)
#         # --------------------------------------------------------------
#         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
#         self.current_spiffs_index = 0       # index inside self.spiffs_partitions

#         # State variables
#         self.connected = False
#         self.current_files = {}       # filename → content (text content or empty for non‑text)
#         self.selected_file = None     # filename currently in editor
#         self.spiffs_downloaded = False
#         self.editor_modified = False  # True while editor has unsaved changes

#         # Create GUI
#         self.create_widgets()
#         self.scan_ports()

#         # Ask on unsaved changes when user closes window
#         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

#         # Check required files on startup
#         self.check_dependencies()

#     # ------------------------------------------------------------------
#     #  NEW:  generic "ask unsaved" helper  (returns True = proceed, False = abort)
#     # ------------------------------------------------------------------
#     def ask_unsaved_changes(self, action: str = "switch file"):
#         """Return True if the caller may continue, False if user chose Cancel."""
#         if not self.editor_modified:
#             return True

#         answer = messagebox.askyesnocancel(
#             "Unsaved changes",
#             f'File "{self.selected_file}" has unsaved changes.\n\n'
#             f'Save before {action}?',
#             default=messagebox.YES
#         )
#         if answer is True:          # Save
#             self.save_current_file()
#             return True
#         elif answer is False:       # Discard
#             return True
#         else:                       # Cancel
#             return False

#     # ------------------------------------------------------------------
#     #  Small helpers (unchanged)
#     # ------------------------------------------------------------------
#     @staticmethod
#     def _ensure_int(value):
#         """Return int whether value is already int or decimal/hex string."""
#         if isinstance(value, int):
#             return value
#         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

#     def load_config(self):
#         default_config = {
#             "spiffs_offset": 6750208,  # 0x670000
#             "spiffs_size": 1572864,    # 0x180000
#             "esp32_chip": "esp32-s3",
#             "baud_rate": "921600",
#             "last_port": ""
#         }
#         try:
#             if os.path.exists(self.config_file):
#                 with open(self.config_file, 'r') as f:
#                     self.config = json.load(f)
#                 for key, value in default_config.items():
#                     if key not in self.config:
#                         self.config[key] = value
#             else:
#                 self.config = default_config
#                 self.save_config()
#         except Exception as e:
#             print(f"Error loading config: {e}")
#             self.config = default_config
#             self.save_config()

#     def save_config(self):
#         try:
#             with open(self.config_file, 'w') as f:
#                 json.dump(self.config, f, indent=4)
#         except Exception as e:
#             print(f"Error saving config: {e}")

#     def format_value_for_display(self, value):
#         if isinstance(value, int):
#             return f"0x{value:X}"
#         return str(value)

#     def parse_value_from_input(self, value_str):
#         value_str = value_str.strip()
#         if value_str.lower().startswith('0x'):
#             return int(value_str, 16)
#         else:
#             return int(value_str)

#     def validate_config_input(self, value_str, field_name):
#         try:
#             return self.parse_value_from_input(value_str)
#         except ValueError:
#             messagebox.showerror("Invalid Input",
#                                f"Invalid {field_name} value: {value_str}\n"
#                                f"Please enter a decimal number or hex value (0x...)")
#             return None

#     # ------------------------------------------------------------------
#     #  NEW:  Read partition table from ESP32
#     # ------------------------------------------------------------------
#     def read_partition_table_from_esp32(self):
#         """Read and parse partition table from connected ESP32"""
#         esp = None
#         try:
#             import esptool

#             port = self.get_selected_port()
#             if not port:
#                 raise Exception("No COM port selected")

#             print(f"Connecting to ESP32 on port {port}...")

#             # Connect to ESP32
#             esp = esptool.get_default_connected_device(
#                 serial_list=[port],
#                 port=port,
#                 connect_attempts=7,
#                 initial_baud=115200
#             )

#             if not esp:
#                 raise Exception("Failed to connect to ESP32")

#             # Detect chip model and extract base chip type
#             chip_description = esp.get_chip_description()
#             print(f"Chip detected: {chip_description}")
#             chip_model = self.extract_chip_model(chip_description)
#             print(f"Extracted chip model: {chip_model}")
#             self.chip_var.set(chip_model)
#             self.config["esp32_chip"] = chip_model
#             self.save_config()
#             self.chip_display_var.set(chip_description)

#             # Read partition table
#             PARTITION_TABLE_OFFSET = 0x8000
#             PARTITION_TABLE_SIZE = 0xC00  # 3KB

#             print(f"Reading partition table from offset 0x{PARTITION_TABLE_OFFSET:X}...")
#             esp = esp.run_stub()
#             partition_data = esp.read_flash(PARTITION_TABLE_OFFSET, PARTITION_TABLE_SIZE)
#             print(f"Successfully read {len(partition_data)} bytes of partition table")

#             # Parse partition table
#             partitions = self.parse_partition_table(partition_data)
#             print(f"Parsed {len(partitions)} partitions from table")

#             # Filter only SPIFFS partitions
#             spiffs_partitions = []
#             for p in partitions:
#                 if p['subtype'].lower() == 'spiffs':
#                     # Convert hex strings to integers
#                     offset = int(p['offset'], 0) if isinstance(p['offset'], str) else p['offset']
#                     size = int(p['size'], 0) if isinstance(p['size'], str) else p['size']
#                     spiffs_partitions.append({
#                         "name": p['name'],
#                         "offset": offset,
#                         "size": size
#                     })
#                     print(f"Found SPIFFS partition: {p['name']} at 0x{offset:X}, size 0x{size:X}")

#             if not spiffs_partitions:
#                 raise Exception("No SPIFFS partitions found in partition table")

#             return spiffs_partitions

#         except ImportError:
#             raise Exception("esptool library not found. Please install it: pip install esptool")
#         except Exception as e:
#             raise Exception(f"Failed to read partition table: {str(e)}")
#         finally:
#             # Ensure the connection is properly closed
#             if esp is not None:
#                 try:
#                     esp._port.close()
#                     print("ESP32 connection closed successfully")
#                 except Exception as e:
#                     print(f"Error closing ESP32 connection: {e}")

#     def extract_chip_model(self, chip_description):
#         """Extract base chip model from full chip description"""
#         # Common ESP32 chip models
#         chip_models = ['esp32-s2', 'esp32-s3', 'esp32-c3', 'esp32-c6', 'esp32']

#         # Convert to lowercase for comparison
#         desc_lower = chip_description.lower()

#         # Check for specific chip models
#         for model in chip_models:
#             if model in desc_lower:
#                 return model

#         # Default fallback
#         return 'esp32'

#     def parse_partition_table(self, data):
#         """Parse binary partition table data"""
#         partitions = []
#         offset = 0

#         # MD5 hash is at the end, partition entries are 32 bytes each
#         while offset < len(data) - 32:
#             entry = data[offset:offset + 32]

#             # Check for end marker (all 0xFF) or empty entry
#             if entry[0:2] == b'\xFF\xFF' or entry[0:2] == b'\x00\x00':
#                 break

#             # Magic byte check (0xAA, 0x50)
#             if entry[0] != 0xAA or entry[1] != 0x50:
#                 offset += 32
#                 continue

#             # Parse partition entry
#             p_type = entry[2]
#             p_subtype = entry[3]
#             p_offset = int.from_bytes(entry[4:8], 'little')
#             p_size = int.from_bytes(entry[8:12], 'little')

#             # Name is null‑terminated string
#             name_bytes = entry[12:28]
#             name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='ignore')

#             flags = int.from_bytes(entry[28:32], 'little')

#             # Type and subtype mapping
#             type_str = self.get_partition_type(p_type)
#             subtype_str = self.get_partition_subtype(p_type, p_subtype)

#             partitions.append({
#                 'name': name,
#                 'type': type_str,
#                 'subtype': subtype_str,
#                 'offset': f"0x{p_offset:X}",
#                 'size': f"0x{p_size:X}",
#                 'flags': f"0x{flags:X}"
#             })

#             offset += 32

#         return partitions

#     def get_partition_type(self, p_type):
#         """Convert partition type byte to string"""
#         types = {
#             0x00: 'app',
#             0x01: 'data',
#         }
#         return types.get(p_type, f'0x{p_type:02X}')

#     def get_partition_subtype(self, p_type, p_subtype):
#         """Convert partition subtype to string"""
#         if p_type == 0x00:  # app
#             subtypes = {
#                 0x00: 'factory',
#                 0x10: 'ota_0',
#                 0x11: 'ota_1',
#                 0x12: 'ota_2',
#                 0x13: 'ota_3',
#                 0x20: 'test',
#             }
#         elif p_type == 0x01:  # data
#             subtypes = {
#                 0x00: 'ota',
#                 0x01: 'phy',
#                 0x02: 'nvs',
#                 0x03: 'coredump',
#                 0x04: 'nvs_keys',
#                 0x05: 'efuse',
#                 0x80: 'esphttpd',
#                 0x81: 'fat',
#                 0x82: 'spiffs',
#             }
#         else:
#             return f'0x{p_subtype:02X}'

#         return subtypes.get(p_subtype, f'0x{p_subtype:02X}')

#     # ------------------------------------------------------------------
#     #  GUI creation (modified layout)
#     # ------------------------------------------------------------------
#     def create_widgets(self):
#         main_frame = ttk.Frame(self.root, padding="10")
#         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
#         self.root.columnconfigure(0, weight=1)
#         self.root.rowconfigure(0, weight=1)
#         main_frame.columnconfigure(1, weight=1)
#         main_frame.rowconfigure(3, weight=1)

#         # ---------------- Connection frame ----------------
#         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
#         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
#         conn_frame.columnconfigure(1, weight=1)

#         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
#         self.port_var = tk.StringVar()
#         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
#         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

#         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
#         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

#         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
#         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

#         # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

#         # ---------------- SPIFFS Configuration frame ----------------
#         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
#         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

#         # ----- Partition selector (wider) -----
#         ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
#         self.partition_var = tk.StringVar()
#         self.partition_combo = ttk.Combobox(
#             spiffs_frame,
#             textvariable=self.partition_var,
#             state="readonly",
#             width=40,                # made wider as requested
#         )
#         partition_names = [
#             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
#         ]
#         self.partition_combo['values'] = partition_names
#         if partition_names:  # Only set current if there are partitions
#             self.partition_combo.current(self.current_spiffs_index)
#         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
#         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)
#         self.partition_combo.state(['disabled'])          # locked until download

#         # ----- Offset (read‑only) -----
#         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
#         self.offset_var = tk.StringVar()
#         self.offset_entry = ttk.Entry(
#             spiffs_frame,
#             textvariable=self.offset_var,
#             width=15,
#             state="readonly"
#         )
#         self.offset_entry.grid(row=0, column=3, padx=(0, 10))
#         self.offset_entry.state(['disabled'])

#         # ----- Size (read‑only) -----
#         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
#         self.size_var = tk.StringVar()
#         self.size_entry = ttk.Entry(
#             spiffs_frame,
#             textvariable=self.size_var,
#             width=15,
#             state="readonly"
#         )
#         self.size_entry.grid(row=0, column=5, padx=(0, 10))
#         self.size_entry.state(['disabled'])

#         # ----- Chip (read‑only, shown after connection) -----
#         ttk.Label(spiffs_frame, text="Chip:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
#         self.chip_display_var = tk.StringVar()
#         self.chip_display_entry = ttk.Entry(
#             spiffs_frame,
#             textvariable=self.chip_display_var,
#             width=12,
#             state="readonly"
#         )
#         self.chip_display_entry.grid(row=0, column=7, padx=(0, 10))
#         self.chip_display_entry.state(['disabled'])

#         # Initialise the displayed values (empty at start)
#         self.update_spiffs_fields()

#         # Hide the now‑redundant "Save Config" button (kept for layout)
#         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
#         self.save_config_btn.grid(row=0, column=8, padx=(10, 0))
#         self.save_config_btn.grid_remove()          # completely hide it

#         # ---------------- Action frame ----------------
#         action_frame = ttk.Frame(main_frame)
#         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

#         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
#         self.action_btn.grid(row=0, column=0, padx=(0, 10))
#         self.action_btn.config(state="disabled")

#         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
#         self.progress.grid(row=0, column=1, padx=(10, 0))

#         # ---------------- Content frame ----------------
#         content_frame = ttk.Frame(main_frame)
#         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
#         content_frame.columnconfigure(1, weight=2)
#         content_frame.rowconfigure(0, weight=1)

#         # File list
#         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
#         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
#         file_frame.columnconfigure(0, weight=1)
#         file_frame.rowconfigure(0, weight=1)

#         list_frame = ttk.Frame(file_frame)
#         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
#         list_frame.columnconfigure(0, weight=1)
#         list_frame.rowconfigure(0, weight=1)

#         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
#         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
#         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

#         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
#         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
#         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

#         file_btn_frame = ttk.Frame(file_frame)
#         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

#         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
#         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))
#         self.add_file_btn.config(state="disabled")   # enabled only after download

#         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
#         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
#         self.save_file_btn.config(state="disabled")

#         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
#         self.delete_file_btn.grid(row=0, column=2)
#         self.delete_file_btn.config(state="disabled")

#         # Editor
#         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
#         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
#         editor_frame.columnconfigure(0, weight=1)
#         editor_frame.rowconfigure(0, weight=1)

#         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
#         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
#         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

#         # Status bar
#         self.status_var = tk.StringVar(value="Ready")
#         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
#         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

#     # ------------------------------------------------------------------
#     #  Dependency / connection / scan helpers (unchanged)
#     # ------------------------------------------------------------------
#     def check_dependencies(self):
#         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
#         missing_files = []
#         for file in required_files:
#             if not os.path.exists(file):
#                 missing_files.append(file)
#         if missing_files:
#             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
#             message += "\n\nPlease ensure these files are in the application directory."
#             messagebox.showerror("Missing Dependencies", message)
#             self.status_var.set("Missing dependencies")
#             return False
#         try:
#             import serial.tools.list_ports
#         except ImportError:
#             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
#             self.status_var.set("Missing pyserial")
#             return False
#         self.status_var.set("Dependencies OK")
#         return True

#     def scan_ports(self):
#         ports = serial.tools.list_ports.comports()
#         port_list = []
#         for port in ports:
#             description = port.description if port.description != 'n/a' else 'Unknown device'
#             port_display = f"{port.device} - {description}"
#             port_list.append(port_display)
#         self.port_combo['values'] = port_list
#         if self.config.get("last_port"):
#             for port_display in port_list:
#                 if port_display.startswith(self.config["last_port"] + " "):
#                     self.port_var.set(port_display)
#                     break
#         elif port_list:
#             self.port_var.set(port_list[0])
#         self.status_var.set(f"Found {len(port_list)} COM ports")

#     def get_selected_port(self):
#         port_display = self.port_var.get()
#         if not port_display:
#             return ""
#         return port_display.split(" - ")[0]

#     # ------------------------------------------------------------------
#     #  NEW:  on disconnect reset button to initial state + clear file list & editor
#     # ------------------------------------------------------------------
#     def toggle_connection(self):
#         if not self.connected:
#             if not self.port_var.get():
#                 messagebox.showerror("Error", "Please select a COM port")
#                 return

#             try:
#                 # Read partition table from ESP32
#                 self.status_var.set("Reading partition table...")
#                 self.root.update()

#                 spiffs_partitions = self.read_partition_table_from_esp32()

#                 # Update internal state with new partitions
#                 self.spiffs_partitions = spiffs_partitions
#                 self.current_spiffs_index = 0

#                 # Update UI with new partition data
#                 self.update_partition_combo()

#                 # Connection considered successful
#                 self.connected = True
#                 self.connect_btn.config(text="Disconnect")
#                 self.action_btn.config(state="normal")

#                 # Enable partition combo when connected
#                 self.partition_combo.state(['!disabled'])

#                 self.config["last_port"] = self.get_selected_port()
#                 self.save_config()
#                 self.status_var.set(f"Connected to {self.get_selected_port()} ({self.chip_var.get()})")

#             except Exception as e:
#                 messagebox.showerror("Connection Error", f"Could not read partition table:\n{e}")
#                 self.status_var.set("Connection failed")
#                 return

#         else:
#             # ---------- disconnect ----------
#             self.connected = False
#             self.connect_btn.config(text="Connect")
#             self.action_btn.config(state="disabled")
#             # reset big button to initial download state
#             self.spiffs_downloaded = False
#             self.action_btn.config(text="Download SPIFFS")
#             # clear file list and editor
#             self.file_listbox.delete(0, tk.END)
#             self.content_editor.delete(1.0, tk.END)
#             self.current_files.clear()
#             self.selected_file = None
#             self.editor_modified = False
#             self.save_file_btn.config(state="disabled")
#             self.delete_file_btn.config(state="disabled")
#             self.add_file_btn.config(state="disabled")
#             # unlock COM port UI
#             self.port_combo.state(['!disabled'])
#             self.scan_btn.state(['!disabled'])
#             # clear partition UI
#             self.partition_combo.state(['disabled'])  # disable when disconnected
#             self.offset_entry.state(['disabled'])
#             self.size_entry.state(['disabled'])
#             self.chip_display_var.set("")
#             self.chip_display_entry.state(['disabled'])
#             self.status_var.set("Disconnected")

#     def update_partition_combo(self):
#         """Update the partition combo box with current partitions"""
#         partition_names = [
#             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
#         ]
#         self.partition_combo['values'] = partition_names
#         if partition_names:  # Only set current if there are partitions
#             self.partition_combo.current(self.current_spiffs_index)
#         self.update_spiffs_fields()

#     # ------------------------------------------------------------------
#     #  NEW:  Called when the user changes the selected partition
#     # ------------------------------------------------------------------
#     def on_partition_selected(self, event=None):
#         """Update offset/size fields to reflect the newly selected partition."""
#         try:
#             self.current_spiffs_index = self.partition_combo.current()
#             self.update_spiffs_fields()
#         except Exception:
#             pass   # defensive – should never happen

#     def update_spiffs_fields(self):
#         """Write the offset and size of the currently selected partition to the UI."""
#         if not self.spiffs_partitions:
#             self.offset_var.set("")
#             self.size_var.set("")
#             return
#         part = self.spiffs_partitions[self.current_spiffs_index]
#         self.offset_var.set(self.format_value_for_display(part['offset']))
#         self.size_var.set(self.format_value_for_display(part['size']))

#     def save_spiffs_config(self):
#         # The configuration is now derived from ESP32 partition table
#         messagebox.showinfo(
#             "Info",
#             "SPIFFS partitions are read directly from the connected ESP32.\n"
#             "No configuration file is used."
#         )

#     def perform_action(self):
#         if not self.connected:
#             messagebox.showerror("Error", "Not connected to ESP32")
#             return
#         if not self.spiffs_downloaded:
#             self.download_spiffs()
#         else:
#             # ---- ask for confirmation before upload ----
#             if not messagebox.askyesno("Confirm Upload",
#                                        "Are you sure you want to upload the SPIFFS image to the ESP32?"):
#                 return
#             # ---- ask for unsaved before upload ----
#             if not self.ask_unsaved_changes("uploading"):
#                 return
#             self.upload_spiffs()

#     def download_spiffs(self):
#         def download_worker():
#             try:
#                 self.progress.start()
#                 self.action_btn.config(state="disabled")
#                 self.status_var.set("Downloading SPIFFS...")

#                 # Use the values from the selected partition
#                 part = self.spiffs_partitions[self.current_spiffs_index]
#                 offset_val = part['offset']
#                 size_val   = part['size']

#                 offset_hex = f"0x{offset_val:X}"
#                 size_dec   = str(size_val)

#                 cmd = [
#                     "esptool.exe",
#                     "--chip", self.chip_var.get(),
#                     "--port", self.get_selected_port(),
#                     "--baud", self.config["baud_rate"],
#                     "read_flash", offset_hex, size_dec,
#                     "spiffs_dump.bin"
#                 ]

#                 print(f"Executing command: {' '.join(cmd)}")
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 print(f"esptool return code: {result.returncode}")
#                 if result.stdout:
#                     print(f"esptool stdout: {result.stdout}")
#                 if result.stderr:
#                     print(f"esptool stderr: {result.stderr}")

#                 if result.returncode != 0:
#                     error_msg = result.stderr if result.stderr else "Unknown error"
#                     raise Exception(f"Failed to read flash: {error_msg}")

#                 data_dir = Path("data")
#                 data_dir.mkdir(exist_ok=True)
#                 for file in data_dir.glob("*"):
#                     if file.is_file():
#                         file.unlink()

#                 cmd = [
#                     "mkspiffs_espressif32_arduino.exe",
#                     "-u", "data",
#                     "spiffs_dump.bin"
#                 ]

#                 print(f"Executing command: {' '.join(cmd)}")
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 print(f"mkspiffs return code: {result.returncode}")
#                 if result.stdout:
#                     print(f"mkspiffs stdout: {result.stdout}")
#                 if result.stderr:
#                     print(f"mkspiffs stderr: {result.stderr}")

#                 if result.returncode != 0:
#                     error_msg = result.stderr if result.stderr else "Unknown error"
#                     raise Exception(f"Failed to extract SPIFFS: {error_msg}")

#                 self.root.after(0, self.download_complete)

#             except Exception as e:
#                 error_msg = str(e)
#                 print(f"Download error: {error_msg}")
#                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

#         thread = threading.Thread(target=download_worker)
#         thread.daemon = True
#         thread.start()

#     def download_complete(self):
#         self.progress.stop()
#         self.action_btn.config(state="normal", text="Upload SPIFFS")
#         self.spiffs_downloaded = True
#         self.status_var.set("SPIFFS downloaded successfully")
#         self.load_files()
#         # Enable partition UI now that we have data
#         self.partition_combo.state(['!disabled'])
#         self.offset_entry.state(['!disabled'])
#         self.size_entry.state(['!disabled'])
#         self.add_file_btn.config(state="normal")
#         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

#     def download_error(self, error_msg):
#         self.progress.stop()
#         self.action_btn.config(state="normal")
#         self.status_var.set("Download failed")
#         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

#     def upload_spiffs(self):
#         def upload_worker():
#             try:
#                 self.progress.start()
#                 self.action_btn.config(state="disabled")
#                 self.status_var.set("Creating SPIFFS image...")

#                 spiffs_dir = Path("spiffs")
#                 spiffs_dir.mkdir(exist_ok=True)

#                 # Use the values from the selected partition
#                 part = self.spiffs_partitions[self.current_spiffs_index]
#                 size_val   = part['size']
#                 offset_val = part['offset']

#                 cmd = [
#                     "mkspiffs_espressif32_arduino.exe",
#                     "-c", "data",
#                     "-p", "256",
#                     "-b", "4096",
#                     "-s", str(size_val),
#                     "spiffs/data.bin"
#                 ]

#                 print(f"Executing command: {' '.join(cmd)}")
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 print(f"mkspiffs create return code: {result.returncode}")
#                 if result.stdout:
#                     print(f"mkspiffs create stdout: {result.stdout}")
#                 if result.stderr:
#                     print(f"mkspiffs create stderr: {result.stderr}")

#                 if result.returncode != 0:
#                     error_msg = result.stderr if result.stderr else "Unknown error"
#                     raise Exception(f"Failed to create SPIFFS image: {error_msg}")

#                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

#                 offset_hex = f"0x{offset_val:X}"
#                 cmd = [
#                     "esptool.exe",
#                     "--chip", self.chip_var.get(),
#                     "--port", self.get_selected_port(),
#                     "--baud", self.config["baud_rate"],
#                     "--before", "default_reset",
#                     "--after", "hard_reset",
#                     "write_flash", "-z",
#                     "--flash_mode", "dio",
#                     "--flash_size", "detect",
#                     offset_hex, "spiffs/data.bin"
#                 ]

#                 print(f"Executing command: {' '.join(cmd)}")
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 print(f"esptool write return code: {result.returncode}")
#                 if result.stdout:
#                     print(f"esptool write stdout: {result.stdout}")
#                 if result.stderr:
#                     print(f"esptool write stderr: {result.stderr}")

#                 if result.returncode != 0:
#                     error_msg = result.stderr if result.stderr else "Unknown error"
#                     raise Exception(f"Failed to upload SPIFFS: {error_msg}")

#                 self.root.after(0, self.upload_complete)

#             except Exception as e:
#                 error_msg = str(e)
#                 print(f"Upload error: {error_msg}")
#                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

#         thread = threading.Thread(target=upload_worker)
#         thread.daemon = True
#         thread.start()

#     def upload_complete(self):
#         self.progress.stop()
#         self.action_btn.config(state="normal")
#         self.status_var.set("SPIFFS uploaded successfully")
#         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

#     def upload_error(self, error_msg):
#         self.progress.stop()
#         self.action_btn.config(state="normal")
#         self.status_var.set("Upload failed")
#         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

#     # ------------------------------------------------------------------
#     #  File management (adjusted for editor_modified flag, full file list)
#     # ------------------------------------------------------------------
#     def load_files(self):
#         self.current_files = {}
#         self.file_listbox.delete(0, tk.END)
#         data_dir = Path("data")
#         if not data_dir.exists():
#             return
#         # we now list *all* files; only read as text when possible
#         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
#         file_paths = list(data_dir.iterdir())

#         print(f"Loading {len(file_paths)} files from data directory")

#         for file_path in file_paths:
#             if file_path.is_file():
#                 filename = file_path.name
#                 try:
#                     if file_path.suffix.lower() in text_extensions:
#                         with open(file_path, 'r', encoding='utf-8') as f:
#                             content = f.read()
#                         print(f"Loaded text file: {filename} ({len(content)} chars)")
#                     else:
#                         # binary or unknown – keep empty placeholder
#                         content = ""
#                         print(f"Loaded binary file: {filename} (empty content)")
#                     self.current_files[filename] = content
#                     self.file_listbox.insert(tk.END, filename)
#                 except Exception as e:
#                     print(f"Error reading {file_path}: {e}")
#                     # Still add the file to the list but with error content
#                     self.current_files[filename] = f"[Error reading file: {e}]"
#                     self.file_listbox.insert(tk.END, filename)

#         # keep add‑file button enabled after a successful download
#         if self.spiffs_downloaded:
#             self.add_file_btn.config(state="normal")

#         # Select the first file if there are any files
#         if self.current_files:
#             first_filename = list(self.current_files.keys())[0]
#             print(f"Selecting first file: {first_filename}")
#             self.file_listbox.selection_set(0)
#             self.on_file_select()
#         else:
#             print("No files found in data directory")

#     # NEW: ask unsaved when changing file selection
#     def on_file_select(self, event=None):
#         selection = self.file_listbox.curselection()
#         if not selection:
#             return
#         if not self.ask_unsaved_changes("switching file"):
#             # restore previous selection
#             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
#             self.file_listbox.selection_clear(0, tk.END)
#             self.file_listbox.selection_set(idx)
#             return

#         filename = self.file_listbox.get(selection[0])
#         print(f"Selected file: {filename}")
#         if filename in self.current_files:
#             self.selected_file = filename
#             content = self.current_files[filename]
#             print(f"File content length: {len(content)}")
#             self.content_editor.delete(1.0, tk.END)
#             self.content_editor.insert(1.0, content)
#             self.editor_modified = False
#             self.save_file_btn.config(state="disabled")
#             self.delete_file_btn.config(state="normal")

#     def on_content_changed(self, event=None):
#         if self.selected_file:
#             self.editor_modified = True
#             self.save_file_btn.config(state="normal")

#     def save_current_file(self):
#         if not self.selected_file:
#             return
#         content = self.content_editor.get(1.0, tk.END).rstrip()
#         self.current_files[self.selected_file] = content
#         try:
#             data_dir = Path("data")
#             data_dir.mkdir(exist_ok=True)
#             file_path = data_dir / self.selected_file
#             with open(file_path, 'w', encoding='utf-8') as f:
#                 f.write(content)
#             self.editor_modified = False
#             self.save_file_btn.config(state="disabled")
#             self.status_var.set(f"Saved {self.selected_file}")
#         except Exception as e:
#             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

#     # ------------------------------------------------------------------
#     #  NEW:  Simple Add‑File that selects an existing file from the host
#     # ------------------------------------------------------------------
#     def add_file(self):
#         src_path = filedialog.askopenfilename(title="Select file to add")
#         if not src_path:
#             return

#         filename = os.path.basename(src_path)
#         if filename in self.current_files:
#             messagebox.showerror("Error", f"File \"{filename}\" already exists in the SPIFFS.")
#             return

#         try:
#             with open(src_path, 'r', encoding='utf-8') as f:
#                 content = f.read()
#         except Exception as e:
#             messagebox.showerror("Error", f"Could not read selected file:\n{e}")
#             return

#         # Register in internal structures and write to disk
#         self.current_files[filename] = content
#         self.file_listbox.insert(tk.END, filename)

#         data_dir = Path("data")
#         data_dir.mkdir(exist_ok=True)
#         dest_path = data_dir / filename
#         try:
#             with open(dest_path, 'w', encoding='utf-8') as f:
#                 f.write(content)
#         except Exception as e:
#             messagebox.showerror("Error", f"Failed to copy file to data folder:\n{e}")
#             return

#         self.file_listbox.selection_clear(0, tk.END)
#         self.file_listbox.selection_set(tk.END)
#         self.on_file_select()

#     def delete_file(self):
#         if not self.selected_file:
#             return
#         result = messagebox.askyesno("Confirm Delete",
#                                    f"Are you sure you want to delete {self.selected_file}?")
#         if not result:
#             return
#         del self.current_files[self.selected_file]
#         selection = self.file_listbox.curselection()
#         if selection:
#             self.file_listbox.delete(selection[0])
#         try:
#             file_path = Path("data") / self.selected_file
#             if file_path.is_file():
#                 file_path.unlink()
#         except Exception as e:
#             print(f"Error deleting file: {e}")
#         self.content_editor.delete(1.0, tk.END)
#         self.selected_file = None
#         self.editor_modified = False
#         self.save_file_btn.config(state="disabled")
#         self.delete_file_btn.config(state="disabled")

#     # ------------------------------------------------------------------
#     #  Application close handler
#     # ------------------------------------------------------------------
#     def on_app_closing(self):
#         if self.ask_unsaved_changes("closing the application"):
#             self.root.destroy()


# # ----------------------------------------------------------------------
# #  Entry-point
# # ----------------------------------------------------------------------
# def main():
#     import tkinter.simpledialog
#     tk.simpledialog = tkinter.simpledialog
#     root = tk.Tk()
#     ESP32SPIFFSManager(root)
#     root.mainloop()


# if __name__ == "__main__":
#     main()


# # #!/usr/bin/env python3
# # """
# # ESP32 SPIFFS Manager GUI
# # Windows GUI application for managing ESP32 SPIFFS filesystem
# # """
# # VERSION = "v.025"  #  <── incremented on every program update

# # import os
# # import json
# # import subprocess
# # import sys
# # import tkinter as tk
# # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # import csv
# # from pathlib import Path
# # import serial.tools.list_ports
# # import threading
# # from datetime import datetime

# # # ------------------------------------------------------------------
# # #  Main application class
# # # ------------------------------------------------------------------
# # class ESP32SPIFFSManager:
# #     def __init__(self, root):
# #         self.root = root
# #         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
# #         self.root.geometry("1000x700")
# #         self.root.minsize(800, 600)

# #         # Configuration
# #         self.config_file = "spiffs_config.json"
# #         self.load_config()

# #         # keep chip variable even though the UI element is hidden
# #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

# #         # --------------------------------------------------------------
# #         #  SPIFFS partition information (now loaded from ESP32)
# #         # --------------------------------------------------------------
# #         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
# #         self.current_spiffs_index = 0       # index inside self.spiffs_partitions

# #         # State variables
# #         self.connected = False
# #         self.current_files = {}       # filename → content (text content or empty for non‑text)
# #         self.selected_file = None     # filename currently in editor
# #         self.spiffs_downloaded = False
# #         self.editor_modified = False  # True while editor has unsaved changes

# #         # Create GUI
# #         self.create_widgets()
# #         self.scan_ports()

# #         # Ask on unsaved changes when user closes window
# #         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

# #         # Check required files on startup
# #         self.check_dependencies()

# #     # ------------------------------------------------------------------
# #     #  NEW:  generic "ask unsaved" helper  (returns True = proceed, False = abort)
# #     # ------------------------------------------------------------------
# #     def ask_unsaved_changes(self, action: str = "switch file"):
# #         """Return True if the caller may continue, False if user chose Cancel."""
# #         if not self.editor_modified:
# #             return True

# #         answer = messagebox.askyesnocancel(
# #             "Unsaved changes",
# #             f'File "{self.selected_file}" has unsaved changes.\n\n'
# #             f'Save before {action}?',
# #             default=messagebox.YES
# #         )
# #         if answer is True:          # Save
# #             self.save_current_file()
# #             return True
# #         elif answer is False:       # Discard
# #             return True
# #         else:                       # Cancel
# #             return False

# #     # ------------------------------------------------------------------
# #     #  Small helpers (unchanged)
# #     # ------------------------------------------------------------------
# #     @staticmethod
# #     def _ensure_int(value):
# #         """Return int whether value is already int or decimal/hex string."""
# #         if isinstance(value, int):
# #             return value
# #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# #     def load_config(self):
# #         default_config = {
# #             "spiffs_offset": 6750208,  # 0x670000
# #             "spiffs_size": 1572864,    # 0x180000
# #             "esp32_chip": "esp32-s3",
# #             "baud_rate": "921600",
# #             "last_port": ""
# #         }
# #         try:
# #             if os.path.exists(self.config_file):
# #                 with open(self.config_file, 'r') as f:
# #                     self.config = json.load(f)
# #                 for key, value in default_config.items():
# #                     if key not in self.config:
# #                         self.config[key] = value
# #             else:
# #                 self.config = default_config
# #                 self.save_config()
# #         except Exception as e:
# #             print(f"Error loading config: {e}")
# #             self.config = default_config
# #             self.save_config()

# #     def save_config(self):
# #         try:
# #             with open(self.config_file, 'w') as f:
# #                 json.dump(self.config, f, indent=4)
# #         except Exception as e:
# #             print(f"Error saving config: {e}")

# #     def format_value_for_display(self, value):
# #         if isinstance(value, int):
# #             return f"0x{value:X}"
# #         return str(value)

# #     def parse_value_from_input(self, value_str):
# #         value_str = value_str.strip()
# #         if value_str.lower().startswith('0x'):
# #             return int(value_str, 16)
# #         else:
# #             return int(value_str)

# #     def validate_config_input(self, value_str, field_name):
# #         try:
# #             return self.parse_value_from_input(value_str)
# #         except ValueError:
# #             messagebox.showerror("Invalid Input",
# #                                f"Invalid {field_name} value: {value_str}\n"
# #                                f"Please enter a decimal number or hex value (0x...)")
# #             return None

# #     # ------------------------------------------------------------------
# #     #  NEW:  Read partition table from ESP32
# #     # ------------------------------------------------------------------
# #     def read_partition_table_from_esp32(self):
# #         """Read and parse partition table from connected ESP32"""
# #         esp = None
# #         try:
# #             import esptool
            
# #             port = self.get_selected_port()
# #             if not port:
# #                 raise Exception("No COM port selected")
            
# #             print(f"Connecting to ESP32 on port {port}...")
            
# #             # Connect to ESP32
# #             esp = esptool.get_default_connected_device(
# #                 serial_list=[port],
# #                 port=port,
# #                 connect_attempts=7,
# #                 initial_baud=115200
# #             )
            
# #             if not esp:
# #                 raise Exception("Failed to connect to ESP32")
            
# #             # Detect chip model and extract base chip type
# #             chip_description = esp.get_chip_description()
# #             print(f"Chip detected: {chip_description}")
# #             chip_model = self.extract_chip_model(chip_description)
# #             print(f"Extracted chip model: {chip_model}")
# #             self.chip_var.set(chip_model)
# #             self.config["esp32_chip"] = chip_model
# #             self.save_config()
# #             self.chip_display_var.set(chip_description)
            
# #             # Read partition table
# #             PARTITION_TABLE_OFFSET = 0x8000
# #             PARTITION_TABLE_SIZE = 0xC00  # 3KB
            
# #             print(f"Reading partition table from offset 0x{PARTITION_TABLE_OFFSET:X}...")
# #             esp = esp.run_stub()
# #             partition_data = esp.read_flash(PARTITION_TABLE_OFFSET, PARTITION_TABLE_SIZE)
# #             print(f"Successfully read {len(partition_data)} bytes of partition table")
            
# #             # Parse partition table
# #             partitions = self.parse_partition_table(partition_data)
# #             print(f"Parsed {len(partitions)} partitions from table")
            
# #             # Filter only SPIFFS partitions
# #             spiffs_partitions = []
# #             for p in partitions:
# #                 if p['subtype'].lower() == 'spiffs':
# #                     # Convert hex strings to integers
# #                     offset = int(p['offset'], 0) if isinstance(p['offset'], str) else p['offset']
# #                     size = int(p['size'], 0) if isinstance(p['size'], str) else p['size']
# #                     spiffs_partitions.append({
# #                         "name": p['name'],
# #                         "offset": offset,
# #                         "size": size
# #                     })
# #                     print(f"Found SPIFFS partition: {p['name']} at 0x{offset:X}, size 0x{size:X}")
            
# #             if not spiffs_partitions:
# #                 raise Exception("No SPIFFS partitions found in partition table")
            
# #             return spiffs_partitions
            
# #         except ImportError:
# #             raise Exception("esptool library not found. Please install it: pip install esptool")
# #         except Exception as e:
# #             raise Exception(f"Failed to read partition table: {str(e)}")
# #         finally:
# #             # Ensure the connection is properly closed
# #             if esp is not None:
# #                 try:
# #                     esp._port.close()
# #                     print("ESP32 connection closed successfully")
# #                 except Exception as e:
# #                     print(f"Error closing ESP32 connection: {e}")

# #     def extract_chip_model(self, chip_description):
# #         """Extract base chip model from full chip description"""
# #         # Common ESP32 chip models
# #         chip_models = ['esp32-s2', 'esp32-s3', 'esp32-c3', 'esp32-c6', 'esp32']
        
# #         # Convert to lowercase for comparison
# #         desc_lower = chip_description.lower()
        
# #         # Check for specific chip models
# #         for model in chip_models:
# #             if model in desc_lower:
# #                 return model
        
# #         # Default fallback
# #         return 'esp32'

# #     def parse_partition_table(self, data):
# #         """Parse binary partition table data"""
# #         partitions = []
# #         offset = 0
        
# #         # MD5 hash is at the end, partition entries are 32 bytes each
# #         while offset < len(data) - 32:
# #             entry = data[offset:offset + 32]
            
# #             # Check for end marker (all 0xFF) or empty entry
# #             if entry[0:2] == b'\xFF\xFF' or entry[0:2] == b'\x00\x00':
# #                 break
            
# #             # Magic byte check (0xAA, 0x50)
# #             if entry[0] != 0xAA or entry[1] != 0x50:
# #                 offset += 32
# #                 continue
            
# #             # Parse partition entry
# #             p_type = entry[2]
# #             p_subtype = entry[3]
# #             p_offset = int.from_bytes(entry[4:8], 'little')
# #             p_size = int.from_bytes(entry[8:12], 'little')
            
# #             # Name is null-terminated string
# #             name_bytes = entry[12:28]
# #             name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='ignore')
            
# #             flags = int.from_bytes(entry[28:32], 'little')
            
# #             # Type and subtype mapping
# #             type_str = self.get_partition_type(p_type)
# #             subtype_str = self.get_partition_subtype(p_type, p_subtype)
            
# #             partitions.append({
# #                 'name': name,
# #                 'type': type_str,
# #                 'subtype': subtype_str,
# #                 'offset': f"0x{p_offset:X}",
# #                 'size': f"0x{p_size:X}",
# #                 'flags': f"0x{flags:X}"
# #             })
            
# #             offset += 32
        
# #         return partitions

# #     def get_partition_type(self, p_type):
# #         """Convert partition type byte to string"""
# #         types = {
# #             0x00: 'app',
# #             0x01: 'data',
# #         }
# #         return types.get(p_type, f'0x{p_type:02X}')

# #     def get_partition_subtype(self, p_type, p_subtype):
# #         """Convert partition subtype to string"""
# #         if p_type == 0x00:  # app
# #             subtypes = {
# #                 0x00: 'factory',
# #                 0x10: 'ota_0',
# #                 0x11: 'ota_1',
# #                 0x12: 'ota_2',
# #                 0x13: 'ota_3',
# #                 0x20: 'test',
# #             }
# #         elif p_type == 0x01:  # data
# #             subtypes = {
# #                 0x00: 'ota',
# #                 0x01: 'phy',
# #                 0x02: 'nvs',
# #                 0x03: 'coredump',
# #                 0x04: 'nvs_keys',
# #                 0x05: 'efuse',
# #                 0x80: 'esphttpd',
# #                 0x81: 'fat',
# #                 0x82: 'spiffs',
# #             }
# #         else:
# #             return f'0x{p_subtype:02X}'
        
# #         return subtypes.get(p_subtype, f'0x{p_subtype:02X}')

# #     # ------------------------------------------------------------------
# #     #  GUI creation (modified layout)
# #     # ------------------------------------------------------------------
# #     def create_widgets(self):
# #         main_frame = ttk.Frame(self.root, padding="10")
# #         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# #         self.root.columnconfigure(0, weight=1)
# #         self.root.rowconfigure(0, weight=1)
# #         main_frame.columnconfigure(1, weight=1)
# #         main_frame.rowconfigure(3, weight=1)

# #         # ---------------- Connection frame ----------------
# #         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
# #         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
# #         conn_frame.columnconfigure(1, weight=1)

# #         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# #         self.port_var = tk.StringVar()
# #         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
# #         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

# #         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
# #         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

# #         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
# #         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

# #         # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

# #         # ---------------- SPIFFS Configuration frame ----------------
# #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# #         # ----- Partition selector (wider) -----
# #         ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# #         self.partition_var = tk.StringVar()
# #         self.partition_combo = ttk.Combobox(
# #             spiffs_frame,
# #             textvariable=self.partition_var,
# #             state="readonly",
# #             width=40,                # made wider as requested
# #         )
# #         partition_names = [
# #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# #         ]
# #         self.partition_combo['values'] = partition_names
# #         if partition_names:  # Only set current if there are partitions
# #             self.partition_combo.current(self.current_spiffs_index)
# #         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
# #         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)
# #         self.partition_combo.state(['disabled'])          # locked until download

# #         # ----- Offset (read‑only) -----
# #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# #         self.offset_var = tk.StringVar()
# #         self.offset_entry = ttk.Entry(
# #             spiffs_frame,
# #             textvariable=self.offset_var,
# #             width=15,
# #             state="readonly"
# #         )
# #         self.offset_entry.grid(row=0, column=3, padx=(0, 10))
# #         self.offset_entry.state(['disabled'])

# #         # ----- Size (read‑only) -----
# #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
# #         self.size_var = tk.StringVar()
# #         self.size_entry = ttk.Entry(
# #             spiffs_frame,
# #             textvariable=self.size_var,
# #             width=15,
# #             state="readonly"
# #         )
# #         self.size_entry.grid(row=0, column=5, padx=(0, 10))
# #         self.size_entry.state(['disabled'])

# #         # ----- Chip (read‑only, shown after connection) -----
# #         ttk.Label(spiffs_frame, text="Chip:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
# #         self.chip_display_var = tk.StringVar()
# #         self.chip_display_entry = ttk.Entry(
# #             spiffs_frame,
# #             textvariable=self.chip_display_var,
# #             width=12,
# #             state="readonly"
# #         )
# #         self.chip_display_entry.grid(row=0, column=7, padx=(0, 10))
# #         self.chip_display_entry.state(['disabled'])

# #         # Initialise the displayed values (empty at start)
# #         self.update_spiffs_fields()

# #         # Hide the now‑redundant "Save Config" button (kept for layout)
# #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# #         self.save_config_btn.grid(row=0, column=8, padx=(10, 0))
# #         self.save_config_btn.grid_remove()          # completely hide it

# #         # ---------------- Action frame ----------------
# #         action_frame = ttk.Frame(main_frame)
# #         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

# #         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
# #         self.action_btn.grid(row=0, column=0, padx=(0, 10))
# #         self.action_btn.config(state="disabled")

# #         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
# #         self.progress.grid(row=0, column=1, padx=(10, 0))

# #         # ---------------- Content frame ----------------
# #         content_frame = ttk.Frame(main_frame)
# #         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
# #         content_frame.columnconfigure(1, weight=2)
# #         content_frame.rowconfigure(0, weight=1)

# #         # File list
# #         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
# #         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
# #         file_frame.columnconfigure(0, weight=1)
# #         file_frame.rowconfigure(0, weight=1)

# #         list_frame = ttk.Frame(file_frame)
# #         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# #         list_frame.columnconfigure(0, weight=1)
# #         list_frame.rowconfigure(0, weight=1)

# #         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
# #         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# #         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

# #         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
# #         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
# #         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

# #         file_btn_frame = ttk.Frame(file_frame)
# #         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

# #         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
# #         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))
# #         self.add_file_btn.config(state="disabled")   # enabled only after download

# #         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
# #         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
# #         self.save_file_btn.config(state="disabled")

# #         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
# #         self.delete_file_btn.grid(row=0, column=2)
# #         self.delete_file_btn.config(state="disabled")

# #         # Editor
# #         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
# #         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
# #         editor_frame.columnconfigure(0, weight=1)
# #         editor_frame.rowconfigure(0, weight=1)

# #         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
# #         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# #         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

# #         # Status bar
# #         self.status_var = tk.StringVar(value="Ready")
# #         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
# #         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

# #     # ------------------------------------------------------------------
# #     #  Dependency / connection / scan helpers (unchanged)
# #     # ------------------------------------------------------------------
# #     def check_dependencies(self):
# #         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
# #         missing_files = []
# #         for file in required_files:
# #             if not os.path.exists(file):
# #                 missing_files.append(file)
# #         if missing_files:
# #             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
# #             message += "\n\nPlease ensure these files are in the application directory."
# #             messagebox.showerror("Missing Dependencies", message)
# #             self.status_var.set("Missing dependencies")
# #             return False
# #         try:
# #             import serial.tools.list_ports
# #         except ImportError:
# #             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
# #             self.status_var.set("Missing pyserial")
# #             return False
# #         self.status_var.set("Dependencies OK")
# #         return True

# #     def scan_ports(self):
# #         ports = serial.tools.list_ports.comports()
# #         port_list = []
# #         for port in ports:
# #             description = port.description if port.description != 'n/a' else 'Unknown device'
# #             port_display = f"{port.device} - {description}"
# #             port_list.append(port_display)
# #         self.port_combo['values'] = port_list
# #         if self.config.get("last_port"):
# #             for port_display in port_list:
# #                 if port_display.startswith(self.config["last_port"] + " "):
# #                     self.port_var.set(port_display)
# #                     break
# #         elif port_list:
# #             self.port_var.set(port_list[0])
# #         self.status_var.set(f"Found {len(port_list)} COM ports")

# #     def get_selected_port(self):
# #         port_display = self.port_var.get()
# #         if not port_display:
# #             return ""
# #         return port_display.split(" - ")[0]

# #     # ------------------------------------------------------------------
# #     #  NEW:  on disconnect reset button to initial state + clear file list & editor
# #     # ------------------------------------------------------------------
# #     def toggle_connection(self):
# #         if not self.connected:
# #             if not self.port_var.get():
# #                 messagebox.showerror("Error", "Please select a COM port")
# #                 return

# #             try:
# #                 # Read partition table from ESP32
# #                 self.status_var.set("Reading partition table...")
# #                 self.root.update()
                
# #                 spiffs_partitions = self.read_partition_table_from_esp32()
                
# #                 # Update internal state with new partitions
# #                 self.spiffs_partitions = spiffs_partitions
# #                 self.current_spiffs_index = 0
                
# #                 # Update UI with new partition data
# #                 self.update_partition_combo()
                
# #                 # Connection considered successful
# #                 self.connected = True
# #                 self.connect_btn.config(text="Disconnect")
# #                 self.action_btn.config(state="normal")
                
# #                 # Enable partition combo when connected
# #                 self.partition_combo.state(['!disabled'])
                
# #                 self.config["last_port"] = self.get_selected_port()
# #                 self.save_config()
# #                 self.status_var.set(f"Connected to {self.get_selected_port()} ({self.chip_var.get()})")
                
# #             except Exception as e:
# #                 messagebox.showerror("Connection Error", f"Could not read partition table:\n{e}")
# #                 self.status_var.set("Connection failed")
# #                 return

# #         else:
# #             # ---------- disconnect ----------
# #             self.connected = False
# #             self.connect_btn.config(text="Connect")
# #             self.action_btn.config(state="disabled")
# #             # reset big button to initial download state
# #             self.spiffs_downloaded = False
# #             self.action_btn.config(text="Download SPIFFS")
# #             # clear file list and editor
# #             self.file_listbox.delete(0, tk.END)
# #             self.content_editor.delete(1.0, tk.END)
# #             self.current_files.clear()
# #             self.selected_file = None
# #             self.editor_modified = False
# #             self.save_file_btn.config(state="disabled")
# #             self.delete_file_btn.config(state="disabled")
# #             self.add_file_btn.config(state="disabled")
# #             # unlock COM port UI
# #             self.port_combo.state(['!disabled'])
# #             self.scan_btn.state(['!disabled'])
# #             # clear partition UI
# #             self.partition_combo.state(['disabled'])  # disable when disconnected
# #             self.offset_entry.state(['disabled'])
# #             self.size_entry.state(['disabled'])
# #             self.chip_display_var.set("")
# #             self.chip_display_entry.state(['disabled'])
# #             self.status_var.set("Disconnected")

# #     def update_partition_combo(self):
# #         """Update the partition combo box with current partitions"""
# #         partition_names = [
# #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# #         ]
# #         self.partition_combo['values'] = partition_names
# #         if partition_names:  # Only set current if there are partitions
# #             self.partition_combo.current(self.current_spiffs_index)
# #         self.update_spiffs_fields()

# #     # ------------------------------------------------------------------
# #     #  NEW:  Called when the user changes the selected partition
# #     # ------------------------------------------------------------------
# #     def on_partition_selected(self, event=None):
# #         """Update offset/size fields to reflect the newly selected partition."""
# #         try:
# #             self.current_spiffs_index = self.partition_combo.current()
# #             self.update_spiffs_fields()
# #         except Exception:
# #             pass   # defensive – should never happen

# #     def update_spiffs_fields(self):
# #         """Write the offset and size of the currently selected partition to the UI."""
# #         if not self.spiffs_partitions:
# #             self.offset_var.set("")
# #             self.size_var.set("")
# #             return
# #         part = self.spiffs_partitions[self.current_spiffs_index]
# #         self.offset_var.set(self.format_value_for_display(part['offset']))
# #         self.size_var.set(self.format_value_for_display(part['size']))

# #     def save_spiffs_config(self):
# #         # The configuration is now derived from ESP32 partition table
# #         messagebox.showinfo(
# #             "Info",
# #             "SPIFFS partitions are read directly from the connected ESP32.\n"
# #             "No configuration file is used."
# #         )

# #     def perform_action(self):
# #         if not self.connected:
# #             messagebox.showerror("Error", "Not connected to ESP32")
# #             return
# #         if not self.spiffs_downloaded:
# #             self.download_spiffs()
# #         else:
# #             # ---- ask for confirmation before upload ----
# #             if not messagebox.askyesno("Confirm Upload",
# #                                        "Are you sure you want to upload the SPIFFS image to the ESP32?"):
# #                 return
# #             # ---- ask for unsaved before upload ----
# #             if not self.ask_unsaved_changes("uploading"):
# #                 return
# #             self.upload_spffs()

# #     def download_spiffs(self):
# #         def download_worker():
# #             try:
# #                 self.progress.start()
# #                 self.action_btn.config(state="disabled")
# #                 self.status_var.set("Downloading SPIFFS...")

# #                 # Use the values from the selected partition
# #                 part = self.spiffs_partitions[self.current_spiffs_index]
# #                 offset_val = part['offset']
# #                 size_val   = part['size']

# #                 offset_hex = f"0x{offset_val:X}"
# #                 size_dec   = str(size_val)

# #                 cmd = [
# #                     "esptool.exe",
# #                     "--chip", self.chip_var.get(),
# #                     "--port", self.get_selected_port(),
# #                     "--baud", self.config["baud_rate"],
# #                     "read_flash", offset_hex, size_dec,
# #                     "spiffs_dump.bin"
# #                 ]
                
# #                 print(f"Executing command: {' '.join(cmd)}")
                
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 print(f"esptool return code: {result.returncode}")
# #                 if result.stdout:
# #                     print(f"esptool stdout: {result.stdout}")
# #                 if result.stderr:
# #                     print(f"esptool stderr: {result.stderr}")
                
# #                 if result.returncode != 0:
# #                     error_msg = result.stderr if result.stderr else "Unknown error"
# #                     raise Exception(f"Failed to read flash: {error_msg}")

# #                 data_dir = Path("data")
# #                 data_dir.mkdir(exist_ok=True)
# #                 for file in data_dir.glob("*"):
# #                     if file.is_file():
# #                         file.unlink()

# #                 cmd = [
# #                     "mkspiffs_espressif32_arduino.exe",
# #                     "-u", "data",
# #                     "spiffs_dump.bin"
# #                 ]
                
# #                 print(f"Executing command: {' '.join(cmd)}")
                
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 print(f"mkspiffs return code: {result.returncode}")
# #                 if result.stdout:
# #                     print(f"mkspiffs stdout: {result.stdout}")
# #                 if result.stderr:
# #                     print(f"mkspiffs stderr: {result.stderr}")
                
# #                 if result.returncode != 0:
# #                     error_msg = result.stderr if result.stderr else "Unknown error"
# #                     raise Exception(f"Failed to extract SPIFFS: {error_msg}")

# #                 self.root.after(0, self.download_complete)

# #             except Exception as e:
# #                 error_msg = str(e)
# #                 print(f"Download error: {error_msg}")
# #                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

# #         thread = threading.Thread(target=download_worker)
# #         thread.daemon = True
# #         thread.start()

# #     def download_complete(self):
# #         self.progress.stop()
# #         self.action_btn.config(state="normal", text="Upload SPIFFS")
# #         self.spiffs_downloaded = True
# #         self.status_var.set("SPIFFS downloaded successfully")
# #         self.load_files()
# #         # Enable partition UI now that we have data
# #         self.partition_combo.state(['!disabled'])
# #         self.offset_entry.state(['!disabled'])
# #         self.size_entry.state(['!disabled'])
# #         self.add_file_btn.config(state="normal")
# #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# #     def download_error(self, error_msg):
# #         self.progress.stop()
# #         self.action_btn.config(state="normal")
# #         self.status_var.set("Download failed")
# #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# #     def upload_spiffs(self):
# #         def upload_worker():
# #             try:
# #                 self.progress.start()
# #                 self.action_btn.config(state="disabled")
# #                 self.status_var.set("Creating SPIFFS image...")

# #                 spiffs_dir = Path("spiffs")
# #                 spiffs_dir.mkdir(exist_ok=True)

# #                 # Use the values from the selected partition
# #                 part = self.spiffs_partitions[self.current_spiffs_index]
# #                 size_val   = part['size']
# #                 offset_val = part['offset']

# #                 cmd = [
# #                     "mkspiffs_espressif32_arduino.exe",
# #                     "-c", "data",
# #                     "-p", "256",
# #                     "-b", "4096",
# #                     "-s", str(size_val),
# #                     "spiffs/data.bin"
# #                 ]
                
# #                 print(f"Executing command: {' '.join(cmd)}")
                
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 print(f"mkspiffs create return code: {result.returncode}")
# #                 if result.stdout:
# #                     print(f"mkspiffs create stdout: {result.stdout}")
# #                 if result.stderr:
# #                     print(f"mkspiffs create stderr: {result.stderr}")
                
# #                 if result.returncode != 0:
# #                     error_msg = result.stderr if result.stderr else "Unknown error"
# #                     raise Exception(f"Failed to create SPIFFS image: {error_msg}")

# #                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

# #                 offset_hex = f"0x{offset_val:X}"
# #                 cmd = [
# #                     "esptool.exe",
# #                     "--chip", self.chip_var.get(),
# #                     "--port", self.get_selected_port(),
# #                     "--baud", self.config["baud_rate"],
# #                     "--before", "default_reset",
# #                     "--after", "hard_reset",
# #                     "write_flash", "-z",
# #                     "--flash_mode", "dio",
# #                     "--flash_size", "detect",
# #                     offset_hex, "spiffs/data.bin"
# #                 ]
                
# #                 print(f"Executing command: {' '.join(cmd)}")
                
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 print(f"esptool write return code: {result.returncode}")
# #                 if result.stdout:
# #                     print(f"esptool write stdout: {result.stdout}")
# #                 if result.stderr:
# #                     print(f"esptool write stderr: {result.stderr}")
                
# #                 if result.returncode != 0:
# #                     error_msg = result.stderr if result.stderr else "Unknown error"
# #                     raise Exception(f"Failed to upload SPIFFS: {error_msg}")

# #                 self.root.after(0, self.upload_complete)

# #             except Exception as e:
# #                 error_msg = str(e)
# #                 print(f"Upload error: {error_msg}")
# #                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

# #         thread = threading.Thread(target=upload_worker)
# #         thread.daemon = True
# #         thread.start()

# #     def upload_complete(self):
# #         self.progress.stop()
# #         self.action_btn.config(state="normal")
# #         self.status_var.set("SPIFFS uploaded successfully")
# #         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

# #     def upload_error(self, error_msg):
# #         self.progress.stop()
# #         self.action_btn.config(state="normal")
# #         self.status_var.set("Upload failed")
# #         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

# #     # ------------------------------------------------------------------
# #     #  File management (adjusted for editor_modified flag, full file list)
# #     # ------------------------------------------------------------------
# #     def load_files(self):
# #         self.current_files = {}
# #         self.file_listbox.delete(0, tk.END)
# #         data_dir = Path("data")
# #         if not data_dir.exists():
# #             return
# #         # we now list *all* files; only read as text when possible
# #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# #         file_paths = list(data_dir.iterdir())
        
# #         print(f"Loading {len(file_paths)} files from data directory")
        
# #         for file_path in file_paths:
# #             if file_path.is_file():
# #                 filename = file_path.name
# #                 try:
# #                     if file_path.suffix.lower() in text_extensions:
# #                         with open(file_path, 'r', encoding='utf-8') as f:
# #                             content = f.read()
# #                         print(f"Loaded text file: {filename} ({len(content)} chars)")
# #                     else:
# #                         # binary or unknown – keep empty placeholder
# #                         content = ""
# #                         print(f"Loaded binary file: {filename} (empty content)")
# #                     self.current_files[filename] = content
# #                     self.file_listbox.insert(tk.END, filename)
# #                 except Exception as e:
# #                     print(f"Error reading {file_path}: {e}")
# #                     # Still add the file to the list but with error content
# #                     self.current_files[filename] = f"[Error reading file: {e}]"
# #                     self.file_listbox.insert(tk.END, filename)
        
# #         # keep add‑file button enabled after a successful download
# #         if self.spiffs_downloaded:
# #             self.add_file_btn.config(state="normal")
        
# #         # Select the first file if there are any files
# #         if self.current_files:
# #             first_filename = list(self.current_files.keys())[0]
# #             print(f"Selecting first file: {first_filename}")
# #             self.file_listbox.selection_set(0)
# #             self.on_file_select()
# #         else:
# #             print("No files found in data directory")

# #     # NEW:  ask unsaved when changing file selection
# #     def on_file_select(self, event=None):
# #         selection = self.file_listbox.curselection()
# #         if not selection:
# #             return
# #         if not self.ask_unsaved_changes("switching file"):
# #             # restore previous selection
# #             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
# #             self.file_listbox.selection_clear(0, tk.END)
# #             self.file_listbox.selection_set(idx)
# #             return

# #         filename = self.file_listbox.get(selection[0])
# #         print(f"Selected file: {filename}")
# #         if filename in self.current_files:
# #             self.selected_file = filename
# #             content = self.current_files[filename]
# #             print(f"File content length: {len(content)}")
# #             self.content_editor.delete(1.0, tk.END)
# #             self.content_editor.insert(1.0, content)
# #             self.editor_modified = False
# #             self.save_file_btn.config(state="disabled")
# #             self.delete_file_btn.config(state="normal")

# #     def on_content_changed(self, event=None):
# #         if self.selected_file:
# #             self.editor_modified = True
# #             self.save_file_btn.config(state="normal")

# #     def save_current_file(self):
# #         if not self.selected_file:
# #             return
# #         content = self.content_editor.get(1.0, tk.END).rstrip()
# #         self.current_files[self.selected_file] = content
# #         try:
# #             data_dir = Path("data")
# #             data_dir.mkdir(exist_ok=True)
# #             file_path = data_dir / self.selected_file
# #             with open(file_path, 'w', encoding='utf-8') as f:
# #                 f.write(content)
# #             self.editor_modified = False
# #             self.save_file_btn.config(state="disabled")
# #             self.status_var.set(f"Saved {self.selected_file}")
# #         except Exception as e:
# #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# #     # ------------------------------------------------------------------
# #     #  NEW:  Simple Add‑File that selects an existing file from the host
# #     # ------------------------------------------------------------------
# #     def add_file(self):
# #         src_path = filedialog.askopenfilename(title="Select file to add")
# #         if not src_path:
# #             return

# #         filename = os.path.basename(src_path)
# #         if filename in self.current_files:
# #             messagebox.showerror("Error", f"File \"{filename}\" already exists in the SPIFFS.")
# #             return

# #         try:
# #             with open(src_path, 'r', encoding='utf-8') as f:
# #                 content = f.read()
# #         except Exception as e:
# #             messagebox.showerror("Error", f"Could not read selected file:\n{e}")
# #             return

# #         # Register in internal structures and write to disk
# #         self.current_files[filename] = content
# #         self.file_listbox.insert(tk.END, filename)

# #         data_dir = Path("data")
# #         data_dir.mkdir(exist_ok=True)
# #         dest_path = data_dir / filename
# #         try:
# #             with open(dest_path, 'w', encoding='utf-8') as f:
# #                 f.write(content)
# #         except Exception as e:
# #             messagebox.showerror("Error", f"Failed to copy file to data folder:\n{e}")
# #             return

# #         self.file_listbox.selection_clear(0, tk.END)
# #         self.file_listbox.selection_set(tk.END)
# #         self.on_file_select()

# #     def delete_file(self):
# #         if not self.selected_file:
# #             return
# #         result = messagebox.askyesno("Confirm Delete",
# #                                    f"Are you sure you want to delete {self.selected_file}?")
# #         if not result:
# #             return
# #         del self.current_files[self.selected_file]
# #         selection = self.file_listbox.curselection()
# #         if selection:
# #             self.file_listbox.delete(selection[0])
# #         try:
# #             file_path = Path("data") / self.selected_file
# #             if file_path.exists():
# #                 file_path.unlink()
# #         except Exception as e:
# #             print(f"Error deleting file: {e}")
# #         self.content_editor.delete(1.0, tk.END)
# #         self.selected_file = None
# #         self.editor_modified = False
# #         self.save_file_btn.config(state="disabled")
# #         self.delete_file_btn.config(state="disabled")

# #     # ------------------------------------------------------------------
# #     #  Application close handler
# #     # ------------------------------------------------------------------
# #     def on_app_closing(self):
# #         if self.ask_unsaved_changes("closing the application"):
# #             self.root.destroy()


# # # ----------------------------------------------------------------------
# # #  Entry-point
# # # ----------------------------------------------------------------------
# # def main():
# #     import tkinter.simpledialog
# #     tk.simpledialog = tkinter.simpledialog
# #     root = tk.Tk()
# #     ESP32SPIFFSManager(root)
# #     root.mainloop()


# # if __name__ == "__main__":
# #     main()






# # # #!/usr/bin/env python3
# # # """
# # # ESP32 SPIFFS Manager GUI
# # # Windows GUI application for managing ESP32 SPIFFS filesystem
# # # """
# # # VERSION = "v.017"  #  <── incremented on every program update

# # # import os
# # # import json
# # # import subprocess
# # # import sys
# # # import tkinter as tk
# # # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # # import csv                      # new – to read partitions.csv
# # # from pathlib import Path
# # # import serial.tools.list_ports
# # # import threading
# # # from datetime import datetime

# # # # ------------------------------------------------------------------
# # # #  Main application class
# # # # ------------------------------------------------------------------
# # # class ESP32SPIFFSManager:
# # #     def __init__(self, root):
# # #         self.root = root
# # #         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
# # #         self.root.geometry("1000x700")
# # #         self.root.minsize(800, 600)

# # #         # Configuration
# # #         self.config_file = "spiffs_config.json"
# # #         self.load_config()

# # #         # keep chip variable even though the UI element is hidden
# # #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

# # #         # --------------------------------------------------------------
# # #         #  Load SPIFFS partition information from *partitions.csv*
# # #         # --------------------------------------------------------------
# # #         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
# # #         self.current_spiffs_index = 0       # index inside self.spiffs_partitions
# # #         self.load_partitions_csv()

# # #         # State variables
# # #         self.connected = False
# # #         self.current_files = {}       # filename → content (text content or empty for non‑text)
# # #         self.selected_file = None     # filename currently in editor
# # #         self.spiffs_downloaded = False
# # #         self.editor_modified = False  # True while editor has unsaved changes

# # #         # Create GUI
# # #         self.create_widgets()
# # #         self.scan_ports()

# # #         # Ask on unsaved changes when user closes window
# # #         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

# # #         # Check required files on startup
# # #         self.check_dependencies()

# # #     # ------------------------------------------------------------------
# # #     #  NEW:  generic "ask unsaved" helper  (returns True = proceed, False = abort)
# # #     # ------------------------------------------------------------------
# # #     def ask_unsaved_changes(self, action: str = "switch file"):
# # #         """Return True if the caller may continue, False if user chose Cancel."""
# # #         if not self.editor_modified:
# # #             return True

# # #         answer = messagebox.askyesnocancel(
# # #             "Unsaved changes",
# # #             f'File "{self.selected_file}" has unsaved changes.\n\n'
# # #             f'Save before {action}?',
# # #             default=messagebox.YES
# # #         )
# # #         if answer is True:          # Save
# # #             self.save_current_file()
# # #             return True
# # #         elif answer is False:       # Discard
# # #             return True
# # #         else:                       # Cancel
# # #             return False

# # #     # ------------------------------------------------------------------
# # #     #  Small helpers (unchanged)
# # #     # ------------------------------------------------------------------
# # #     @staticmethod
# # #     def _ensure_int(value):
# # #         """Return int whether value is already int or decimal/hex string."""
# # #         if isinstance(value, int):
# # #             return value
# # #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# # #     def load_config(self):
# # #         default_config = {
# # #             "spiffs_offset": 6750208,  # 0x670000
# # #             "spiffs_size": 1572864,    # 0x180000
# # #             "esp32_chip": "esp32-s3",
# # #             "baud_rate": "921600",
# # #             "last_port": ""
# # #         }
# # #         try:
# # #             if os.path.exists(self.config_file):
# # #                 with open(self.config_file, 'r') as f:
# # #                     self.config = json.load(f)
# # #                 for key, value in default_config.items():
# # #                     if key not in self.config:
# # #                         self.config[key] = value
# # #             else:
# # #                 self.config = default_config
# # #                 self.save_config()
# # #         except Exception as e:
# # #             print(f"Error loading config: {e}")
# # #             self.config = default_config
# # #             self.save_config()

# # #     def save_config(self):
# # #         try:
# # #             with open(self.config_file, 'w') as f:
# # #                 json.dump(self.config, f, indent=4)
# # #         except Exception as e:
# # #             print(f"Error saving config: {e}")

# # #     def format_value_for_display(self, value):
# # #         if isinstance(value, int):
# # #             return f"0x{value:X}"
# # #         return str(value)

# # #     def parse_value_from_input(self, value_str):
# # #         value_str = value_str.strip()
# # #         if value_str.lower().startswith('0x'):
# # #             return int(value_str, 16)
# # #         else:
# # #             return int(value_str)

# # #     def validate_config_input(self, value_str, field_name):
# # #         try:
# # #             return self.parse_value_from_input(value_str)
# # #         except ValueError:
# # #             messagebox.showerror("Invalid Input",
# # #                                f"Invalid {field_name} value: {value_str}\n"
# # #                                f"Please enter a decimal number or hex value (0x...)")
# # #             return None

# # #     # ------------------------------------------------------------------
# # #     #  NEW:  Read «partitions.csv» and extract all SPIFFS partitions
# # #     # ------------------------------------------------------------------
# # #     def load_partitions_csv(self):
# # #         """
# # #         Looks for a file named *partitions.csv* in the same directory as this
# # #         script.  It must contain a header (or not) with the columns:

# # #             name, type, subtype, offset, size, flags

# # #         All rows whose *subtype* is exactly ``spiffs`` (case‑insensitive) are
# # #         collected.  For each such row we store the name, the integer offset
# # #         and the integer size (hex strings are accepted).  If the file is not
# # #         present or no SPIFFS partition is found, we abort with an error
# # #         message.
# # #         """
# # #         csv_path = Path(__file__).parent / "partitions.csv"
# # #         if not csv_path.is_file():
# # #             messagebox.showerror(
# # #                 "Missing file",
# # #                 "Required file *partitions.csv* not found in the script folder.\n"
# # #                 "The program cannot determine the SPIFFS offset/size.\n"
# # #                 "Place a valid partitions.csv next to the script and restart."
# # #             )
# # #             sys.exit(1)

# # #         try:
# # #             with csv_path.open(newline='') as f:
# # #                 reader = csv.reader(f)
# # #                 for row in reader:
# # #                     # skip empty lines / comments
# # #                     if not row or row[0].strip().startswith('#'):
# # #                         continue
# # #                     # the CSV is usually: name,type,subtype,offset,size,flags
# # #                     if len(row) < 5:
# # #                         continue
# # #                     name, _type, subtype, offset_str, size_str = (
# # #                         row[0].strip(),
# # #                         row[1].strip(),
# # #                         row[2].strip(),
# # #                         row[3].strip(),
# # #                         row[4].strip(),
# # #                     )
# # #                     if subtype.lower() != 'spiffs':
# # #                         continue
# # #                     # Convert hex/dec strings to int
# # #                     offset = int(offset_str, 0)
# # #                     size   = int(size_str, 0)
# # #                     self.spiffs_partitions.append({
# # #                         "name"  : name,
# # #                         "offset": offset,
# # #                         "size"  : size,
# # #                     })
# # #         except Exception as e:
# # #             messagebox.showerror(
# # #                 "Error reading partitions.csv",
# # #                 f"Could not parse *partitions.csv*:\n{e}"
# # #             )
# # #             sys.exit(1)

# # #         if not self.spiffs_partitions:
# # #             messagebox.showerror(
# # #                 "No SPIFFS partition",
# # #                 "The *partitions.csv* file does not contain any SPIFFS partition entries."
# # #             )
# # #             sys.exit(1)

# # #         # Use the first partition as the default selection
# # #         self.current_spiffs_index = 0

# # #     # ------------------------------------------------------------------
# # #     #  GUI creation (modified layout)
# # #     # ------------------------------------------------------------------
# # #     def create_widgets(self):
# # #         main_frame = ttk.Frame(self.root, padding="10")
# # #         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # #         self.root.columnconfigure(0, weight=1)
# # #         self.root.rowconfigure(0, weight=1)
# # #         main_frame.columnconfigure(1, weight=1)
# # #         main_frame.rowconfigure(3, weight=1)

# # #         # ---------------- Connection frame ----------------
# # #         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
# # #         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
# # #         conn_frame.columnconfigure(1, weight=1)

# # #         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # #         self.port_var = tk.StringVar()
# # #         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
# # #         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

# # #         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
# # #         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

# # #         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
# # #         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

# # #         # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

# # #         # ---------------- SPIFFS Configuration frame ----------------
# # #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# # #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# # #         # ----- Partition selector (wider) -----
# # #         ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # #         self.partition_var = tk.StringVar()
# # #         self.partition_combo = ttk.Combobox(
# # #             spiffs_frame,
# # #             textvariable=self.partition_var,
# # #             state="readonly",
# # #             width=40,                # made wider as requested
# # #         )
# # #         partition_names = [
# # #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# # #         ]
# # #         self.partition_combo['values'] = partition_names
# # #         self.partition_combo.current(self.current_spiffs_index)
# # #         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
# # #         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)
# # #         self.partition_combo.state(['disabled'])          # locked until download

# # #         # ----- Offset (read‑only) -----
# # #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# # #         self.offset_var = tk.StringVar()
# # #         self.offset_entry = ttk.Entry(
# # #             spiffs_frame,
# # #             textvariable=self.offset_var,
# # #             width=15,
# # #             state="readonly"
# # #         )
# # #         self.offset_entry.grid(row=0, column=3, padx=(0, 10))
# # #         self.offset_entry.state(['disabled'])

# # #         # ----- Size (read‑only) -----
# # #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
# # #         self.size_var = tk.StringVar()
# # #         self.size_entry = ttk.Entry(
# # #             spiffs_frame,
# # #             textvariable=self.size_var,
# # #             width=15,
# # #             state="readonly"
# # #         )
# # #         self.size_entry.grid(row=0, column=5, padx=(0, 10))
# # #         self.size_entry.state(['disabled'])

# # #         # ----- Chip (read‑only, shown after connection) -----
# # #         ttk.Label(spiffs_frame, text="Chip:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
# # #         self.chip_display_var = tk.StringVar()
# # #         self.chip_display_entry = ttk.Entry(
# # #             spiffs_frame,
# # #             textvariable=self.chip_display_var,
# # #             width=12,
# # #             state="readonly"
# # #         )
# # #         self.chip_display_entry.grid(row=0, column=7, padx=(0, 10))
# # #         self.chip_display_entry.state(['disabled'])

# # #         # Initialise the displayed values (empty at start)
# # #         self.update_spiffs_fields()

# # #         # Hide the now‑redundant "Save Config" button (kept for layout)
# # #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# # #         self.save_config_btn.grid(row=0, column=8, padx=(10, 0))
# # #         self.save_config_btn.grid_remove()          # completely hide it

# # #         # ---------------- Action frame ----------------
# # #         action_frame = ttk.Frame(main_frame)
# # #         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

# # #         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
# # #         self.action_btn.grid(row=0, column=0, padx=(0, 10))
# # #         self.action_btn.config(state="disabled")

# # #         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
# # #         self.progress.grid(row=0, column=1, padx=(10, 0))

# # #         # ---------------- Content frame ----------------
# # #         content_frame = ttk.Frame(main_frame)
# # #         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
# # #         content_frame.columnconfigure(1, weight=2)
# # #         content_frame.rowconfigure(0, weight=1)

# # #         # File list
# # #         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
# # #         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
# # #         file_frame.columnconfigure(0, weight=1)
# # #         file_frame.rowconfigure(0, weight=1)

# # #         list_frame = ttk.Frame(file_frame)
# # #         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # #         list_frame.columnconfigure(0, weight=1)
# # #         list_frame.rowconfigure(0, weight=1)

# # #         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
# # #         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # #         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

# # #         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
# # #         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
# # #         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

# # #         file_btn_frame = ttk.Frame(file_frame)
# # #         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

# # #         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
# # #         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))
# # #         self.add_file_btn.config(state="disabled")   # enabled only after download

# # #         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
# # #         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
# # #         self.save_file_btn.config(state="disabled")

# # #         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
# # #         self.delete_file_btn.grid(row=0, column=2)
# # #         self.delete_file_btn.config(state="disabled")

# # #         # Editor
# # #         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
# # #         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
# # #         editor_frame.columnconfigure(0, weight=1)
# # #         editor_frame.rowconfigure(0, weight=1)

# # #         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
# # #         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # #         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

# # #         # Status bar
# # #         self.status_var = tk.StringVar(value="Ready")
# # #         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
# # #         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

# # #     # ------------------------------------------------------------------
# # #     #  Dependency / connection / scan helpers (unchanged)
# # #     # ------------------------------------------------------------------
# # #     def check_dependencies(self):
# # #         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
# # #         missing_files = []
# # #         for file in required_files:
# # #             if not os.path.exists(file):
# # #                 missing_files.append(file)
# # #         if missing_files:
# # #             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
# # #             message += "\n\nPlease ensure these files are in the application directory."
# # #             messagebox.showerror("Missing Dependencies", message)
# # #             self.status_var.set("Missing dependencies")
# # #             return False
# # #         try:
# # #             import serial.tools.list_ports
# # #         except ImportError:
# # #             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
# # #             self.status_var.set("Missing pyserial")
# # #             return False
# # #         self.status_var.set("Dependencies OK")
# # #         return True

# # #     def scan_ports(self):
# # #         ports = serial.tools.list_ports.comports()
# # #         port_list = []
# # #         for port in ports:
# # #             description = port.description if port.description != 'n/a' else 'Unknown device'
# # #             port_display = f"{port.device} - {description}"
# # #             port_list.append(port_display)
# # #         self.port_combo['values'] = port_list
# # #         if self.config.get("last_port"):
# # #             for port_display in port_list:
# # #                 if port_display.startswith(self.config["last_port"] + " "):
# # #                     self.port_var.set(port_display)
# # #                     break
# # #         elif port_list:
# # #             self.port_var.set(port_list[0])
# # #         self.status_var.set(f"Found {len(port_list)} COM ports")

# # #     def get_selected_port(self):
# # #         port_display = self.port_var.get()
# # #         if not port_display:
# # #             return ""
# # #         return port_display.split(" - ")[0]

# # #     # ------------------------------------------------------------------
# # #     #  NEW:  on disconnect reset button to initial state + clear file list & editor
# # #     # ------------------------------------------------------------------
# # #     def toggle_connection(self):
# # #         if not self.connected:
# # #             if not self.port_var.get():
# # #                 messagebox.showerror("Error", "Please select a COM port")
# # #                 return

# # #             # ---- auto‑detect ESP32 chip ----
# # #             chip, err = self.detect_chip()
# # #             if chip is None:
# # #                 messagebox.showerror("Connection Error", f"Could not detect ESP32 chip:\n{err}")
# # #                 return

# # #             # Store detected chip for later use
# # #             self.chip_var.set(chip)
# # #             self.config["esp32_chip"] = chip
# # #             self.save_config()
# # #             self.chip_display_var.set(chip)
# # #             self.chip_display_entry.state(['!disabled'])

# # #             # lock/combo to prevent changes while connected
# # #             self.port_combo.state(['disabled'])
# # #             self.scan_btn.state(['disabled'])

# # #             # Connection considered successful (esptool already succeeded)
# # #             self.connected = True
# # #             self.connect_btn.config(text="Disconnect")
# # #             self.action_btn.config(state="normal")
            
# # #             # Enable partition combo when connected
# # #             self.partition_combo.state(['!disabled'])
            
# # #             self.config["last_port"] = self.get_selected_port()
# # #             self.save_config()
# # #             self.status_var.set(f"Connected to {self.get_selected_port()} ({chip})")
# # #         else:
# # #             # ---------- disconnect ----------
# # #             self.connected = False
# # #             self.connect_btn.config(text="Connect")
# # #             self.action_btn.config(state="disabled")
# # #             # reset big button to initial download state
# # #             self.spiffs_downloaded = False
# # #             self.action_btn.config(text="Download SPIFFS")
# # #             # clear file list and editor
# # #             self.file_listbox.delete(0, tk.END)
# # #             self.content_editor.delete(1.0, tk.END)
# # #             self.current_files.clear()
# # #             self.selected_file = None
# # #             self.editor_modified = False
# # #             self.save_file_btn.config(state="disabled")
# # #             self.delete_file_btn.config(state="disabled")
# # #             self.add_file_btn.config(state="disabled")
# # #             # unlock COM port UI
# # #             self.port_combo.state(['!disabled'])
# # #             self.scan_btn.state(['!disabled'])
# # #             # clear partition UI
# # #             self.partition_combo.state(['disabled'])  # disable when disconnected
# # #             self.offset_entry.state(['disabled'])
# # #             self.size_entry.state(['disabled'])
# # #             self.chip_display_var.set("")
# # #             self.chip_display_entry.state(['disabled'])
# # #             self.status_var.set("Disconnected")

# # #     # ------------------------------------------------------------------
# # #     #  NEW:  ESP32 chip auto‑recognition
# # #     # ------------------------------------------------------------------
# # #     def detect_chip(self):
# # #         """
# # #         Runs ``esptool.exe chip_id`` and parses its output.
# # #         Returns a tuple (chip_name, error_message). ``chip_name`` is one of
# # #         ``esp32``, ``esp32-s2``, ``esp32-s3``, ``esp32-c3``, ``esp32-c6``.
# # #         If detection fails, ``chip_name`` is ``None`` and ``error_message``
# # #         contains the reason.
# # #         """
# # #         cmd = [
# # #             "esptool.exe",
# # #             "--port", self.get_selected_port(),
# # #             "chip_id"
# # #         ]
# # #         try:
# # #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
# # #         except Exception as e:
# # #             return None, str(e)

# # #         if result.returncode != 0:
# # #             return None, result.stderr or "esptool error"

# # #         for line in result.stdout.splitlines():
# # #             if "Chip is" in line:
# # #                 name_part = line.split("Chip is")[-1].strip().lower()
# # #                 if "esp32s3" in name_part:
# # #                     return "esp32-s3", None
# # #                 if "esp32s2" in name_part:
# # #                     return "esp32-s2", None
# # #                 if "esp32c3" in name_part:
# # #                     return "esp32-c3", None
# # #                 if "esp32c6" in name_part:
# # #                     return "esp32-c6", None
# # #                 if "esp32" in name_part:
# # #                     return "esp32", None
# # #         return None, "Unable to parse chip type from esptool output"

# # #     # ------------------------------------------------------------------
# # #     #  NEW:  hide chip selector – kept only for internal use
# # #     # ------------------------------------------------------------------
# # #     def on_chip_changed(self, event=None):
# # #         # Legacy placeholder – UI no longer exposes chip selection.
# # #         self.config["esp32_chip"] = self.chip_var.get()
# # #         self.save_config()

# # #     # ------------------------------------------------------------------
# # #     #  NEW:  Called when the user changes the selected partition
# # #     # ------------------------------------------------------------------
# # #     def on_partition_selected(self, event=None):
# # #         """Update offset/size fields to reflect the newly selected partition."""
# # #         try:
# # #             self.current_spiffs_index = self.partition_combo.current()
# # #             self.update_spiffs_fields()
# # #         except Exception:
# # #             pass   # defensive – should never happen

# # #     def update_spiffs_fields(self):
# # #         """Write the offset and size of the currently selected partition to the UI."""
# # #         if not self.spiffs_partitions:
# # #             self.offset_var.set("")
# # #             self.size_var.set("")
# # #             return
# # #         part = self.spiffs_partitions[self.current_spiffs_index]
# # #         self.offset_var.set(self.format_value_for_display(part['offset']))
# # #         self.size_var.set(self.format_value_for_display(part['size']))

# # #     def save_spiffs_config(self):
# # #         # The configuration is now derived from partitions.csv, therefore the
# # #         # "Save Config" button is hidden.  This method only informs the user.
# # #         messagebox.showinfo(
# # #             "Info",
# # #             "SPIFFS offset and size are taken from *partitions.csv*.\n"
# # #             "To change them, edit that file and restart the application."
# # #         )

# # #     def perform_action(self):
# # #         if not self.connected:
# # #             messagebox.showerror("Error", "Not connected to ESP32")
# # #             return
# # #         if not self.spiffs_downloaded:
# # #             self.download_spiffs()
# # #         else:
# # #             # ---- ask for confirmation before upload ----
# # #             if not messagebox.askyesno("Confirm Upload",
# # #                                        "Are you sure you want to upload the SPIFFS image to the ESP32?"):
# # #                 return
# # #             # ---- ask for unsaved before upload ----
# # #             if not self.ask_unsaved_changes("uploading"):
# # #                 return
# # #             self.upload_spffs()

# # #     def download_spiffs(self):
# # #         def download_worker():
# # #             try:
# # #                 self.progress.start()
# # #                 self.action_btn.config(state="disabled")
# # #                 self.status_var.set("Downloading SPIFFS...")

# # #                 # Use the values from the selected partition
# # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # #                 offset_val = part['offset']
# # #                 size_val   = part['size']

# # #                 offset_hex = f"0x{offset_val:X}"
# # #                 size_dec   = str(size_val)

# # #                 cmd = [
# # #                     "esptool.exe",
# # #                     "--chip", self.chip_var.get(),
# # #                     "--port", self.get_selected_port(),
# # #                     "--baud", self.config["baud_rate"],
# # #                     "read_flash", offset_hex, size_dec,
# # #                     "spiffs_dump.bin"
# # #                 ]
# # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # #                 if result.returncode != 0:
# # #                     raise Exception(f"Failed to read flash: {result.stderr}")

# # #                 data_dir = Path("data")
# # #                 data_dir.mkdir(exist_ok=True)
# # #                 for file in data_dir.glob("*"):
# # #                     if file.is_file():
# # #                         file.unlink()

# # #                 cmd = [
# # #                     "mkspiffs_espressif32_arduino.exe",
# # #                     "-u", "data",
# # #                     "spiffs_dump.bin"
# # #                 ]
# # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # #                 if result.returncode != 0:
# # #                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

# # #                 self.root.after(0, self.download_complete)

# # #             except Exception as e:
# # #                 error_msg = str(e)
# # #                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

# # #         thread = threading.Thread(target=download_worker)
# # #         thread.daemon = True
# # #         thread.start()

# # #     def download_complete(self):
# # #         self.progress.stop()
# # #         self.action_btn.config(state="normal", text="Upload SPIFFS")
# # #         self.spiffs_downloaded = True
# # #         self.status_var.set("SPIFFS downloaded successfully")
# # #         self.load_files()
# # #         # Enable partition UI now that we have data
# # #         self.partition_combo.state(['!disabled'])
# # #         self.offset_entry.state(['!disabled'])
# # #         self.size_entry.state(['!disabled'])
# # #         self.add_file_btn.config(state="normal")
# # #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# # #     def download_error(self, error_msg):
# # #         self.progress.stop()
# # #         self.action_btn.config(state="normal")
# # #         self.status_var.set("Download failed")
# # #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# # #     def upload_spiffs(self):
# # #         def upload_worker():
# # #             try:
# # #                 self.progress.start()
# # #                 self.action_btn.config(state="disabled")
# # #                 self.status_var.set("Creating SPIFFS image...")

# # #                 spiffs_dir = Path("spiffs")
# # #                 spiffs_dir.mkdir(exist_ok=True)

# # #                 # Use the values from the selected partition
# # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # #                 size_val   = part['size']
# # #                 offset_val = part['offset']

# # #                 cmd = [
# # #                     "mkspiffs_espressif32_arduino.exe",
# # #                     "-c", "data",
# # #                     "-p", "256",
# # #                     "-b", "4096",
# # #                     "-s", str(size_val),
# # #                     "spiffs/data.bin"
# # #                 ]
# # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # #                 if result.returncode != 0:
# # #                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

# # #                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

# # #                 offset_hex = f"0x{offset_val:X}"
# # #                 cmd = [
# # #                     "esptool.exe",
# # #                     "--chip", self.chip_var.get(),
# # #                     "--port", self.get_selected_port(),
# # #                     "--baud", self.config["baud_rate"],
# # #                     "--before", "default_reset",
# # #                     "--after", "hard_reset",
# # #                     "write_flash", "-z",
# # #                     "--flash_mode", "dio",
# # #                     "--flash_size", "detect",
# # #                     offset_hex, "spiffs/data.bin"
# # #                 ]
# # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # #                 if result.returncode != 0:
# # #                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

# # #                 self.root.after(0, self.upload_complete)

# # #             except Exception as e:
# # #                 error_msg = str(e)
# # #                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

# # #         thread = threading.Thread(target=upload_worker)
# # #         thread.daemon = True
# # #         thread.start()

# # #     def upload_complete(self):
# # #         self.progress.stop()
# # #         self.action_btn.config(state="normal")
# # #         self.status_var.set("SPIFFS uploaded successfully")
# # #         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

# # #     def upload_error(self, error_msg):
# # #         self.progress.stop()
# # #         self.action_btn.config(state="normal")
# # #         self.status_var.set("Upload failed")
# # #         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

# # #     # ------------------------------------------------------------------
# # #     #  File management (adjusted for editor_modified flag, full file list)
# # #     # ------------------------------------------------------------------
# # #     def load_files(self):
# # #         self.current_files = {}
# # #         self.file_listbox.delete(0, tk.END)
# # #         data_dir = Path("data")
# # #         if not data_dir.exists():
# # #             return
# # #         # we now list *all* files; only read as text when possible
# # #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# # #         for file_path in data_dir.iterdir():
# # #             if file_path.is_file():
# # #                 try:
# # #                     if file_path.suffix.lower() in text_extensions:
# # #                         with open(file_path, 'r', encoding='utf-8') as f:
# # #                             content = f.read()
# # #                     else:
# # #                         # binary or unknown – keep empty placeholder
# # #                         content = ""
# # #                     self.current_files[file_path.name] = content
# # #                     self.file_listbox.insert(tk.END, file_path.name)
# # #                 except Exception as e:
# # #                     print(f"Error reading {file_path}: {e}")
# # #         # keep add‑file button enabled after a successful download
# # #         if self.spiffs_downloaded:
# # #             self.add_file_btn.config(state="normal")
# # #         if self.current_files:
# # #             self.file_listbox.selection_set(0)
# # #             self.on_file_select()

# # #     # NEW:  ask unsaved when changing file selection
# # #     def on_file_select(self, event=None):
# # #         selection = self.file_listbox.curselection()
# # #         if not selection:
# # #             return
# # #         if not self.ask_unsaved_changes("switching file"):
# # #             # restore previous selection
# # #             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
# # #             self.file_listbox.selection_clear(0, tk.END)
# # #             self.file_listbox.selection_set(idx)
# # #             return

# # #         filename = self.file_listbox.get(selection[0])
# # #         if filename in self.current_files:
# # #             self.selected_file = filename
# # #             self.content_editor.delete(1.0, tk.END)
# # #             self.content_editor.insert(1.0, self.current_files[filename])
# # #             self.editor_modified = False
# # #             self.save_file_btn.config(state="disabled")
# # #             self.delete_file_btn.config(state="normal")

# # #     def on_content_changed(self, event=None):
# # #         if self.selected_file:
# # #             self.editor_modified = True
# # #             self.save_file_btn.config(state="normal")

# # #     def save_current_file(self):
# # #         if not self.selected_file:
# # #             return
# # #         content = self.content_editor.get(1.0, tk.END).rstrip()
# # #         self.current_files[self.selected_file] = content
# # #         try:
# # #             data_dir = Path("data")
# # #             data_dir.mkdir(exist_ok=True)
# # #             file_path = data_dir / self.selected_file
# # #             with open(file_path, 'w', encoding='utf-8') as f:
# # #                 f.write(content)
# # #             self.editor_modified = False
# # #             self.save_file_btn.config(state="disabled")
# # #             self.status_var.set(f"Saved {self.selected_file}")
# # #         except Exception as e:
# # #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# # #     # ------------------------------------------------------------------
# # #     #  NEW:  Simple Add‑File that selects an existing file from the host
# # #     # ------------------------------------------------------------------
# # #     def add_file(self):
# # #         src_path = filedialog.askopenfilename(title="Select file to add")
# # #         if not src_path:
# # #             return

# # #         filename = os.path.basename(src_path)
# # #         if filename in self.current_files:
# # #             messagebox.showerror("Error", f"File \"{filename}\" already exists in the SPIFFS.")
# # #             return

# # #         try:
# # #             with open(src_path, 'r', encoding='utf-8') as f:
# # #                 content = f.read()
# # #         except Exception as e:
# # #             messagebox.showerror("Error", f"Could not read selected file:\n{e}")
# # #             return

# # #         # Register in internal structures and write to disk
# # #         self.current_files[filename] = content
# # #         self.file_listbox.insert(tk.END, filename)

# # #         data_dir = Path("data")
# # #         data_dir.mkdir(exist_ok=True)
# # #         dest_path = data_dir / filename
# # #         try:
# # #             with open(dest_path, 'w', encoding='utf-8') as f:
# # #                 f.write(content)
# # #         except Exception as e:
# # #             messagebox.showerror("Error", f"Failed to copy file to data folder:\n{e}")
# # #             return

# # #         self.file_listbox.selection_clear(0, tk.END)
# # #         self.file_listbox.selection_set(tk.END)
# # #         self.on_file_select()

# # #     def delete_file(self):
# # #         if not self.selected_file:
# # #             return
# # #         result = messagebox.askyesno("Confirm Delete",
# # #                                    f"Are you sure you want to delete {self.selected_file}?")
# # #         if not result:
# # #             return
# # #         del self.current_files[self.selected_file]
# # #         selection = self.file_listbox.curselection()
# # #         if selection:
# # #             self.file_listbox.delete(selection[0])
# # #         try:
# # #             file_path = Path("data") / self.selected_file
# # #             if file_path.exists():
# # #                 file_path.unlink()
# # #         except Exception as e:
# # #             print(f"Error deleting file: {e}")
# # #         self.content_editor.delete(1.0, tk.END)
# # #         self.selected_file = None
# # #         self.editor_modified = False
# # #         self.save_file_btn.config(state="disabled")
# # #         self.delete_file_btn.config(state="disabled")

# # #     # ------------------------------------------------------------------
# # #     #  Application close handler
# # #     # ------------------------------------------------------------------
# # #     def on_app_closing(self):
# # #         if self.ask_unsaved_changes("closing the application"):
# # #             self.root.destroy()


# # # # ----------------------------------------------------------------------
# # # #  Entry-point
# # # # ----------------------------------------------------------------------
# # # def main():
# # #     import tkinter.simpledialog
# # #     tk.simpledialog = tkinter.simpledialog
# # #     root = tk.Tk()
# # #     ESP32SPIFFSManager(root)
# # #     root.mainloop()


# # # if __name__ == "__main__":
# # #     main()


# # # # #!/usr/bin/env python3
# # # # """
# # # # ESP32 SPIFFS Manager GUI
# # # # Windows GUI application for managing ESP32 SPIFFS filesystem
# # # # """
# # # # VERSION = "v.017"  #  <── incremented on every program update

# # # # import os
# # # # import json
# # # # import subprocess
# # # # import sys
# # # # import tkinter as tk
# # # # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # # # import csv                      # new – to read partitions.csv
# # # # from pathlib import Path
# # # # import serial.tools.list_ports
# # # # import threading
# # # # from datetime import datetime

# # # # # ------------------------------------------------------------------
# # # # #  Main application class
# # # # # ------------------------------------------------------------------
# # # # class ESP32SPIFFSManager:
# # # #     def __init__(self, root):
# # # #         self.root = root
# # # #         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
# # # #         self.root.geometry("1000x700")
# # # #         self.root.minsize(800, 600)

# # # #         # Configuration
# # # #         self.config_file = "spiffs_config.json"
# # # #         self.load_config()

# # # #         # keep chip variable even though the UI element is hidden
# # # #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

# # # #         # --------------------------------------------------------------
# # # #         #  Load SPIFFS partition information from *partitions.csv*
# # # #         # --------------------------------------------------------------
# # # #         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
# # # #         self.current_spiffs_index = 0       # index inside self.spiffs_partitions
# # # #         self.load_partitions_csv()

# # # #         # State variables
# # # #         self.connected = False
# # # #         self.current_files = {}       # filename → content (text content or empty for non‑text)
# # # #         self.selected_file = None     # filename currently in editor
# # # #         self.spiffs_downloaded = False
# # # #         self.editor_modified = False  # True while editor has unsaved changes

# # # #         # Create GUI
# # # #         self.create_widgets()
# # # #         self.scan_ports()

# # # #         # Ask on unsaved changes when user closes window
# # # #         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

# # # #         # Check required files on startup
# # # #         self.check_dependencies()

# # # #     # ------------------------------------------------------------------
# # # #     #  NEW:  generic “ask unsaved” helper  (returns True = proceed, False = abort)
# # # #     # ------------------------------------------------------------------
# # # #     def ask_unsaved_changes(self, action: str = "switch file"):
# # # #         """Return True if the caller may continue, False if user chose Cancel."""
# # # #         if not self.editor_modified:
# # # #             return True

# # # #         answer = messagebox.askyesnocancel(
# # # #             "Unsaved changes",
# # # #             f'File "{self.selected_file}" has unsaved changes.\n\n'
# # # #             f'Save before {action}?',
# # # #             default=messagebox.YES
# # # #         )
# # # #         if answer is True:          # Save
# # # #             self.save_current_file()
# # # #             return True
# # # #         elif answer is False:       # Discard
# # # #             return True
# # # #         else:                       # Cancel
# # # #             return False

# # # #     # ------------------------------------------------------------------
# # # #     #  Small helpers (unchanged)
# # # #     # ------------------------------------------------------------------
# # # #     @staticmethod
# # # #     def _ensure_int(value):
# # # #         """Return int whether value is already int or decimal/hex string."""
# # # #         if isinstance(value, int):
# # # #             return value
# # # #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# # # #     def load_config(self):
# # # #         default_config = {
# # # #             "spiffs_offset": 6750208,  # 0x670000
# # # #             "spiffs_size": 1572864,    # 0x180000
# # # #             "esp32_chip": "esp32-s3",
# # # #             "baud_rate": "921600",
# # # #             "last_port": ""
# # # #         }
# # # #         try:
# # # #             if os.path.exists(self.config_file):
# # # #                 with open(self.config_file, 'r') as f:
# # # #                     self.config = json.load(f)
# # # #                 for key, value in default_config.items():
# # # #                     if key not in self.config:
# # # #                         self.config[key] = value
# # # #             else:
# # # #                 self.config = default_config
# # # #                 self.save_config()
# # # #         except Exception as e:
# # # #             print(f"Error loading config: {e}")
# # # #             self.config = default_config
# # # #             self.save_config()

# # # #     def save_config(self):
# # # #         try:
# # # #             with open(self.config_file, 'w') as f:
# # # #                 json.dump(self.config, f, indent=4)
# # # #         except Exception as e:
# # # #             print(f"Error saving config: {e}")

# # # #     def format_value_for_display(self, value):
# # # #         if isinstance(value, int):
# # # #             return f"0x{value:X}"
# # # #         return str(value)

# # # #     def parse_value_from_input(self, value_str):
# # # #         value_str = value_str.strip()
# # # #         if value_str.lower().startswith('0x'):
# # # #             return int(value_str, 16)
# # # #         else:
# # # #             return int(value_str)

# # # #     def validate_config_input(self, value_str, field_name):
# # # #         try:
# # # #             return self.parse_value_from_input(value_str)
# # # #         except ValueError:
# # # #             messagebox.showerror("Invalid Input",
# # # #                                f"Invalid {field_name} value: {value_str}\n"
# # # #                                f"Please enter a decimal number or hex value (0x...)")
# # # #             return None

# # # #     # ------------------------------------------------------------------
# # # #     #  NEW:  Read «partitions.csv» and extract all SPIFFS partitions
# # # #     # ------------------------------------------------------------------
# # # #     def load_partitions_csv(self):
# # # #         """
# # # #         Looks for a file named *partitions.csv* in the same directory as this
# # # #         script.  It must contain a header (or not) with the columns:

# # # #             name, type, subtype, offset, size, flags

# # # #         All rows whose *subtype* is exactly ``spiffs`` (case‑insensitive) are
# # # #         collected.  For each such row we store the name, the integer offset
# # # #         and the integer size (hex strings are accepted).  If the file is not
# # # #         present or no SPIFFS partition is found, we abort with an error
# # # #         message.
# # # #         """
# # # #         csv_path = Path(__file__).parent / "partitions.csv"
# # # #         if not csv_path.is_file():
# # # #             messagebox.showerror(
# # # #                 "Missing file",
# # # #                 "Required file *partitions.csv* not found in the script folder.\n"
# # # #                 "The program cannot determine the SPIFFS offset/size.\n"
# # # #                 "Place a valid partitions.csv next to the script and restart."
# # # #             )
# # # #             sys.exit(1)

# # # #         try:
# # # #             with csv_path.open(newline='') as f:
# # # #                 reader = csv.reader(f)
# # # #                 for row in reader:
# # # #                     # skip empty lines / comments
# # # #                     if not row or row[0].strip().startswith('#'):
# # # #                         continue
# # # #                     # the CSV is usually: name,type,subtype,offset,size,flags
# # # #                     if len(row) < 5:
# # # #                         continue
# # # #                     name, _type, subtype, offset_str, size_str = (
# # # #                         row[0].strip(),
# # # #                         row[1].strip(),
# # # #                         row[2].strip(),
# # # #                         row[3].strip(),
# # # #                         row[4].strip(),
# # # #                     )
# # # #                     if subtype.lower() != 'spiffs':
# # # #                         continue
# # # #                     # Convert hex/dec strings to int
# # # #                     offset = int(offset_str, 0)
# # # #                     size   = int(size_str, 0)
# # # #                     self.spiffs_partitions.append({
# # # #                         "name"  : name,
# # # #                         "offset": offset,
# # # #                         "size"  : size,
# # # #                     })
# # # #         except Exception as e:
# # # #             messagebox.showerror(
# # # #                 "Error reading partitions.csv",
# # # #                 f"Could not parse *partitions.csv*:\n{e}"
# # # #             )
# # # #             sys.exit(1)

# # # #         if not self.spiffs_partitions:
# # # #             messagebox.showerror(
# # # #                 "No SPIFFS partition",
# # # #                 "The *partitions.csv* file does not contain any SPIFFS partition entries."
# # # #             )
# # # #             sys.exit(1)

# # # #         # Use the first partition as the default selection
# # # #         self.current_spiffs_index = 0

# # # #     # ------------------------------------------------------------------
# # # #     #  GUI creation (modified layout)
# # # #     # ------------------------------------------------------------------
# # # #     def create_widgets(self):
# # # #         main_frame = ttk.Frame(self.root, padding="10")
# # # #         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # #         self.root.columnconfigure(0, weight=1)
# # # #         self.root.rowconfigure(0, weight=1)
# # # #         main_frame.columnconfigure(1, weight=1)
# # # #         main_frame.rowconfigure(3, weight=1)

# # # #         # ---------------- Connection frame ----------------
# # # #         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
# # # #         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
# # # #         conn_frame.columnconfigure(1, weight=1)

# # # #         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # #         self.port_var = tk.StringVar()
# # # #         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
# # # #         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

# # # #         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
# # # #         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

# # # #         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
# # # #         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

# # # #         # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

# # # #         # ---------------- SPIFFS Configuration frame ----------------
# # # #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# # # #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# # # #         # ----- Partition selector (wider) -----
# # # #         ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # #         self.partition_var = tk.StringVar()
# # # #         self.partition_combo = ttk.Combobox(
# # # #             spiffs_frame,
# # # #             textvariable=self.partition_var,
# # # #             state="readonly",
# # # #             width=40,                # made wider as requested
# # # #         )
# # # #         partition_names = [
# # # #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# # # #         ]
# # # #         self.partition_combo['values'] = partition_names
# # # #         self.partition_combo.current(self.current_spiffs_index)
# # # #         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
# # # #         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)
# # # #         self.partition_combo.state(['disabled'])          # locked until download

# # # #         # ----- Offset (read‑only) -----
# # # #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# # # #         self.offset_var = tk.StringVar()
# # # #         self.offset_entry = ttk.Entry(
# # # #             spiffs_frame,
# # # #             textvariable=self.offset_var,
# # # #             width=15,
# # # #             state="readonly"
# # # #         )
# # # #         self.offset_entry.grid(row=0, column=3, padx=(0, 10))
# # # #         self.offset_entry.state(['disabled'])

# # # #         # ----- Size (read‑only) -----
# # # #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
# # # #         self.size_var = tk.StringVar()
# # # #         self.size_entry = ttk.Entry(
# # # #             spiffs_frame,
# # # #             textvariable=self.size_var,
# # # #             width=15,
# # # #             state="readonly"
# # # #         )
# # # #         self.size_entry.grid(row=0, column=5, padx=(0, 10))
# # # #         self.size_entry.state(['disabled'])

# # # #         # ----- Chip (read‑only, shown after connection) -----
# # # #         ttk.Label(spiffs_frame, text="Chip:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
# # # #         self.chip_display_var = tk.StringVar()
# # # #         self.chip_display_entry = ttk.Entry(
# # # #             spiffs_frame,
# # # #             textvariable=self.chip_display_var,
# # # #             width=12,
# # # #             state="readonly"
# # # #         )
# # # #         self.chip_display_entry.grid(row=0, column=7, padx=(0, 10))
# # # #         self.chip_display_entry.state(['disabled'])

# # # #         # Initialise the displayed values (empty at start)
# # # #         self.update_spiffs_fields()

# # # #         # Hide the now‑redundant "Save Config" button (kept for layout)
# # # #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# # # #         self.save_config_btn.grid(row=0, column=8, padx=(10, 0))
# # # #         self.save_config_btn.grid_remove()          # completely hide it

# # # #         # ---------------- Action frame ----------------
# # # #         action_frame = ttk.Frame(main_frame)
# # # #         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

# # # #         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
# # # #         self.action_btn.grid(row=0, column=0, padx=(0, 10))
# # # #         self.action_btn.config(state="disabled")

# # # #         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
# # # #         self.progress.grid(row=0, column=1, padx=(10, 0))

# # # #         # ---------------- Content frame ----------------
# # # #         content_frame = ttk.Frame(main_frame)
# # # #         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # #         content_frame.columnconfigure(1, weight=2)
# # # #         content_frame.rowconfigure(0, weight=1)

# # # #         # File list
# # # #         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
# # # #         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
# # # #         file_frame.columnconfigure(0, weight=1)
# # # #         file_frame.rowconfigure(0, weight=1)

# # # #         list_frame = ttk.Frame(file_frame)
# # # #         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # #         list_frame.columnconfigure(0, weight=1)
# # # #         list_frame.rowconfigure(0, weight=1)

# # # #         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
# # # #         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # #         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

# # # #         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
# # # #         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
# # # #         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

# # # #         file_btn_frame = ttk.Frame(file_frame)
# # # #         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

# # # #         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
# # # #         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))
# # # #         self.add_file_btn.config(state="disabled")   # enabled only after download

# # # #         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
# # # #         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
# # # #         self.save_file_btn.config(state="disabled")

# # # #         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
# # # #         self.delete_file_btn.grid(row=0, column=2)
# # # #         self.delete_file_btn.config(state="disabled")

# # # #         # Editor
# # # #         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
# # # #         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # #         editor_frame.columnconfigure(0, weight=1)
# # # #         editor_frame.rowconfigure(0, weight=1)

# # # #         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
# # # #         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # #         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

# # # #         # Status bar
# # # #         self.status_var = tk.StringVar(value="Ready")
# # # #         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
# # # #         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

# # # #     # ------------------------------------------------------------------
# # # #     #  Dependency / connection / scan helpers (unchanged)
# # # #     # ------------------------------------------------------------------
# # # #     def check_dependencies(self):
# # # #         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
# # # #         missing_files = []
# # # #         for file in required_files:
# # # #             if not os.path.exists(file):
# # # #                 missing_files.append(file)
# # # #         if missing_files:
# # # #             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
# # # #             message += "\n\nPlease ensure these files are in the application directory."
# # # #             messagebox.showerror("Missing Dependencies", message)
# # # #             self.status_var.set("Missing dependencies")
# # # #             return False
# # # #         try:
# # # #             import serial.tools.list_ports
# # # #         except ImportError:
# # # #             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
# # # #             self.status_var.set("Missing pyserial")
# # # #             return False
# # # #         self.status_var.set("Dependencies OK")
# # # #         return True

# # # #     def scan_ports(self):
# # # #         ports = serial.tools.list_ports.comports()
# # # #         port_list = []
# # # #         for port in ports:
# # # #             description = port.description if port.description != 'n/a' else 'Unknown device'
# # # #             port_display = f"{port.device} - {description}"
# # # #             port_list.append(port_display)
# # # #         self.port_combo['values'] = port_list
# # # #         if self.config.get("last_port"):
# # # #             for port_display in port_list:
# # # #                 if port_display.startswith(self.config["last_port"] + " "):
# # # #                     self.port_var.set(port_display)
# # # #                     break
# # # #         elif port_list:
# # # #             self.port_var.set(port_list[0])
# # # #         self.status_var.set(f"Found {len(port_list)} COM ports")

# # # #     def get_selected_port(self):
# # # #         port_display = self.port_var.get()
# # # #         if not port_display:
# # # #             return ""
# # # #         return port_display.split(" - ")[0]

# # # #     # ------------------------------------------------------------------
# # # #     #  NEW:  on disconnect reset button to initial state + clear file list & editor
# # # #     # ------------------------------------------------------------------
# # # #     def toggle_connection(self):
# # # #         if not self.connected:
# # # #             if not self.port_var.get():
# # # #                 messagebox.showerror("Error", "Please select a COM port")
# # # #                 return

# # # #             # ---- auto‑detect ESP32 chip ----
# # # #             chip, err = self.detect_chip()
# # # #             if chip is None:
# # # #                 messagebox.showerror("Connection Error", f"Could not detect ESP32 chip:\n{err}")
# # # #                 return

# # # #             # Store detected chip for later use
# # # #             self.chip_var.set(chip)
# # # #             self.config["esp32_chip"] = chip
# # # #             self.save_config()
# # # #             self.chip_display_var.set(chip)
# # # #             self.chip_display_entry.state(['!disabled'])

# # # #             # lock/combo to prevent changes while connected
# # # #             self.port_combo.state(['disabled'])
# # # #             self.scan_btn.state(['disabled'])

# # # #             # Connection considered successful (esptool already succeeded)
# # # #             self.connected = True
# # # #             self.connect_btn.config(text="Disconnect")
# # # #             self.action_btn.config(state="normal")
# # # #             self.config["last_port"] = self.get_selected_port()
# # # #             self.save_config()
# # # #             self.status_var.set(f"Connected to {self.get_selected_port()} ({chip})")
# # # #         else:
# # # #             # ---------- disconnect ----------
# # # #             self.connected = False
# # # #             self.connect_btn.config(text="Connect")
# # # #             self.action_btn.config(state="disabled")
# # # #             # reset big button to initial download state
# # # #             self.spiffs_downloaded = False
# # # #             self.action_btn.config(text="Download SPIFFS")
# # # #             # clear file list and editor
# # # #             self.file_listbox.delete(0, tk.END)
# # # #             self.content_editor.delete(1.0, tk.END)
# # # #             self.current_files.clear()
# # # #             self.selected_file = None
# # # #             self.editor_modified = False
# # # #             self.save_file_btn.config(state="disabled")
# # # #             self.delete_file_btn.config(state="disabled")
# # # #             self.add_file_btn.config(state="disabled")
# # # #             # unlock COM port UI
# # # #             self.port_combo.state(['!disabled'])
# # # #             self.scan_btn.state(['!disabled'])
# # # #             # clear partition UI
# # # #             self.partition_combo.state(['disabled'])
# # # #             self.offset_entry.state(['disabled'])
# # # #             self.size_entry.state(['disabled'])
# # # #             self.chip_display_var.set("")
# # # #             self.chip_display_entry.state(['disabled'])
# # # #             self.status_var.set("Disconnected")

# # # #     # ------------------------------------------------------------------
# # # #     #  NEW:  ESP32 chip auto‑recognition
# # # #     # ------------------------------------------------------------------
# # # #     def detect_chip(self):
# # # #         """
# # # #         Runs ``esptool.exe chip_id`` and parses its output.
# # # #         Returns a tuple (chip_name, error_message). ``chip_name`` is one of
# # # #         ``esp32``, ``esp32-s2``, ``esp32-s3``, ``esp32-c3``, ``esp32-c6``.
# # # #         If detection fails, ``chip_name`` is ``None`` and ``error_message``
# # # #         contains the reason.
# # # #         """
# # # #         cmd = [
# # # #             "esptool.exe",
# # # #             "--port", self.get_selected_port(),
# # # #             "chip_id"
# # # #         ]
# # # #         try:
# # # #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
# # # #         except Exception as e:
# # # #             return None, str(e)

# # # #         if result.returncode != 0:
# # # #             return None, result.stderr or "esptool error"

# # # #         for line in result.stdout.splitlines():
# # # #             if "Chip is" in line:
# # # #                 name_part = line.split("Chip is")[-1].strip().lower()
# # # #                 if "esp32s3" in name_part:
# # # #                     return "esp32-s3", None
# # # #                 if "esp32s2" in name_part:
# # # #                     return "esp32-s2", None
# # # #                 if "esp32c3" in name_part:
# # # #                     return "esp32-c3", None
# # # #                 if "esp32c6" in name_part:
# # # #                     return "esp32-c6", None
# # # #                 if "esp32" in name_part:
# # # #                     return "esp32", None
# # # #         return None, "Unable to parse chip type from esptool output"

# # # #     # ------------------------------------------------------------------
# # # #     #  NEW:  hide chip selector – kept only for internal use
# # # #     # ------------------------------------------------------------------
# # # #     def on_chip_changed(self, event=None):
# # # #         # Legacy placeholder – UI no longer exposes chip selection.
# # # #         self.config["esp32_chip"] = self.chip_var.get()
# # # #         self.save_config()

# # # #     # ------------------------------------------------------------------
# # # #     #  NEW:  Called when the user changes the selected partition
# # # #     # ------------------------------------------------------------------
# # # #     def on_partition_selected(self, event=None):
# # # #         """Update offset/size fields to reflect the newly selected partition."""
# # # #         try:
# # # #             self.current_spiffs_index = self.partition_combo.current()
# # # #             self.update_spiffs_fields()
# # # #         except Exception:
# # # #             pass   # defensive – should never happen

# # # #     def update_spiffs_fields(self):
# # # #         """Write the offset and size of the currently selected partition to the UI."""
# # # #         if not self.spiffs_partitions:
# # # #             self.offset_var.set("")
# # # #             self.size_var.set("")
# # # #             return
# # # #         part = self.spiffs_partitions[self.current_spiffs_index]
# # # #         self.offset_var.set(self.format_value_for_display(part['offset']))
# # # #         self.size_var.set(self.format_value_for_display(part['size']))

# # # #     def save_spiffs_config(self):
# # # #         # The configuration is now derived from partitions.csv, therefore the
# # # #         # “Save Config” button is hidden.  This method only informs the user.
# # # #         messagebox.showinfo(
# # # #             "Info",
# # # #             "SPIFFS offset and size are taken from *partitions.csv*.\n"
# # # #             "To change them, edit that file and restart the application."
# # # #         )

# # # #     def perform_action(self):
# # # #         if not self.connected:
# # # #             messagebox.showerror("Error", "Not connected to ESP32")
# # # #             return
# # # #         if not self.spiffs_downloaded:
# # # #             self.download_spiffs()
# # # #         else:
# # # #             # ---- ask for confirmation before upload ----
# # # #             if not messagebox.askyesno("Confirm Upload",
# # # #                                        "Are you sure you want to upload the SPIFFS image to the ESP32?"):
# # # #                 return
# # # #             # ---- ask for unsaved before upload ----
# # # #             if not self.ask_unsaved_changes("uploading"):
# # # #                 return
# # # #             self.upload_spffs()

# # # #     def download_spiffs(self):
# # # #         def download_worker():
# # # #             try:
# # # #                 self.progress.start()
# # # #                 self.action_btn.config(state="disabled")
# # # #                 self.status_var.set("Downloading SPIFFS...")

# # # #                 # Use the values from the selected partition
# # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # #                 offset_val = part['offset']
# # # #                 size_val   = part['size']

# # # #                 offset_hex = f"0x{offset_val:X}"
# # # #                 size_dec   = str(size_val)

# # # #                 cmd = [
# # # #                     "esptool.exe",
# # # #                     "--chip", self.chip_var.get(),
# # # #                     "--port", self.get_selected_port(),
# # # #                     "--baud", self.config["baud_rate"],
# # # #                     "read_flash", offset_hex, size_dec,
# # # #                     "spiffs_dump.bin"
# # # #                 ]
# # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # #                 if result.returncode != 0:
# # # #                     raise Exception(f"Failed to read flash: {result.stderr}")

# # # #                 data_dir = Path("data")
# # # #                 data_dir.mkdir(exist_ok=True)
# # # #                 for file in data_dir.glob("*"):
# # # #                     if file.is_file():
# # # #                         file.unlink()

# # # #                 cmd = [
# # # #                     "mkspiffs_espressif32_arduino.exe",
# # # #                     "-u", "data",
# # # #                     "spiffs_dump.bin"
# # # #                 ]
# # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # #                 if result.returncode != 0:
# # # #                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

# # # #                 self.root.after(0, self.download_complete)

# # # #             except Exception as e:
# # # #                 error_msg = str(e)
# # # #                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

# # # #         thread = threading.Thread(target=download_worker)
# # # #         thread.daemon = True
# # # #         thread.start()

# # # #     def download_complete(self):
# # # #         self.progress.stop()
# # # #         self.action_btn.config(state="normal", text="Upload SPIFFS")
# # # #         self.spiffs_downloaded = True
# # # #         self.status_var.set("SPIFFS downloaded successfully")
# # # #         self.load_files()
# # # #         # Enable partition UI now that we have data
# # # #         self.partition_combo.state(['!disabled'])
# # # #         self.offset_entry.state(['!disabled'])
# # # #         self.size_entry.state(['!disabled'])
# # # #         self.add_file_btn.config(state="normal")
# # # #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# # # #     def download_error(self, error_msg):
# # # #         self.progress.stop()
# # # #         self.action_btn.config(state="normal")
# # # #         self.status_var.set("Download failed")
# # # #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# # # #     def upload_spffs(self):
# # # #         def upload_worker():
# # # #             try:
# # # #                 self.progress.start()
# # # #                 self.action_btn.config(state="disabled")
# # # #                 self.status_var.set("Creating SPIFFS image...")

# # # #                 spiffs_dir = Path("spiffs")
# # # #                 spiffs_dir.mkdir(exist_ok=True)

# # # #                 # Use the values from the selected partition
# # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # #                 size_val   = part['size']
# # # #                 offset_val = part['offset']

# # # #                 cmd = [
# # # #                     "mkspiffs_espressif32_arduino.exe",
# # # #                     "-c", "data",
# # # #                     "-p", "256",
# # # #                     "-b", "4096",
# # # #                     "-s", str(size_val),
# # # #                     "spiffs/data.bin"
# # # #                 ]
# # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # #                 if result.returncode != 0:
# # # #                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

# # # #                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

# # # #                 offset_hex = f"0x{offset_val:X}"
# # # #                 cmd = [
# # # #                     "esptool.exe",
# # # #                     "--chip", self.chip_var.get(),
# # # #                     "--port", self.get_selected_port(),
# # # #                     "--baud", self.config["baud_rate"],
# # # #                     "--before", "default_reset",
# # # #                     "--after", "hard_reset",
# # # #                     "write_flash", "-z",
# # # #                     "--flash_mode", "dio",
# # # #                     "--flash_size", "detect",
# # # #                     offset_hex, "spiffs/data.bin"
# # # #                 ]
# # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # #                 if result.returncode != 0:
# # # #                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

# # # #                 self.root.after(0, self.upload_complete)

# # # #             except Exception as e:
# # # #                 error_msg = str(e)
# # # #                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

# # # #         thread = threading.Thread(target=upload_worker)
# # # #         thread.daemon = True
# # # #         thread.start()

# # # #     def upload_complete(self):
# # # #         self.progress.stop()
# # # #         self.action_btn.config(state="normal")
# # # #         self.status_var.set("SPIFFS uploaded successfully")
# # # #         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

# # # #     def upload_error(self, error_msg):
# # # #         self.progress.stop()
# # # #         self.action_btn.config(state="normal")
# # # #         self.status_var.set("Upload failed")
# # # #         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

# # # #     # ------------------------------------------------------------------
# # # #     #  File management (adjusted for editor_modified flag, full file list)
# # # #     # ------------------------------------------------------------------
# # # #     def load_files(self):
# # # #         self.current_files = {}
# # # #         self.file_listbox.delete(0, tk.END)
# # # #         data_dir = Path("data")
# # # #         if not data_dir.exists():
# # # #             return
# # # #         # we now list *all* files; only read as text when possible
# # # #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# # # #         for file_path in data_dir.iterdir():
# # # #             if file_path.is_file():
# # # #                 try:
# # # #                     if file_path.suffix.lower() in text_extensions:
# # # #                         with open(file_path, 'r', encoding='utf-8') as f:
# # # #                             content = f.read()
# # # #                     else:
# # # #                         # binary or unknown – keep empty placeholder
# # # #                         content = ""
# # # #                     self.current_files[file_path.name] = content
# # # #                     self.file_listbox.insert(tk.END, file_path.name)
# # # #                 except Exception as e:
# # # #                     print(f"Error reading {file_path}: {e}")
# # # #         # keep add‑file button enabled after a successful download
# # # #         if self.spiffs_downloaded:
# # # #             self.add_file_btn.config(state="normal")
# # # #         if self.current_files:
# # # #             self.file_listbox.selection_set(0)
# # # #             self.on_file_select()

# # # #     # NEW:  ask unsaved when changing file selection
# # # #     def on_file_select(self, event=None):
# # # #         selection = self.file_listbox.curselection()
# # # #         if not selection:
# # # #             return
# # # #         if not self.ask_unsaved_changes("switching file"):
# # # #             # restore previous selection
# # # #             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
# # # #             self.file_listbox.selection_clear(0, tk.END)
# # # #             self.file_listbox.selection_set(idx)
# # # #             return

# # # #         filename = self.file_listbox.get(selection[0])
# # # #         if filename in self.current_files:
# # # #             self.selected_file = filename
# # # #             self.content_editor.delete(1.0, tk.END)
# # # #             self.content_editor.insert(1.0, self.current_files[filename])
# # # #             self.editor_modified = False
# # # #             self.save_file_btn.config(state="disabled")
# # # #             self.delete_file_btn.config(state="normal")

# # # #     def on_content_changed(self, event=None):
# # # #         if self.selected_file:
# # # #             self.editor_modified = True
# # # #             self.save_file_btn.config(state="normal")

# # # #     def save_current_file(self):
# # # #         if not self.selected_file:
# # # #             return
# # # #         content = self.content_editor.get(1.0, tk.END).rstrip()
# # # #         self.current_files[self.selected_file] = content
# # # #         try:
# # # #             data_dir = Path("data")
# # # #             data_dir.mkdir(exist_ok=True)
# # # #             file_path = data_dir / self.selected_file
# # # #             with open(file_path, 'w', encoding='utf-8') as f:
# # # #                 f.write(content)
# # # #             self.editor_modified = False
# # # #             self.save_file_btn.config(state="disabled")
# # # #             self.status_var.set(f"Saved {self.selected_file}")
# # # #         except Exception as e:
# # # #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# # # #     # ------------------------------------------------------------------
# # # #     #  NEW:  Simple Add‑File that selects an existing file from the host
# # # #     # ------------------------------------------------------------------
# # # #     def add_file(self):
# # # #         src_path = filedialog.askopenfilename(title="Select file to add")
# # # #         if not src_path:
# # # #             return

# # # #         filename = os.path.basename(src_path)
# # # #         if filename in self.current_files:
# # # #             messagebox.showerror("Error", f"File \"{filename}\" already exists in the SPIFFS.")
# # # #             return

# # # #         try:
# # # #             with open(src_path, 'r', encoding='utf-8') as f:
# # # #                 content = f.read()
# # # #         except Exception as e:
# # # #             messagebox.showerror("Error", f"Could not read selected file:\n{e}")
# # # #             return

# # # #         # Register in internal structures and write to disk
# # # #         self.current_files[filename] = content
# # # #         self.file_listbox.insert(tk.END, filename)

# # # #         data_dir = Path("data")
# # # #         data_dir.mkdir(exist_ok=True)
# # # #         dest_path = data_dir / filename
# # # #         try:
# # # #             with open(dest_path, 'w', encoding='utf-8') as f:
# # # #                 f.write(content)
# # # #         except Exception as e:
# # # #             messagebox.showerror("Error", f"Failed to copy file to data folder:\n{e}")
# # # #             return

# # # #         self.file_listbox.selection_clear(0, tk.END)
# # # #         self.file_listbox.selection_set(tk.END)
# # # #         self.on_file_select()

# # # #     def delete_file(self):
# # # #         if not self.selected_file:
# # # #             return
# # # #         result = messagebox.askyesno("Confirm Delete",
# # # #                                    f"Are you sure you want to delete {self.selected_file}?")
# # # #         if not result:
# # # #             return
# # # #         del self.current_files[self.selected_file]
# # # #         selection = self.file_listbox.curselection()
# # # #         if selection:
# # # #             self.file_listbox.delete(selection[0])
# # # #         try:
# # # #             file_path = Path("data") / self.selected_file
# # # #             if file_path.exists():
# # # #                 file_path.unlink()
# # # #         except Exception as e:
# # # #             print(f"Error deleting file: {e}")
# # # #         self.content_editor.delete(1.0, tk.END)
# # # #         self.selected_file = None
# # # #         self.editor_modified = False
# # # #         self.save_file_btn.config(state="disabled")
# # # #         self.delete_file_btn.config(state="disabled")

# # # #     # ------------------------------------------------------------------
# # # #     #  Application close handler
# # # #     # ------------------------------------------------------------------
# # # #     def on_app_closing(self):
# # # #         if self.ask_unsaved_changes("closing the application"):
# # # #             self.root.destroy()


# # # # # ----------------------------------------------------------------------
# # # # #  Entry-point
# # # # # ----------------------------------------------------------------------
# # # # def main():
# # # #     import tkinter.simpledialog
# # # #     tk.simpledialog = tkinter.simpledialog
# # # #     root = tk.Tk()
# # # #     ESP32SPIFFSManager(root)
# # # #     root.mainloop()


# # # # if __name__ == "__main__":
# # # #     main()


# # # # # #!/usr/bin/env python3
# # # # # """
# # # # # ESP32 SPIFFS Manager GUI
# # # # # Windows GUI application for managing ESP32 SPIFFS filesystem
# # # # # """
# # # # # VERSION = "v.017"  #  <── incremented on every program update

# # # # # import os
# # # # # import json
# # # # # import subprocess
# # # # # import sys
# # # # # import tkinter as tk
# # # # # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # # # # import csv                      # new – to read partitions.csv
# # # # # from pathlib import Path
# # # # # import serial.tools.list_ports
# # # # # import threading
# # # # # from datetime import datetime

# # # # # # ------------------------------------------------------------------
# # # # # #  Main application class
# # # # # # ------------------------------------------------------------------
# # # # # class ESP32SPIFFSManager:
# # # # #     def __init__(self, root):
# # # # #         self.root = root
# # # # #         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
# # # # #         self.root.geometry("1000x700")
# # # # #         self.root.minsize(800, 600)

# # # # #         # Configuration
# # # # #         self.config_file = "spiffs_config.json"
# # # # #         self.load_config()

# # # # #         # keep chip variable even though the UI element is hidden
# # # # #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

# # # # #         # --------------------------------------------------------------
# # # # #         #  Load SPIFFS partition information from *partitions.csv*
# # # # #         # --------------------------------------------------------------
# # # # #         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
# # # # #         self.current_spiffs_index = 0       # index inside self.spiffs_partitions
# # # # #         self.load_partitions_csv()

# # # # #         # State variables
# # # # #         self.connected = False
# # # # #         self.current_files = {}       # filename → content
# # # # #         self.selected_file = None     # filename currently in editor
# # # # #         self.spiffs_downloaded = False
# # # # #         self.editor_modified = False  # True while editor has unsaved changes

# # # # #         # Create GUI
# # # # #         self.create_widgets()
# # # # #         self.scan_ports()

# # # # #         # Ask on unsaved changes when user closes window
# # # # #         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

# # # # #         # Check required files on startup
# # # # #         self.check_dependencies()

# # # # #     # ------------------------------------------------------------------
# # # # #     #  NEW:  generic “ask unsaved” helper  (returns True = proceed, False = abort)
# # # # #     # ------------------------------------------------------------------
# # # # #     def ask_unsaved_changes(self, action: str = "switch file"):
# # # # #         """Return True if the caller may continue, False if user chose Cancel."""
# # # # #         if not self.editor_modified:
# # # # #             return True

# # # # #         answer = messagebox.askyesnocancel(
# # # # #             "Unsaved changes",
# # # # #             f'File "{self.selected_file}" has unsaved changes.\n\n'
# # # # #             f'Save before {action}?',
# # # # #             default=messagebox.YES
# # # # #         )
# # # # #         if answer is True:          # Save
# # # # #             self.save_current_file()
# # # # #             return True
# # # # #         elif answer is False:       # Discard
# # # # #             return True
# # # # #         else:                       # Cancel
# # # # #             return False

# # # # #     # ------------------------------------------------------------------
# # # # #     #  Small helpers (unchanged)
# # # # #     # ------------------------------------------------------------------
# # # # #     @staticmethod
# # # # #     def _ensure_int(value):
# # # # #         """Return int whether value is already int or decimal/hex string."""
# # # # #         if isinstance(value, int):
# # # # #             return value
# # # # #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# # # # #     def load_config(self):
# # # # #         default_config = {
# # # # #             "spiffs_offset": 6750208,  # 0x670000
# # # # #             "spiffs_size": 1572864,    # 0x180000
# # # # #             "esp32_chip": "esp32-s3",
# # # # #             "baud_rate": "921600",
# # # # #             "last_port": ""
# # # # #         }
# # # # #         try:
# # # # #             if os.path.exists(self.config_file):
# # # # #                 with open(self.config_file, 'r') as f:
# # # # #                     self.config = json.load(f)
# # # # #                 for key, value in default_config.items():
# # # # #                     if key not in self.config:
# # # # #                         self.config[key] = value
# # # # #             else:
# # # # #                 self.config = default_config
# # # # #                 self.save_config()
# # # # #         except Exception as e:
# # # # #             print(f"Error loading config: {e}")
# # # # #             self.config = default_config
# # # # #             self.save_config()

# # # # #     def save_config(self):
# # # # #         try:
# # # # #             with open(self.config_file, 'w') as f:
# # # # #                 json.dump(self.config, f, indent=4)
# # # # #         except Exception as e:
# # # # #             print(f"Error saving config: {e}")

# # # # #     def format_value_for_display(self, value):
# # # # #         if isinstance(value, int):
# # # # #             return f"0x{value:X}"
# # # # #         return str(value)

# # # # #     def parse_value_from_input(self, value_str):
# # # # #         value_str = value_str.strip()
# # # # #         if value_str.lower().startswith('0x'):
# # # # #             return int(value_str, 16)
# # # # #         else:
# # # # #             return int(value_str)

# # # # #     def validate_config_input(self, value_str, field_name):
# # # # #         try:
# # # # #             return self.parse_value_from_input(value_str)
# # # # #         except ValueError:
# # # # #             messagebox.showerror("Invalid Input",
# # # # #                                f"Invalid {field_name} value: {value_str}\n"
# # # # #                                f"Please enter a decimal number or hex value (0x...)")
# # # # #             return None

# # # # #     # ------------------------------------------------------------------
# # # # #     #  NEW:  Read «partitions.csv» and extract all SPIFFS partitions
# # # # #     # ------------------------------------------------------------------
# # # # #     def load_partitions_csv(self):
# # # # #         """
# # # # #         Looks for a file named *partitions.csv* in the same directory as this
# # # # #         script.  It must contain a header (or not) with the columns:

# # # # #             name, type, subtype, offset, size, flags

# # # # #         All rows whose *subtype* is exactly ``spiffs`` (case‑insensitive) are
# # # # #         collected.  For each such row we store the name, the integer offset
# # # # #         and the integer size (hex strings are accepted).  If the file is not
# # # # #         present or no SPIFFS partition is found, we abort with an error
# # # # #         message.
# # # # #         """
# # # # #         csv_path = Path(__file__).parent / "partitions.csv"
# # # # #         if not csv_path.is_file():
# # # # #             messagebox.showerror(
# # # # #                 "Missing file",
# # # # #                 "Required file *partitions.csv* not found in the script folder.\n"
# # # # #                 "The program cannot determine the SPIFFS offset/size.\n"
# # # # #                 "Place a valid partitions.csv next to the script and restart."
# # # # #             )
# # # # #             sys.exit(1)

# # # # #         try:
# # # # #             with csv_path.open(newline='') as f:
# # # # #                 reader = csv.reader(f)
# # # # #                 for row in reader:
# # # # #                     # skip empty lines / comments
# # # # #                     if not row or row[0].strip().startswith('#'):
# # # # #                         continue
# # # # #                     # the CSV is usually: name,type,subtype,offset,size,flags
# # # # #                     if len(row) < 5:
# # # # #                         continue
# # # # #                     name, _type, subtype, offset_str, size_str = (
# # # # #                         row[0].strip(),
# # # # #                         row[1].strip(),
# # # # #                         row[2].strip(),
# # # # #                         row[3].strip(),
# # # # #                         row[4].strip(),
# # # # #                     )
# # # # #                     if subtype.lower() != 'spiffs':
# # # # #                         continue
# # # # #                     # Convert hex/dec strings to int
# # # # #                     offset = int(offset_str, 0)
# # # # #                     size   = int(size_str, 0)
# # # # #                     self.spiffs_partitions.append({
# # # # #                         "name"  : name,
# # # # #                         "offset": offset,
# # # # #                         "size"  : size,
# # # # #                     })
# # # # #         except Exception as e:
# # # # #             messagebox.showerror(
# # # # #                 "Error reading partitions.csv",
# # # # #                 f"Could not parse *partitions.csv*:\n{e}"
# # # # #             )
# # # # #             sys.exit(1)

# # # # #         if not self.spiffs_partitions:
# # # # #             messagebox.showerror(
# # # # #                 "No SPIFFS partition",
# # # # #                 "The *partitions.csv* file does not contain any SPIFFS partition entries."
# # # # #             )
# # # # #             sys.exit(1)

# # # # #         # Use the first partition as the default selection
# # # # #         self.current_spiffs_index = 0

# # # # #     # ------------------------------------------------------------------
# # # # #     #  GUI creation (modified layout)
# # # # #     # ------------------------------------------------------------------
# # # # #     def create_widgets(self):
# # # # #         main_frame = ttk.Frame(self.root, padding="10")
# # # # #         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # #         self.root.columnconfigure(0, weight=1)
# # # # #         self.root.rowconfigure(0, weight=1)
# # # # #         main_frame.columnconfigure(1, weight=1)
# # # # #         main_frame.rowconfigure(3, weight=1)

# # # # #         # ---------------- Connection frame ----------------
# # # # #         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
# # # # #         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
# # # # #         conn_frame.columnconfigure(1, weight=1)

# # # # #         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # #         self.port_var = tk.StringVar()
# # # # #         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
# # # # #         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

# # # # #         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
# # # # #         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

# # # # #         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
# # # # #         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

# # # # #         # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

# # # # #         # ---------------- SPIFFS Configuration frame ----------------
# # # # #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# # # # #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# # # # #         # ----- Partition selector (wider) -----
# # # # #         ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # #         self.partition_var = tk.StringVar()
# # # # #         self.partition_combo = ttk.Combobox(
# # # # #             spiffs_frame,
# # # # #             textvariable=self.partition_var,
# # # # #             state="readonly",
# # # # #             width=40,                # made wider as requested
# # # # #         )
# # # # #         partition_names = [
# # # # #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# # # # #         ]
# # # # #         self.partition_combo['values'] = partition_names
# # # # #         self.partition_combo.current(self.current_spiffs_index)
# # # # #         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
# # # # #         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)

# # # # #         # ----- Offset (read‑only) -----
# # # # #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# # # # #         self.offset_var = tk.StringVar()
# # # # #         self.offset_entry = ttk.Entry(
# # # # #             spiffs_frame,
# # # # #             textvariable=self.offset_var,
# # # # #             width=15,
# # # # #             state="readonly"
# # # # #         )
# # # # #         self.offset_entry.grid(row=0, column=3, padx=(0, 10))

# # # # #         # ----- Size (read‑only) -----
# # # # #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
# # # # #         self.size_var = tk.StringVar()
# # # # #         self.size_entry = ttk.Entry(
# # # # #             spiffs_frame,
# # # # #             textvariable=self.size_var,
# # # # #             width=15,
# # # # #             state="readonly"
# # # # #         )
# # # # #         self.size_entry.grid(row=0, column=5, padx=(0, 10))

# # # # #         # ----- Chip (read‑only, shown after connection) -----
# # # # #         ttk.Label(spiffs_frame, text="Chip:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
# # # # #         self.chip_display_var = tk.StringVar()
# # # # #         self.chip_display_entry = ttk.Entry(
# # # # #             spiffs_frame,
# # # # #             textvariable=self.chip_display_var,
# # # # #             width=12,
# # # # #             state="readonly"
# # # # #         )
# # # # #         self.chip_display_entry.grid(row=0, column=7, padx=(0, 10))

# # # # #         # Initialise the displayed values for the default partition
# # # # #         self.update_spiffs_fields()

# # # # #         # Hide the now‑redundant "Save Config" button (kept for layout)
# # # # #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# # # # #         self.save_config_btn.grid(row=0, column=8, padx=(10, 0))
# # # # #         self.save_config_btn.grid_remove()          # completely hide it

# # # # #         # ---------------- Action frame ----------------
# # # # #         action_frame = ttk.Frame(main_frame)
# # # # #         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

# # # # #         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
# # # # #         self.action_btn.grid(row=0, column=0, padx=(0, 10))
# # # # #         self.action_btn.config(state="disabled")

# # # # #         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
# # # # #         self.progress.grid(row=0, column=1, padx=(10, 0))

# # # # #         # ---------------- Content frame ----------------
# # # # #         content_frame = ttk.Frame(main_frame)
# # # # #         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # #         content_frame.columnconfigure(1, weight=2)
# # # # #         content_frame.rowconfigure(0, weight=1)

# # # # #         # File list
# # # # #         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
# # # # #         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
# # # # #         file_frame.columnconfigure(0, weight=1)
# # # # #         file_frame.rowconfigure(0, weight=1)

# # # # #         list_frame = ttk.Frame(file_frame)
# # # # #         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # #         list_frame.columnconfigure(0, weight=1)
# # # # #         list_frame.rowconfigure(0, weight=1)

# # # # #         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
# # # # #         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # #         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

# # # # #         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
# # # # #         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
# # # # #         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

# # # # #         file_btn_frame = ttk.Frame(file_frame)
# # # # #         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

# # # # #         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
# # # # #         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))
# # # # #         self.add_file_btn.config(state="disabled")   # enabled only after download

# # # # #         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
# # # # #         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
# # # # #         self.save_file_btn.config(state="disabled")

# # # # #         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
# # # # #         self.delete_file_btn.grid(row=0, column=2)
# # # # #         self.delete_file_btn.config(state="disabled")

# # # # #         # Editor
# # # # #         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
# # # # #         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # #         editor_frame.columnconfigure(0, weight=1)
# # # # #         editor_frame.rowconfigure(0, weight=1)

# # # # #         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
# # # # #         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # #         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

# # # # #         # Status bar
# # # # #         self.status_var = tk.StringVar(value="Ready")
# # # # #         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
# # # # #         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

# # # # #     # ------------------------------------------------------------------
# # # # #     #  Dependency / connection / scan helpers (unchanged)
# # # # #     # ------------------------------------------------------------------
# # # # #     def check_dependencies(self):
# # # # #         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
# # # # #         missing_files = []
# # # # #         for file in required_files:
# # # # #             if not os.path.exists(file):
# # # # #                 missing_files.append(file)
# # # # #         if missing_files:
# # # # #             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
# # # # #             message += "\n\nPlease ensure these files are in the application directory."
# # # # #             messagebox.showerror("Missing Dependencies", message)
# # # # #             self.status_var.set("Missing dependencies")
# # # # #             return False
# # # # #         try:
# # # # #             import serial.tools.list_ports
# # # # #         except ImportError:
# # # # #             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
# # # # #             self.status_var.set("Missing pyserial")
# # # # #             return False
# # # # #         self.status_var.set("Dependencies OK")
# # # # #         return True

# # # # #     def scan_ports(self):
# # # # #         ports = serial.tools.list_ports.comports()
# # # # #         port_list = []
# # # # #         for port in ports:
# # # # #             description = port.description if port.description != 'n/a' else 'Unknown device'
# # # # #             port_display = f"{port.device} - {description}"
# # # # #             port_list.append(port_display)
# # # # #         self.port_combo['values'] = port_list
# # # # #         if self.config.get("last_port"):
# # # # #             for port_display in port_list:
# # # # #                 if port_display.startswith(self.config["last_port"] + " "):
# # # # #                     self.port_var.set(port_display)
# # # # #                     break
# # # # #         elif port_list:
# # # # #             self.port_var.set(port_list[0])
# # # # #         self.status_var.set(f"Found {len(port_list)} COM ports")

# # # # #     def get_selected_port(self):
# # # # #         port_display = self.port_var.get()
# # # # #         if not port_display:
# # # # #             return ""
# # # # #         return port_display.split(" - ")[0]

# # # # #     # ------------------------------------------------------------------
# # # # #     #  NEW:  on disconnect reset button to initial state + clear file list & editor
# # # # #     # ------------------------------------------------------------------
# # # # #     def toggle_connection(self):
# # # # #         if not self.connected:
# # # # #             if not self.port_var.get():
# # # # #                 messagebox.showerror("Error", "Please select a COM port")
# # # # #                 return

# # # # #             # ---- auto‑detect ESP32 chip ----
# # # # #             chip, err = self.detect_chip()
# # # # #             if chip is None:
# # # # #                 messagebox.showerror("Connection Error", f"Could not detect ESP32 chip:\n{err}")
# # # # #                 return

# # # # #             # Store detected chip for later use
# # # # #             self.chip_var.set(chip)
# # # # #             self.config["esp32_chip"] = chip
# # # # #             self.save_config()
# # # # #             self.chip_display_var.set(chip)          # show it in the UI

# # # # #             # Connection considered successful (esptool already succeeded)
# # # # #             self.connected = True
# # # # #             self.connect_btn.config(text="Disconnect")
# # # # #             self.action_btn.config(state="normal")
# # # # #             self.config["last_port"] = self.get_selected_port()
# # # # #             self.save_config()
# # # # #             self.status_var.set(f"Connected to {self.get_selected_port()} ({chip})")
# # # # #         else:
# # # # #             # ---------- disconnect ----------
# # # # #             self.connected = False
# # # # #             self.connect_btn.config(text="Connect")
# # # # #             self.action_btn.config(state="disabled")
# # # # #             # reset big button to initial download state
# # # # #             self.spiffs_downloaded = False
# # # # #             self.action_btn.config(text="Download SPIFFS")
# # # # #             # clear file list and editor
# # # # #             self.file_listbox.delete(0, tk.END)
# # # # #             self.content_editor.delete(1.0, tk.END)
# # # # #             self.current_files.clear()
# # # # #             self.selected_file = None
# # # # #             self.editor_modified = False
# # # # #             self.save_file_btn.config(state="disabled")
# # # # #             self.delete_file_btn.config(state="disabled")
# # # # #             self.add_file_btn.config(state="disabled")
# # # # #             self.chip_display_var.set("")
# # # # #             self.status_var.set("Disconnected")

# # # # #     # ------------------------------------------------------------------
# # # # #     #  NEW:  ESP32 chip auto‑recognition
# # # # #     # ------------------------------------------------------------------
# # # # #     def detect_chip(self):
# # # # #         """
# # # # #         Runs ``esptool.exe chip_id`` and parses its output.
# # # # #         Returns a tuple (chip_name, error_message). ``chip_name`` is one of
# # # # #         ``esp32``, ``esp32-s2``, ``esp32-s3``, ``esp32-c3``, ``esp32-c6``.
# # # # #         If detection fails, ``chip_name`` is ``None`` and ``error_message``
# # # # #         contains the reason.
# # # # #         """
# # # # #         cmd = [
# # # # #             "esptool.exe",
# # # # #             "--port", self.get_selected_port(),
# # # # #             "chip_id"
# # # # #         ]
# # # # #         try:
# # # # #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
# # # # #         except Exception as e:
# # # # #             return None, str(e)

# # # # #         if result.returncode != 0:
# # # # #             return None, result.stderr or "esptool error"

# # # # #         # Example line: "Chip is ESP32S3"
# # # # #         for line in result.stdout.splitlines():
# # # # #             if "Chip is" in line:
# # # # #                 name_part = line.split("Chip is")[-1].strip().lower()
# # # # #                 if "esp32s3" in name_part:
# # # # #                     return "esp32-s3", None
# # # # #                 if "esp32s2" in name_part:
# # # # #                     return "esp32-s2", None
# # # # #                 if "esp32c3" in name_part:
# # # # #                     return "esp32-c3", None
# # # # #                 if "esp32c6" in name_part:
# # # # #                     return "esp32-c6", None
# # # # #                 if "esp32" in name_part:
# # # # #                     return "esp32", None
# # # # #         return None, "Unable to parse chip type from esptool output"

# # # # #     # ------------------------------------------------------------------
# # # # #     #  NEW:  hide chip selector – kept only for internal use
# # # # #     # ------------------------------------------------------------------
# # # # #     def on_chip_changed(self, event=None):
# # # # #         # Legacy placeholder – UI no longer exposes chip selection.
# # # # #         self.config["esp32_chip"] = self.chip_var.get()
# # # # #         self.save_config()

# # # # #     # ------------------------------------------------------------------
# # # # #     #  NEW:  Called when the user changes the selected partition
# # # # #     # ------------------------------------------------------------------
# # # # #     def on_partition_selected(self, event=None):
# # # # #         """Update offset/size fields to reflect the newly selected partition."""
# # # # #         try:
# # # # #             self.current_spiffs_index = self.partition_combo.current()
# # # # #             self.update_spiffs_fields()
# # # # #         except Exception:
# # # # #             pass   # defensive – should never happen

# # # # #     def update_spiffs_fields(self):
# # # # #         """Write the offset and size of the currently selected partition to the UI."""
# # # # #         part = self.spiffs_partitions[self.current_spiffs_index]
# # # # #         self.offset_var.set(self.format_value_for_display(part['offset']))
# # # # #         self.size_var.set(self.format_value_for_display(part['size']))

# # # # #     def save_spiffs_config(self):
# # # # #         # The configuration is now derived from partitions.csv, therefore the
# # # # #         # “Save Config” button is hidden.  This method only informs the user.
# # # # #         messagebox.showinfo(
# # # # #             "Info",
# # # # #             "SPIFFS offset and size are taken from *partitions.csv*.\n"
# # # # #             "To change them, edit that file and restart the application."
# # # # #         )

# # # # #     def perform_action(self):
# # # # #         if not self.connected:
# # # # #             messagebox.showerror("Error", "Not connected to ESP32")
# # # # #             return
# # # # #         if not self.spiffs_downloaded:
# # # # #             self.download_spiffs()
# # # # #         else:
# # # # #             # ---- ask for confirmation before upload ----
# # # # #             if not messagebox.askyesno("Confirm Upload",
# # # # #                                        "Are you sure you want to upload the SPIFFS image to the ESP32?"):
# # # # #                 return
# # # # #             # ---- ask for unsaved before upload ----
# # # # #             if not self.ask_unsaved_changes("uploading"):
# # # # #                 return
# # # # #             self.upload_spiffs()

# # # # #     def download_spiffs(self):
# # # # #         def download_worker():
# # # # #             try:
# # # # #                 self.progress.start()
# # # # #                 self.action_btn.config(state="disabled")
# # # # #                 self.status_var.set("Downloading SPIFFS...")

# # # # #                 # Use the values from the selected partition
# # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # #                 offset_val = part['offset']
# # # # #                 size_val   = part['size']

# # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # #                 size_dec   = str(size_val)

# # # # #                 cmd = [
# # # # #                     "esptool.exe",
# # # # #                     "--chip", self.chip_var.get(),
# # # # #                     "--port", self.get_selected_port(),
# # # # #                     "--baud", self.config["baud_rate"],
# # # # #                     "read_flash", offset_hex, size_dec,
# # # # #                     "spiffs_dump.bin"
# # # # #                 ]
# # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # #                 if result.returncode != 0:
# # # # #                     raise Exception(f"Failed to read flash: {result.stderr}")

# # # # #                 data_dir = Path("data")
# # # # #                 data_dir.mkdir(exist_ok=True)
# # # # #                 for file in data_dir.glob("*"):
# # # # #                     if file.is_file():
# # # # #                         file.unlink()

# # # # #                 cmd = [
# # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # #                     "-u", "data",
# # # # #                     "spiffs_dump.bin"
# # # # #                 ]
# # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # #                 if result.returncode != 0:
# # # # #                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

# # # # #                 self.root.after(0, self.download_complete)

# # # # #             except Exception as e:
# # # # #                 error_msg = str(e)
# # # # #                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

# # # # #         thread = threading.Thread(target=download_worker)
# # # # #         thread.daemon = True
# # # # #         thread.start()

# # # # #     def download_complete(self):
# # # # #         self.progress.stop()
# # # # #         self.action_btn.config(state="normal", text="Upload SPIFFS")
# # # # #         self.spiffs_downloaded = True
# # # # #         self.status_var.set("SPIFFS downloaded successfully")
# # # # #         self.load_files()
# # # # #         # Enable file‑related buttons now that we have a filesystem
# # # # #         self.add_file_btn.config(state="normal")
# # # # #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# # # # #     def download_error(self, error_msg):
# # # # #         self.progress.stop()
# # # # #         self.action_btn.config(state="normal")
# # # # #         self.status_var.set("Download failed")
# # # # #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# # # # #     def upload_spiffs(self):
# # # # #         def upload_worker():
# # # # #             try:
# # # # #                 self.progress.start()
# # # # #                 self.action_btn.config(state="disabled")
# # # # #                 self.status_var.set("Creating SPIFFS image...")

# # # # #                 spiffs_dir = Path("spiffs")
# # # # #                 spiffs_dir.mkdir(exist_ok=True)

# # # # #                 # Use the values from the selected partition
# # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # #                 size_val   = part['size']
# # # # #                 offset_val = part['offset']

# # # # #                 cmd = [
# # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # #                     "-c", "data",
# # # # #                     "-p", "256",
# # # # #                     "-b", "4096",
# # # # #                     "-s", str(size_val),
# # # # #                     "spiffs/data.bin"
# # # # #                 ]
# # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # #                 if result.returncode != 0:
# # # # #                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

# # # # #                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

# # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # #                 cmd = [
# # # # #                     "esptool.exe",
# # # # #                     "--chip", self.chip_var.get(),
# # # # #                     "--port", self.get_selected_port(),
# # # # #                     "--baud", self.config["baud_rate"],
# # # # #                     "--before", "default_reset",
# # # # #                     "--after", "hard_reset",
# # # # #                     "write_flash", "-z",
# # # # #                     "--flash_mode", "dio",
# # # # #                     "--flash_size", "detect",
# # # # #                     offset_hex, "spiffs/data.bin"
# # # # #                 ]
# # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # #                 if result.returncode != 0:
# # # # #                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

# # # # #                 self.root.after(0, self.upload_complete)

# # # # #             except Exception as e:
# # # # #                 error_msg = str(e)
# # # # #                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

# # # # #         thread = threading.Thread(target=upload_worker)
# # # # #         thread.daemon = True
# # # # #         thread.start()

# # # # #     def upload_complete(self):
# # # # #         self.progress.stop()
# # # # #         self.action_btn.config(state="normal")
# # # # #         self.status_var.set("SPIFFS uploaded successfully")
# # # # #         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

# # # # #     def upload_error(self, error_msg):
# # # # #         self.progress.stop()
# # # # #         self.action_btn.config(state="normal")
# # # # #         self.status_var.set("Upload failed")
# # # # #         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

# # # # #     # ------------------------------------------------------------------
# # # # #     #  File management (adjusted for editor_modified flag)
# # # # #     # ------------------------------------------------------------------
# # # # #     def load_files(self):
# # # # #         self.current_files = {}
# # # # #         self.file_listbox.delete(0, tk.END)
# # # # #         data_dir = Path("data")
# # # # #         if not data_dir.exists():
# # # # #             return
# # # # #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# # # # #         for file_path in data_dir.iterdir():
# # # # #             if file_path.is_file() and file_path.suffix.lower() in text_extensions:
# # # # #                 try:
# # # # #                     with open(file_path, 'r', encoding='utf-8') as f:
# # # # #                         content = f.read()
# # # # #                     self.current_files[file_path.name] = content
# # # # #                     self.file_listbox.insert(tk.END, file_path.name)
# # # # #                 except Exception as e:
# # # # #                     print(f"Error reading {file_path}: {e}")
# # # # #         self.add_file_btn.config(state="normal")
# # # # #         if self.current_files:
# # # # #             self.file_listbox.selection_set(0)
# # # # #             self.on_file_select()

# # # # #     # NEW:  ask unsaved when changing file selection
# # # # #     def on_file_select(self, event=None):
# # # # #         selection = self.file_listbox.curselection()
# # # # #         if not selection:
# # # # #             return
# # # # #         if not self.ask_unsaved_changes("switching file"):
# # # # #             # restore previous selection
# # # # #             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
# # # # #             self.file_listbox.selection_clear(0, tk.END)
# # # # #             self.file_listbox.selection_set(idx)
# # # # #             return

# # # # #         filename = self.file_listbox.get(selection[0])
# # # # #         if filename in self.current_files:
# # # # #             self.selected_file = filename
# # # # #             self.content_editor.delete(1.0, tk.END)
# # # # #             self.content_editor.insert(1.0, self.current_files[filename])
# # # # #             self.editor_modified = False
# # # # #             self.save_file_btn.config(state="disabled")
# # # # #             self.delete_file_btn.config(state="normal")

# # # # #     def on_content_changed(self, event=None):
# # # # #         if self.selected_file:
# # # # #             self.editor_modified = True
# # # # #             self.save_file_btn.config(state="normal")

# # # # #     def save_current_file(self):
# # # # #         if not self.selected_file:
# # # # #             return
# # # # #         content = self.content_editor.get(1.0, tk.END).rstrip()
# # # # #         self.current_files[self.selected_file] = content
# # # # #         try:
# # # # #             data_dir = Path("data")
# # # # #             data_dir.mkdir(exist_ok=True)
# # # # #             file_path = data_dir / self.selected_file
# # # # #             with open(file_path, 'w', encoding='utf-8') as f:
# # # # #                 f.write(content)
# # # # #             self.editor_modified = False
# # # # #             self.save_file_btn.config(state="disabled")
# # # # #             self.status_var.set(f"Saved {self.selected_file}")
# # # # #         except Exception as e:
# # # # #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# # # # #     # ------------------------------------------------------------------
# # # # #     #  NEW:  Simple Add‑File that selects an existing file from the host
# # # # #     # ------------------------------------------------------------------
# # # # #     def add_file(self):
# # # # #         src_path = filedialog.askopenfilename(title="Select file to add")
# # # # #         if not src_path:
# # # # #             return

# # # # #         filename = os.path.basename(src_path)
# # # # #         if filename in self.current_files:
# # # # #             messagebox.showerror("Error", f"File \"{filename}\" already exists in the SPIFFS.")
# # # # #             return

# # # # #         try:
# # # # #             with open(src_path, 'r', encoding='utf-8') as f:
# # # # #                 content = f.read()
# # # # #         except Exception as e:
# # # # #             messagebox.showerror("Error", f"Could not read selected file:\n{e}")
# # # # #             return

# # # # #         # Register in internal structures and write to disk
# # # # #         self.current_files[filename] = content
# # # # #         self.file_listbox.insert(tk.END, filename)

# # # # #         data_dir = Path("data")
# # # # #         data_dir.mkdir(exist_ok=True)
# # # # #         dest_path = data_dir / filename
# # # # #         try:
# # # # #             with open(dest_path, 'w', encoding='utf-8') as f:
# # # # #                 f.write(content)
# # # # #         except Exception as e:
# # # # #             messagebox.showerror("Error", f"Failed to copy file to data folder:\n{e}")
# # # # #             return

# # # # #         self.file_listbox.selection_clear(0, tk.END)
# # # # #         self.file_listbox.selection_set(tk.END)
# # # # #         self.on_file_select()

# # # # #     def delete_file(self):
# # # # #         if not self.selected_file:
# # # # #             return
# # # # #         result = messagebox.askyesno("Confirm Delete",
# # # # #                                    f"Are you sure you want to delete {self.selected_file}?")
# # # # #         if not result:
# # # # #             return
# # # # #         del self.current_files[self.selected_file]
# # # # #         selection = self.file_listbox.curselection()
# # # # #         if selection:
# # # # #             self.file_listbox.delete(selection[0])
# # # # #         try:
# # # # #             file_path = Path("data") / self.selected_file
# # # # #             if file_path.exists():
# # # # #                 file_path.unlink()
# # # # #         except Exception as e:
# # # # #             print(f"Error deleting file: {e}")
# # # # #         self.content_editor.delete(1.0, tk.END)
# # # # #         self.selected_file = None
# # # # #         self.editor_modified = False
# # # # #         self.save_file_btn.config(state="disabled")
# # # # #         self.delete_file_btn.config(state="disabled")

# # # # #     # ------------------------------------------------------------------
# # # # #     #  Application close handler
# # # # #     # ------------------------------------------------------------------
# # # # #     def on_app_closing(self):
# # # # #         if self.ask_unsaved_changes("closing the application"):
# # # # #             self.root.destroy()


# # # # # # ----------------------------------------------------------------------
# # # # # #  Entry-point
# # # # # # ----------------------------------------------------------------------
# # # # # def main():
# # # # #     import tkinter.simpledialog
# # # # #     tk.simpledialog = tkinter.simpledialog
# # # # #     root = tk.Tk()
# # # # #     ESP32SPIFFSManager(root)
# # # # #     root.mainloop()


# # # # # if __name__ == "__main__":
# # # # #     main()

# # # # # # #!/usr/bin/env python3
# # # # # # """
# # # # # # ESP32 SPIFFS Manager GUI
# # # # # # Windows GUI application for managing ESP32 SPIFFS filesystem
# # # # # # """
# # # # # # VERSION = "v.021"  #  <── incremented on every program update

# # # # # # import os
# # # # # # import json
# # # # # # import subprocess
# # # # # # import sys
# # # # # # import tkinter as tk
# # # # # # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # # # # # import csv                      # new – to read partitions.csv
# # # # # # from pathlib import Path
# # # # # # import serial.tools.list_ports
# # # # # # import threading
# # # # # # from datetime import datetime

# # # # # # # ------------------------------------------------------------------
# # # # # # #  Main application class
# # # # # # # ------------------------------------------------------------------
# # # # # # class ESP32SPIFFSManager:
# # # # # #     def __init__(self, root):
# # # # # #         self.root = root
# # # # # #         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
# # # # # #         self.root.geometry("1000x700")
# # # # # #         self.root.minsize(800, 600)

# # # # # #         # Configuration
# # # # # #         self.config_file = "spiffs_config.json"
# # # # # #         self.load_config()

# # # # # #         # keep chip variable even though the UI element is hidden
# # # # # #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

# # # # # #         # --------------------------------------------------------------
# # # # # #         #  Load SPIFFS partition information from *partitions.csv*
# # # # # #         # --------------------------------------------------------------
# # # # # #         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
# # # # # #         self.current_spiffs_index = 0       # index inside self.spiffs_partitions
# # # # # #         self.load_partitions_csv()

# # # # # #         # State variables
# # # # # #         self.connected = False
# # # # # #         self.current_files = {}       # filename → content
# # # # # #         self.selected_file = None     # filename currently in editor
# # # # # #         self.spiffs_downloaded = False
# # # # # #         self.editor_modified = False  # True while editor has unsaved changes

# # # # # #         # Create GUI
# # # # # #         self.create_widgets()
# # # # # #         self.scan_ports()

# # # # # #         # Ask on unsaved changes when user closes window
# # # # # #         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

# # # # # #         # Check required files on startup
# # # # # #         self.check_dependencies()

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  NEW:  generic “ask unsaved” helper  (returns True = proceed, False = abort)
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def ask_unsaved_changes(self, action: str = "switch file"):
# # # # # #         """Return True if the caller may continue, False if user chose Cancel."""
# # # # # #         if not self.editor_modified:
# # # # # #             return True

# # # # # #         answer = messagebox.askyesnocancel(
# # # # # #             "Unsaved changes",
# # # # # #             f'File "{self.selected_file}" has unsaved changes.\n\n'
# # # # # #             f'Save before {action}?',
# # # # # #             default=messagebox.YES
# # # # # #         )
# # # # # #         if answer is True:          # Save
# # # # # #             self.save_current_file()
# # # # # #             return True
# # # # # #         elif answer is False:       # Discard
# # # # # #             return True
# # # # # #         else:                       # Cancel
# # # # # #             return False

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  Small helpers (unchanged)
# # # # # #     # ------------------------------------------------------------------
# # # # # #     @staticmethod
# # # # # #     def _ensure_int(value):
# # # # # #         """Return int whether value is already int or decimal/hex string."""
# # # # # #         if isinstance(value, int):
# # # # # #             return value
# # # # # #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# # # # # #     def load_config(self):
# # # # # #         default_config = {
# # # # # #             "spiffs_offset": 6750208,  # 0x670000
# # # # # #             "spiffs_size": 1572864,    # 0x180000
# # # # # #             "esp32_chip": "esp32-s3",
# # # # # #             "baud_rate": "921600",
# # # # # #             "last_port": ""
# # # # # #         }
# # # # # #         try:
# # # # # #             if os.path.exists(self.config_file):
# # # # # #                 with open(self.config_file, 'r') as f:
# # # # # #                     self.config = json.load(f)
# # # # # #                 for key, value in default_config.items():
# # # # # #                     if key not in self.config:
# # # # # #                         self.config[key] = value
# # # # # #             else:
# # # # # #                 self.config = default_config
# # # # # #                 self.save_config()
# # # # # #         except Exception as e:
# # # # # #             print(f"Error loading config: {e}")
# # # # # #             self.config = default_config
# # # # # #             self.save_config()

# # # # # #     def save_config(self):
# # # # # #         try:
# # # # # #             with open(self.config_file, 'w') as f:
# # # # # #                 json.dump(self.config, f, indent=4)
# # # # # #         except Exception as e:
# # # # # #             print(f"Error saving config: {e}")

# # # # # #     def format_value_for_display(self, value):
# # # # # #         if isinstance(value, int):
# # # # # #             return f"0x{value:X}"
# # # # # #         return str(value)

# # # # # #     def parse_value_from_input(self, value_str):
# # # # # #         value_str = value_str.strip()
# # # # # #         if value_str.lower().startswith('0x'):
# # # # # #             return int(value_str, 16)
# # # # # #         else:
# # # # # #             return int(value_str)

# # # # # #     def validate_config_input(self, value_str, field_name):
# # # # # #         try:
# # # # # #             return self.parse_value_from_input(value_str)
# # # # # #         except ValueError:
# # # # # #             messagebox.showerror("Invalid Input",
# # # # # #                                f"Invalid {field_name} value: {value_str}\n"
# # # # # #                                f"Please enter a decimal number or hex value (0x...)")
# # # # # #             return None

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  NEW:  Read «partitions.csv» and extract all SPIFFS partitions
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def load_partitions_csv(self):
# # # # # #         """
# # # # # #         Looks for a file named *partitions.csv* in the same directory as this
# # # # # #         script.  It must contain a header (or not) with the columns:

# # # # # #             name, type, subtype, offset, size, flags

# # # # # #         All rows whose *subtype* is exactly ``spiffs`` (case‑insensitive) are
# # # # # #         collected.  For each such row we store the name, the integer offset
# # # # # #         and the integer size (hex strings are accepted).  If the file is not
# # # # # #         present or no SPIFFS partition is found, we abort with an error
# # # # # #         message.
# # # # # #         """
# # # # # #         csv_path = Path(__file__).parent / "partitions.csv"
# # # # # #         if not csv_path.is_file():
# # # # # #             messagebox.showerror(
# # # # # #                 "Missing file",
# # # # # #                 "Required file *partitions.csv* not found in the script folder.\n"
# # # # # #                 "The program cannot determine the SPIFFS offset/size.\n"
# # # # # #                 "Place a valid partitions.csv next to the script and restart."
# # # # # #             )
# # # # # #             sys.exit(1)

# # # # # #         try:
# # # # # #             with csv_path.open(newline='') as f:
# # # # # #                 reader = csv.reader(f)
# # # # # #                 for row in reader:
# # # # # #                     # skip empty lines / comments
# # # # # #                     if not row or row[0].strip().startswith('#'):
# # # # # #                         continue
# # # # # #                     # the CSV is usually: name,type,subtype,offset,size,flags
# # # # # #                     if len(row) < 5:
# # # # # #                         continue
# # # # # #                     name, _type, subtype, offset_str, size_str = (
# # # # # #                         row[0].strip(),
# # # # # #                         row[1].strip(),
# # # # # #                         row[2].strip(),
# # # # # #                         row[3].strip(),
# # # # # #                         row[4].strip(),
# # # # # #                     )
# # # # # #                     if subtype.lower() != 'spiffs':
# # # # # #                         continue
# # # # # #                     # Convert hex/dec strings to int
# # # # # #                     offset = int(offset_str, 0)
# # # # # #                     size   = int(size_str, 0)
# # # # # #                     self.spiffs_partitions.append({
# # # # # #                         "name"  : name,
# # # # # #                         "offset": offset,
# # # # # #                         "size"  : size,
# # # # # #                     })
# # # # # #         except Exception as e:
# # # # # #             messagebox.showerror(
# # # # # #                 "Error reading partitions.csv",
# # # # # #                 f"Could not parse *partitions.csv*:\n{e}"
# # # # # #             )
# # # # # #             sys.exit(1)

# # # # # #         if not self.spiffs_partitions:
# # # # # #             messagebox.showerror(
# # # # # #                 "No SPIFFS partition",
# # # # # #                 "The *partitions.csv* file does not contain any SPIFFS partition entries."
# # # # # #             )
# # # # # #             sys.exit(1)

# # # # # #         # Use the first partition as the default selection
# # # # # #         self.current_spiffs_index = 0

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  GUI creation (modified layout)
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def create_widgets(self):
# # # # # #         main_frame = ttk.Frame(self.root, padding="10")
# # # # # #         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # #         self.root.columnconfigure(0, weight=1)
# # # # # #         self.root.rowconfigure(0, weight=1)
# # # # # #         main_frame.columnconfigure(1, weight=1)
# # # # # #         main_frame.rowconfigure(3, weight=1)

# # # # # #         # ---------------- Connection frame ----------------
# # # # # #         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
# # # # # #         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
# # # # # #         conn_frame.columnconfigure(1, weight=1)

# # # # # #         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # # #         self.port_var = tk.StringVar()
# # # # # #         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
# # # # # #         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

# # # # # #         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
# # # # # #         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

# # # # # #         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
# # # # # #         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

# # # # # #         # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

# # # # # #         # ---------------- SPIFFS Configuration frame ----------------
# # # # # #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# # # # # #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# # # # # #         # ----- Partition selector (wider) -----
# # # # # #         ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # # #         self.partition_var = tk.StringVar()
# # # # # #         self.partition_combo = ttk.Combobox(
# # # # # #             spiffs_frame,
# # # # # #             textvariable=self.partition_var,
# # # # # #             state="readonly",
# # # # # #             width=40,                # made wider as requested
# # # # # #         )
# # # # # #         partition_names = [
# # # # # #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# # # # # #         ]
# # # # # #         self.partition_combo['values'] = partition_names
# # # # # #         self.partition_combo.current(self.current_spiffs_index)
# # # # # #         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
# # # # # #         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)

# # # # # #         # ----- Offset (read‑only) -----
# # # # # #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# # # # # #         self.offset_var = tk.StringVar()
# # # # # #         self.offset_entry = ttk.Entry(
# # # # # #             spiffs_frame,
# # # # # #             textvariable=self.offset_var,
# # # # # #             width=15,
# # # # # #             state="readonly"
# # # # # #         )
# # # # # #         self.offset_entry.grid(row=0, column=3, padx=(0, 10))

# # # # # #         # ----- Size (read‑only) -----
# # # # # #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
# # # # # #         self.size_var = tk.StringVar()
# # # # # #         self.size_entry = ttk.Entry(
# # # # # #             spiffs_frame,
# # # # # #             textvariable=self.size_var,
# # # # # #             width=15,
# # # # # #             state="readonly"
# # # # # #         )
# # # # # #         self.size_entry.grid(row=0, column=5, padx=(0, 10))

# # # # # #         # ----- Chip (read‑only, shown after connection) -----
# # # # # #         ttk.Label(spiffs_frame, text="Chip:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
# # # # # #         self.chip_display_var = tk.StringVar()
# # # # # #         self.chip_display_entry = ttk.Entry(
# # # # # #             spiffs_frame,
# # # # # #             textvariable=self.chip_display_var,
# # # # # #             width=12,
# # # # # #             state="readonly"
# # # # # #         )
# # # # # #         self.chip_display_entry.grid(row=0, column=7, padx=(0, 10))

# # # # # #         # Initialise the displayed values for the default partition
# # # # # #         self.update_spiffs_fields()

# # # # # #         # Hide the now‑redundant "Save Config" button (kept for layout)
# # # # # #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# # # # # #         self.save_config_btn.grid(row=0, column=8, padx=(10, 0))
# # # # # #         self.save_config_btn.grid_remove()          # completely hide it

# # # # # #         # ---------------- Action frame ----------------
# # # # # #         action_frame = ttk.Frame(main_frame)
# # # # # #         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

# # # # # #         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
# # # # # #         self.action_btn.grid(row=0, column=0, padx=(0, 10))
# # # # # #         self.action_btn.config(state="disabled")

# # # # # #         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
# # # # # #         self.progress.grid(row=0, column=1, padx=(10, 0))

# # # # # #         # ---------------- Content frame ----------------
# # # # # #         content_frame = ttk.Frame(main_frame)
# # # # # #         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # #         content_frame.columnconfigure(1, weight=2)
# # # # # #         content_frame.rowconfigure(0, weight=1)

# # # # # #         # File list
# # # # # #         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
# # # # # #         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
# # # # # #         file_frame.columnconfigure(0, weight=1)
# # # # # #         file_frame.rowconfigure(0, weight=1)

# # # # # #         list_frame = ttk.Frame(file_frame)
# # # # # #         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # #         list_frame.columnconfigure(0, weight=1)
# # # # # #         list_frame.rowconfigure(0, weight=1)

# # # # # #         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
# # # # # #         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # #         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

# # # # # #         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
# # # # # #         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
# # # # # #         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

# # # # # #         file_btn_frame = ttk.Frame(file_frame)
# # # # # #         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

# # # # # #         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
# # # # # #         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))
# # # # # #         self.add_file_btn.config(state="disabled")   # enabled only after download

# # # # # #         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
# # # # # #         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
# # # # # #         self.save_file_btn.config(state="disabled")

# # # # # #         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
# # # # # #         self.delete_file_btn.grid(row=0, column=2)
# # # # # #         self.delete_file_btn.config(state="disabled")

# # # # # #         # Editor
# # # # # #         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
# # # # # #         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # #         editor_frame.columnconfigure(0, weight=1)
# # # # # #         editor_frame.rowconfigure(0, weight=1)

# # # # # #         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
# # # # # #         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # #         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

# # # # # #         # Status bar
# # # # # #         self.status_var = tk.StringVar(value="Ready")
# # # # # #         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
# # # # # #         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  Dependency / connection / scan helpers (unchanged)
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def check_dependencies(self):
# # # # # #         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
# # # # # #         missing_files = []
# # # # # #         for file in required_files:
# # # # # #             if not os.path.exists(file):
# # # # # #                 missing_files.append(file)
# # # # # #         if missing_files:
# # # # # #             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
# # # # # #             message += "\n\nPlease ensure these files are in the application directory."
# # # # # #             messagebox.showerror("Missing Dependencies", message)
# # # # # #             self.status_var.set("Missing dependencies")
# # # # # #             return False
# # # # # #         try:
# # # # # #             import serial.tools.list_ports
# # # # # #         except ImportError:
# # # # # #             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
# # # # # #             self.status_var.set("Missing pyserial")
# # # # # #             return False
# # # # # #         self.status_var.set("Dependencies OK")
# # # # # #         return True

# # # # # #     def scan_ports(self):
# # # # # #         ports = serial.tools.list_ports.comports()
# # # # # #         port_list = []
# # # # # #         for port in ports:
# # # # # #             description = port.description if port.description != 'n/a' else 'Unknown device'
# # # # # #             port_display = f"{port.device} - {description}"
# # # # # #             port_list.append(port_display)
# # # # # #         self.port_combo['values'] = port_list
# # # # # #         if self.config.get("last_port"):
# # # # # #             for port_display in port_list:
# # # # # #                 if port_display.startswith(self.config["last_port"] + " "):
# # # # # #                     self.port_var.set(port_display)
# # # # # #                     break
# # # # # #         elif port_list:
# # # # # #             self.port_var.set(port_list[0])
# # # # # #         self.status_var.set(f"Found {len(port_list)} COM ports")

# # # # # #     def get_selected_port(self):
# # # # # #         port_display = self.port_var.get()
# # # # # #         if not port_display:
# # # # # #             return ""
# # # # # #         return port_display.split(" - ")[0]

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  NEW:  on disconnect reset button to initial state + clear file list & editor
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def toggle_connection(self):
# # # # # #         if not self.connected:
# # # # # #             if not self.port_var.get():
# # # # # #                 messagebox.showerror("Error", "Please select a COM port")
# # # # # #                 return

# # # # # #             # ---- auto‑detect ESP32 chip ----
# # # # # #             chip, err = self.detect_chip()
# # # # # #             if chip is None:
# # # # # #                 messagebox.showerror("Connection Error", f"Could not detect ESP32 chip:\n{err}")
# # # # # #                 return

# # # # # #             # Store detected chip for later use
# # # # # #             self.chip_var.set(chip)
# # # # # #             self.config["esp32_chip"] = chip
# # # # # #             self.save_config()
# # # # # #             self.chip_display_var.set(chip)          # show it in the UI

# # # # # #             # Connection considered successful (esptool already succeeded)
# # # # # #             self.connected = True
# # # # # #             self.connect_btn.config(text="Disconnect")
# # # # # #             self.action_btn.config(state="normal")
# # # # # #             self.config["last_port"] = self.get_selected_port()
# # # # # #             self.save_config()
# # # # # #             self.status_var.set(f"Connected to {self.get_selected_port()} ({chip})")
# # # # # #         else:
# # # # # #             # ---------- disconnect ----------
# # # # # #             self.connected = False
# # # # # #             self.connect_btn.config(text="Connect")
# # # # # #             self.action_btn.config(state="disabled")
# # # # # #             # reset big button to initial download state
# # # # # #             self.spiffs_downloaded = False
# # # # # #             self.action_btn.config(text="Download SPIFFS")
# # # # # #             # clear file list and editor
# # # # # #             self.file_listbox.delete(0, tk.END)
# # # # # #             self.content_editor.delete(1.0, tk.END)
# # # # # #             self.current_files.clear()
# # # # # #             self.selected_file = None
# # # # # #             self.editor_modified = False
# # # # # #             self.save_file_btn.config(state="disabled")
# # # # # #             self.delete_file_btn.config(state="disabled")
# # # # # #             self.add_file_btn.config(state="disabled")
# # # # # #             self.chip_display_var.set("")
# # # # # #             self.status_var.set("Disconnected")

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  NEW:  ESP32 chip auto‑recognition
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def detect_chip(self):
# # # # # #         """
# # # # # #         Runs ``esptool.exe chip_id`` and parses its output.
# # # # # #         Returns a tuple (chip_name, error_message). ``chip_name`` is one of
# # # # # #         ``esp32``, ``esp32-s2``, ``esp32-s3``, ``esp32-c3``, ``esp32-c6``.
# # # # # #         If detection fails, ``chip_name`` is ``None`` and ``error_message``
# # # # # #         contains the reason.
# # # # # #         """
# # # # # #         cmd = [
# # # # # #             "esptool.exe",
# # # # # #             "--port", self.get_selected_port(),
# # # # # #             "chip_id"
# # # # # #         ]
# # # # # #         try:
# # # # # #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
# # # # # #         except Exception as e:
# # # # # #             return None, str(e)

# # # # # #         if result.returncode != 0:
# # # # # #             return None, result.stderr or "esptool error"

# # # # # #         # Example line: "Chip is ESP32S3"
# # # # # #         for line in result.stdout.splitlines():
# # # # # #             if "Chip is" in line:
# # # # # #                 name_part = line.split("Chip is")[-1].strip().lower()
# # # # # #                 if "esp32s3" in name_part:
# # # # # #                     return "esp32-s3", None
# # # # # #                 if "esp32s2" in name_part:
# # # # # #                     return "esp32-s2", None
# # # # # #                 if "esp32c3" in name_part:
# # # # # #                     return "esp32-c3", None
# # # # # #                 if "esp32c6" in name_part:
# # # # # #                     return "esp32-c6", None
# # # # # #                 if "esp32" in name_part:
# # # # # #                     return "esp32", None
# # # # # #         return None, "Unable to parse chip type from esptool output"

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  NEW:  hide chip selector – kept only for internal use
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def on_chip_changed(self, event=None):
# # # # # #         # Legacy placeholder – UI no longer exposes chip selection.
# # # # # #         self.config["esp32_chip"] = self.chip_var.get()
# # # # # #         self.save_config()

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  NEW:  Called when the user changes the selected partition
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def on_partition_selected(self, event=None):
# # # # # #         """Update offset/size fields to reflect the newly selected partition."""
# # # # # #         try:
# # # # # #             self.current_spiffs_index = self.partition_combo.current()
# # # # # #             self.update_spiffs_fields()
# # # # # #         except Exception:
# # # # # #             pass   # defensive – should never happen

# # # # # #     def update_spiffs_fields(self):
# # # # # #         """Write the offset and size of the currently selected partition to the UI."""
# # # # # #         part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # #         self.offset_var.set(self.format_value_for_display(part['offset']))
# # # # # #         self.size_var.set(self.format_value_for_display(part['size']))

# # # # # #     def save_spiffs_config(self):
# # # # # #         # The configuration is now derived from partitions.csv, therefore the
# # # # # #         # “Save Config” button is hidden.  This method only informs the user.
# # # # # #         messagebox.showinfo(
# # # # # #             "Info",
# # # # # #             "SPIFFS offset and size are taken from *partitions.csv*.\n"
# # # # # #             "To change them, edit that file and restart the application."
# # # # # #         )

# # # # # #     def perform_action(self):
# # # # # #         if not self.connected:
# # # # # #             messagebox.showerror("Error", "Not connected to ESP32")
# # # # # #             return
# # # # # #         if not self.spiffs_downloaded:
# # # # # #             self.download_spiffs()
# # # # # #         else:
# # # # # #             # ---- ask for confirmation before upload ----
# # # # # #             if not messagebox.askyesno("Confirm Upload",
# # # # # #                                        "Are you sure you want to upload the SPIFFS image to the ESP32?"):
# # # # # #                 return
# # # # # #             # ---- ask for unsaved before upload ----
# # # # # #             if not self.ask_unsaved_changes("uploading"):
# # # # # #                 return
# # # # # #             self.upload_spiffs()

# # # # # #     def download_spiffs(self):
# # # # # #         def download_worker():
# # # # # #             try:
# # # # # #                 self.progress.start()
# # # # # #                 self.action_btn.config(state="disabled")
# # # # # #                 self.status_var.set("Downloading SPIFFS...")

# # # # # #                 # Use the values from the selected partition
# # # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # #                 offset_val = part['offset']
# # # # # #                 size_val   = part['size']

# # # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # # #                 size_dec   = str(size_val)

# # # # # #                 cmd = [
# # # # # #                     "esptool.exe",
# # # # # #                     "--chip", self.chip_var.get(),
# # # # # #                     "--port", self.get_selected_port(),
# # # # # #                     "--baud", self.config["baud_rate"],
# # # # # #                     "read_flash", offset_hex, size_dec,
# # # # # #                     "spiffs_dump.bin"
# # # # # #                 ]
# # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # #                 if result.returncode != 0:
# # # # # #                     raise Exception(f"Failed to read flash: {result.stderr}")

# # # # # #                 data_dir = Path("data")
# # # # # #                 data_dir.mkdir(exist_ok=True)
# # # # # #                 for file in data_dir.glob("*"):
# # # # # #                     if file.is_file():
# # # # # #                         file.unlink()

# # # # # #                 cmd = [
# # # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # # #                     "-u", "data",
# # # # # #                     "spiffs_dump.bin"
# # # # # #                 ]
# # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # #                 if result.returncode != 0:
# # # # # #                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

# # # # # #                 self.root.after(0, self.download_complete)

# # # # # #             except Exception as e:
# # # # # #                 error_msg = str(e)
# # # # # #                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

# # # # # #         thread = threading.Thread(target=download_worker)
# # # # # #         thread.daemon = True
# # # # # #         thread.start()

# # # # # #     def download_complete(self):
# # # # # #         self.progress.stop()
# # # # # #         self.action_btn.config(state="normal", text="Upload SPIFFS")
# # # # # #         self.spiffs_downloaded = True
# # # # # #         self.status_var.set("SPIFFS downloaded successfully")
# # # # # #         self.load_files()
# # # # # #         # Enable file‑related buttons now that we have a filesystem
# # # # # #         self.add_file_btn.config(state="normal")
# # # # # #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# # # # # #     def download_error(self, error_msg):
# # # # # #         self.progress.stop()
# # # # # #         self.action_btn.config(state="normal")
# # # # # #         self.status_var.set("Download failed")
# # # # # #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# # # # # #     def upload_spiffs(self):
# # # # # #         def upload_worker():
# # # # # #             try:
# # # # # #                 self.progress.start()
# # # # # #                 self.action_btn.config(state="disabled")
# # # # # #                 self.status_var.set("Creating SPIFFS image...")

# # # # # #                 spiffs_dir = Path("spiffs")
# # # # # #                 spiffs_dir.mkdir(exist_ok=True)

# # # # # #                 # Use the values from the selected partition
# # # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # #                 size_val   = part['size']
# # # # # #                 offset_val = part['offset']

# # # # # #                 cmd = [
# # # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # # #                     "-c", "data",
# # # # # #                     "-p", "256",
# # # # # #                     "-b", "4096",
# # # # # #                     "-s", str(size_val),
# # # # # #                     "spiffs/data.bin"
# # # # # #                 ]
# # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # #                 if result.returncode != 0:
# # # # # #                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

# # # # # #                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

# # # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # # #                 cmd = [
# # # # # #                     "esptool.exe",
# # # # # #                     "--chip", self.chip_var.get(),
# # # # # #                     "--port", self.get_selected_port(),
# # # # # #                     "--baud", self.config["baud_rate"],
# # # # # #                     "--before", "default_reset",
# # # # # #                     "--after", "hard_reset",
# # # # # #                     "write_flash", "-z",
# # # # # #                     "--flash_mode", "dio",
# # # # # #                     "--flash_size", "detect",
# # # # # #                     offset_hex, "spiffs/data.bin"
# # # # # #                 ]
# # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # #                 if result.returncode != 0:
# # # # # #                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

# # # # # #                 self.root.after(0, self.upload_complete)

# # # # # #             except Exception as e:
# # # # # #                 error_msg = str(e)
# # # # # #                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

# # # # # #         thread = threading.Thread(target=upload_worker)
# # # # # #         thread.daemon = True
# # # # # #         thread.start()

# # # # # #     def upload_complete(self):
# # # # # #         self.progress.stop()
# # # # # #         self.action_btn.config(state="normal")
# # # # # #         self.status_var.set("SPIFFS uploaded successfully")
# # # # # #         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

# # # # # #     def upload_error(self, error_msg):
# # # # # #         self.progress.stop()
# # # # # #         self.action_btn.config(state="normal")
# # # # # #         self.status_var.set("Upload failed")
# # # # # #         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  File management (adjusted for editor_modified flag)
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def load_files(self):
# # # # # #         self.current_files = {}
# # # # # #         self.file_listbox.delete(0, tk.END)
# # # # # #         data_dir = Path("data")
# # # # # #         if not data_dir.exists():
# # # # # #             return
# # # # # #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# # # # # #         for file_path in data_dir.iterdir():
# # # # # #             if file_path.is_file() and file_path.suffix.lower() in text_extensions:
# # # # # #                 try:
# # # # # #                     with open(file_path, 'r', encoding='utf-8') as f:
# # # # # #                         content = f.read()
# # # # # #                     self.current_files[file_path.name] = content
# # # # # #                     self.file_listbox.insert(tk.END, file_path.name)
# # # # # #                 except Exception as e:
# # # # # #                     print(f"Error reading {file_path}: {e}")
# # # # # #         self.add_file_btn.config(state="normal")
# # # # # #         if self.current_files:
# # # # # #             self.file_listbox.selection_set(0)
# # # # # #             self.on_file_select()

# # # # # #     # NEW:  ask unsaved when changing file selection
# # # # # #     def on_file_select(self, event=None):
# # # # # #         selection = self.file_listbox.curselection()
# # # # # #         if not selection:
# # # # # #             return
# # # # # #         if not self.ask_unsaved_changes("switching file"):
# # # # # #             # restore previous selection
# # # # # #             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
# # # # # #             self.file_listbox.selection_clear(0, tk.END)
# # # # # #             self.file_listbox.selection_set(idx)
# # # # # #             return

# # # # # #         filename = self.file_listbox.get(selection[0])
# # # # # #         if filename in self.current_files:
# # # # # #             self.selected_file = filename
# # # # # #             self.content_editor.delete(1.0, tk.END)
# # # # # #             self.content_editor.insert(1.0, self.current_files[filename])
# # # # # #             self.editor_modified = False
# # # # # #             self.save_file_btn.config(state="disabled")
# # # # # #             self.delete_file_btn.config(state="normal")

# # # # # #     def on_content_changed(self, event=None):
# # # # # #         if self.selected_file:
# # # # # #             self.editor_modified = True
# # # # # #             self.save_file_btn.config(state="normal")

# # # # # #     def save_current_file(self):
# # # # # #         if not self.selected_file:
# # # # # #             return
# # # # # #         content = self.content_editor.get(1.0, tk.END).rstrip()
# # # # # #         self.current_files[self.selected_file] = content
# # # # # #         try:
# # # # # #             data_dir = Path("data")
# # # # # #             data_dir.mkdir(exist_ok=True)
# # # # # #             file_path = data_dir / self.selected_file
# # # # # #             with open(file_path, 'w', encoding='utf-8') as f:
# # # # # #                 f.write(content)
# # # # # #             self.editor_modified = False
# # # # # #             self.save_file_btn.config(state="disabled")
# # # # # #             self.status_var.set(f"Saved {self.selected_file}")
# # # # # #         except Exception as e:
# # # # # #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  NEW:  Enhanced Add‑File dialog (wider entry + browse)
# # # # # #     # ------------------------------------------------------------------
# # # # # #     class _AddFileDialog:
# # # # # #         """Simple modal dialog to input a filename and optionally select a source file."""
# # # # # #         def __init__(self, parent):
# # # # # #             self.top = tk.Toplevel(parent)
# # # # # #             self.top.title("Add File")
# # # # # #             self.top.transient(parent)
# # # # # #             self.top.grab_set()

# # # # # #             ttk.Label(self.top, text="File name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
# # # # # #             self.name_var = tk.StringVar()
# # # # # #             self.entry = ttk.Entry(self.top, textvariable=self.name_var, width=50)
# # # # # #             self.entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky=tk.EW)

# # # # # #             ttk.Label(self.top, text="Source (optional):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
# # # # # #             self.source_var = tk.StringVar()
# # # # # #             self.source_entry = ttk.Entry(self.top, textvariable=self.source_var, width=40)
# # # # # #             self.source_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
# # # # # #             self.browse_btn = ttk.Button(self.top, text="Browse...", command=self.browse)
# # # # # #             self.browse_btn.grid(row=1, column=2, padx=5, pady=5)

# # # # # #             btn_frame = ttk.Frame(self.top)
# # # # # #             btn_frame.grid(row=2, column=0, columnspan=3, pady=10)

# # # # # #             self.ok_btn = ttk.Button(btn_frame, text="OK", command=self.ok)
# # # # # #             self.ok_btn.grid(row=0, column=0, padx=5)
# # # # # #             self.cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self.cancel)
# # # # # #             self.cancel_btn.grid(row=0, column=1, padx=5)

# # # # # #             self.result = None
# # # # # #             self.entry.focus_set()
# # # # # #             self.top.bind("<Return>", lambda e: self.ok())
# # # # # #             self.top.bind("<Escape>", lambda e: self.cancel())

# # # # # #         def browse(self):
# # # # # #             file_path = filedialog.askopenfilename(title="Select source file")
# # # # # #             if file_path:
# # # # # #                 self.source_var.set(file_path)
# # # # # #                 # If filename entry empty, pre‑fill it with the selected file name
# # # # # #                 if not self.name_var.get():
# # # # # #                     self.name_var.set(os.path.basename(file_path))

# # # # # #         def ok(self):
# # # # # #             name = self.name_var.get().strip()
# # # # # #             src = self.source_var.get().strip()
# # # # # #             if not name:
# # # # # #                 messagebox.showerror("Error", "File name cannot be empty", parent=self.top)
# # # # # #                 return
# # # # # #             self.result = (name, src if src else None)
# # # # # #             self.top.destroy()

# # # # # #         def cancel(self):
# # # # # #             self.top.destroy()

# # # # # #     def add_file(self):
# # # # # #         dlg = self._AddFileDialog(self.root)
# # # # # #         self.root.wait_window(dlg.top)
# # # # # #         if dlg.result is None:
# # # # # #             return
# # # # # #         filename, src_path = dlg.result

# # # # # #         # Ensure a proper extension
# # # # # #         if not any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.ini', '.cfg', '.conf']):
# # # # # #             filename += '.txt'

# # # # # #         if filename in self.current_files:
# # # # # #             messagebox.showerror("Error", "File already exists!")
# # # # # #             return

# # # # # #         content = ""
# # # # # #         if src_path:
# # # # # #             try:
# # # # # #                 with open(src_path, 'r', encoding='utf-8') as f:
# # # # # #                     content = f.read()
# # # # # #             except Exception as e:
# # # # # #                 messagebox.showerror("Error", f"Could not read selected file:\n{e}")
# # # # # #                 return

# # # # # #         # Register in internal structures and write to disk
# # # # # #         self.current_files[filename] = content
# # # # # #         self.file_listbox.insert(tk.END, filename)

# # # # # #         data_dir = Path("data")
# # # # # #         data_dir.mkdir(exist_ok=True)
# # # # # #         file_path = data_dir / filename
# # # # # #         try:
# # # # # #             with open(file_path, 'w', encoding='utf-8') as f:
# # # # # #                 f.write(content)
# # # # # #         except Exception as e:
# # # # # #             messagebox.showerror("Error", f"Could not create file on device:\n{e}")
# # # # # #             return

# # # # # #         self.file_listbox.selection_clear(0, tk.END)
# # # # # #         self.file_listbox.selection_set(tk.END)
# # # # # #         self.on_file_select()

# # # # # #     def delete_file(self):
# # # # # #         if not self.selected_file:
# # # # # #             return
# # # # # #         result = messagebox.askyesno("Confirm Delete",
# # # # # #                                    f"Are you sure you want to delete {self.selected_file}?")
# # # # # #         if not result:
# # # # # #             return
# # # # # #         del self.current_files[self.selected_file]
# # # # # #         selection = self.file_listbox.curselection()
# # # # # #         if selection:
# # # # # #             self.file_listbox.delete(selection[0])
# # # # # #         try:
# # # # # #             file_path = Path("data") / self.selected_file
# # # # # #             if file_path.exists():
# # # # # #                 file_path.unlink()
# # # # # #         except Exception as e:
# # # # # #             print(f"Error deleting file: {e}")
# # # # # #         self.content_editor.delete(1.0, tk.END)
# # # # # #         self.selected_file = None
# # # # # #         self.editor_modified = False
# # # # # #         self.save_file_btn.config(state="disabled")
# # # # # #         self.delete_file_btn.config(state="disabled")

# # # # # #     # ------------------------------------------------------------------
# # # # # #     #  Application close handler
# # # # # #     # ------------------------------------------------------------------
# # # # # #     def on_app_closing(self):
# # # # # #         if self.ask_unsaved_changes("closing the application"):
# # # # # #             self.root.destroy()


# # # # # # # ----------------------------------------------------------------------
# # # # # # #  Entry-point
# # # # # # # ----------------------------------------------------------------------
# # # # # # def main():
# # # # # #     import tkinter.simpledialog
# # # # # #     tk.simpledialog = tkinter.simpledialog
# # # # # #     root = tk.Tk()
# # # # # #     ESP32SPIFFSManager(root)
# # # # # #     root.mainloop()


# # # # # # if __name__ == "__main__":
# # # # # #     main()

# # # # # # # #!/usr/bin/env python3
# # # # # # # """
# # # # # # # ESP32 SPIFFS Manager GUI
# # # # # # # Windows GUI application for managing ESP32 SPIFFS filesystem
# # # # # # # """
# # # # # # # VERSION = "v.017"  #  <── incremented on every program update

# # # # # # # import os
# # # # # # # import json
# # # # # # # import subprocess
# # # # # # # import sys
# # # # # # # import tkinter as tk
# # # # # # # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # # # # # # import csv                      # new – to read partitions.csv
# # # # # # # from pathlib import Path
# # # # # # # import serial.tools.list_ports
# # # # # # # import threading
# # # # # # # from datetime import datetime

# # # # # # # # ------------------------------------------------------------------
# # # # # # # #  Main application class
# # # # # # # # ------------------------------------------------------------------
# # # # # # # class ESP32SPIFFSManager:
# # # # # # #     def __init__(self, root):
# # # # # # #         self.root = root
# # # # # # #         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
# # # # # # #         self.root.geometry("1000x700")
# # # # # # #         self.root.minsize(800, 600)

# # # # # # #         # Configuration
# # # # # # #         self.config_file = "spiffs_config.json"
# # # # # # #         self.load_config()

# # # # # # #         # keep chip variable even though the UI element is hidden
# # # # # # #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))

# # # # # # #         # --------------------------------------------------------------
# # # # # # #         #  Load SPIFFS partition information from *partitions.csv*
# # # # # # #         # --------------------------------------------------------------
# # # # # # #         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
# # # # # # #         self.current_spiffs_index = 0       # index inside self.spiffs_partitions
# # # # # # #         self.load_partitions_csv()

# # # # # # #         # State variables
# # # # # # #         self.connected = False
# # # # # # #         self.current_files = {}       # filename → content
# # # # # # #         self.selected_file = None     # filename currently in editor
# # # # # # #         self.spiffs_downloaded = False
# # # # # # #         self.editor_modified = False  # True while editor has unsaved changes

# # # # # # #         # Create GUI
# # # # # # #         self.create_widgets()
# # # # # # #         self.scan_ports()

# # # # # # #         # Ask on unsaved changes when user closes window
# # # # # # #         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

# # # # # # #         # Check required files on startup
# # # # # # #         self.check_dependencies()

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  NEW:  generic “ask unsaved” helper  (returns True = proceed, False = abort)
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def ask_unsaved_changes(self, action: str = "switch file"):
# # # # # # #         """Return True if the caller may continue, False if user chose Cancel."""
# # # # # # #         if not self.editor_modified:
# # # # # # #             return True

# # # # # # #         answer = messagebox.askyesnocancel(
# # # # # # #             "Unsaved changes",
# # # # # # #             f'File "{self.selected_file}" has unsaved changes.\n\n'
# # # # # # #             f'Save before {action}?',
# # # # # # #             default=messagebox.YES
# # # # # # #         )
# # # # # # #         if answer is True:          # Save
# # # # # # #             self.save_current_file()
# # # # # # #             return True
# # # # # # #         elif answer is False:       # Discard
# # # # # # #             return True
# # # # # # #         else:                       # Cancel
# # # # # # #             return False

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  Small helpers (unchanged)
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     @staticmethod
# # # # # # #     def _ensure_int(value):
# # # # # # #         """Return int whether value is already int or decimal/hex string."""
# # # # # # #         if isinstance(value, int):
# # # # # # #             return value
# # # # # # #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# # # # # # #     def load_config(self):
# # # # # # #         default_config = {
# # # # # # #             "spiffs_offset": 6750208,  # 0x670000
# # # # # # #             "spiffs_size": 1572864,    # 0x180000
# # # # # # #             "esp32_chip": "esp32-s3",
# # # # # # #             "baud_rate": "921600",
# # # # # # #             "last_port": ""
# # # # # # #         }
# # # # # # #         try:
# # # # # # #             if os.path.exists(self.config_file):
# # # # # # #                 with open(self.config_file, 'r') as f:
# # # # # # #                     self.config = json.load(f)
# # # # # # #                 for key, value in default_config.items():
# # # # # # #                     if key not in self.config:
# # # # # # #                         self.config[key] = value
# # # # # # #             else:
# # # # # # #                 self.config = default_config
# # # # # # #                 self.save_config()
# # # # # # #         except Exception as e:
# # # # # # #             print(f"Error loading config: {e}")
# # # # # # #             self.config = default_config
# # # # # # #             self.save_config()

# # # # # # #     def save_config(self):
# # # # # # #         try:
# # # # # # #             with open(self.config_file, 'w') as f:
# # # # # # #                 json.dump(self.config, f, indent=4)
# # # # # # #         except Exception as e:
# # # # # # #             print(f"Error saving config: {e}")

# # # # # # #     def format_value_for_display(self, value):
# # # # # # #         if isinstance(value, int):
# # # # # # #             return f"0x{value:X}"
# # # # # # #         return str(value)

# # # # # # #     def parse_value_from_input(self, value_str):
# # # # # # #         value_str = value_str.strip()
# # # # # # #         if value_str.lower().startswith('0x'):
# # # # # # #             return int(value_str, 16)
# # # # # # #         else:
# # # # # # #             return int(value_str)

# # # # # # #     def validate_config_input(self, value_str, field_name):
# # # # # # #         try:
# # # # # # #             return self.parse_value_from_input(value_str)
# # # # # # #         except ValueError:
# # # # # # #             messagebox.showerror("Invalid Input",
# # # # # # #                                f"Invalid {field_name} value: {value_str}\n"
# # # # # # #                                f"Please enter a decimal number or hex value (0x...)")
# # # # # # #             return None

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  NEW:  Read «partitions.csv» and extract all SPIFFS partitions
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def load_partitions_csv(self):
# # # # # # #         """
# # # # # # #         Looks for a file named *partitions.csv* in the same directory as this
# # # # # # #         script.  It must contain a header (or not) with the columns:

# # # # # # #             name, type, subtype, offset, size, flags

# # # # # # #         All rows whose *subtype* is exactly ``spiffs`` (case‑insensitive) are
# # # # # # #         collected.  For each such row we store the name, the integer offset
# # # # # # #         and the integer size (hex strings are accepted).  If the file is not
# # # # # # #         present or no SPIFFS partition is found, we abort with an error
# # # # # # #         message.
# # # # # # #         """
# # # # # # #         csv_path = Path(__file__).parent / "partitions.csv"
# # # # # # #         if not csv_path.is_file():
# # # # # # #             messagebox.showerror(
# # # # # # #                 "Missing file",
# # # # # # #                 "Required file *partitions.csv* not found in the script folder.\n"
# # # # # # #                 "The program cannot determine the SPIFFS offset/size.\n"
# # # # # # #                 "Place a valid partitions.csv next to the script and restart."
# # # # # # #             )
# # # # # # #             sys.exit(1)

# # # # # # #         try:
# # # # # # #             with csv_path.open(newline='') as f:
# # # # # # #                 reader = csv.reader(f)
# # # # # # #                 for row in reader:
# # # # # # #                     # skip empty lines / comments
# # # # # # #                     if not row or row[0].strip().startswith('#'):
# # # # # # #                         continue
# # # # # # #                     # the CSV is usually: name,type,subtype,offset,size,flags
# # # # # # #                     if len(row) < 5:
# # # # # # #                         continue
# # # # # # #                     name, _type, subtype, offset_str, size_str = (
# # # # # # #                         row[0].strip(),
# # # # # # #                         row[1].strip(),
# # # # # # #                         row[2].strip(),
# # # # # # #                         row[3].strip(),
# # # # # # #                         row[4].strip(),
# # # # # # #                     )
# # # # # # #                     if subtype.lower() != 'spiffs':
# # # # # # #                         continue
# # # # # # #                     # Convert hex/dec strings to int
# # # # # # #                     offset = int(offset_str, 0)
# # # # # # #                     size   = int(size_str, 0)
# # # # # # #                     self.spiffs_partitions.append({
# # # # # # #                         "name"  : name,
# # # # # # #                         "offset": offset,
# # # # # # #                         "size"  : size,
# # # # # # #                     })
# # # # # # #         except Exception as e:
# # # # # # #             messagebox.showerror(
# # # # # # #                 "Error reading partitions.csv",
# # # # # # #                 f"Could not parse *partitions.csv*:\n{e}"
# # # # # # #             )
# # # # # # #             sys.exit(1)

# # # # # # #         if not self.spiffs_partitions:
# # # # # # #             messagebox.showerror(
# # # # # # #                 "No SPIFFS partition",
# # # # # # #                 "The *partitions.csv* file does not contain any SPIFFS partition entries."
# # # # # # #             )
# # # # # # #             sys.exit(1)

# # # # # # #         # Use the first partition as the default selection
# # # # # # #         self.current_spiffs_index = 0

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  GUI creation (modified layout)
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def create_widgets(self):
# # # # # # #         main_frame = ttk.Frame(self.root, padding="10")
# # # # # # #         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # #         self.root.columnconfigure(0, weight=1)
# # # # # # #         self.root.rowconfigure(0, weight=1)
# # # # # # #         main_frame.columnconfigure(1, weight=1)
# # # # # # #         main_frame.rowconfigure(3, weight=1)

# # # # # # #         # ---------------- Connection frame ----------------
# # # # # # #         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
# # # # # # #         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
# # # # # # #         conn_frame.columnconfigure(1, weight=1)

# # # # # # #         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # # # #         self.port_var = tk.StringVar()
# # # # # # #         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
# # # # # # #         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

# # # # # # #         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
# # # # # # #         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

# # # # # # #         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
# # # # # # #         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

# # # # # # #         # NOTE: ESP32 chip selector is hidden – the chip will be auto‑detected.

# # # # # # #         # ---------------- SPIFFS Configuration frame ----------------
# # # # # # #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# # # # # # #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# # # # # # #         # ----- Partition selector (wider) -----
# # # # # # #         ttk.Label(spiffs_frame, text="Partitions:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # # # #         self.partition_var = tk.StringVar()
# # # # # # #         self.partition_combo = ttk.Combobox(
# # # # # # #             spiffs_frame,
# # # # # # #             textvariable=self.partition_var,
# # # # # # #             state="readonly",
# # # # # # #             width=40,                # made wider as requested
# # # # # # #         )
# # # # # # #         partition_names = [
# # # # # # #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# # # # # # #         ]
# # # # # # #         self.partition_combo['values'] = partition_names
# # # # # # #         self.partition_combo.current(self.current_spiffs_index)
# # # # # # #         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
# # # # # # #         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)

# # # # # # #         # ----- Offset (read‑only) -----
# # # # # # #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# # # # # # #         self.offset_var = tk.StringVar()
# # # # # # #         self.offset_entry = ttk.Entry(
# # # # # # #             spiffs_frame,
# # # # # # #             textvariable=self.offset_var,
# # # # # # #             width=15,
# # # # # # #             state="readonly"
# # # # # # #         )
# # # # # # #         self.offset_entry.grid(row=0, column=3, padx=(0, 10))

# # # # # # #         # ----- Size (read‑only) -----
# # # # # # #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
# # # # # # #         self.size_var = tk.StringVar()
# # # # # # #         self.size_entry = ttk.Entry(
# # # # # # #             spiffs_frame,
# # # # # # #             textvariable=self.size_var,
# # # # # # #             width=15,
# # # # # # #             state="readonly"
# # # # # # #         )
# # # # # # #         self.size_entry.grid(row=0, column=5, padx=(0, 10))

# # # # # # #         # Initialise the displayed values for the default partition
# # # # # # #         self.update_spiffs_fields()

# # # # # # #         # Hide the now‑redundant "Save Config" button
# # # # # # #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# # # # # # #         self.save_config_btn.grid(row=0, column=6, padx=(10, 0))
# # # # # # #         self.save_config_btn.grid_remove()          # completely hide it

# # # # # # #         # ---------------- Action frame ----------------
# # # # # # #         action_frame = ttk.Frame(main_frame)
# # # # # # #         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

# # # # # # #         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
# # # # # # #         self.action_btn.grid(row=0, column=0, padx=(0, 10))
# # # # # # #         self.action_btn.config(state="disabled")

# # # # # # #         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
# # # # # # #         self.progress.grid(row=0, column=1, padx=(10, 0))

# # # # # # #         # ---------------- Content frame ----------------
# # # # # # #         content_frame = ttk.Frame(main_frame)
# # # # # # #         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # #         content_frame.columnconfigure(1, weight=2)
# # # # # # #         content_frame.rowconfigure(0, weight=1)

# # # # # # #         # File list
# # # # # # #         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
# # # # # # #         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
# # # # # # #         file_frame.columnconfigure(0, weight=1)
# # # # # # #         file_frame.rowconfigure(0, weight=1)

# # # # # # #         list_frame = ttk.Frame(file_frame)
# # # # # # #         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # #         list_frame.columnconfigure(0, weight=1)
# # # # # # #         list_frame.rowconfigure(0, weight=1)

# # # # # # #         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
# # # # # # #         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # #         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

# # # # # # #         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
# # # # # # #         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
# # # # # # #         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

# # # # # # #         file_btn_frame = ttk.Frame(file_frame)
# # # # # # #         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

# # # # # # #         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
# # # # # # #         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))

# # # # # # #         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
# # # # # # #         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
# # # # # # #         self.save_file_btn.config(state="disabled")

# # # # # # #         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
# # # # # # #         self.delete_file_btn.grid(row=0, column=2)
# # # # # # #         self.delete_file_btn.config(state="disabled")

# # # # # # #         # Editor
# # # # # # #         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
# # # # # # #         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # #         editor_frame.columnconfigure(0, weight=1)
# # # # # # #         editor_frame.rowconfigure(0, weight=1)

# # # # # # #         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
# # # # # # #         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # #         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

# # # # # # #         # Status bar
# # # # # # #         self.status_var = tk.StringVar(value="Ready")
# # # # # # #         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
# # # # # # #         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  Dependency / connection / scan helpers (unchanged)
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def check_dependencies(self):
# # # # # # #         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
# # # # # # #         missing_files = []
# # # # # # #         for file in required_files:
# # # # # # #             if not os.path.exists(file):
# # # # # # #                 missing_files.append(file)
# # # # # # #         if missing_files:
# # # # # # #             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
# # # # # # #             message += "\n\nPlease ensure these files are in the application directory."
# # # # # # #             messagebox.showerror("Missing Dependencies", message)
# # # # # # #             self.status_var.set("Missing dependencies")
# # # # # # #             return False
# # # # # # #         try:
# # # # # # #             import serial.tools.list_ports
# # # # # # #         except ImportError:
# # # # # # #             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
# # # # # # #             self.status_var.set("Missing pyserial")
# # # # # # #             return False
# # # # # # #         self.status_var.set("Dependencies OK")
# # # # # # #         return True

# # # # # # #     def scan_ports(self):
# # # # # # #         ports = serial.tools.list_ports.comports()
# # # # # # #         port_list = []
# # # # # # #         for port in ports:
# # # # # # #             description = port.description if port.description != 'n/a' else 'Unknown device'
# # # # # # #             port_display = f"{port.device} - {description}"
# # # # # # #             port_list.append(port_display)
# # # # # # #         self.port_combo['values'] = port_list
# # # # # # #         if self.config.get("last_port"):
# # # # # # #             for port_display in port_list:
# # # # # # #                 if port_display.startswith(self.config["last_port"] + " "):
# # # # # # #                     self.port_var.set(port_display)
# # # # # # #                     break
# # # # # # #         elif port_list:
# # # # # # #             self.port_var.set(port_list[0])
# # # # # # #         self.status_var.set(f"Found {len(port_list)} COM ports")

# # # # # # #     def get_selected_port(self):
# # # # # # #         port_display = self.port_var.get()
# # # # # # #         if not port_display:
# # # # # # #             return ""
# # # # # # #         return port_display.split(" - ")[0]

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  NEW:  on disconnect reset button to initial state + clear file list & editor
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def toggle_connection(self):
# # # # # # #         if not self.connected:
# # # # # # #             if not self.port_var.get():
# # # # # # #                 messagebox.showerror("Error", "Please select a COM port")
# # # # # # #                 return

# # # # # # #             # ---- auto‑detect ESP32 chip ----
# # # # # # #             chip, err = self.detect_chip()
# # # # # # #             if chip is None:
# # # # # # #                 messagebox.showerror("Connection Error", f"Could not detect ESP32 chip:\n{err}")
# # # # # # #                 return

# # # # # # #             # Store detected chip for later use
# # # # # # #             self.chip_var.set(chip)
# # # # # # #             self.config["esp32_chip"] = chip
# # # # # # #             self.save_config()

# # # # # # #             # Connection considered successful (esptool already succeeded)
# # # # # # #             self.connected = True
# # # # # # #             self.connect_btn.config(text="Disconnect")
# # # # # # #             self.action_btn.config(state="normal")
# # # # # # #             self.config["last_port"] = self.get_selected_port()
# # # # # # #             self.save_config()
# # # # # # #             self.status_var.set(f"Connected to {self.get_selected_port()} ({chip})")
# # # # # # #         else:
# # # # # # #             # ---------- disconnect ----------
# # # # # # #             self.connected = False
# # # # # # #             self.connect_btn.config(text="Connect")
# # # # # # #             self.action_btn.config(state="disabled")
# # # # # # #             # reset big button to initial download state
# # # # # # #             self.spiffs_downloaded = False
# # # # # # #             self.action_btn.config(text="Download SPIFFS")
# # # # # # #             # clear file list and editor
# # # # # # #             self.file_listbox.delete(0, tk.END)
# # # # # # #             self.content_editor.delete(1.0, tk.END)
# # # # # # #             self.current_files.clear()
# # # # # # #             self.selected_file = None
# # # # # # #             self.editor_modified = False
# # # # # # #             self.save_file_btn.config(state="disabled")
# # # # # # #             self.delete_file_btn.config(state="disabled")
# # # # # # #             self.status_var.set("Disconnected")

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  NEW:  ESP32 chip auto‑recognition
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def detect_chip(self):
# # # # # # #         """
# # # # # # #         Runs ``esptool.exe chip_id`` and parses its output.
# # # # # # #         Returns a tuple (chip_name, error_message). ``chip_name`` is one of
# # # # # # #         ``esp32``, ``esp32-s2``, ``esp32-s3``, ``esp32-c3``, ``esp32-c6``.
# # # # # # #         If detection fails, ``chip_name`` is ``None`` and ``error_message``
# # # # # # #         contains the reason.
# # # # # # #         """
# # # # # # #         cmd = [
# # # # # # #             "esptool.exe",
# # # # # # #             "--port", self.get_selected_port(),
# # # # # # #             "chip_id"
# # # # # # #         ]
# # # # # # #         try:
# # # # # # #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
# # # # # # #         except Exception as e:
# # # # # # #             return None, str(e)

# # # # # # #         if result.returncode != 0:
# # # # # # #             return None, result.stderr or "esptool error"

# # # # # # #         # Example line: "Chip is ESP32S3"
# # # # # # #         for line in result.stdout.splitlines():
# # # # # # #             if "Chip is" in line:
# # # # # # #                 name_part = line.split("Chip is")[-1].strip().lower()
# # # # # # #                 if "esp32s3" in name_part:
# # # # # # #                     return "esp32-s3", None
# # # # # # #                 if "esp32s2" in name_part:
# # # # # # #                     return "esp32-s2", None
# # # # # # #                 if "esp32c3" in name_part:
# # # # # # #                     return "esp32-c3", None
# # # # # # #                 if "esp32c6" in name_part:
# # # # # # #                     return "esp32-c6", None
# # # # # # #                 if "esp32" in name_part:
# # # # # # #                     return "esp32", None
# # # # # # #         return None, "Unable to parse chip type from esptool output"

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  NEW:  hide chip selector – kept only for internal use
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def on_chip_changed(self, event=None):
# # # # # # #         # Legacy placeholder – UI no longer exposes chip selection.
# # # # # # #         self.config["esp32_chip"] = self.chip_var.get()
# # # # # # #         self.save_config()

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  NEW:  Called when the user changes the selected partition
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def on_partition_selected(self, event=None):
# # # # # # #         """Update offset/size fields to reflect the newly selected partition."""
# # # # # # #         try:
# # # # # # #             self.current_spiffs_index = self.partition_combo.current()
# # # # # # #             self.update_spiffs_fields()
# # # # # # #         except Exception:
# # # # # # #             pass   # defensive – should never happen

# # # # # # #     def update_spiffs_fields(self):
# # # # # # #         """Write the offset and size of the currently selected partition to the UI."""
# # # # # # #         part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # # #         self.offset_var.set(self.format_value_for_display(part['offset']))
# # # # # # #         self.size_var.set(self.format_value_for_display(part['size']))

# # # # # # #     def save_spiffs_config(self):
# # # # # # #         # The configuration is now derived from partitions.csv, therefore the
# # # # # # #         # “Save Config” button is hidden.  This method only informs the user.
# # # # # # #         messagebox.showinfo(
# # # # # # #             "Info",
# # # # # # #             "SPIFFS offset and size are taken from *partitions.csv*.\n"
# # # # # # #             "To change them, edit that file and restart the application."
# # # # # # #         )

# # # # # # #     def perform_action(self):
# # # # # # #         if not self.connected:
# # # # # # #             messagebox.showerror("Error", "Not connected to ESP32")
# # # # # # #             return
# # # # # # #         if not self.spiffs_downloaded:
# # # # # # #             self.download_spiffs()
# # # # # # #         else:
# # # # # # #             # ---- ask for unsaved before upload ----
# # # # # # #             if not self.ask_unsaved_changes("uploading"):
# # # # # # #                 return
# # # # # # #             self.upload_spiffs()

# # # # # # #     def download_spiffs(self):
# # # # # # #         def download_worker():
# # # # # # #             try:
# # # # # # #                 self.progress.start()
# # # # # # #                 self.action_btn.config(state="disabled")
# # # # # # #                 self.status_var.set("Downloading SPIFFS...")

# # # # # # #                 # Use the values from the selected partition
# # # # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # # #                 offset_val = part['offset']
# # # # # # #                 size_val   = part['size']

# # # # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # # # #                 size_dec   = str(size_val)

# # # # # # #                 cmd = [
# # # # # # #                     "esptool.exe",
# # # # # # #                     "--chip", self.chip_var.get(),
# # # # # # #                     "--port", self.get_selected_port(),
# # # # # # #                     "--baud", self.config["baud_rate"],
# # # # # # #                     "read_flash", offset_hex, size_dec,
# # # # # # #                     "spiffs_dump.bin"
# # # # # # #                 ]
# # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # #                 if result.returncode != 0:
# # # # # # #                     raise Exception(f"Failed to read flash: {result.stderr}")

# # # # # # #                 data_dir = Path("data")
# # # # # # #                 data_dir.mkdir(exist_ok=True)
# # # # # # #                 for file in data_dir.glob("*"):
# # # # # # #                     if file.is_file():
# # # # # # #                         file.unlink()

# # # # # # #                 cmd = [
# # # # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # # # #                     "-u", "data",
# # # # # # #                     "spiffs_dump.bin"
# # # # # # #                 ]
# # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # #                 if result.returncode != 0:
# # # # # # #                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

# # # # # # #                 self.root.after(0, self.download_complete)

# # # # # # #             except Exception as e:
# # # # # # #                 error_msg = str(e)
# # # # # # #                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

# # # # # # #         thread = threading.Thread(target=download_worker)
# # # # # # #         thread.daemon = True
# # # # # # #         thread.start()

# # # # # # #     def download_complete(self):
# # # # # # #         self.progress.stop()
# # # # # # #         self.action_btn.config(state="normal", text="Upload SPIFFS")
# # # # # # #         self.spiffs_downloaded = True
# # # # # # #         self.status_var.set("SPIFFS downloaded successfully")
# # # # # # #         self.load_files()
# # # # # # #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# # # # # # #     def download_error(self, error_msg):
# # # # # # #         self.progress.stop()
# # # # # # #         self.action_btn.config(state="normal")
# # # # # # #         self.status_var.set("Download failed")
# # # # # # #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# # # # # # #     def upload_spiffs(self):
# # # # # # #         def upload_worker():
# # # # # # #             try:
# # # # # # #                 self.progress.start()
# # # # # # #                 self.action_btn.config(state="disabled")
# # # # # # #                 self.status_var.set("Creating SPIFFS image...")

# # # # # # #                 spiffs_dir = Path("spiffs")
# # # # # # #                 spiffs_dir.mkdir(exist_ok=True)

# # # # # # #                 # Use the values from the selected partition
# # # # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # # #                 size_val   = part['size']
# # # # # # #                 offset_val = part['offset']

# # # # # # #                 cmd = [
# # # # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # # # #                     "-c", "data",
# # # # # # #                     "-p", "256",
# # # # # # #                     "-b", "4096",
# # # # # # #                     "-s", str(size_val),
# # # # # # #                     "spiffs/data.bin"
# # # # # # #                 ]
# # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # #                 if result.returncode != 0:
# # # # # # #                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

# # # # # # #                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

# # # # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # # # #                 cmd = [
# # # # # # #                     "esptool.exe",
# # # # # # #                     "--chip", self.chip_var.get(),
# # # # # # #                     "--port", self.get_selected_port(),
# # # # # # #                     "--baud", self.config["baud_rate"],
# # # # # # #                     "--before", "default_reset",
# # # # # # #                     "--after", "hard_reset",
# # # # # # #                     "write_flash", "-z",
# # # # # # #                     "--flash_mode", "dio",
# # # # # # #                     "--flash_size", "detect",
# # # # # # #                     offset_hex, "spiffs/data.bin"
# # # # # # #                 ]
# # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # #                 if result.returncode != 0:
# # # # # # #                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

# # # # # # #                 self.root.after(0, self.upload_complete)

# # # # # # #             except Exception as e:
# # # # # # #                 error_msg = str(e)
# # # # # # #                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

# # # # # # #         thread = threading.Thread(target=upload_worker)
# # # # # # #         thread.daemon = True
# # # # # # #         thread.start()

# # # # # # #     def upload_complete(self):
# # # # # # #         self.progress.stop()
# # # # # # #         self.action_btn.config(state="normal")
# # # # # # #         self.status_var.set("SPIFFS uploaded successfully")
# # # # # # #         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

# # # # # # #     def upload_error(self, error_msg):
# # # # # # #         self.progress.stop()
# # # # # # #         self.action_btn.config(state="normal")
# # # # # # #         self.status_var.set("Upload failed")
# # # # # # #         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  File management (adjusted for editor_modified flag)
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def load_files(self):
# # # # # # #         self.current_files = {}
# # # # # # #         self.file_listbox.delete(0, tk.END)
# # # # # # #         data_dir = Path("data")
# # # # # # #         if not data_dir.exists():
# # # # # # #             return
# # # # # # #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# # # # # # #         for file_path in data_dir.iterdir():
# # # # # # #             if file_path.is_file() and file_path.suffix.lower() in text_extensions:
# # # # # # #                 try:
# # # # # # #                     with open(file_path, 'r', encoding='utf-8') as f:
# # # # # # #                         content = f.read()
# # # # # # #                     self.current_files[file_path.name] = content
# # # # # # #                     self.file_listbox.insert(tk.END, file_path.name)
# # # # # # #                 except Exception as e:
# # # # # # #                     print(f"Error reading {file_path}: {e}")
# # # # # # #         self.add_file_btn.config(state="normal")
# # # # # # #         if self.current_files:
# # # # # # #             self.file_listbox.selection_set(0)
# # # # # # #             self.on_file_select()

# # # # # # #     # NEW:  ask unsaved when changing file selection
# # # # # # #     def on_file_select(self, event=None):
# # # # # # #         selection = self.file_listbox.curselection()
# # # # # # #         if not selection:
# # # # # # #             return
# # # # # # #         if not self.ask_unsaved_changes("switching file"):
# # # # # # #             # restore previous selection
# # # # # # #             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
# # # # # # #             self.file_listbox.selection_clear(0, tk.END)
# # # # # # #             self.file_listbox.selection_set(idx)
# # # # # # #             return

# # # # # # #         filename = self.file_listbox.get(selection[0])
# # # # # # #         if filename in self.current_files:
# # # # # # #             self.selected_file = filename
# # # # # # #             self.content_editor.delete(1.0, tk.END)
# # # # # # #             self.content_editor.insert(1.0, self.current_files[filename])
# # # # # # #             self.editor_modified = False
# # # # # # #             self.save_file_btn.config(state="disabled")
# # # # # # #             self.delete_file_btn.config(state="normal")

# # # # # # #     def on_content_changed(self, event=None):
# # # # # # #         if self.selected_file:
# # # # # # #             self.editor_modified = True
# # # # # # #             self.save_file_btn.config(state="normal")

# # # # # # #     def save_current_file(self):
# # # # # # #         if not self.selected_file:
# # # # # # #             return
# # # # # # #         content = self.content_editor.get(1.0, tk.END).rstrip()
# # # # # # #         self.current_files[self.selected_file] = content
# # # # # # #         try:
# # # # # # #             data_dir = Path("data")
# # # # # # #             data_dir.mkdir(exist_ok=True)
# # # # # # #             file_path = data_dir / self.selected_file
# # # # # # #             with open(file_path, 'w', encoding='utf-8') as f:
# # # # # # #                 f.write(content)
# # # # # # #             self.editor_modified = False
# # # # # # #             self.save_file_btn.config(state="disabled")
# # # # # # #             self.status_var.set(f"Saved {self.selected_file}")
# # # # # # #         except Exception as e:
# # # # # # #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# # # # # # #     def add_file(self):
# # # # # # #         filename = tk.simpledialog.askstring("New File", "Enter filename:")
# # # # # # #         if not filename:
# # # # # # #             return
# # # # # # #         if not any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.ini', '.cfg', '.conf']):
# # # # # # #             filename += '.txt'
# # # # # # #         if filename in self.current_files:
# # # # # # #             messagebox.showerror("Error", "File already exists!")
# # # # # # #             return
# # # # # # #         self.current_files[filename] = ""
# # # # # # #         self.file_listbox.insert(tk.END, filename)
# # # # # # #         self.file_listbox.selection_clear(0, tk.END)
# # # # # # #         self.file_listbox.selection_set(tk.END)
# # # # # # #         self.on_file_select()

# # # # # # #     def delete_file(self):
# # # # # # #         if not self.selected_file:
# # # # # # #             return
# # # # # # #         result = messagebox.askyesno("Confirm Delete",
# # # # # # #                                    f"Are you sure you want to delete {self.selected_file}?")
# # # # # # #         if not result:
# # # # # # #             return
# # # # # # #         del self.current_files[self.selected_file]
# # # # # # #         selection = self.file_listbox.curselection()
# # # # # # #         if selection:
# # # # # # #             self.file_listbox.delete(selection[0])
# # # # # # #         try:
# # # # # # #             file_path = Path("data") / self.selected_file
# # # # # # #             if file_path.exists():
# # # # # # #                 file_path.unlink()
# # # # # # #         except Exception as e:
# # # # # # #             print(f"Error deleting file: {e}")
# # # # # # #         self.content_editor.delete(1.0, tk.END)
# # # # # # #         self.selected_file = None
# # # # # # #         self.editor_modified = False
# # # # # # #         self.save_file_btn.config(state="disabled")
# # # # # # #         self.delete_file_btn.config(state="disabled")

# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     #  Application close handler
# # # # # # #     # ------------------------------------------------------------------
# # # # # # #     def on_app_closing(self):
# # # # # # #         if self.ask_unsaved_changes("closing the application"):
# # # # # # #             self.root.destroy()


# # # # # # # # ----------------------------------------------------------------------
# # # # # # # #  Entry-point
# # # # # # # # ----------------------------------------------------------------------
# # # # # # # def main():
# # # # # # #     import tkinter.simpledialog
# # # # # # #     tk.simpledialog = tkinter.simpledialog
# # # # # # #     root = tk.Tk()
# # # # # # #     ESP32SPIFFSManager(root)
# # # # # # #     root.mainloop()


# # # # # # # if __name__ == "__main__":
# # # # # # #     main()


# # # # # # # # #!/usr/bin/env python3
# # # # # # # # """
# # # # # # # # ESP32 SPIFFS Manager GUI
# # # # # # # # Windows GUI application for managing ESP32 SPIFFS filesystem
# # # # # # # # """
# # # # # # # # VERSION = "v.021"  #  <── incremented on every program update

# # # # # # # # import os
# # # # # # # # import json
# # # # # # # # import subprocess
# # # # # # # # import sys
# # # # # # # # import tkinter as tk
# # # # # # # # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # # # # # # # import csv                      # ← new – to read partitions.csv
# # # # # # # # from pathlib import Path
# # # # # # # # import serial.tools.list_ports
# # # # # # # # import threading
# # # # # # # # from datetime import datetime

# # # # # # # # # ------------------------------------------------------------------
# # # # # # # # #  Main application class
# # # # # # # # # ------------------------------------------------------------------
# # # # # # # # class ESP32SPIFFSManager:
# # # # # # # #     def __init__(self, root):
# # # # # # # #         self.root = root
# # # # # # # #         self.root.title(f"ESP32 SPIFFS Manager {VERSION}")
# # # # # # # #         self.root.geometry("1000x700")
# # # # # # # #         self.root.minsize(800, 600)

# # # # # # # #         # Configuration
# # # # # # # #         self.config_file = "spiffs_config.json"
# # # # # # # #         self.load_config()

# # # # # # # #         # --------------------------------------------------------------
# # # # # # # #         #  Load SPIFFS partition information from *partitions.csv*
# # # # # # # #         # --------------------------------------------------------------
# # # # # # # #         self.spiffs_partitions = []          # list of dicts: {name, offset, size}
# # # # # # # #         self.current_spiffs_index = 0       # index inside self.spiffs_partitions
# # # # # # # #         self.load_partitions_csv()

# # # # # # # #         # State variables
# # # # # # # #         self.connected = False
# # # # # # # #         self.current_files = {}       # filename → content
# # # # # # # #         self.selected_file = None     # filename currently in editor
# # # # # # # #         self.spiffs_downloaded = False
# # # # # # # #         self.editor_modified = False  # True while editor has unsaved changes

# # # # # # # #         # Create GUI
# # # # # # # #         self.create_widgets()
# # # # # # # #         self.scan_ports()

# # # # # # # #         # Ask on unsaved changes when user closes window
# # # # # # # #         self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

# # # # # # # #         # Check required files on startup
# # # # # # # #         self.check_dependencies()

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  NEW:  generic “ask unsaved” helper  (returns True = proceed, False = abort)
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def ask_unsaved_changes(self, action: str = "switch file"):
# # # # # # # #         """Return True if the caller may continue, False if user chose Cancel."""
# # # # # # # #         if not self.editor_modified:
# # # # # # # #             return True

# # # # # # # #         answer = messagebox.askyesnocancel(
# # # # # # # #             "Unsaved changes",
# # # # # # # #             f'File "{self.selected_file}" has unsaved changes.\n\n'
# # # # # # # #             f'Save before {action}?',
# # # # # # # #             default=messagebox.YES
# # # # # # # #         )
# # # # # # # #         if answer is True:          # Save
# # # # # # # #             self.save_current_file()
# # # # # # # #             return True
# # # # # # # #         elif answer is False:       # Discard
# # # # # # # #             return True
# # # # # # # #         else:                       # Cancel
# # # # # # # #             return False

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  Small helpers (unchanged)
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     @staticmethod
# # # # # # # #     def _ensure_int(value):
# # # # # # # #         """Return int whether value is already int or decimal/hex string."""
# # # # # # # #         if isinstance(value, int):
# # # # # # # #             return value
# # # # # # # #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# # # # # # # #     def load_config(self):
# # # # # # # #         default_config = {
# # # # # # # #             "spiffs_offset": 6750208,  # 0x670000
# # # # # # # #             "spiffs_size": 1572864,    # 0x180000
# # # # # # # #             "esp32_chip": "esp32-s3",
# # # # # # # #             "baud_rate": "921600",
# # # # # # # #             "last_port": ""
# # # # # # # #         }
# # # # # # # #         try:
# # # # # # # #             if os.path.exists(self.config_file):
# # # # # # # #                 with open(self.config_file, 'r') as f:
# # # # # # # #                     self.config = json.load(f)
# # # # # # # #                 for key, value in default_config.items():
# # # # # # # #                     if key not in self.config:
# # # # # # # #                         self.config[key] = value
# # # # # # # #             else:
# # # # # # # #                 self.config = default_config
# # # # # # # #                 self.save_config()
# # # # # # # #         except Exception as e:
# # # # # # # #             print(f"Error loading config: {e}")
# # # # # # # #             self.config = default_config
# # # # # # # #             self.save_config()

# # # # # # # #     def save_config(self):
# # # # # # # #         try:
# # # # # # # #             with open(self.config_file, 'w') as f:
# # # # # # # #                 json.dump(self.config, f, indent=4)
# # # # # # # #         except Exception as e:
# # # # # # # #             print(f"Error saving config: {e}")

# # # # # # # #     def format_value_for_display(self, value):
# # # # # # # #         if isinstance(value, int):
# # # # # # # #             return f"0x{value:X}"
# # # # # # # #         return str(value)

# # # # # # # #     def parse_value_from_input(self, value_str):
# # # # # # # #         value_str = value_str.strip()
# # # # # # # #         if value_str.lower().startswith('0x'):
# # # # # # # #             return int(value_str, 16)
# # # # # # # #         else:
# # # # # # # #             return int(value_str)

# # # # # # # #     def validate_config_input(self, value_str, field_name):
# # # # # # # #         try:
# # # # # # # #             return self.parse_value_from_input(value_str)
# # # # # # # #         except ValueError:
# # # # # # # #             messagebox.showerror("Invalid Input",
# # # # # # # #                                f"Invalid {field_name} value: {value_str}\n"
# # # # # # # #                                f"Please enter a decimal number or hex value (0x...)")
# # # # # # # #             return None

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  NEW:  Read «partitions.csv» and extract all SPIFFS partitions
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def load_partitions_csv(self):
# # # # # # # #         """
# # # # # # # #         Looks for a file named *partitions.csv* in the same directory as this
# # # # # # # #         script.  It must contain a header (or not) with the columns:

# # # # # # # #             name, type, subtype, offset, size, flags

# # # # # # # #         All rows whose *subtype* is exactly ``spiffs`` (case‑insensitive) are
# # # # # # # #         collected.  For each such row we store the name, the integer offset
# # # # # # # #         and the integer size (hex strings are accepted).  If the file is not
# # # # # # # #         present or no SPIFFS partition is found, we abort with an error
# # # # # # # #         message.
# # # # # # # #         """
# # # # # # # #         csv_path = Path(__file__).parent / "partitions.csv"
# # # # # # # #         if not csv_path.is_file():
# # # # # # # #             messagebox.showerror(
# # # # # # # #                 "Missing file",
# # # # # # # #                 "Required file *partitions.csv* not found in the script folder.\n"
# # # # # # # #                 "The program cannot determine the SPIFFS offset/size.\n"
# # # # # # # #                 "Place a valid partitions.csv next to the script and restart."
# # # # # # # #             )
# # # # # # # #             sys.exit(1)

# # # # # # # #         try:
# # # # # # # #             with csv_path.open(newline='') as f:
# # # # # # # #                 reader = csv.reader(f)
# # # # # # # #                 for row in reader:
# # # # # # # #                     # skip empty lines / comments
# # # # # # # #                     if not row or row[0].strip().startswith('#'):
# # # # # # # #                         continue
# # # # # # # #                     # the CSV is usually: name,type,subtype,offset,size,flags
# # # # # # # #                     if len(row) < 5:
# # # # # # # #                         continue
# # # # # # # #                     name, _type, subtype, offset_str, size_str = (
# # # # # # # #                         row[0].strip(),
# # # # # # # #                         row[1].strip(),
# # # # # # # #                         row[2].strip(),
# # # # # # # #                         row[3].strip(),
# # # # # # # #                         row[4].strip(),
# # # # # # # #                     )
# # # # # # # #                     if subtype.lower() != 'spiffs':
# # # # # # # #                         continue
# # # # # # # #                     # Convert hex/dec strings to int
# # # # # # # #                     offset = int(offset_str, 0)
# # # # # # # #                     size   = int(size_str, 0)
# # # # # # # #                     self.spiffs_partitions.append({
# # # # # # # #                         "name"  : name,
# # # # # # # #                         "offset": offset,
# # # # # # # #                         "size"  : size,
# # # # # # # #                     })
# # # # # # # #         except Exception as e:
# # # # # # # #             messagebox.showerror(
# # # # # # # #                 "Error reading partitions.csv",
# # # # # # # #                 f"Could not parse *partitions.csv*:\n{e}"
# # # # # # # #             )
# # # # # # # #             sys.exit(1)

# # # # # # # #         if not self.spiffs_partitions:
# # # # # # # #             messagebox.showerror(
# # # # # # # #                 "No SPIFFS partition",
# # # # # # # #                 "The *partitions.csv* file does not contain any SPIFFS partition entries."
# # # # # # # #             )
# # # # # # # #             sys.exit(1)

# # # # # # # #         # Use the first partition as the default selection
# # # # # # # #         self.current_spiffs_index = 0

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  GUI creation (modified layout)
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def create_widgets(self):
# # # # # # # #         main_frame = ttk.Frame(self.root, padding="10")
# # # # # # # #         main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # # #         self.root.columnconfigure(0, weight=1)
# # # # # # # #         self.root.rowconfigure(0, weight=1)
# # # # # # # #         main_frame.columnconfigure(1, weight=1)
# # # # # # # #         main_frame.rowconfigure(3, weight=1)

# # # # # # # #         # ---------------- Connection frame ----------------
# # # # # # # #         conn_frame = ttk.LabelFrame(main_frame, text="Connection", padding="5")
# # # # # # # #         conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
# # # # # # # #         conn_frame.columnconfigure(1, weight=1)

# # # # # # # #         ttk.Label(conn_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # # # # #         self.port_var = tk.StringVar()
# # # # # # # #         self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, state="readonly", width=15)
# # # # # # # #         self.port_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

# # # # # # # #         self.scan_btn = ttk.Button(conn_frame, text="Scan", command=self.scan_ports, width=8)
# # # # # # # #         self.scan_btn.grid(row=0, column=2, padx=(0, 5))

# # # # # # # #         self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=12)
# # # # # # # #         self.connect_btn.grid(row=0, column=3, padx=(0, 10))

# # # # # # # #         ttk.Label(conn_frame, text="ESP32 Chip:").grid(row=0, column=4, sticky=tk.W, padx=(10, 5))
# # # # # # # #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))
# # # # # # # #         self.chip_combo = ttk.Combobox(conn_frame, textvariable=self.chip_var,
# # # # # # # #                                       values=["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6"],
# # # # # # # #                                       state="readonly", width=12)
# # # # # # # #         self.chip_combo.grid(row=0, column=5, sticky=tk.W)
# # # # # # # #         self.chip_combo.bind('<<ComboboxSelected>>', self.on_chip_changed)

# # # # # # # #         # ---------------- SPIFFS Configuration frame ----------------
# # # # # # # #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# # # # # # # #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# # # # # # # #         # ----- Partition selector (shown when >1 SPIFFS partition) -----
# # # # # # # #         ttk.Label(spiffs_frame, text="Partition:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# # # # # # # #         self.partition_var = tk.StringVar()
# # # # # # # #         self.partition_combo = ttk.Combobox(
# # # # # # # #             spiffs_frame,
# # # # # # # #             textvariable=self.partition_var,
# # # # # # # #             state="readonly",
# # # # # # # #             width=20,
# # # # # # # #         )
# # # # # # # #         # Fill combobox with names (or name+offset) of the discovered partitions
# # # # # # # #         partition_names = [
# # # # # # # #             f"{p['name']} (0x{p['offset']:X}, {p['size']} B)" for p in self.spiffs_partitions
# # # # # # # #         ]
# # # # # # # #         self.partition_combo['values'] = partition_names
# # # # # # # #         self.partition_combo.current(self.current_spiffs_index)
# # # # # # # #         self.partition_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
# # # # # # # #         self.partition_combo.bind('<<ComboboxSelected>>', self.on_partition_selected)

# # # # # # # #         # ----- Offset (read‑only) -----
# # # # # # # #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# # # # # # # #         self.offset_var = tk.StringVar()
# # # # # # # #         self.offset_entry = ttk.Entry(
# # # # # # # #             spiffs_frame,
# # # # # # # #             textvariable=self.offset_var,
# # # # # # # #             width=15,
# # # # # # # #             state="readonly"
# # # # # # # #         )
# # # # # # # #         self.offset_entry.grid(row=0, column=3, padx=(0, 10))

# # # # # # # #         # ----- Size (read‑only) -----
# # # # # # # #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
# # # # # # # #         self.size_var = tk.StringVar()
# # # # # # # #         self.size_entry = ttk.Entry(
# # # # # # # #             spiffs_frame,
# # # # # # # #             textvariable=self.size_var,
# # # # # # # #             width=15,
# # # # # # # #             state="readonly"
# # # # # # # #         )
# # # # # # # #         self.size_entry.grid(row=0, column=5, padx=(0, 10))

# # # # # # # #         # Initialise the displayed values for the default partition
# # # # # # # #         self.update_spiffs_fields()

# # # # # # # #         # The “Save Config” button is no longer useful because the values are now
# # # # # # # #         # taken from partitions.csv.  We keep the widget but disable it so the UI
# # # # # # # #         # layout stays unchanged.
# # # # # # # #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# # # # # # # #         self.save_config_btn.grid(row=0, column=6, padx=(10, 0))
# # # # # # # #         self.save_config_btn.state(['disabled'])

# # # # # # # #         # ---------------- Action frame ----------------
# # # # # # # #         action_frame = ttk.Frame(main_frame)
# # # # # # # #         action_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

# # # # # # # #         self.action_btn = ttk.Button(action_frame, text="Download SPIFFS", command=self.perform_action, width=20)
# # # # # # # #         self.action_btn.grid(row=0, column=0, padx=(0, 10))
# # # # # # # #         self.action_btn.config(state="disabled")

# # # # # # # #         self.progress = ttk.Progressbar(action_frame, mode='indeterminate', length=200)
# # # # # # # #         self.progress.grid(row=0, column=1, padx=(10, 0))

# # # # # # # #         # ---------------- Content frame ----------------
# # # # # # # #         content_frame = ttk.Frame(main_frame)
# # # # # # # #         content_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # # #         content_frame.columnconfigure(1, weight=2)
# # # # # # # #         content_frame.rowconfigure(0, weight=1)

# # # # # # # #         # File list
# # # # # # # #         file_frame = ttk.LabelFrame(content_frame, text="Files", padding="5")
# # # # # # # #         file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
# # # # # # # #         file_frame.columnconfigure(0, weight=1)
# # # # # # # #         file_frame.rowconfigure(0, weight=1)

# # # # # # # #         list_frame = ttk.Frame(file_frame)
# # # # # # # #         list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # # #         list_frame.columnconfigure(0, weight=1)
# # # # # # # #         list_frame.rowconfigure(0, weight=1)

# # # # # # # #         self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
# # # # # # # #         self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # # #         self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

# # # # # # # #         file_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
# # # # # # # #         file_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
# # # # # # # #         self.file_listbox.config(yscrollcommand=file_scrollbar.set)

# # # # # # # #         file_btn_frame = ttk.Frame(file_frame)
# # # # # # # #         file_btn_frame.grid(row=1, column=0, pady=(5, 0))

# # # # # # # #         self.add_file_btn = ttk.Button(file_btn_frame, text="Add File", command=self.add_file, width=10)
# # # # # # # #         self.add_file_btn.grid(row=0, column=0, padx=(0, 5))

# # # # # # # #         self.save_file_btn = ttk.Button(file_btn_frame, text="Save", command=self.save_current_file, width=10)
# # # # # # # #         self.save_file_btn.grid(row=0, column=1, padx=(0, 5))
# # # # # # # #         self.save_file_btn.config(state="disabled")

# # # # # # # #         self.delete_file_btn = ttk.Button(file_btn_frame, text="Delete", command=self.delete_file, width=10)
# # # # # # # #         self.delete_file_btn.grid(row=0, column=2)
# # # # # # # #         self.delete_file_btn.config(state="disabled")

# # # # # # # #         # Editor
# # # # # # # #         editor_frame = ttk.LabelFrame(content_frame, text="File Content", padding="5")
# # # # # # # #         editor_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # # #         editor_frame.columnconfigure(0, weight=1)
# # # # # # # #         editor_frame.rowconfigure(0, weight=1)

# # # # # # # #         self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
# # # # # # # #         self.content_editor.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
# # # # # # # #         self.content_editor.bind('<KeyRelease>', self.on_content_changed)

# # # # # # # #         # Status bar
# # # # # # # #         self.status_var = tk.StringVar(value="Ready")
# # # # # # # #         status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
# # # # # # # #         status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  Dependency / connection / scan helpers (unchanged)
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def check_dependencies(self):
# # # # # # # #         required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
# # # # # # # #         missing_files = []
# # # # # # # #         for file in required_files:
# # # # # # # #             if not os.path.exists(file):
# # # # # # # #                 missing_files.append(file)
# # # # # # # #         if missing_files:
# # # # # # # #             message = "Missing required files:\n" + "\n".join(f"- {file}" for file in missing_files)
# # # # # # # #             message += "\n\nPlease ensure these files are in the application directory."
# # # # # # # #             messagebox.showerror("Missing Dependencies", message)
# # # # # # # #             self.status_var.set("Missing dependencies")
# # # # # # # #             return False
# # # # # # # #         try:
# # # # # # # #             import serial.tools.list_ports
# # # # # # # #         except ImportError:
# # # # # # # #             messagebox.showerror("Missing Library", "pyserial library not found!\nPlease install it using: pip install pyserial")
# # # # # # # #             self.status_var.set("Missing pyserial")
# # # # # # # #             return False
# # # # # # # #         self.status_var.set("Dependencies OK")
# # # # # # # #         return True

# # # # # # # #     def scan_ports(self):
# # # # # # # #         ports = serial.tools.list_ports.comports()
# # # # # # # #         port_list = []
# # # # # # # #         for port in ports:
# # # # # # # #             description = port.description if port.description != 'n/a' else 'Unknown device'
# # # # # # # #             port_display = f"{port.device} - {description}"
# # # # # # # #             port_list.append(port_display)
# # # # # # # #         self.port_combo['values'] = port_list
# # # # # # # #         if self.config.get("last_port"):
# # # # # # # #             for port_display in port_list:
# # # # # # # #                 if port_display.startswith(self.config["last_port"] + " "):
# # # # # # # #                     self.port_var.set(port_display)
# # # # # # # #                     break
# # # # # # # #         elif port_list:
# # # # # # # #             self.port_var.set(port_list[0])
# # # # # # # #         self.status_var.set(f"Found {len(port_list)} COM ports")

# # # # # # # #     def get_selected_port(self):
# # # # # # # #         port_display = self.port_var.get()
# # # # # # # #         if not port_display:
# # # # # # # #             return ""
# # # # # # # #         return port_display.split(" - ")[0]

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  NEW:  on disconnect reset button to initial state + clear file list & editor
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def toggle_connection(self):
# # # # # # # #         if not self.connected:
# # # # # # # #             if not self.port_var.get():
# # # # # # # #                 messagebox.showerror("Error", "Please select a COM port")
# # # # # # # #                 return
# # # # # # # #             if self.test_connection():
# # # # # # # #                 self.connected = True
# # # # # # # #                 self.connect_btn.config(text="Disconnect")
# # # # # # # #                 self.action_btn.config(state="normal")
# # # # # # # #                 self.config["last_port"] = self.get_selected_port()
# # # # # # # #                 self.save_config()
# # # # # # # #                 self.status_var.set(f"Connected to {self.get_selected_port()}")
# # # # # # # #             else:
# # # # # # # #                 messagebox.showerror("Connection Error", "Failed to connect to ESP32")
# # # # # # # #         else:
# # # # # # # #             # ---------- disconnect ----------
# # # # # # # #             self.connected = False
# # # # # # # #             self.connect_btn.config(text="Connect")
# # # # # # # #             self.action_btn.config(state="disabled")
# # # # # # # #             # reset big button to initial download state
# # # # # # # #             self.spiffs_downloaded = False
# # # # # # # #             self.action_btn.config(text="Download SPIFFS")
# # # # # # # #             # clear file list and editor
# # # # # # # #             self.file_listbox.delete(0, tk.END)
# # # # # # # #             self.content_editor.delete(1.0, tk.END)
# # # # # # # #             self.current_files.clear()
# # # # # # # #             self.selected_file = None
# # # # # # # #             self.editor_modified = False
# # # # # # # #             self.save_file_btn.config(state="disabled")
# # # # # # # #             self.delete_file_btn.config(state="disabled")
# # # # # # # #             self.status_var.set("Disconnected")

# # # # # # # #     def test_connection(self):
# # # # # # # #         try:
# # # # # # # #             cmd = [
# # # # # # # #                 "esptool.exe",
# # # # # # # #                 "--chip", self.chip_var.get(),
# # # # # # # #                 "--port", self.get_selected_port(),
# # # # # # # #                 "--baud", self.config["baud_rate"],
# # # # # # # #                 "chip_id"
# # # # # # # #             ]
# # # # # # # #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
# # # # # # # #             return result.returncode == 0
# # # # # # # #         except Exception as e:
# # # # # # # #             print(f"Connection test failed: {e}")
# # # # # # # #             return False

# # # # # # # #     def on_chip_changed(self, event=None):
# # # # # # # #         self.config["esp32_chip"] = self.chip_var.get()
# # # # # # # #         self.save_config()

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  NEW:  Called when the user changes the selected partition
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def on_partition_selected(self, event=None):
# # # # # # # #         """Update offset/size fields to reflect the newly selected partition."""
# # # # # # # #         try:
# # # # # # # #             self.current_spiffs_index = self.partition_combo.current()
# # # # # # # #             self.update_spiffs_fields()
# # # # # # # #         except Exception:
# # # # # # # #             pass   # defensive – should never happen

# # # # # # # #     def update_spiffs_fields(self):
# # # # # # # #         """Write the offset and size of the currently selected partition to the UI."""
# # # # # # # #         part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # # # #         self.offset_var.set(self.format_value_for_display(part['offset']))
# # # # # # # #         self.size_var.set(self.format_value_for_display(part['size']))

# # # # # # # #     def save_spiffs_config(self):
# # # # # # # #         # The configuration is now derived from partitions.csv, therefore the
# # # # # # # #         # “Save Config” button is disabled.  This method is kept only for legacy
# # # # # # # #         # compatibility – it simply informs the user.
# # # # # # # #         messagebox.showinfo(
# # # # # # # #             "Info",
# # # # # # # #             "SPIFFS offset and size are taken from *partitions.csv*.\n"
# # # # # # # #             "To change them, edit that file and restart the application."
# # # # # # # #         )

# # # # # # # #     def perform_action(self):
# # # # # # # #         if not self.connected:
# # # # # # # #             messagebox.showerror("Error", "Not connected to ESP32")
# # # # # # # #             return
# # # # # # # #         if not self.spiffs_downloaded:
# # # # # # # #             self.download_spiffs()
# # # # # # # #         else:
# # # # # # # #             # ---- ask for unsaved before upload ----
# # # # # # # #             if not self.ask_unsaved_changes("uploading"):
# # # # # # # #                 return
# # # # # # # #             self.upload_spiffs()

# # # # # # # #     def download_spiffs(self):
# # # # # # # #         def download_worker():
# # # # # # # #             try:
# # # # # # # #                 self.progress.start()
# # # # # # # #                 self.action_btn.config(state="disabled")
# # # # # # # #                 self.status_var.set("Downloading SPIFFS...")

# # # # # # # #                 # Use the values from the selected partition
# # # # # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # # # #                 offset_val = part['offset']
# # # # # # # #                 size_val   = part['size']

# # # # # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # # # # #                 size_dec   = str(size_val)

# # # # # # # #                 cmd = [
# # # # # # # #                     "esptool.exe",
# # # # # # # #                     "--chip", self.chip_var.get(),
# # # # # # # #                     "--port", self.get_selected_port(),
# # # # # # # #                     "--baud", self.config["baud_rate"],
# # # # # # # #                     "read_flash", offset_hex, size_dec,
# # # # # # # #                     "spiffs_dump.bin"
# # # # # # # #                 ]
# # # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # # #                 if result.returncode != 0:
# # # # # # # #                     raise Exception(f"Failed to read flash: {result.stderr}")

# # # # # # # #                 data_dir = Path("data")
# # # # # # # #                 data_dir.mkdir(exist_ok=True)
# # # # # # # #                 for file in data_dir.glob("*"):
# # # # # # # #                     if file.is_file():
# # # # # # # #                         file.unlink()

# # # # # # # #                 cmd = [
# # # # # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # # # # #                     "-u", "data",
# # # # # # # #                     "spiffs_dump.bin"
# # # # # # # #                 ]
# # # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # # #                 if result.returncode != 0:
# # # # # # # #                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

# # # # # # # #                 self.root.after(0, self.download_complete)

# # # # # # # #             except Exception as e:
# # # # # # # #                 error_msg = str(e)
# # # # # # # #                 self.root.after(0, lambda msg=error_msg: self.download_error(msg))

# # # # # # # #         thread = threading.Thread(target=download_worker)
# # # # # # # #         thread.daemon = True
# # # # # # # #         thread.start()

# # # # # # # #     def download_complete(self):
# # # # # # # #         self.progress.stop()
# # # # # # # #         self.action_btn.config(state="normal", text="Upload SPIFFS")
# # # # # # # #         self.spiffs_downloaded = True
# # # # # # # #         self.status_var.set("SPIFFS downloaded successfully")
# # # # # # # #         self.load_files()
# # # # # # # #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# # # # # # # #     def download_error(self, error_msg):
# # # # # # # #         self.progress.stop()
# # # # # # # #         self.action_btn.config(state="normal")
# # # # # # # #         self.status_var.set("Download failed")
# # # # # # # #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# # # # # # # #     def upload_spiffs(self):
# # # # # # # #         def upload_worker():
# # # # # # # #             try:
# # # # # # # #                 self.progress.start()
# # # # # # # #                 self.action_btn.config(state="disabled")
# # # # # # # #                 self.status_var.set("Creating SPIFFS image...")

# # # # # # # #                 spiffs_dir = Path("spiffs")
# # # # # # # #                 spiffs_dir.mkdir(exist_ok=True)

# # # # # # # #                 # Use the values from the selected partition
# # # # # # # #                 part = self.spiffs_partitions[self.current_spiffs_index]
# # # # # # # #                 size_val   = part['size']
# # # # # # # #                 offset_val = part['offset']

# # # # # # # #                 cmd = [
# # # # # # # #                     "mkspiffs_espressif32_arduino.exe",
# # # # # # # #                     "-c", "data",
# # # # # # # #                     "-p", "256",
# # # # # # # #                     "-b", "4096",
# # # # # # # #                     "-s", str(size_val),
# # # # # # # #                     "spiffs/data.bin"
# # # # # # # #                 ]
# # # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # # #                 if result.returncode != 0:
# # # # # # # #                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

# # # # # # # #                 self.root.after(0, lambda: self.status_var.set("Uploading to ESP32..."))

# # # # # # # #                 offset_hex = f"0x{offset_val:X}"
# # # # # # # #                 cmd = [
# # # # # # # #                     "esptool.exe",
# # # # # # # #                     "--chip", self.chip_var.get(),
# # # # # # # #                     "--port", self.get_selected_port(),
# # # # # # # #                     "--baud", self.config["baud_rate"],
# # # # # # # #                     "--before", "default_reset",
# # # # # # # #                     "--after", "hard_reset",
# # # # # # # #                     "write_flash", "-z",
# # # # # # # #                     "--flash_mode", "dio",
# # # # # # # #                     "--flash_size", "detect",
# # # # # # # #                     offset_hex, "spiffs/data.bin"
# # # # # # # #                 ]
# # # # # # # #                 result = subprocess.run(cmd, capture_output=True, text=True)
# # # # # # # #                 if result.returncode != 0:
# # # # # # # #                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

# # # # # # # #                 self.root.after(0, self.upload_complete)

# # # # # # # #             except Exception as e:
# # # # # # # #                 error_msg = str(e)
# # # # # # # #                 self.root.after(0, lambda msg=error_msg: self.upload_error(msg))

# # # # # # # #         thread = threading.Thread(target=upload_worker)
# # # # # # # #         thread.daemon = True
# # # # # # # #         thread.start()

# # # # # # # #     def upload_complete(self):
# # # # # # # #         self.progress.stop()
# # # # # # # #         self.action_btn.config(state="normal")
# # # # # # # #         self.status_var.set("SPIFFS uploaded successfully")
# # # # # # # #         messagebox.showinfo("Success", "SPIFFS uploaded successfully!")

# # # # # # # #     def upload_error(self, error_msg):
# # # # # # # #         self.progress.stop()
# # # # # # # #         self.action_btn.config(state="normal")
# # # # # # # #         self.status_var.set("Upload failed")
# # # # # # # #         messagebox.showerror("Upload Error", f"Failed to upload SPIFFS:\n{error_msg}")

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  File management (adjusted for editor_modified flag)
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def load_files(self):
# # # # # # # #         self.current_files = {}
# # # # # # # #         self.file_listbox.delete(0, tk.END)
# # # # # # # #         data_dir = Path("data")
# # # # # # # #         if not data_dir.exists():
# # # # # # # #             return
# # # # # # # #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# # # # # # # #         for file_path in data_dir.iterdir():
# # # # # # # #             if file_path.is_file() and file_path.suffix.lower() in text_extensions:
# # # # # # # #                 try:
# # # # # # # #                     with open(file_path, 'r', encoding='utf-8') as f:
# # # # # # # #                         content = f.read()
# # # # # # # #                     self.current_files[file_path.name] = content
# # # # # # # #                     self.file_listbox.insert(tk.END, file_path.name)
# # # # # # # #                 except Exception as e:
# # # # # # # #                     print(f"Error reading {file_path}: {e}")
# # # # # # # #         self.add_file_btn.config(state="normal")
# # # # # # # #         if self.current_files:
# # # # # # # #             self.file_listbox.selection_set(0)
# # # # # # # #             self.on_file_select()

# # # # # # # #     # NEW:  ask unsaved when changing file selection
# # # # # # # #     def on_file_select(self, event=None):
# # # # # # # #         selection = self.file_listbox.curselection()
# # # # # # # #         if not selection:
# # # # # # # #             return
# # # # # # # #         if not self.ask_unsaved_changes("switching file"):
# # # # # # # #             # restore previous selection
# # # # # # # #             idx = list(self.current_files.keys()).index(self.selected_file) if self.selected_file else 0
# # # # # # # #             self.file_listbox.selection_clear(0, tk.END)
# # # # # # # #             self.file_listbox.selection_set(idx)
# # # # # # # #             return

# # # # # # # #         filename = self.file_listbox.get(selection[0])
# # # # # # # #         if filename in self.current_files:
# # # # # # # #             self.selected_file = filename
# # # # # # # #             self.content_editor.delete(1.0, tk.END)
# # # # # # # #             self.content_editor.insert(1.0, self.current_files[filename])
# # # # # # # #             self.editor_modified = False
# # # # # # # #             self.save_file_btn.config(state="disabled")
# # # # # # # #             self.delete_file_btn.config(state="normal")

# # # # # # # #     def on_content_changed(self, event=None):
# # # # # # # #         if self.selected_file:
# # # # # # # #             self.editor_modified = True
# # # # # # # #             self.save_file_btn.config(state="normal")

# # # # # # # #     def save_current_file(self):
# # # # # # # #         if not self.selected_file:
# # # # # # # #             return
# # # # # # # #         content = self.content_editor.get(1.0, tk.END).rstrip()
# # # # # # # #         self.current_files[self.selected_file] = content
# # # # # # # #         try:
# # # # # # # #             data_dir = Path("data")
# # # # # # # #             data_dir.mkdir(exist_ok=True)
# # # # # # # #             file_path = data_dir / self.selected_file
# # # # # # # #             with open(file_path, 'w', encoding='utf-8') as f:
# # # # # # # #                 f.write(content)
# # # # # # # #             self.editor_modified = False
# # # # # # # #             self.save_file_btn.config(state="disabled")
# # # # # # # #             self.status_var.set(f"Saved {self.selected_file}")
# # # # # # # #         except Exception as e:
# # # # # # # #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# # # # # # # #     def add_file(self):
# # # # # # # #         filename = tk.simpledialog.askstring("New File", "Enter filename:")
# # # # # # # #         if not filename:
# # # # # # # #             return
# # # # # # # #         if not any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.ini', '.cfg', '.conf']):
# # # # # # # #             filename += '.txt'
# # # # # # # #         if filename in self.current_files:
# # # # # # # #             messagebox.showerror("Error", "File already exists!")
# # # # # # # #             return
# # # # # # # #         self.current_files[filename] = ""
# # # # # # # #         self.file_listbox.insert(tk.END, filename)
# # # # # # # #         self.file_listbox.selection_clear(0, tk.END)
# # # # # # # #         self.file_listbox.selection_set(tk.END)
# # # # # # # #         self.on_file_select()

# # # # # # # #     def delete_file(self):
# # # # # # # #         if not self.selected_file:
# # # # # # # #             return
# # # # # # # #         result = messagebox.askyesno("Confirm Delete",
# # # # # # # #                                    f"Are you sure you want to delete {self.selected_file}?")
# # # # # # # #         if not result:
# # # # # # # #             return
# # # # # # # #         del self.current_files[self.selected_file]
# # # # # # # #         selection = self.file_listbox.curselection()
# # # # # # # #         if selection:
# # # # # # # #             self.file_listbox.delete(selection[0])
# # # # # # # #         try:
# # # # # # # #             file_path = Path("data") / self.selected_file
# # # # # # # #             if file_path.exists():
# # # # # # # #                 file_path.unlink()
# # # # # # # #         except Exception as e:
# # # # # # # #             print(f"Error deleting file: {e}")
# # # # # # # #         self.content_editor.delete(1.0, tk.END)
# # # # # # # #         self.selected_file = None
# # # # # # # #         self.editor_modified = False
# # # # # # # #         self.save_file_btn.config(state="disabled")
# # # # # # # #         self.delete_file_btn.config(state="disabled")

# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     #  Application close handler
# # # # # # # #     # ------------------------------------------------------------------
# # # # # # # #     def on_app_closing(self):
# # # # # # # #         if self.ask_unsaved_changes("closing the application"):
# # # # # # # #             self.root.destroy()


# # # # # # # # # ----------------------------------------------------------------------
# # # # # # # # #  Entry-point
# # # # # # # # # ----------------------------------------------------------------------
# # # # # # # # def main():
# # # # # # # #     import tkinter.simpledialog
# # # # # # # #     tk.simpledialog = tkinter.simpledialog
# # # # # # # #     root = tk.Tk()
# # # # # # # #     ESP32SPIFFSManager(root)
# # # # # # # #     root.mainloop()


# # # # # # # # if __name__ == "__main__":
# # # # # # # #     main()
