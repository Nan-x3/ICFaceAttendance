# ESP32 Door Lock Firmware

This folder contains the cleaned firmware source for the ESP32 door controller.
It preserves the current wiring and behavior:

- Relay: GPIO 18, active LOW, unlocked for 10 seconds.
- PIR motion sensor output: GPIO 19, active HIGH, using the internal pull-down.
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

## Firmware Update Timing

Edit `firmware_config.h` to control how often the ESP32 checks the Pi for a
new firmware build:

```cpp
constexpr unsigned long FirmwareCheckIntervalMinutes = 10;
```

Use a longer interval for deployed devices to reduce network and power usage.
The ESP32 also checks immediately after boot when Wi-Fi connects.

## Commands From The Raspberry Pi

The Pi sends newline-terminated commands:

- `UNLOCK`: unlocks the relay for 10 seconds.
- `UNLOCK:<name>`: unlocks the relay and shows the person's first name.
- `ADD:<pin>:<name>`: adds a keypad credential.
- `REMOVE:<pin>`: removes a keypad credential.
- `LIST`: prints all keypad credentials.

## PIR Motion Sensor Wiring

Connect the PIR module's `OUT` to GPIO `19` and connect its `GND` to ESP32 `GND`.
Power the module according to its specifications. The firmware configures GPIO
19 as `INPUT_PULLDOWN` and unlocks for 10 seconds when the output remains HIGH
for 50 ms. The output must return LOW before another trigger is accepted.

ESP32 GPIOs are not 5 V tolerant. Verify that the PIR `OUT` signal is no more
than 3.3 V; use a suitable level shifter if the module outputs 5 V. PIR sensors
detect movement, not a person's continued presence, and firmware cannot set
their detection distance to exactly 30 cm. Adjust the sensor's range control if
it has one and test its actual detection zone; use a short-range proximity
sensor instead if a reliable 30 cm threshold is required.

## OTA

After the first USB upload, the ESP32 connects to Wi-Fi and starts ArduinoOTA.
The Pi and ESP32 must be on the same network. In Arduino IDE, select the ESP32
network port and upload the next firmware version wirelessly.

GitHub Actions builds and publishes `door_lock.bin` and `firmware-version.txt`
for the `firmware-latest` release. The ESP32 checks GitHub first at boot and on
its configured interval, which avoids a dependency on a running Flask app. The
Pi endpoint remains as a fallback for local-only deployments or private testing.

Set the repo-specific URLs in local `secrets.h` and keep `PI_UPDATE_TOKEN` only
if you want the Pi fallback to be active. The default GitHub URLs are already in
`secrets.example.h`.

Do not change relay behavior until the physical lock wiring has been tested.
