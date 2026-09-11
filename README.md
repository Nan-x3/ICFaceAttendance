# FaceAttend

FaceAttend is a Raspberry Pi attendance and door-unlock system. It uses a camera for face recognition and QR scanning, stores attendance, and sends `UNLOCK` to an ESP32 door controller.

## Safety Rule

Only QR values listed in `users_directory.json` can unlock the door. Unknown QR values are ignored. The website has no login system, so keep it on a trusted local network.

## Important Files

- `app.py`: Flask server, camera, QR scanner, face recognition, and ESP32 control.
- `recognition_engine.py`: Builds and searches face encodings.
- `register_worker.py`: Processes face photos separately from Flask.
- `attendance.py`: Stores people and attendance in SQLite.
- `config.py`: Camera, timing, recognition, and storage settings.
- `guest_manager.py`: Optional ESP32 user-management and lock-test tool.
- `setup_pi.sh`: Raspberry Pi installer.
- `templates/` and `static/`: Website pages, CSS, and JavaScript.
- `users_directory.json`: QR text mapped to person names.
- `face_recognition_models`: Git submodule containing recognition models.
- `esp32/door_lock/`: cleaned ESP32 firmware source, wiring notes, and OTA instructions.

The unused `live_tuner.py` and `tracker.py` modules were removed.

The ESP32 firmware also supports an exit/contact button on GPIO 19. Wire the
dry contact between GPIO 19 and GND; the firmware uses the internal pull-up.

## Install On A New Raspberry Pi

1. Open Terminal on the Pi, or connect over SSH.
2. Install Git: `sudo apt-get update && sudo apt-get install -y git`.
3. Download the project: `git clone https://github.com/Nan-x3/ICFaceAttendance.git && cd ICFaceAttendance`.
4. Install everything: `chmod +x setup_pi.sh && ./setup_pi.sh`.
5. Start the app: `source venv/bin/activate && python app.py`.
6. Find the Pi address with `hostname -I` and open `http://PI_IP_ADDRESS:5000` on the same network.

The installer adds camera support, OpenCV, Flask, dlib, and face recognition. Building dlib can take a long time. Do not close the terminal.

## Register A Person

### Face registration

1. Open the **Register** page.
2. Type the person's full name.
3. Capture at least 3 clear photos. Five photos from different angles is better.
4. Make sure exactly one face is visible in every photo.
5. Click **Register** and wait for success.

Photos are stored in `known_faces/`. Encodings are stored in `encodings/encodings.pkl`.

### QR-only registration

When all three identity values are available, a face is optional:

1. Type the person's name.
2. Show the QR to the camera. The **QR Code** field fills automatically.
3. Type the printed roll number in **Registration Number**.
4. Click **Register** without taking face photos.

This enables QR unlocking but does not create face-recognition data. The QR text may differ from the printed roll number, so store both values in `users_directory.json`:

`{"QR_TEXT_FROM_CARD": "Person Name", "2023003299": "Person Name"}`

## Face Photo Limit And Refresh

Each person can have at most **50 face photos**. When a new normal-registration or high-confidence automatic-learning photo arrives at the limit, the oldest photo is removed and the newest photo is kept. Encodings are rebuilt from the remaining files.

This keeps the model current with new haircuts, facial hair, glasses, and other appearance changes without filling the USB drive. Change `MAX_FACE_PHOTOS` in `config.py` only if you intentionally want a different limit.

## Use The Door

Point the camera at a registered QR. A successful scan prints `[+] Scanned QR ID: QR_VALUE -> Person Name` and `[Door] Sent UNLOCK command to ESP32.` Unknown values print `Ignoring unregistered QR ID` and cannot unlock. `ESP32 is not connected` means the Pi cannot reach the board.

Attendance has a cooldown to avoid duplicate rows. That cooldown does not stop a valid QR from unlocking again. Repeated camera frames are throttled.

## ESP32 Maintenance

Stop `app.py` first because only one program can use the serial port. Then run `source venv/bin/activate && python guest_manager.py`.

The tool can add students, add PIN users, remove users, list users, and test the lock. Its default port is `/dev/ttyUSB0`. Find ports with `ls /dev/ttyUSB* /dev/ttyACM*`. The ESP32 firmware must understand `UNLOCK` followed by a newline.

## ESP32 Firmware Handoff

The ESP32 source is in `esp32/door_lock/`:

- `door_lock.ino`: firmware source.
- `secrets.example.h`: safe template for local Wi-Fi and OTA settings.
- `README.md`: wiring, library, USB upload, and OTA instructions.
- `secrets.h`: real local credentials; ignored by Git and never uploaded.

The first firmware upload must be done over USB. After the ESP32 connects to
Wi-Fi, Arduino IDE can upload later firmware versions over OTA:

