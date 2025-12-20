#!/usr/bin/env python3
"""
Test script to simulate ESP32 device connections
Useful for testing the server without physical devices
"""

import requests
import json
import time
import random
import sys


def create_test_device(device_id, role='neutral', status='sleep'):
    """Create a test device data payload"""
    return {
        'id': device_id,
        'ip': f'192.168.1.{random.randint(100, 200)}',
        'rssi': random.randint(-80, -40),
        'role': role,
        'status': status,
        'health': random.randint(80, 100),
        'battery': random.randint(70, 100),
        'comment': f'Test device {device_id}'
    }


def send_device_update(server_url, device_data):
    """Send device update to server"""
    try:
        data_json = json.dumps(device_data)
        response = requests.get(
            f'{server_url}/api/device',
            params={'data': data_json},
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Device {device_data['id']}: {response.status_code}")
            print(f"  Server response: {result}")
            return result
        else:
            print(f"✗ Device {device_data['id']}: HTTP {response.status_code}")
            print(f"  Error: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to server at {server_url}")
        print("  Make sure the application is running")
        return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def test_single_device(server_url):
    """Test with a single device"""
    print("Testing single device connection...")
    print("-" * 60)
    
    device = create_test_device('test_device_001')
    response = send_device_update(server_url, device)
    
    if response:
        print("\n✓ Single device test successful!")
        return True
    else:
        print("\n✗ Single device test failed!")
        return False


def test_multiple_devices(server_url, num_devices=5):
    """Test with multiple devices"""
    print(f"\nTesting {num_devices} devices...")
    print("-" * 60)
    
    success_count = 0
    
    for i in range(num_devices):
        device_id = f'test_device_{i+1:03d}'
        device = create_test_device(device_id)
        
        response = send_device_update(server_url, device)
        if response:
            success_count += 1
        
        time.sleep(0.5)  # Small delay between requests
    
    print(f"\n✓ Successfully connected {success_count}/{num_devices} devices")
    return success_count == num_devices


def test_game_flow(server_url):
    """Test a complete game flow with state changes"""
    print("\nTesting game flow...")
    print("-" * 60)
    
    device_id = 'test_device_flow'
    
    # Test sleep state
    print("\n1. Testing 'sleep' state...")
    device = create_test_device(device_id, status='sleep')
    response = send_device_update(server_url, device)
    if not response or response.get('status') != 'sleep':
        print("✗ Sleep state test failed")
        return False
    
    time.sleep(1)
    
    # Test prepare state
    print("\n2. Testing 'prepare' state...")
    device = create_test_device(device_id, status='prepare')
    response = send_device_update(server_url, device)
    print(f"  Device role assigned: {response.get('role', 'unknown')}")
    
    time.sleep(1)
    
    # Test game state
    print("\n3. Testing 'game' state...")
    device = create_test_device(device_id, role='human', status='game')
    response = send_device_update(server_url, device)
    if not response:
        print("✗ Game state test failed")
        return False
    
    print("\n✓ Game flow test successful!")
    return True


def interactive_test(server_url):
    """Interactive testing mode"""
    print("\n=== Interactive Test Mode ===")
    print("Commands:")
    print("  1 - Send single device update")
    print("  5 - Send 5 device updates")
    print("  10 - Send 10 device updates")
    print("  flow - Test complete game flow")
    print("  q - Quit")
    print()
    
    while True:
        try:
            cmd = input("Enter command: ").strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == '1':
                test_single_device(server_url)
            elif cmd == '5':
                test_multiple_devices(server_url, 5)
            elif cmd == '10':
                test_multiple_devices(server_url, 10)
            elif cmd == 'flow':
                test_game_flow(server_url)
            else:
                print("Unknown command")
                
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break


def main():
    """Main test function"""
    # Default server URL
    server_url = 'http://127.0.0.1:5000'
    
    # Check for custom server URL
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    
    print("=" * 60)
    print("Zombie Game - API Test Script")
    print("=" * 60)
    print(f"Server URL: {server_url}")
    print("=" * 60)
    print()
    
    # Run tests
    if test_single_device(server_url):
        test_multiple_devices(server_url, 5)
        test_game_flow(server_url)
        
        # Offer interactive mode
        print("\n" + "=" * 60)
        response = input("Start interactive mode? (y/n): ").strip().lower()
        if response == 'y':
            interactive_test(server_url)
    
    print("\nTests completed!")


if __name__ == '__main__':
    main()
