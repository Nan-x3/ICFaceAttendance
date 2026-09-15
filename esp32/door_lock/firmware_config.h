#pragma once

// How often the ESP32 checks the Raspberry Pi for a newer firmware build.
constexpr unsigned long FirmwareCheckIntervalMinutes = 10;
constexpr unsigned long FirmwareCheckIntervalMs =
    FirmwareCheckIntervalMinutes * 60UL * 1000UL;
