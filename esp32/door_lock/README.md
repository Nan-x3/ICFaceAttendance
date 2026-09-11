# ESP32 Door Lock Firmware

This folder contains the cleaned firmware source for the ESP32 door controller.
It preserves the current wiring and behavior:

- Relay: GPIO 18, active LOW, unlocked for 10 seconds.
- Keypad rows: GPIO 13, 12, 14, 27.
- Keypad columns: GPIO 26, 25, 33, 32.
- OLED: I2C address `0x3C`, 128x64.
- Serial speed: 9600 baud.
- Guest records: `/guests.json` in SPIFFS.

## Libraries

Install these Arduino libraries:

- Keypad
- Adafruit GFX Library
- Adafruit SSD1306
- ArduinoJson

WiFi, ArduinoOTA, SPIFFS, Wire, and SPI are provided by the ESP32 Arduino core.

## Build

1. Copy `secrets.example.h` to `secrets.h`.
2. Fill in the Wi-Fi and OTA password values.
3. Open `door_lock.ino` in Arduino IDE or PlatformIO.
4. Select an ESP32 board and the correct serial port.
5. Upload over USB the first time.
6. Open Serial Monitor at `9600` baud.

`secrets.h` must stay local and must never be committed.

## Commands From The Raspberry Pi

The Pi sends newline-terminated commands:

- `UNLOCK`: unlocks the relay for 10 seconds.
- `ADD:<pin>:<name>`: adds a keypad credential.
- `REMOVE:<pin>`: removes a keypad credential.
- `LIST`: prints all keypad credentials.

## OTA

After the first USB upload, the ESP32 connects to Wi-Fi and starts ArduinoOTA.
The Pi and ESP32 must be on the same network. In Arduino IDE, select the ESP32
network port and upload the next firmware version wirelessly.

The current repository does not yet host a compiled firmware endpoint. The next
step is to add a Pi-hosted upload endpoint or a GitHub Actions release workflow.
Do not change relay behavior until the physical lock wiring has been tested.
