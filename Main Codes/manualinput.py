#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import serial
import time
import subprocess
import re
import os
import json
import sys

# ============================================
# SEQUENCE SETTINGS
# ============================================
POSITION_DELAY = 3.0
TRANSITION_DELAY = 0.5
LOOP_SEQUENCE = True
# ============================================

# ============================================
# POSITION SEQUENCE (ALL MOTORS TEST)
# ============================================
POSITION_SEQUENCE = [
    (45,  0, 90, "Position 1 - M1 Max, M3 Max"),
    (0,  45, 45, "Position 2 - M2 Max, M3 Mid"),
    (22, 22, 90, "Position 3 - All Mid/Max"),
    (10, 10, 10, "Position 4 - All Low"),
    (45, 45, 90, "Position 5 - All Max"),
    (22, 22, 45, "Home Position"),
]
# ============================================

# ============================================
# ESP32 BLUETOOTH CLASS
# ============================================
class ESP32Bluetooth:
    def __init__(self, device_name="ESP32_Receiver", port="/dev/rfcomm0", baudrate=115200):
        self.device_name = device_name
        self.port = port
        self.baudrate = baudrate
        self.mac_address = None
        self.ser = None
        self.mac_file = "/tmp/esp32_mac.json"
        
        self.M1_MIN = 0
        self.M1_MAX = 45
        self.M2_MIN = 0
        self.M2_MAX = 45
        self.M3_MIN = 0
        self.M3_MAX = 90
    
    def load_mac(self):
        if os.path.exists(self.mac_file):
            try:
                with open(self.mac_file, 'r') as f:
                    data = json.load(f)
                    saved_mac = data.get('mac')
                    if saved_mac and not saved_mac.upper().startswith('B8:27:EB'):
                        self.mac_address = saved_mac.upper()
                        return True
                    else:
                        os.remove(self.mac_file)
            except: 
                pass
        return False
    
    def save_mac(self):
        if self.mac_address:
            try:
                with open(self.mac_file, 'w') as f:
                    json.dump({'mac': self.mac_address, 'device': self.device_name}, f)
            except: 
                pass
    
    def clear_mac(self):
        if os.path.exists(self.mac_file):
            os.remove(self.mac_file)
    
    def is_esp32_mac(self, mac):
        if not mac:
            return False
        mac = mac.upper()
        if mac.startswith('B8:27:EB') or mac.startswith('DC:A6:32'):
            return False
        return True
    
    def find_device(self, scan_time=30):
        if self.load_mac():
            return True
        
        print("[SCAN] Searching for {}...".format(self.device_name))
        try:
            result = subprocess.run(
                ['sudo', 'hcitool', 'scan'],
                capture_output=True,
                text=True,
                timeout=scan_time + 10
            )
            output = result.stdout
            
            for line in output.split('\n'):
                if self.device_name in line:
                    match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
                    if match:
                        candidate_mac = match.group(0).upper()
                        if self.is_esp32_mac(candidate_mac):
                            self.mac_address = candidate_mac
                            self.save_mac()
                            return True
            
            self.mac_address = "40:91:51:FB:B8:AE"
            self.save_mac()
            return True
            
        except Exception as e:
            print("[ERROR] Scanning error: {}".format(e))
            return False

    def pair_and_connect(self, max_retries=3):
        if not self.mac_address:
            return False

        for attempt in range(max_retries):
            commands = [
                "sudo bluetoothctl pair {}".format(self.mac_address),
                "sudo bluetoothctl trust {}".format(self.mac_address),
                "sudo bluetoothctl connect {}".format(self.mac_address)
            ]

            success = True
            for cmd in commands:
                try:
                    result = subprocess.run(cmd.split(), timeout=15, capture_output=True, text=True)
                    if result.returncode != 0:
                        success = False
                        break
                    time.sleep(1)
                except: 
                    success = False
                    break
            
            if success:
                time.sleep(2)
                return True
            
            time.sleep(2)
        
        return True

    def bind_rfcomm(self, max_retries=3):
        if not self.mac_address:
            return False

        for attempt in range(max_retries):
            try:
                subprocess.run(['sudo', 'rfcomm', 'release', '0'], 
                              capture_output=True, timeout=5)
                time.sleep(1)
                
                result = subprocess.run(
                    ['sudo', 'rfcomm', 'bind', '0', self.mac_address, '1'],
                    capture_output=True,
                    timeout=10,
                    text=True
                )
                
                if result.returncode == 0 or os.path.exists(self.port):
                    time.sleep(2)
                    return True
                else:
                    time.sleep(2)
            except: 
                time.sleep(2)
        
        return False

    def connect_serial(self, max_retries=3):
        for attempt in range(max_retries):
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
                time.sleep(2)
                return True
            except serial.SerialException as e:
                time.sleep(2)
        
        return False

    def send_data(self, x, y, z):
        if self.ser and self.ser.is_open:
            try:
                x = max(self.M1_MIN, min(self.M1_MAX, int(x)))
                y = max(self.M2_MIN, min(self.M2_MAX, int(y)))
                z = max(self.M3_MIN, min(self.M3_MAX, int(z)))
                
                data = "{},{},{}\n".format(x, y, z)
                self.ser.write(data.encode('utf-8'))
                return True
            except: 
                return False
        return False

    def is_connected(self):
        return self.ser and self.ser.is_open

    def reconnect(self):
        time.sleep(2)
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except: 
                pass
        return self.bind_rfcomm() and self.connect_serial()

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()