1. Copy `secrets.example.h` to `secrets.h` beside `door_lock.ino`.
2. Fill in the Wi-Fi name, Wi-Fi password, and OTA password.
3. Upload once over USB and confirm `IC DoorLock Ready` in Serial Monitor at 9600 baud.
4. Connect the computer and ESP32 to the same Wi-Fi network.
5. Select the ESP32 network port under Arduino IDE's **Tools > Port** menu.
6. Upload and enter the OTA password when asked.

### Pi-hosted automatic updates

The ESP32 can now check the Pi for a newer firmware build at boot and every 10
minutes. The Pi serves the binary only when the shared update token is correct.
GitHub Actions builds the binary on every firmware-related push, and the Pi's
sync timer downloads the latest published binary every five minutes.

To enable it:

1. Create `data/esp32/update_token` on the Pi. The application reads this ignored local file automatically.
2. Run `sudo systemctl enable --now faceattend-esp32-sync.timer` on the Pi.
3. Set the same token as `PI_UPDATE_TOKEN` in the ESP32's local `secrets.h`.
4. Push a firmware change to `main`. GitHub Actions builds and publishes `door_lock.bin`.
5. The Pi downloads the release automatically within five minutes.
6. The ESP32 downloads the newer binary on its next ten-minute check and reboots into it.

The Pi does not compile Arduino firmware. GitHub Actions does the build.
Arduino IDE OTA remains the recovery path if a Pi-hosted update fails.

## Website Pages

- `/`: Dashboard with live feed, totals, and recent events.
- `/register`: Face photos and QR mappings.
- `/attendance`: Attendance by date.
- `/kiosk`: Fullscreen display.

For a Pi monitor, run `chromium-browser --kiosk http://localhost:5000/kiosk`.

## Start On Boot

During `setup_pi.sh`, answer `y` when asked to create a systemd service. Use `sudo systemctl start face-attendance`, `sudo systemctl status face-attendance`, `sudo systemctl restart face-attendance`, or `sudo systemctl stop face-attendance`. View logs with `journalctl -u face-attendance -f`.

## Settings

Edit `config.py`, then restart the app. Important settings are `CAMERA_SOURCE`, `RECOGNITION_TOLERANCE`, `FRAME_SKIP`, `SCAN_COOLDOWN_SECONDS`, `SLEEP_AFTER_SECONDS`, `MOTION_THRESHOLD`, `MAX_FACE_PHOTOS` (default 50), and `MAX_REGISTRATION_PHOTOS`.

## Data And Backups

Git ignores `data/attendance.db`, `data/attendance.log`, `known_faces/`, and `encodings/`. These contain attendance records, logs, private face photos, and cached encodings.

Back up with `tar -czf faceattend-backup-$(date +%F).tar.gz data known_faces encodings users_directory.json`. Restore with `tar -xzf faceattend-backup-YYYY-MM-DD.tar.gz` inside the project folder. Face photos and encodings are biometric data; keep backups private.

## Update From GitHub

Stop the app, then run `cd ~/ICFaceAttendance && git pull origin main && source venv/bin/activate && python -m py_compile app.py && sudo systemctl restart face-attendance`. If the app was started manually, run `python app.py` again instead.

## Troubleshooting

- **Camera blank:** check the camera cable and `CAMERA_SOURCE`; try `libcamera-hello` for a Pi Camera.
- **Face not recognized:** use bright, even lighting and one face per photo; capture more photos.
- **No face during registration:** move closer, improve the light, and ensure exactly one face is visible.
- **QR visible but ignored:** read the exact decoded value in the Flask terminal and register that exact value. Tilt laminated cards to reduce glare, move closer, or use a phone screen.
- **QR recognized but lock closed:** `Sent UNLOCK command to ESP32` means Pi-to-serial worked; otherwise check USB, power, port, and firmware.

## API Reference

- `GET /video_feed`: camera stream.
- `GET /api/qr/latest`: recently decoded QR for registration.
- `GET /api/stats`: today's statistics.
- `GET /api/status`: recognition and sleep status.
- `GET /api/events`: recent events.
- `POST /api/register`: face or QR-only registration.
- `POST /api/delete_person`: remove face data, records, and QR mappings.
- `POST /api/recognition/toggle`: pause or resume recognition.
- `GET /export?start=YYYY-MM-DD&end=YYYY-MM-DD`: attendance CSV.

## Checks Before A Push

Run `python -m py_compile app.py attendance.py config.py recognition_engine.py register_worker.py`, then `git diff --check`. Do not commit `venv/`, face photos, encodings, the SQLite database, or logs.

Maintainer: [Nandith S Menon](https://github.com/Nan-x3)