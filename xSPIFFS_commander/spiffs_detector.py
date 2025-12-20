import esptool
import serial.tools.list_ports
import sys
import csv

def scan_ports():
    """Scan and return available COM ports"""
    ports = serial.tools.list_ports.comports()
    available_ports = []
    
    print("\nAvailable COM ports:")
    print("-" * 50)
    
    if not ports:
        print("No COM ports found!")
        return None
    
    for i, port in enumerate(ports, 1):
        print(f"{i}. {port.device} - {port.description}")
        available_ports.append(port.device)
    
    return available_ports

def get_user_port(available_ports):
    """Ask user to select a COM port"""
    while True:
        try:
            choice = input(f"\nSelect port number (1-{len(available_ports)}) or enter COM port directly: ").strip()
            
            # Check if user entered a number
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(available_ports):
                    return available_ports[idx]
                else:
                    print(f"Invalid selection. Please choose 1-{len(available_ports)}")
            # Check if user entered a COM port directly
            elif choice.upper().startswith("COM"):
                return choice.upper()
            else:
                print("Invalid input. Enter a number or COM port (e.g., COM3)")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user")
            sys.exit(0)

def detect_esp32_model(port):
    """Detect ESP32 chip model - auto-detects the correct chip type"""
    print(f"\nConnecting to {port}...")
    
    try:
        # Use detect_chip to automatically identify the chip type
        esp = esptool.get_default_connected_device(
            serial_list=[port],
            port=port,
            connect_attempts=7,
            initial_baud=115200
        )
        
        chip_name = esp.get_chip_description()
        print(f"\nChip detected: {chip_name}")
        print(f"Chip features: {', '.join(esp.get_chip_features())}")
        print(f"MAC Address: {':'.join(f'{b:02x}' for b in esp.read_mac())}")
        
        try:
            crystal = esp.get_crystal_freq()
            print(f"Crystal: {crystal}MHz")
        except:
            print("Crystal: Unable to detect")
        
        return esp
    except Exception as e:
        print(f"Error connecting to ESP32: {e}")
        print("\nTroubleshooting:")
        print("- Make sure the ESP32 is connected to the selected port")
        print("- Try pressing the BOOT button during connection")
        print("- Check if another program is using the port")
        sys.exit(1)

def read_partition_table(esp):
    """Read partition table from ESP32"""
    PARTITION_TABLE_OFFSET = 0x8000
    PARTITION_TABLE_SIZE = 0xC00  # 3KB
    
    print(f"\nReading partition table from offset 0x{PARTITION_TABLE_OFFSET:X}...")
    
    try:
        # Run stub for faster and more reliable flash operations
        print("Running stub loader...")
        esp = esp.run_stub()
        
        # Read the partition table
        partition_data = esp.read_flash(PARTITION_TABLE_OFFSET, PARTITION_TABLE_SIZE)
        print(f"Successfully read {len(partition_data)} bytes")
        return partition_data
    except Exception as e:
        print(f"Error reading partition table: {e}")
        print("\nTrying alternative method...")
        try:
            # Try reading with smaller chunks
            partition_data = b''
            chunk_size = 0x100  # 256 bytes at a time
            for offset in range(PARTITION_TABLE_OFFSET, PARTITION_TABLE_OFFSET + PARTITION_TABLE_SIZE, chunk_size):
                chunk = esp.read_flash(offset, chunk_size)
                partition_data += chunk
            print(f"Successfully read {len(partition_data)} bytes using chunked method")
            return partition_data
        except Exception as e2:
            print(f"Alternative method also failed: {e2}")
            return None

def parse_partition_table(data):
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
        
        # Name is null-terminated string
        name_bytes = entry[12:28]
        name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='ignore')
        
        flags = int.from_bytes(entry[28:32], 'little')
        
        # Type and subtype mapping
        type_str = get_partition_type(p_type)
        subtype_str = get_partition_subtype(p_type, p_subtype)
        
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

def get_partition_type(p_type):
    """Convert partition type byte to string"""
    types = {
        0x00: 'app',
        0x01: 'data',
    }
    return types.get(p_type, f'0x{p_type:02X}')

def get_partition_subtype(p_type, p_subtype):
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

def save_to_csv(partitions, filename='partitions.csv'):
    """Save partition table to CSV file"""
    if not partitions:
        print("No partitions to save!")
        return
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            # CSV header format matching ESP-IDF partition table format
            f.write("# Name, Type, SubType, Offset, Size, Flags\n")
            
            writer = csv.writer(f)
            for p in partitions:
                writer.writerow([
                    p['name'],
                    p['type'],
                    p['subtype'],
                    p['offset'],
                    p['size'],
                    p['flags']
                ])
        
        print(f"\nPartition table saved to '{filename}'")
        print(f"Total partitions: {len(partitions)}")
        
        # Display partition table
        print("\nPartition Table:")
        print("-" * 80)
        print(f"{'Name':<15} {'Type':<10} {'SubType':<12} {'Offset':<12} {'Size':<12} {'Flags'}")
        print("-" * 80)
        for p in partitions:
            print(f"{p['name']:<15} {p['type']:<10} {p['subtype']:<12} {p['offset']:<12} {p['size']:<12} {p['flags']}")
        
    except Exception as e:
        print(f"Error saving CSV file: {e}")

def main():
    print("=" * 50)
    print("ESP32 Partition Table Reader")
    print("=" * 50)
    
    # Step 1: Scan and select COM port
    available_ports = scan_ports()
    if not available_ports:
        sys.exit(1)
    
    port = get_user_port(available_ports)
    
    # Step 2: Detect ESP32 model
    esp = detect_esp32_model(port)
    
    # Step 3: Read and parse partition table
    partition_data = read_partition_table(esp)
    
    if partition_data:
        partitions = parse_partition_table(partition_data)
        
        # Save to CSV
        save_to_csv(partitions)
    
    print("\nDone!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)