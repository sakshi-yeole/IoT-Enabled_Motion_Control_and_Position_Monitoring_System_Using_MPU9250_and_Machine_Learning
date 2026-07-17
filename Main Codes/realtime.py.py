#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import serial
import time
import subprocess
import re
import os
import json
import sys
import smbus

# ============================================
# ?? ADJUSTABLE DELAY SETTINGS
# ============================================
SENSOR_READ_DELAY = 1.8    # ?? INCREASE THIS for slower movement (default: 0.5 seconds)
                              # Try: 1.0, 1.5, 2.0 for even slower response
# ============================================

from mpu9250_jmdev.mpu_9250 import MPU9250
from mpu9250_jmdev.registers import *

# Wake MPU9250 from sleep
bus_i2c = smbus.SMBus(1)
MPU_ADDR = 0x68
PWR_MGMT_1 = 0x6B

try:
    bus_i2c.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0x00)
    time.sleep(0.2)
except Exception as e:
    print("[WARN] Failed to wake MPU9250:", e)

# Initialize MPU
mpu = MPU9250(
    address_ak=None,
    address_mpu_master=MPU9050_ADDRESS_68,
    bus=1,
    gfs=GFS_250,
    afs=AFS_2G
)

try:
    mpu.configure()
except Exception as e:
    print("[WARN] Warning during configuration:", e)

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
# SENSOR TO SERVO MAPPING
# ============================================
def map_sensor_to_servo(accel_x, accel_y, gyro_z):
    m1_angle = int(((accel_x + 2) / 4) * 45)
    m1_angle = max(0, min(45, m1_angle))
    
    m2_angle = int(((accel_y + 2) / 4) * 45)
    m2_angle = max(0, min(45, m2_angle))
    
    m3_angle = int(((gyro_z + 250) / 500) * 90)
    m3_angle = max(0, min(90, m3_angle))
    
    return m1_angle, m2_angle, m3_angle


# ============================================
# MAIN PROGRAM
# ============================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  MPU9250 Sensor to ESP32 Servo Controller")
    print("=" * 60)
    print("  Sensor Update Delay: {} seconds".format(SENSOR_READ_DELAY))
    print("  M1 (Side Left):  0-45 deg (Accelerometer X)")
    print("  M2 (Side Right): 0-45 deg (Accelerometer Y)")
    print("  M3 (Base):       0-90 deg (Gyroscope Z)")
    print("=" * 60 + "\n")
    
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

        print("[READY] Connected! Reading MPU9250...\n")

        disconnect_count = 0
        max_disconnects = 5
        
        while True:
            if bt.is_connected():
                try:
                    # Read MPU9250 sensor data
                    accel = mpu.readAccelerometerMaster()
                    gyro = mpu.readGyroscopeMaster()
                    
                    accel = [round(a, 3) for a in accel]
                    gyro = [round(g, 3) for g in gyro]
                    
                    # Map sensor values to servo angles
                    m1, m2, m3 = map_sensor_to_servo(accel[0], accel[1], gyro[2])
                    
                    # Display sensor data
                    print("[SENSOR] Accel: X={:.2f}g, Y={:.2f}g, Z={:.2f}g | Gyro: X={:.1f}, Y={:.1f}, Z={:.1f} deg/s".format(
                        accel[0], accel[1], accel[2],
                        gyro[0], gyro[1], gyro[2]))
                    
                    # Send to ESP32
                    bt.send_data(m1, m2, m3)
                    
                    # ?? THIS DELAY CONTROLS MOVEMENT SPEED ??
                    time.sleep(SENSOR_READ_DELAY)
                    
                except Exception as e:
                    time.sleep(SENSOR_READ_DELAY)
            else:
                if bt.reconnect():
                    disconnect_count = 0
                else:
                    disconnect_count += 1
                    if disconnect_count >= max_disconnects:
                        break
            
            time.sleep(SENSOR_READ_DELAY)

    except KeyboardInterrupt:
        print("\n[STOP] Stopped by user")
    except Exception as e:
        print("\n[ERROR] {}".format(e))
    finally:
        bt.close()