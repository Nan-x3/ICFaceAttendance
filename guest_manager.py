#!/usr/bin/env python3
"""
IC DoorLock — Guest Manager
Run on the Raspberry Pi to manage the ESP32 guest list.
Usage: python3 guest_manager.py
"""

import serial
import time
import random
import sys

# ── Config ────────────────────────────────────────────
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE   = 9600
TIMEOUT     = 2

# Valid keypad characters (excluding * and # which are control keys)
KEYPAD_CHARS = "0123456789ABCD"

# ── Serial Helper ─────────────────────────────────────
def get_serial():
    try:
        s = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=TIMEOUT)
        time.sleep(2)  # Wait for ESP32 to settle
        return s
    except Exception as e:
        print(f"Error: Could not open {SERIAL_PORT} — {e}")
        print("Make sure the ESP32 is connected via USB.")
        sys.exit(1)

def send_command(ser, cmd):
    ser.write((cmd + '\n').encode())
    time.sleep(0.5)
    response = []
    while ser.in_waiting:
        line = ser.readline().decode(errors='ignore').strip()
        if line:
            response.append(line)
    return response

# ── PIN Generator ─────────────────────────────────────
def generate_pin(length=8):
    return ''.join(random.choices(KEYPAD_CHARS, k=length))

# ── Actions ───────────────────────────────────────────
def add_student(ser):
    roll = input("Enter student roll number (e.g. 22BCE1234): ").strip().upper()
    if not roll:
        print("Cancelled.")
        return
    name = input("Enter student name: ").strip()
    if not name:
        print("Cancelled.")
        return
    resp = send_command(ser, f"ADD:{roll}:{name}")
    print(f"✅ Added student: {name} → PIN/Roll: {roll}")
    for r in resp:
        print(f"   ESP32: {r}")

def add_faculty(ser):
    name = input("Enter faculty/staff name: ").strip()
    if not name:
        print("Cancelled.")
        return
    length = input("PIN length? (default 8): ").strip()
    length = int(length) if length.isdigit() else 8
    pin = generate_pin(length)
    resp = send_command(ser, f"ADD:{pin}:{name}")
    print(f"✅ Added: {name}")
    print(f"   PIN: {pin}  ← Give this to {name}, save it somewhere safe!")
    for r in resp:
        print(f"   ESP32: {r}")

def add_custom(ser):
    name = input("Enter name: ").strip()
    pin  = input("Enter custom PIN (use only 0-9, A, B, C, D): ").strip().upper()
    if not name or not pin:
        print("Cancelled.")
        return
    # Validate
    for ch in pin:
        if ch not in KEYPAD_CHARS:
            print(f"Invalid character '{ch}' — only 0-9, A, B, C, D allowed.")
            return
    resp = send_command(ser, f"ADD:{pin}:{name}")
    print(f"✅ Added: {name} → PIN: {pin}")
    for r in resp:
        print(f"   ESP32: {r}")

def remove_person(ser):
    pin = input("Enter PIN or roll number to remove: ").strip().upper()
    if not pin:
        print("Cancelled.")
        return
    confirm = input(f"Remove '{pin}'? (y/n): ").strip().lower()
    if confirm == 'y':
        resp = send_command(ser, f"REMOVE:{pin}")
        print(f"🗑️  Removed: {pin}")
        for r in resp:
            print(f"   ESP32: {r}")
    else:
        print("Cancelled.")

def list_guests(ser):
    print("\n📋 Fetching guest list from ESP32...")
    resp = send_command(ser, "LIST")
    if resp:
        for r in resp:
            print(f"   {r}")
    else:
        print("   (No response — list may be empty)")

def test_unlock(ser):
    confirm = input("Send UNLOCK command to test door? (y/n): ").strip().lower()
    if confirm == 'y':
        resp = send_command(ser, "UNLOCK")
        print("🔓 UNLOCK sent")
        for r in resp:
            print(f"   ESP32: {r}")

# ── Main Menu ─────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════╗")
    print("║   IC DoorLock — Guest Manager            ║")
    print("╚══════════════════════════════════════════╝")
    print(f"Connecting to ESP32 on {SERIAL_PORT}...")
    ser = get_serial()
    print("Connected!\n")

    while True:
        print("\n── Menu ────────────────────────────────")
        print("  1. Add student (by roll number)")
        print("  2. Add faculty/staff (random PIN)")
        print("  3. Add person (custom PIN)")
        print("  4. Remove person")
        print("  5. List all guests")
        print("  6. Test unlock door")
        print("  0. Exit")
        print("────────────────────────────────────────")

        choice = input("Choice: ").strip()

        if   choice == '1': add_student(ser)
        elif choice == '2': add_faculty(ser)
        elif choice == '3': add_custom(ser)
        elif choice == '4': remove_person(ser)
        elif choice == '5': list_guests(ser)
        elif choice == '6': test_unlock(ser)
        elif choice == '0':
            print("Bye!")
            ser.close()
            break
        else:
            print("Invalid choice.")

if __name__ == '__main__':
    main()
