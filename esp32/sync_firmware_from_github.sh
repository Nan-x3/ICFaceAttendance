#!/bin/bash
set -euo pipefail

REPO="Nan-x3/ICFaceAttendance"
RELEASE_TAG="firmware-latest"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="$PROJECT_DIR/data/esp32"
BASE_URL="https://github.com/$REPO/releases/download/$RELEASE_TAG"
CACHE_BUSTER="?cache_bust=$(date +%s)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TARGET_DIR"
curl --fail --location --silent --show-error \
    "$BASE_URL/door_lock.bin$CACHE_BUSTER" \
    --output "$TMP_DIR/door_lock.bin"
curl --fail --location --silent --show-error \
    "$BASE_URL/firmware-version.txt$CACHE_BUSTER" \
    --output "$TMP_DIR/firmware-version.txt"

test -s "$TMP_DIR/door_lock.bin"
test -s "$TMP_DIR/firmware-version.txt"

install -m 0644 "$TMP_DIR/door_lock.bin" "$TARGET_DIR/door_lock.bin"
install -m 0644 "$TMP_DIR/firmware-version.txt" "$TARGET_DIR/firmware-version.txt"
printf 'ESP32 firmware synced: %s\n' "$(tr -d '\r\n' < "$TARGET_DIR/firmware-version.txt")"
