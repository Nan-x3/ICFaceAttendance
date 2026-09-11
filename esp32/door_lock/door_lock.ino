#include <Arduino.h>
#include <Keypad.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include "secrets.h"

namespace Pins {
constexpr uint8_t Relay = 18;
constexpr uint8_t ExitButton = 19;
byte KeypadRows[] = {13, 12, 14, 27};
byte KeypadColumns[] = {26, 25, 33, 32};
}

namespace DisplayConfig {
constexpr uint8_t Width = 128;
constexpr uint8_t Height = 64;
constexpr int8_t Reset = -1;
constexpr uint8_t Address = 0x3C;
}

constexpr unsigned long UnlockDurationMs = 10000;
constexpr unsigned long ButtonDebounceMs = 50;
constexpr unsigned long FirmwareCheckIntervalMs = 10UL * 60UL * 1000UL;
const char* FirmwareVersion = "0.1.0";
const char* GuestFile = "/guests.json";
unsigned long lastFirmwareCheck = 0;
unsigned long lastButtonChange = 0;
bool lastButtonState = HIGH;
bool buttonArmed = true;

Adafruit_SSD1306 display(
    DisplayConfig::Width,
    DisplayConfig::Height,
    &Wire,
    DisplayConfig::Reset
);

const byte KeypadRows = 4;
const byte KeypadColumns = 4;
char keypadKeys[KeypadRows][KeypadColumns] = {
    {'D', 'C', 'B', 'A'},
    {'#', '9', '6', '3'},
    {'0', '8', '5', '2'},
    {'*', '7', '4', '1'}
};
Keypad keypad = Keypad(makeKeymap(keypadKeys), Pins::KeypadRows,
                       Pins::KeypadColumns, KeypadRows, KeypadColumns);

String enteredPin;

void showLocked() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(2);
    display.setCursor(28, 24);
    display.println("LOCKED");
    display.display();
}

void showTyping() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(10, 4);
    display.println("Enter PIN / Roll No:");

    String stars;
    for (size_t index = 0; index < enteredPin.length(); index++) {
        stars += '*';
    }

    display.setTextSize(2);
    int cursorX = (DisplayConfig::Width - static_cast<int>(stars.length()) * 12) / 2;
    display.setCursor(max(cursorX, 0), 30);
    display.println(stars);
    display.setTextSize(1);
    display.setCursor(50, 54);
    display.println(String(enteredPin.length()) + " chars");
    display.display();
}

void showBooting() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(2);
    display.setCursor(10, 10);
    display.println("IC LOCK");
    display.setTextSize(1);
    display.setCursor(28, 36);
    display.println("Booting...");
    display.display();
}

void showAccessGranted(String name) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(2);
    display.setCursor(18, 4);
    display.println("ENTER!");
    display.setTextSize(1);
    display.setCursor(10, 28);
    display.println(name.substring(0, min(name.length(), static_cast<unsigned int>(18))));
    display.setTextSize(2);
    display.setCursor(48, 44);
    display.println("OK");
    display.display();
}

void showWrongPin() {
    display.clearDisplay();
    display.fillRect(0, 0, DisplayConfig::Width, DisplayConfig::Height, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setTextSize(2);
    display.setCursor(22, 6);
    display.println("WRONG");
    display.setCursor(30, 28);
    display.println("PIN!");
    display.setTextSize(3);
    display.setCursor(52, 42);
    display.println("X");
    display.display();
}

bool loadGuests(JsonDocument& document) {
    if (!SPIFFS.exists(GuestFile)) {
        File file = SPIFFS.open(GuestFile, FILE_WRITE);
        if (!file) return false;
        file.println("{}");
        file.close();
    }

    File file = SPIFFS.open(GuestFile, FILE_READ);
    if (!file) return false;
    DeserializationError error = deserializeJson(document, file);
    file.close();
    return !error;
}

bool saveGuests(JsonDocument& document) {
    File file = SPIFFS.open(GuestFile, FILE_WRITE);
    if (!file) return false;
    serializeJson(document, file);
    file.close();
    return true;
}

String lookupPin(const String& pin) {
    StaticJsonDocument<8192> document;
    if (!loadGuests(document) || !document.containsKey(pin)) return "";
    return document[pin].as<String>();
}

void addGuest(const String& pin, const String& name) {
    StaticJsonDocument<8192> document;
    if (loadGuests(document)) {
        document[pin] = name;
        saveGuests(document);
    }
}

void removeGuest(const String& pin) {
    StaticJsonDocument<8192> document;
    if (loadGuests(document)) {
        document.remove(pin);
        saveGuests(document);
    }
}

void listGuests() {
    StaticJsonDocument<8192> document;
    if (!loadGuests(document)) return;

    Serial.println("=== GUEST LIST ===");
    for (JsonPair guest : document.as<JsonObject>()) {
        Serial.println(String(guest.key().c_str()) + " -> " + guest.value().as<String>());
    }
    Serial.println("==================");
}

void unlockDoor(const String& name, const String& reason) {
    Serial.println("UNLOCKING: " + name + " (" + reason + ")");
    showAccessGranted(name);
    digitalWrite(Pins::Relay, LOW);
    delay(UnlockDurationMs);
    digitalWrite(Pins::Relay, HIGH);
    Serial.println("LOCKED");
    enteredPin = "";
    showLocked();
}

void handleSerialCommand(String command) {
    command.trim();

    if (command == "UNLOCK") {
        unlockDoor("Face ID", "Pi command");
    } else if (command.startsWith("ADD:")) {
        int separator = command.indexOf(':', 4);
        if (separator > 0) {
            addGuest(command.substring(4, separator), command.substring(separator + 1));
            Serial.println("ADDED");
        }
    } else if (command.startsWith("REMOVE:")) {
        removeGuest(command.substring(7));
        Serial.println("REMOVED");
    } else if (command == "LIST") {
        listGuests();
    } else {
        Serial.println("UNKNOWN: " + command);
    }
}

void configureOta() {
    ArduinoOTA.setHostname(OTA_HOSTNAME);
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() {
        Serial.println("OTA START");
    });
    ArduinoOTA.onEnd([]() {
        Serial.println("OTA DONE");
    });
    ArduinoOTA.begin();
}

