import time
import cv2
import requests
from pyzbar.pyzbar import decode

# Whitelist of allowed roll numbers/registration codes
WHITELIST = {"3611", "1368", "1099"}

# Replace with your ESP32's actual local IP address on the network
ESP32_URL = "http://192.168.137.50/unlock"

def main():
    print("[*] Initializing camera for QR scanning...")
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    
    if not cap.isOpened():
        print("[!] Error: Could not open video stream.")
        return

    print("[+] Scanner active. Present your ID QR code...")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[!] Failed to grab frame. Retrying...")
            time.sleep(1)
            continue

        for barcode in decode(frame):
            reg_number = barcode.data.decode("utf-8").strip()
            print(f"[+] Scanned ID: {reg_number}")

            if reg_number in WHITELIST:
                print("[✔] Access Granted! Triggering door unlock...")
                try:
                    response = requests.get(ESP32_URL, timeout=2)
                    if response.status_code == 200:
                        print("[✔] ESP32 unlocked the door successfully!")
                    else:
                        print(f"[!] ESP32 error response: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"[!] Could not reach ESP32: {e}")
                
                time.sleep(2)
            else:
                print(f"[✖] Access Denied: {reg_number} is not on the whitelist.")
                time.sleep(1)

        time.sleep(0.1)

if __name__ == "__main__":
    main()
