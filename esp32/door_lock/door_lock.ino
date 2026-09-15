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
#include "firmware_config.h"
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
#ifndef FIRMWARE_VERSION
#define FIRMWARE_VERSION "0.2.0"
#endif
const char* FirmwareVersion = FIRMWARE_VERSION;
const char* GuestFile = "/guests.json";
unsigned long lastFirmwareCheck = 0;
unsigned long lastButtonChange = 0;
unsigned long lastIdleFrame = 0;
uint8_t idleFrame = 0;
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

void renderLocked(uint8_t frame) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.drawRoundRect(47, 28, 34, 27, 5, SSD1306_WHITE);
    display.drawRoundRect(54, 12, 20, 27, 9, SSD1306_WHITE);
    display.fillRect(59, 25, 10, 14, SSD1306_BLACK);
    display.fillCircle(64, 39, 3, SSD1306_WHITE);
    display.drawLine(64, 39, 64, 47, SSD1306_WHITE);
    display.fillCircle(45 + (frame % 5) * 10, 20, 1, SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(43, 57);
    display.println("LOCKED");
    display.display();
}

void showLocked() {
    idleFrame = 0;
    renderLocked(idleFrame);
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
    for (uint8_t frame = 0; frame < 5; frame++) {
        display.clearDisplay();
        display.setTextColor(SSD1306_WHITE);
        display.setTextSize(2);
        display.setCursor(10, 10);
        display.println("IC LOCK");
        display.setTextSize(1);
        display.setCursor(28, 36);
        display.println("Booting...");
        display.drawRect(20, 51, 88, 7, SSD1306_WHITE);
        display.fillRect(22, 53, 17 * (frame + 1), 3, SSD1306_WHITE);
        display.display();
        delay(100);
    }
}

void showAccessGranted(String name) {
    int separator = name.indexOf(' ');
    String firstName = separator > 0 ? name.substring(0, separator) : name;
    firstName.trim();
    firstName = firstName.substring(0, min(firstName.length(), static_cast<unsigned int>(12)));

    for (int frame = 0; frame < 6; frame++) {
        display.clearDisplay();
        display.setTextColor(SSD1306_WHITE);
        display.drawCircle(64, 27, 18 + frame * 4, SSD1306_WHITE);
        if (frame >= 2) {
            display.drawCircle(64, 27, 12, SSD1306_WHITE);
        }
        display.drawLine(53, 27, 61, 35, SSD1306_WHITE);
        display.drawLine(61, 35, 76, 18, SSD1306_WHITE);
        display.setTextSize(1);
        int textX = (DisplayConfig::Width - static_cast<int>(firstName.length()) * 6) / 2;
        display.setCursor(max(textX, 0), 52);
        display.println(firstName);
        display.display();
        delay(90);
    }
}

void showWrongPin() {
    for (uint8_t frame = 0; frame < 3; frame++) {
        display.clearDisplay();
        display.fillRect(0, 0, DisplayConfig::Width, DisplayConfig::Height,
                         frame % 2 == 0 ? SSD1306_WHITE : SSD1306_BLACK);
        display.setTextColor(frame % 2 == 0 ? SSD1306_BLACK : SSD1306_WHITE);
        display.setTextSize(2);
        display.setCursor(22, 6);
        display.println("WRONG");
        display.setCursor(30, 28);
        display.println("PIN!");
        display.setTextSize(3);
        display.setCursor(52, 42);
        display.println("X");
        display.display();
        delay(100);
    }
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
    } else if (command.startsWith("UNLOCK:")) {
        String name = command.substring(7);
        name.trim();
        unlockDoor(name.length() > 0 ? name : "Face ID", "Pi command");
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

bool fetchTextFromUrl(const String& url, String& responseText) {
    WiFiClient client;
    HTTPClient http;
    if (!http.begin(client, url)) {
        return false;
    }

    int responseCode = http.GET();
    if (responseCode != HTTP_CODE_OK) {
        http.end();
        return false;
    }

    responseText = http.getString();
    http.end();
    responseText.trim();
    return !responseText.isEmpty();
}

bool checkForFirmwareUpdateFromSource(const String& sourceName,
                                     const String& versionUrl,
                                     const String& firmwareUrl,
                                     const String& authSuffix) {
    String remoteVersion;
    String versionEndpoint = versionUrl + authSuffix;
    if (!fetchTextFromUrl(versionEndpoint, remoteVersion)) {
        return false;
    }

    if (!isNewerVersion(remoteVersion)) {
        return false;
    }

    Serial.println("Firmware update available from " + sourceName + ": " + remoteVersion);
    HTTPUpdate httpUpdate;
    WiFiClient updateClient;
    String firmwareEndpoint = firmwareUrl + authSuffix;
    HTTPUpdateResult updateResult = httpUpdate.update(updateClient, firmwareEndpoint, FirmwareVersion);
    if (updateResult != HTTP_UPDATE_OK && updateResult != HTTP_UPDATE_NO_UPDATES) {
        Serial.println("Firmware update failed from " + sourceName + ": " + String(updateResult));
        return false;
    }

    return true;
}

void checkForPiFirmwareUpdate() {
    if (WiFi.status() != WL_CONNECTED ||
        String(PI_UPDATE_TOKEN) == "CHANGE_THIS_PI_UPDATE_TOKEN") {
        return;
    }

    String authSuffix = "?token=" + String(PI_UPDATE_TOKEN);
    checkForFirmwareUpdateFromSource("Pi", String(PI_VERSION_URL), String(PI_FIRMWARE_URL), authSuffix);
}

void checkForGitHubFirmwareUpdate() {
    if (WiFi.status() != WL_CONNECTED) {
        return;
    }

    bool updateChecked = checkForFirmwareUpdateFromSource(
        "GitHub",
        String(GITHUB_VERSION_URL),
        String(GITHUB_FIRMWARE_URL),
        ""
    );

    if (!updateChecked) {
        checkForPiFirmwareUpdate();
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

    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.setAutoReconnect(true);
    WiFi.persistent(false);
    Serial.printf("[WiFi] connecting to SSID: %s\n", WIFI_SSID);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    unsigned int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        Serial.printf("[WiFi] attempt %u/30 status=%d\n", attempts + 1, WiFi.status());
        delay(500);
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("WiFi: " + WiFi.localIP().toString());
        configureOta();
        checkForGitHubFirmwareUpdate();
        lastFirmwareCheck = millis();
    } else {
        Serial.printf("[WiFi] failed to connect to %s; final status=%d\n", WIFI_SSID, WiFi.status());
        Serial.println("WiFi: offline (PIN and serial only)");
    }

    showLocked();
    Serial.println("IC DoorLock Ready");
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        ArduinoOTA.handle();
        if (millis() - lastFirmwareCheck >= FirmwareCheckIntervalMs) {
            checkForGitHubFirmwareUpdate();
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

    if (!enteredPin.length() && millis() - lastIdleFrame >= 700) {
        lastIdleFrame = millis();
        idleFrame = (idleFrame + 1) % 8;
        renderLocked(idleFrame);
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