bool isNewerVersion(const String& remoteVersion) {
    int currentMajor = 0;
    int currentMinor = 0;
    int currentPatch = 0;
    int remoteMajor = 0;
    int remoteMinor = 0;
    int remotePatch = 0;

    if (sscanf(FirmwareVersion, "%d.%d.%d", &currentMajor, &currentMinor,
               &currentPatch) != 3 ||
        sscanf(remoteVersion.c_str(), "%d.%d.%d", &remoteMajor, &remoteMinor,
               &remotePatch) != 3) {
        return false;
    }

    if (remoteMajor != currentMajor) return remoteMajor > currentMajor;
    if (remoteMinor != currentMinor) return remoteMinor > currentMinor;
    return remotePatch > currentPatch;
}

void checkForPiFirmwareUpdate() {
    if (WiFi.status() != WL_CONNECTED ||
        String(PI_UPDATE_TOKEN) == "CHANGE_THIS_PI_UPDATE_TOKEN") {
        return;
    }

    WiFiClient client;
    HTTPClient http;
    String versionUrl = String(PI_VERSION_URL) + "?token=" + PI_UPDATE_TOKEN;
    if (!http.begin(client, versionUrl)) return;

    int responseCode = http.GET();
    if (responseCode != HTTP_CODE_OK) {
        http.end();
        return;
    }

    StaticJsonDocument<256> document;
    DeserializationError error = deserializeJson(document, http.getString());
    http.end();
    if (error || !document.containsKey("version")) return;

    String remoteVersion = document["version"].as<String>();
    if (!isNewerVersion(remoteVersion)) return;

    Serial.println("Firmware update available: " + remoteVersion);
    HTTPUpdate httpUpdate;
    String firmwareUrl = String(PI_FIRMWARE_URL) + "?token=" + PI_UPDATE_TOKEN;
    HTTPUpdateResult updateResult = httpUpdate.update(client, firmwareUrl, FirmwareVersion);
    if (updateResult != HTTP_UPDATE_OK && updateResult != HTTP_UPDATE_NO_UPDATES) {
        Serial.println("Firmware update failed: " + String(updateResult));
    }
}

void setup() {
    pinMode(Pins::Relay, OUTPUT);
    digitalWrite(Pins::Relay, HIGH);
    pinMode(Pins::ExitButton, INPUT_PULLUP);
    Serial.begin(9600);

    if (!display.begin(SSD1306_SWITCHCAPVCC, DisplayConfig::Address)) {
        Serial.println("OLED failed");
    } else {
        showBooting();
    }

    if (!SPIFFS.begin(true)) {
        Serial.println("SPIFFS failed");
    }

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    unsigned int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("WiFi: " + WiFi.localIP().toString());
        configureOta();
        checkForPiFirmwareUpdate();
        lastFirmwareCheck = millis();
    } else {
        Serial.println("WiFi: offline (PIN and serial only)");
    }

    showLocked();
    Serial.println("IC DoorLock Ready");
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        ArduinoOTA.handle();
        if (millis() - lastFirmwareCheck >= FirmwareCheckIntervalMs) {
            checkForPiFirmwareUpdate();
            lastFirmwareCheck = millis();
        }
    }

    if (Serial.available()) {
        handleSerialCommand(Serial.readStringUntil('\n'));
    }

    char key = keypad.getKey();
    bool buttonState = digitalRead(Pins::ExitButton);
    if (buttonState != lastButtonState) {
        lastButtonChange = millis();
        lastButtonState = buttonState;
    }

    if (buttonState == HIGH && millis() - lastButtonChange >= ButtonDebounceMs) {
        buttonArmed = true;
    }

    if (buttonState == LOW && buttonArmed &&
        millis() - lastButtonChange >= ButtonDebounceMs) {
        unlockDoor("Exit Button", "GPIO 19");
        buttonArmed = false;
        lastButtonChange = millis();
    }

    if (!key) return;

    if (key == '#') {
        if (enteredPin.length() == 0) return;

        String name = lookupPin(enteredPin);
        if (name.length() > 0) {
            unlockDoor(name, "PIN/Roll");
        } else {
            showWrongPin();
            delay(2000);
            enteredPin = "";
            showLocked();
        }
    } else if (key == '*') {
        enteredPin = "";
        showLocked();
    } else {
        enteredPin += key;
        showTyping();
    }
}
