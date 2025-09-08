#!/usr/bin/env python3
"""
ESP32 SPIFFS Manager GUI
Windows GUI application for managing ESP32 SPIFFS filesystem
"""
VERSION = "v.017"  #  <── incremented on every program update

import os
import json
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
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

        # State variables
        self.connected = False
        self.current_files = {}       # filename → content
        self.selected_file = None     # filename currently in editor
        self.spiffs_downloaded = False
        self.editor_modified = False  # True while editor has unsaved changes

        # Create GUI
        self.create_widgets()
        self.scan_ports()

        # Ask on unsaved changes when user closes window
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)

        # Check required files on startup
        self.check_dependencies()

    # ------------------------------------------------------------------
    #  NEW:  generic “ask unsaved” helper  (returns True = proceed, False = abort)
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
    #  GUI creation (unchanged layout)
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

        ttk.Label(conn_frame, text="ESP32 Chip:").grid(row=0, column=4, sticky=tk.W, padx=(10, 5))
        self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))
        self.chip_combo = ttk.Combobox(conn_frame, textvariable=self.chip_var,
                                      values=["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6"],
                                      state="readonly", width=12)
        self.chip_combo.grid(row=0, column=5, sticky=tk.W)
        self.chip_combo.bind('<<ComboboxSelected>>', self.on_chip_changed)

        # ---------------- SPIFFS Configuration frame ----------------
        spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
        spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.offset_var = tk.StringVar(value=self.format_value_for_display(self.config.get("spiffs_offset", 6750208)))
        self.offset_entry = ttk.Entry(spiffs_frame, textvariable=self.offset_var, width=15)
        self.offset_entry.grid(row=0, column=1, padx=(0, 10))

        ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.size_var = tk.StringVar(value=self.format_value_for_display(self.config.get("spiffs_size", 1572864)))
        self.size_entry = ttk.Entry(spiffs_frame, textvariable=self.size_var, width=15)
        self.size_entry.grid(row=0, column=3, padx=(0, 10))

        self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
        self.save_config_btn.grid(row=0, column=4, padx=(10, 0))

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

        self.content_editor = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, width=50, height=20)
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
            if self.test_connection():
                self.connected = True
                self.connect_btn.config(text="Disconnect")
                self.action_btn.config(state="normal")
                self.config["last_port"] = self.get_selected_port()
                self.save_config()
                self.status_var.set(f"Connected to {self.get_selected_port()}")
            else:
                messagebox.showerror("Connection Error", "Failed to connect to ESP32")
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
            self.status_var.set("Disconnected")

    def test_connection(self):
        try:
            cmd = [
                "esptool.exe",
                "--chip", self.chip_var.get(),
                "--port", self.get_selected_port(),
                "--baud", self.config["baud_rate"],
                "chip_id"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    def on_chip_changed(self, event=None):
        self.config["esp32_chip"] = self.chip_var.get()
        self.save_config()

    def save_spiffs_config(self):
        offset_value = self.validate_config_input(self.offset_var.get(), "offset")
        if offset_value is None:
            return
        size_value = self.validate_config_input(self.size_var.get(), "size")
        if size_value is None:
            return
        self.config["spiffs_offset"] = offset_value
        self.config["spiffs_size"] = size_value
        self.save_config()
        self.offset_var.set(self.format_value_for_display(offset_value))
        self.size_var.set(self.format_value_for_display(size_value))
        messagebox.showinfo("Config Saved", "SPIFFS configuration saved successfully!")
        self.status_var.set(f"Config saved: Offset={self.format_value_for_display(offset_value)}, Size={self.format_value_for_display(size_value)}")

    def perform_action(self):
        if not self.connected:
            messagebox.showerror("Error", "Not connected to ESP32")
            return
        if not self.spiffs_downloaded:
            self.download_spiffs()
        else:
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

                offset_val = self._ensure_int(self.config['spiffs_offset'])
                size_val   = self._ensure_int(self.config['spiffs_size'])

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
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Failed to read flash: {result.stderr}")

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
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

                self.root.after(0, self.download_complete)

            except Exception as e:
                error_msg = str(e)
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

                size_val   = self._ensure_int(self.config['spiffs_size'])
                offset_val = self._ensure_int(self.config['spiffs_offset'])

                cmd = [
                    "mkspiffs_espressif32_arduino.exe",
                    "-c", "data",
                    "-p", "256",
                    "-b", "4096",
                    "-s", str(size_val),
                    "spiffs/data.bin"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

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
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

                self.root.after(0, self.upload_complete)

            except Exception as e:
                error_msg = str(e)
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
    #  File management (adjusted for editor_modified flag)
    # ------------------------------------------------------------------
    def load_files(self):
        self.current_files = {}
        self.file_listbox.delete(0, tk.END)
        data_dir = Path("data")
        if not data_dir.exists():
            return
        text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
        for file_path in data_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in text_extensions:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.current_files[file_path.name] = content
                    self.file_listbox.insert(tk.END, file_path.name)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
        self.add_file_btn.config(state="normal")
        if self.current_files:
            self.file_listbox.selection_set(0)
            self.on_file_select()

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
        if filename in self.current_files:
            self.selected_file = filename
            self.content_editor.delete(1.0, tk.END)
            self.content_editor.insert(1.0, self.current_files[filename])
            self.editor_modified = False
            self.save_file_btn.config(state="disabled")
            self.delete_file_btn.config(state="normal")

    def on_content_changed(self, event=None):
        if self.selected_file:
            self.editor_modified = True
            self.save_file_btn.config(state="normal")

    def save_current_file(self):
        if not self.selected_file:
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

    def add_file(self):
        filename = tk.simpledialog.askstring("New File", "Enter filename:")
        if not filename:
            return
        if not any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.ini', '.cfg', '.conf']):
            filename += '.txt'
        if filename in self.current_files:
            messagebox.showerror("Error", "File already exists!")
            return
        self.current_files[filename] = ""
        self.file_listbox.insert(tk.END, filename)
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
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            print(f"Error deleting file: {e}")
        self.content_editor.delete(1.0, tk.END)
        self.selected_file = None
        self.editor_modified = False
        self.save_file_btn.config(state="disabled")
        self.delete_file_btn.config(state="disabled")

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
# VERSION = "v.016"  #  <── incremented on every program update

# import os
# import json
# import subprocess
# import sys
# import tkinter as tk
# from tkinter import ttk, messagebox, scrolledtext, filedialog
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

#         # State variables
#         self.connected = False
#         self.current_files = {}       # filename → content
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
#     #  NEW:  generic “ask unsaved” helper  (returns True = proceed, False = abort)
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
#     #  GUI creation (unchanged layout)
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

#         ttk.Label(conn_frame, text="ESP32 Chip:").grid(row=0, column=4, sticky=tk.W, padx=(10, 5))
#         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))
#         self.chip_combo = ttk.Combobox(conn_frame, textvariable=self.chip_var,
#                                       values=["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6"],
#                                       state="readonly", width=12)
#         self.chip_combo.grid(row=0, column=5, sticky=tk.W)
#         self.chip_combo.bind('<<ComboboxSelected>>', self.on_chip_changed)

#         # ---------------- SPIFFS Configuration frame ----------------
#         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
#         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

#         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
#         self.offset_var = tk.StringVar(value=self.format_value_for_display(self.config.get("spiffs_offset", 6750208)))
#         self.offset_entry = ttk.Entry(spiffs_frame, textvariable=self.offset_var, width=15)
#         self.offset_entry.grid(row=0, column=1, padx=(0, 10))

#         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
#         self.size_var = tk.StringVar(value=self.format_value_for_display(self.config.get("spiffs_size", 1572864)))
#         self.size_entry = ttk.Entry(spiffs_frame, textvariable=self.size_var, width=15)
#         self.size_entry.grid(row=0, column=3, padx=(0, 10))

#         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
#         self.save_config_btn.grid(row=0, column=4, padx=(10, 0))

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
#     #  NEW:  on disconnect reset button to initial state
#     # ------------------------------------------------------------------
#     def toggle_connection(self):
#         if not self.connected:
#             if not self.port_var.get():
#                 messagebox.showerror("Error", "Please select a COM port")
#                 return
#             if self.test_connection():
#                 self.connected = True
#                 self.connect_btn.config(text="Disconnect")
#                 self.action_btn.config(state="normal")
#                 self.config["last_port"] = self.get_selected_port()
#                 self.save_config()
#                 self.status_var.set(f"Connected to {self.get_selected_port()}")
#             else:
#                 messagebox.showerror("Connection Error", "Failed to connect to ESP32")
#         else:
#             # ---------- disconnect ----------
#             self.connected = False
#             self.connect_btn.config(text="Connect")
#             self.action_btn.config(state="disabled")
#             # reset big button to initial download state
#             self.spiffs_downloaded = False
#             self.action_btn.config(text="Download SPIFFS")
#             self.status_var.set("Disconnected")

#     def test_connection(self):
#         try:
#             cmd = [
#                 "esptool.exe",
#                 "--chip", self.chip_var.get(),
#                 "--port", self.get_selected_port(),
#                 "--baud", self.config["baud_rate"],
#                 "chip_id"
#             ]
#             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
#             return result.returncode == 0
#         except Exception as e:
#             print(f"Connection test failed: {e}")
#             return False

#     def on_chip_changed(self, event=None):
#         self.config["esp32_chip"] = self.chip_var.get()
#         self.save_config()

#     def save_spiffs_config(self):
#         offset_value = self.validate_config_input(self.offset_var.get(), "offset")
#         if offset_value is None:
#             return
#         size_value = self.validate_config_input(self.size_var.get(), "size")
#         if size_value is None:
#             return
#         self.config["spiffs_offset"] = offset_value
#         self.config["spiffs_size"] = size_value
#         self.save_config()
#         self.offset_var.set(self.format_value_for_display(offset_value))
#         self.size_var.set(self.format_value_for_display(size_value))
#         messagebox.showinfo("Config Saved", "SPIFFS configuration saved successfully!")
#         self.status_var.set(f"Config saved: Offset={self.format_value_for_display(offset_value)}, Size={self.format_value_for_display(size_value)}")

#     # ------------------------------------------------------------------
#     #  Upload / Download workers (unchanged except for _ensure_int)
#     # ------------------------------------------------------------------
#     def perform_action(self):
#         if not self.connected:
#             messagebox.showerror("Error", "Not connected to ESP32")
#             return
#         if not self.spiffs_downloaded:
#             self.download_spiffs()
#         else:
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

#                 offset_val = self._ensure_int(self.config['spiffs_offset'])
#                 size_val   = self._ensure_int(self.config['spiffs_size'])

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
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 if result.returncode != 0:
#                     raise Exception(f"Failed to read flash: {result.stderr}")

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
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 if result.returncode != 0:
#                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

#                 self.root.after(0, self.download_complete)

#             except Exception as e:
#                 error_msg = str(e)
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

#                 size_val   = self._ensure_int(self.config['spiffs_size'])
#                 offset_val = self._ensure_int(self.config['spiffs_offset'])

#                 cmd = [
#                     "mkspiffs_espressif32_arduino.exe",
#                     "-c", "data",
#                     "-p", "256",
#                     "-b", "4096",
#                     "-s", str(size_val),
#                     "spiffs/data.bin"
#                 ]
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 if result.returncode != 0:
#                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

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
#                 result = subprocess.run(cmd, capture_output=True, text=True)
#                 if result.returncode != 0:
#                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

#                 self.root.after(0, self.upload_complete)

#             except Exception as e:
#                 error_msg = str(e)
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
#     #  File management (adjusted for editor_modified flag)
#     # ------------------------------------------------------------------
#     def load_files(self):
#         self.current_files = {}
#         self.file_listbox.delete(0, tk.END)
#         data_dir = Path("data")
#         if not data_dir.exists():
#             return
#         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
#         for file_path in data_dir.iterdir():
#             if file_path.is_file() and file_path.suffix.lower() in text_extensions:
#                 try:
#                     with open(file_path, 'r', encoding='utf-8') as f:
#                         content = f.read()
#                     self.current_files[file_path.name] = content
#                     self.file_listbox.insert(tk.END, file_path.name)
#                 except Exception as e:
#                     print(f"Error reading {file_path}: {e}")
#         self.add_file_btn.config(state="normal")
#         if self.current_files:
#             self.file_listbox.selection_set(0)
#             self.on_file_select()

#     # NEW:  ask unsaved when changing file selection
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
#         if filename in self.current_files:
#             self.selected_file = filename
#             self.content_editor.delete(1.0, tk.END)
#             self.content_editor.insert(1.0, self.current_files[filename])
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

#     def add_file(self):
#         filename = tk.simpledialog.askstring("New File", "Enter filename:")
#         if not filename:
#             return
#         if not any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.ini', '.cfg', '.conf']):
#             filename += '.txt'
#         if filename in self.current_files:
#             messagebox.showerror("Error", "File already exists!")
#             return
#         self.current_files[filename] = ""
#         self.file_listbox.insert(tk.END, filename)
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
#             if file_path.exists():
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
# # VERSION = "v.015"  # Increment this on every program update

# # import os
# # import json
# # import subprocess
# # import sys
# # import tkinter as tk
# # from tkinter import ttk, messagebox, scrolledtext, filedialog
# # from pathlib import Path
# # import serial.tools.list_ports
# # import threading
# # from datetime import datetime

# # class ESP32SPIFFSManager:
# #     def __init__(self, root):
# #         self.root = root
# #         self.root.title(f"ESP32 SPIFFS Manager v.{VERSION}")
# #         self.root.geometry("1000x700")
# #         self.root.minsize(800, 600)

# #         # Configuration
# #         self.config_file = "spiffs_config.json"
# #         self.load_config()

# #         # State variables
# #         self.connected = False
# #         self.current_files = {}
# #         self.selected_file = None
# #         self.spiffs_downloaded = False

# #         # Create GUI
# #         self.create_widgets()
# #         self.scan_ports()

# #         # Check required files on startup
# #         self.check_dependencies()

# #     # ------------------------------------------------------------------
# #     #  NEW HELPER:  guarantees we have an int before :X formatting
# #     # ------------------------------------------------------------------
# #     @staticmethod
# #     def _ensure_int(value):
# #         """Return an int whether value is already int or decimal/hex string."""
# #         if isinstance(value, int):
# #             return value
# #         return int(value, 0)          # 0 → auto-detect base (handles 0x...)

# #     # ------------------------------------------------------------------
# #     #  Existing helpers (unchanged)
# #     # ------------------------------------------------------------------
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
# #     #  GUI creation (unchanged)
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

# #         ttk.Label(conn_frame, text="ESP32 Chip:").grid(row=0, column=4, sticky=tk.W, padx=(10, 5))
# #         self.chip_var = tk.StringVar(value=self.config.get("esp32_chip", "esp32-s3"))
# #         self.chip_combo = ttk.Combobox(conn_frame, textvariable=self.chip_var,
# #                                       values=["esp32", "esp32-s2", "esp32-s3", "esp32-c3", "esp32-c6"],
# #                                       state="readonly", width=12)
# #         self.chip_combo.grid(row=0, column=5, sticky=tk.W)
# #         self.chip_combo.bind('<<ComboboxSelected>>', self.on_chip_changed)

# #         # ---------------- SPIFFS Configuration frame ----------------
# #         spiffs_frame = ttk.LabelFrame(main_frame, text="SPIFFS Configuration", padding="5")
# #         spiffs_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

# #         ttk.Label(spiffs_frame, text="Offset:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
# #         self.offset_var = tk.StringVar(value=self.format_value_for_display(self.config.get("spiffs_offset", 6750208)))
# #         self.offset_entry = ttk.Entry(spiffs_frame, textvariable=self.offset_var, width=15)
# #         self.offset_entry.grid(row=0, column=1, padx=(0, 10))

# #         ttk.Label(spiffs_frame, text="Size:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
# #         self.size_var = tk.StringVar(value=self.format_value_for_display(self.config.get("spiffs_size", 1572864)))
# #         self.size_entry = ttk.Entry(spiffs_frame, textvariable=self.size_var, width=15)
# #         self.size_entry.grid(row=0, column=3, padx=(0, 10))

# #         self.save_config_btn = ttk.Button(spiffs_frame, text="Save Config", command=self.save_spiffs_config)
# #         self.save_config_btn.grid(row=0, column=4, padx=(10, 0))

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
# #     #  Dependency / connection helpers (unchanged)
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

# #     def toggle_connection(self):
# #         if not self.connected:
# #             if not self.port_var.get():
# #                 messagebox.showerror("Error", "Please select a COM port")
# #                 return
# #             if self.test_connection():
# #                 self.connected = True
# #                 self.connect_btn.config(text="Disconnect")
# #                 self.action_btn.config(state="normal")
# #                 self.config["last_port"] = self.get_selected_port()
# #                 self.save_config()
# #                 self.status_var.set(f"Connected to {self.get_selected_port()}")
# #             else:
# #                 messagebox.showerror("Connection Error", "Failed to connect to ESP32")
# #         else:
# #             self.connected = False
# #             self.connect_btn.config(text="Connect")
# #             self.action_btn.config(state="disabled")
# #             self.status_var.set("Disconnected")

# #     def test_connection(self):
# #         try:
# #             cmd = [
# #                 "esptool.exe",
# #                 "--chip", self.chip_var.get(),
# #                 "--port", self.get_selected_port(),
# #                 "--baud", self.config["baud_rate"],
# #                 "chip_id"
# #             ]
# #             result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
# #             return result.returncode == 0
# #         except Exception as e:
# #             print(f"Connection test failed: {e}")
# #             return False

# #     def on_chip_changed(self, event=None):
# #         self.config["esp32_chip"] = self.chip_var.get()
# #         self.save_config()

# #     def save_spiffs_config(self):
# #         offset_value = self.validate_config_input(self.offset_var.get(), "offset")
# #         if offset_value is None:
# #             return
# #         size_value = self.validate_config_input(self.size_var.get(), "size")
# #         if size_value is None:
# #             return
# #         self.config["spiffs_offset"] = offset_value
# #         self.config["spiffs_size"] = size_value
# #         self.save_config()
# #         self.offset_var.set(self.format_value_for_display(offset_value))
# #         self.size_var.set(self.format_value_for_display(size_value))
# #         messagebox.showinfo("Config Saved", "SPIFFS configuration saved successfully!")
# #         self.status_var.set(f"Config saved: Offset={self.format_value_for_display(offset_value)}, Size={self.format_value_for_display(size_value)}")

# #     def perform_action(self):
# #         if not self.connected:
# #             messagebox.showerror("Error", "Not connected to ESP32")
# #             return
# #         if not self.spiffs_downloaded:
# #             self.download_spiffs()
# #         else:
# #             self.upload_spiffs()

# #     # ------------------------------------------------------------------
# #     #  DOWNLOAD  ––  fixed with _ensure_int
# #     # ------------------------------------------------------------------
# #     def download_spiffs(self):
# #         def download_worker():
# #             try:
# #                 self.progress.start()
# #                 self.action_btn.config(state="disabled")
# #                 self.status_var.set("Downloading SPIFFS...")

# #                 #  FIX:  make sure we have integers before :X formatting
# #                 offset_val = self._ensure_int(self.config['spiffs_offset'])
# #                 size_val   = self._ensure_int(self.config['spiffs_size'])

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
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 if result.returncode != 0:
# #                     raise Exception(f"Failed to read flash: {result.stderr}")

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
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 if result.returncode != 0:
# #                     raise Exception(f"Failed to extract SPIFFS: {result.stderr}")

# #                 self.root.after(0, self.download_complete)

# #             except Exception as e:
# #                 error_msg = str(e)
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
# #         messagebox.showinfo("Success", "SPIFFS downloaded successfully!")

# #     def download_error(self, error_msg):
# #         self.progress.stop()
# #         self.action_btn.config(state="normal")
# #         self.status_var.set("Download failed")
# #         messagebox.showerror("Download Error", f"Failed to download SPIFFS:\n{error_msg}")

# #     # ------------------------------------------------------------------
# #     #  UPLOAD  ––  fixed with _ensure_int
# #     # ------------------------------------------------------------------
# #     def upload_spiffs(self):
# #         if self.selected_file and self.save_file_btn['state'] == 'normal':
# #             self.save_current_file()

# #         def upload_worker():
# #             try:
# #                 self.progress.start()
# #                 self.action_btn.config(state="disabled")
# #                 self.status_var.set("Creating SPIFFS image...")

# #                 spiffs_dir = Path("spiffs")
# #                 spiffs_dir.mkdir(exist_ok=True)

# #                 #  FIX:  ensure integers before :X formatting
# #                 size_val   = self._ensure_int(self.config['spiffs_size'])
# #                 offset_val = self._ensure_int(self.config['spiffs_offset'])

# #                 cmd = [
# #                     "mkspiffs_espressif32_arduino.exe",
# #                     "-c", "data",
# #                     "-p", "256",
# #                     "-b", "4096",
# #                     "-s", str(size_val),
# #                     "spiffs/data.bin"
# #                 ]
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 if result.returncode != 0:
# #                     raise Exception(f"Failed to create SPIFFS image: {result.stderr}")

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
# #                 result = subprocess.run(cmd, capture_output=True, text=True)
# #                 if result.returncode != 0:
# #                     raise Exception(f"Failed to upload SPIFFS: {result.stderr}")

# #                 self.root.after(0, self.upload_complete)

# #             except Exception as e:
# #                 error_msg = str(e)
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
# #     #  File management helpers (unchanged)
# #     # ------------------------------------------------------------------
# #     def load_files(self):
# #         self.current_files = {}
# #         self.file_listbox.delete(0, tk.END)
# #         data_dir = Path("data")
# #         if not data_dir.exists():
# #             return
# #         text_extensions = {'.json', '.txt', '.ini', '.cfg', '.conf', '.log', '.csv'}
# #         for file_path in data_dir.iterdir():
# #             if file_path.is_file() and file_path.suffix.lower() in text_extensions:
# #                 try:
# #                     with open(file_path, 'r', encoding='utf-8') as f:
# #                         content = f.read()
# #                     self.current_files[file_path.name] = content
# #                     self.file_listbox.insert(tk.END, file_path.name)
# #                 except Exception as e:
# #                     print(f"Error reading {file_path}: {e}")
# #         self.add_file_btn.config(state="normal")
# #         if self.current_files:
# #             self.file_listbox.selection_set(0)
# #             self.on_file_select()

# #     def on_file_select(self, event=None):
# #         selection = self.file_listbox.curselection()
# #         if not selection:
# #             return
# #         if self.selected_file and self.save_file_btn['state'] == 'normal':
# #             result = messagebox.askyesnocancel("Unsaved Changes",
# #                                               f"Save changes to {self.selected_file}?")
# #             if result is True:
# #                 self.save_current_file()
# #             elif result is None:
# #                 return
# #         filename = self.file_listbox.get(selection[0])
# #         if filename in self.current_files:
# #             self.selected_file = filename
# #             self.content_editor.delete(1.0, tk.END)
# #             self.content_editor.insert(1.0, self.current_files[filename])
# #             self.save_file_btn.config(state="disabled")
# #             self.delete_file_btn.config(state="normal")

# #     def on_content_changed(self, event=None):
# #         if self.selected_file:
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
# #             self.save_file_btn.config(state="disabled")
# #             self.status_var.set(f"Saved {self.selected_file}")
# #         except Exception as e:
# #             messagebox.showerror("Save Error", f"Failed to save file:\n{e}")

# #     def add_file(self):
# #         filename = tk.simpledialog.askstring("New File", "Enter filename:")
# #         if not filename:
# #             return
# #         if not any(filename.lower().endswith(ext) for ext in ['.json', '.txt', '.ini', '.cfg', '.conf']):
# #             filename += '.txt'
# #         if filename in self.current_files:
# #             messagebox.showerror("Error", "File already exists!")
# #             return
# #         self.current_files[filename] = ""
# #         self.file_listbox.insert(tk.END, filename)
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
# #         self.save_file_btn.config(state="disabled")
# #         self.delete_file_btn.config(state="disabled")

# # # ----------------------------------------------------------------------
# # #  Entry-point (unchanged)
# # # ----------------------------------------------------------------------
# # def main():
# #     import tkinter.simpledialog
# #     tk.simpledialog = tkinter.simpledialog
# #     root = tk.Tk()
# #     app = ESP32SPIFFSManager(root)
# #     root.mainloop()

# # if __name__ == "__main__":
# #     main()