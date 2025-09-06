#!/usr/bin/env python3
"""
ESP32 SPIFFS Manager
Combines upload and download functionality for ESP32 SPIFFS filesystem
"""

import os
import subprocess
import sys
import shutil
from pathlib import Path
import serial.tools.list_ports

def run_command(cmd, check=True):
    """Run a command and display real-time output"""
    print(f"Running: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        # Run with real-time output
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,  # Merge stderr with stdout
            text=True, 
            bufsize=1, 
            universal_newlines=True
        )
        
        # Display output in real-time
        output_lines = []
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
                output_lines.append(output.strip())
        
        # Wait for process to complete
        return_code = process.poll()
        
        if check and return_code != 0:
            raise subprocess.CalledProcessError(return_code, cmd, ''.join(output_lines))
        
        print("-" * 50)
        return return_code
        
    except subprocess.CalledProcessError as e:
        print(f"\nError running command (exit code {e.returncode}): {' '.join(cmd)}")
        raise
    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}")
        print("Make sure the required tools are in your PATH or current directory")
        raise

def check_required_files():
    """Check if required executables exist"""
    required_files = ["esptool.exe", "mkspiffs_espressif32_arduino.exe"]
    missing_files = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("Missing required files:")
        for file in missing_files:
            print(f"  - {file}")
        print("\nPlease ensure these files are in the current directory or PATH")
        return False
    return True

def check_pyserial():
    """Check if pyserial is installed"""
    try:
        import serial.tools.list_ports
        return True
    except ImportError:
        print("Error: pyserial library not found!")
        print("Please install it using: pip install pyserial")
        return False

def get_user_choice():
    """Get user's choice for upload or download"""
    while True:
        print("\nESP32 SPIFFS Manager")
        print("1. Download SPIFFS from ESP32")
        print("2. Upload SPIFFS to ESP32")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice in ['1', '2', '3']:
            return choice
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

def get_com_port():
    """Get COM port from user with auto-detection"""
    # Get list of available COM ports
    ports = serial.tools.list_ports.comports()
    available_ports = [port.device for port in ports]
    
    if not available_ports:
        print("No COM ports detected!")
        print("Please make sure your ESP32 is connected and drivers are installed.")
        # Fallback to manual entry
        while True:
            port = input("Enter COM port manually (e.g., COM15): ").strip().upper()
            if port.startswith("COM") and port[3:].isdigit():
                return port
            else:
                print("Invalid COM port format. Please use format like COM15")
    
    print(f"\nDetected COM ports:")
    for i, port_info in enumerate(ports, 1):
        description = port_info.description if port_info.description != 'n/a' else 'Unknown device'
        print(f"{i}. {port_info.device} - {description}")
    
    print(f"{len(ports) + 1}. Enter manually")
    
    while True:
        try:
            choice = input(f"\nSelect COM port (1-{len(ports) + 1}): ").strip()
            choice_num = int(choice)
            
            if 1 <= choice_num <= len(ports):
                selected_port = available_ports[choice_num - 1]
                print(f"Selected: {selected_port}")
                return selected_port
            elif choice_num == len(ports) + 1:
                # Manual entry
                while True:
                    port = input("Enter COM port (e.g., COM15): ").strip().upper()
                    if port.startswith("COM") and port[3:].isdigit():
                        return port
                    else:
                        print("Invalid COM port format. Please use format like COM15")
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(ports) + 1}")
        except ValueError:
            print("Invalid input. Please enter a number.")

def download_spiffs(com_port):
    """Download SPIFFS from ESP32"""
    print("\n=== Downloading SPIFFS from ESP32 ===")
    
    # Read flash to partition-table.bin
    cmd = [
        "esptool.exe",
        "--chip", "esp32-s3",
        "--port", com_port,
        "--baud", "921600",
        "read_flash", "8060928", "7340032",
        "partition-table.bin"
    ]
    run_command(cmd)
    
    # Create data directory if it doesn't exist
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    # Clear data directory
    print("Clearing data directory...")
    for file in data_dir.glob("*"):
        if file.is_file():
            file.unlink()
            print(f"Deleted: {file}")
    
    # Extract SPIFFS data
    cmd = [
        "mkspiffs_espressif32_arduino.exe",
        "-u", "data",
        "partition-table.bin"
    ]
    run_command(cmd)
    
    print("SPIFFS download completed successfully!")

def upload_spiffs(com_port):
    """Upload SPIFFS to ESP32"""
    print("\n=== Uploading SPIFFS to ESP32 ===")
    
    # Check if data directory exists
    if not os.path.exists("data"):
        print("Error: 'data' directory not found!")
        print("Please create a 'data' directory with your files to upload")
        return False
    
    # Create spiffs directory if it doesn't exist
    spiffs_dir = Path("spiffs")
    spiffs_dir.mkdir(exist_ok=True)
    
    # Create SPIFFS image
    cmd = [
        "mkspiffs_espressif32_arduino.exe",
        "-c", "data",
        "-p", "256",
        "-b", "4096",
        "-s", "7340032",
        "spiffs/data.bin"
    ]
    run_command(cmd)
    
    # Upload to ESP32
    cmd = [
        "esptool.exe",
        "--chip", "esp32-s3",
        "--port", com_port,
        "--baud", "921600",
        "--before", "default_reset",
        "--after", "hard_reset",
        "write_flash", "-z",
        "--flash_mode", "dio",
        "--flash_size", "detect",
        "8060928", "spiffs/data.bin"
    ]
    run_command(cmd)
    
    print("SPIFFS upload completed successfully!")
    return True

def main():
    """Main function"""
    print("ESP32 SPIFFS Manager")
    print("===================")
    
    # Check for required dependencies
    if not check_pyserial():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # Check for required files
    if not check_required_files():
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    try:
        while True:
            choice = get_user_choice()
            
            if choice == '3':
                print("Exiting...")
                break
            
            com_port = get_com_port()
            
            if choice == '1':
                download_spiffs(com_port)
            elif choice == '2':
                upload_spiffs(com_port)
            
            print("\nOperation completed!")
            continue_choice = input("Do you want to perform another operation? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes']:
                break
    
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