# ============================================
# MAIN PROGRAM
# ============================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  ESP32 Servo Controller - ALL MOTORS TEST")
    print("=" * 60)
    print("  M1 (Side Left):  0-45 deg (Channel 0)")
    print("  M2 (Side Right): 0-45 deg (Channel 1)")
    print("  M3 (Base):       0-90 deg (Channel 2) ? BASE MOTOR")
    print("=" * 60 + "\n")
    
    print("[SEQUENCE] Test Positions:")
    print("-" * 60)
    for i, (m1, m2, m3, desc) in enumerate(POSITION_SEQUENCE, 1):
        print("  {:d}. {:<30} M1={:2d}, M2={:2d}, M3={:2d}".format(i, desc, m1, m2, m3))
    print("-" * 60 + "\n")
    
    bt = ESP32Bluetooth(device_name="ESP32_Receiver", baudrate=115200)

    try:
        if '--reset' in sys.argv:
            bt.clear_mac()
            exit(0)
        
        if not bt.find_device():
            exit(1)

        bt.pair_and_connect()

        if not bt.bind_rfcomm():
            exit(1)

        if not bt.connect_serial():
            exit(1)

        print("[READY] Connected! Starting motor test...\n")
        print("??  WATCH ALL 3 MOTORS - Especially M3 (Base)!\n")

        disconnect_count = 0
        max_disconnects = 5
        sequence_count = 0
        
        while True:
            sequence_count += 1
            print("\n[SEQUENCE] Run #{}\n".format(sequence_count))
            
            for i, (m1, m2, m3, desc) in enumerate(POSITION_SEQUENCE, 1):
                if not bt.is_connected():
                    print("[WARN] Connection lost!")
                    if not bt.reconnect():
                        print("[ERROR] Reconnect failed")
                        break
                
                print("[POSITION {}/{}] {}".format(i, len(POSITION_SEQUENCE), desc))
                print("           Sending: M1={}deg, M2={}deg, M3={}deg".format(m1, m2, m3))
                
                if bt.send_data(m1, m2, m3):
                    print("           [OK] Sent - Check if ALL motors moved!")
                    print("           [WAIT] Holding for {} seconds...\n".format(POSITION_DELAY))
                    time.sleep(POSITION_DELAY)
                else:
                    print("           [ERROR] Send failed!")
                    disconnect_count += 1
                    if disconnect_count >= max_disconnects:
                        print("[ERROR] Too many failures")
                        break
                
                time.sleep(TRANSITION_DELAY)
            
            if not LOOP_SEQUENCE:
                print("\n[COMPLETE] Sequence finished!")
                break
            
            print("\n[LOOP] Restarting sequence...\n")
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[STOP] Stopped by user")
    except Exception as e:
        print("\n[ERROR] {}".format(e))
    finally:
        bt.close()