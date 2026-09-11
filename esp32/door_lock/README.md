# ESP32 Door Lock Firmware

This folder contains the cleaned firmware source for the ESP32 door controller.
It preserves the current wiring and behavior:

- Relay: GPIO 18, active LOW, unlocked for 10 seconds.
- Exit/contact button: GPIO 19 to GND, using the internal pull-up.
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

## Exit Contact Wiring

For the SIBASS ZB2-BE101 dry contact, connect one contact terminal to ESP32
`GND` and the other contact terminal to GPIO `19`. The firmware configures GPIO
19 as `INPUT_PULLUP`: it reads HIGH while open and LOW when the contact closes.
Do not connect an external voltage to this contact input. One press unlocks the
relay for 10 seconds; the contact must release before another press is accepted.

## OTA

After the first USB upload, the ESP32 connects to Wi-Fi and starts ArduinoOTA.
The Pi and ESP32 must be on the same network. In Arduino IDE, select the ESP32
network port and upload the next firmware version wirelessly.

The current repository does not yet host a compiled firmware endpoint. The next
step is to build `door_lock.bin` and place it on the Pi at
`data/esp32/door_lock.bin`. Put the shared token in the Pi's ignored local file
`data/esp32/update_token` and set the same value as `PI_UPDATE_TOKEN` in local
`secrets.h`. Then increase
`FirmwareVersion` before uploading the new firmware once over Arduino IDE OTA
or USB. The ESP32 checks the Pi at boot and every ten minutes.

Do not change relay behavior until the physical lock wiring has been tested.
