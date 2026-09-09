# 🎯 Face Recognition Attendance System

A real-time face recognition attendance system built for Raspberry Pi deployment. Detects registered faces via webcam, automatically logs IN/OUT attendance with a per-person cooldown, and provides a web dashboard accessible from any device on the network.

---

## 📸 Features

| Feature | Description |
|---------|-------------|
| **Real-time Face Recognition** | Detects and identifies faces from a live camera feed using dlib's deep learning model |
| **Auto IN/OUT Logging** | Alternates between IN and OUT for each person with a configurable cooldown (default 30s) |
| **Per-Person Cooldown** | The 30-second cooldown is per-person — multiple people can scan simultaneously |
| **Web Dashboard** | Live camera feed, attendance table, stats, and event ticker accessible from any browser |
| **Kiosk Mode** | Fullscreen display mode (`/kiosk`) designed for a monitor attached to the Pi |
| **Motion Sleep/Wake** | Auto-sleeps after 30s of no motion to save CPU; wakes instantly when someone approaches |
| **Pause Recognition** | Pausing stops the camera entirely — shows a static "Paused" screen |
| **Auto-Pause During Registration** | Recognition pauses automatically while a new person is being registered |
| **Subprocess Registration** | Face registration runs in an isolated subprocess — if dlib crashes, the server stays alive |
| **File Logging** | All attendance events logged to `data/attendance.log` for remote monitoring |
| **CSV Export** | Export attendance data as CSV for any date range |
| **Raspberry Pi Ready** | Includes setup script, systemd service, and Pi Camera Module support |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Flask Web Server (app.py)               │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Camera   │→│  Recognition │→│  Attendance DB (SQLite) │ │
│  │  Feed     │  │  Engine      │  │  - mark_attendance()   │ │
│  │  (MJPEG)  │  │  (dlib/HOG)  │  │  - auto IN/OUT toggle  │ │
│  └──────────┘  └──────────────┘  └────────────────────────┘ │
│       │              │                      │                │
│       │         ┌────┴────┐           ┌─────┴─────┐         │
│       │         │ Motion  │           │ File      │         │
│       │         │ Detect  │           │ Logger    │         │
│       │         │ (sleep/ │           │ (.log)    │         │
│       │         │  wake)  │           └───────────┘         │
│       │         └─────────┘                                  │
│       ↓                                                      │
│  ┌───────────────────────────────────────────────────┐      │
│  │              Web Interface (Jinja2)                │      │
│  │  /          → Dashboard (stats + live feed)        │      │
│  │  /kiosk     → Fullscreen Pi monitor display        │      │
│  │  /register  → Face registration UI                 │      │
│  │  /attendance→ Historical attendance records        │      │
│  └───────────────────────────────────────────────────┘      │
│                                                              │
│  ┌───────────────────────────────────────────────────┐      │
│  │          Registration Subprocess                   │      │
│  │  register_worker.py (isolated dlib process)        │      │
│  └───────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | Flask 3.x | Web server, API endpoints, MJPEG streaming |
| **Face Detection** | dlib (HOG model) | Fast CPU-based face detection |
| **Face Recognition** | face_recognition (dlib) | 128-dimension face encoding & matching |
| **Computer Vision** | OpenCV 4.x | Camera capture, image processing, drawing overlays |
| **Database** | SQLite3 | Attendance records, registered persons |
| **Frontend** | HTML/CSS/JS (Jinja2) | Dashboard, kiosk display, registration UI |
| **Logging** | Python `logging` | File-based attendance event logging |
| **Camera (Pi)** | Picamera2 | Raspberry Pi Camera Module support |

---

## 📁 Project Structure

```
face_attendance/
├── app.py                    # Main Flask application + MJPEG stream generator
├── attendance.py             # SQLite database operations (AttendanceDB class)
├── recognition_engine.py     # Face encoding, matching, registration (FaceRecognitionEngine)
├── register_worker.py        # Subprocess worker for isolated dlib registration
├── config.py                 # All configurable settings
├── tracker.py                # Centroid tracker (legacy, not currently active)
├── requirements.txt          # Python dependencies
├── setup_pi.sh               # Raspberry Pi automated setup script
├── .gitignore                # Excludes data/, known_faces/, encodings/
│
├── templates/
│   ├── base.html             # Base template with nav and shared styles
│   ├── index.html            # Dashboard — live feed, stats, attendance table
│   ├── register.html         # Face registration — capture photos, submit
│   ├── attendance.html       # Historical attendance with date picker
│   └── kiosk.html            # Fullscreen Pi display — camera + events sidebar
│
├── static/
│   ├── css/style.css         # Global styles (dark theme, glassmorphism)
│   └── js/main.js            # Client-side JS (registration flow)
│
├── data/                     # (gitignored) Runtime data
│   ├── attendance.db         # SQLite database
│   └── attendance.log        # Timestamped event log
│
├── known_faces/              # (gitignored) Registered face images
│   └── <PersonName>/         # Folder per person with .jpg photos
│
└── encodings/                # (gitignored) Cached face encodings
    └── encodings.pkl         # Pickled dict of encodings + names
```

---

## 🚀 Setup & Installation

### Prerequisites

- **Python 3.9+**
- **CMake** (required by dlib)
- **A webcam** (USB or Pi Camera Module)

### Windows / Linux (Development)

```bash
# 1. Clone the repository
git clone https://github.com/Nan-x3/FaceAttendace.git
cd FaceAttendace

# 2. Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the server
python app.py
```

> **Note**: `dlib` requires CMake and a C++ compiler. On Windows, install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/). On Linux: `sudo apt install cmake build-essential`.

### Raspberry Pi (Production)

```bash
# 1. Clone the repository
git clone https://github.com/Nan-x3/FaceAttendace.git
cd FaceAttendace

# 2. Run the automated setup script
chmod +x setup_pi.sh
./setup_pi.sh
```

The setup script will:
- Install all system dependencies (cmake, libatlas, picamera2, etc.)
- Create a Python virtual environment with system site packages
- Temporarily increase swap to 2GB for dlib compilation (~30-90 min)
- Install all Python packages
- Switch config to Pi Camera (`picamera2`)
- Optionally create a systemd service for auto-start on boot

### After Setup

Open in your browser:
```
http://localhost:5000        # From the same machine
http://<device-ip>:5000     # From any device on the network
```

---

## 📖 Usage Guide

### 1. Register a Person

1. Navigate to `/register`
2. Enter the person's name
3. Capture **3–10 photos** from different angles (the camera feed is shown)
4. Click **Register** — the system processes photos in the background
5. Recognition is automatically paused during registration and resumes after

> **Tip**: Take photos from slightly different angles and with different expressions for better accuracy. Avoid having multiple people in frame.

### 2. Attendance Tracking

Once registered, simply walk in front of the camera:

| Event | What happens |
|-------|-------------|
| **First scan of the day** | Logged as **→ IN** |
| **Same person within 30s** | **Ignored** (cooldown) |
| **Same person after 30s** | Logged as **← OUT** (alternates automatically) |
| **Different person** | Logged immediately (cooldown is per-person) |

### 3. Viewing Attendance

| Page | URL | Description |
|------|-----|-------------|
| **Dashboard** | `/` | Live feed, today's stats, recent events |
| **Kiosk** | `/kiosk` | Fullscreen Pi display — camera + events sidebar |
| **History** | `/attendance?date=2026-03-23` | View attendance for any date |
| **Export** | `/export?start=2026-03-01&end=2026-03-31` | Download CSV |

### 4. Kiosk Mode (Pi Monitor)

For a monitor connected to the Pi, open Chromium in kiosk mode:

```bash
chromium-browser --kiosk http://localhost:5000/kiosk
```

The kiosk display shows:
- Live camera feed (left)
- Clock, IN/OUT/Today stats, and scrolling event cards (right)
- Active/Sleeping status indicator

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/video_feed` | MJPEG camera stream |
| `GET` | `/api/stats` | Today's stats (present, in, out, registered) |
| `GET` | `/api/status` | System status (sleeping, recognition active, etc.) |
| `GET` | `/api/events` | Last 10 IN/OUT events (real-time) |
| `GET` | `/api/attendance/today` | Today's full attendance records |
| `GET` | `/api/logs?n=50` | Last N lines from the log file |
| `POST` | `/api/register` | Register a new face (JSON: `{name, images[]}`) |
| `POST` | `/api/recognition/toggle` | Pause/resume recognition |
| `POST` | `/api/delete_person` | Delete a registered person (JSON: `{name}`) |
| `GET` | `/export?start=&end=` | Export attendance as CSV |

---

## ⚙️ Configuration

All settings are in `config.py`:

### Camera

| Setting | Default | Description |
|---------|---------|-------------|
| `CAMERA_SOURCE` | `0` | `0` for USB webcam, `"picamera2"` for Pi Camera |
| `CAMERA_RESOLUTION` | `(640, 480)` | Frame resolution |
| `FRAME_RATE` | `24` | Target FPS for the MJPEG stream |

### Face Recognition

| Setting | Default | Description |
|---------|---------|-------------|
| `FACE_DETECTION_MODEL` | `"hog"` | `"hog"` (fast, CPU) or `"cnn"` (accurate, GPU) |
| `RECOGNITION_TOLERANCE` | `0.5` | Lower = stricter. Range: 0.3 (strict) to 0.7 (lenient) |
| `FRAME_SKIP` | `2` | Process every Nth frame (higher = faster) |
| `FACE_DETECTION_SCALE` | `0.25` | Downscale factor (0.25 = quarter res, much faster) |

### Attendance

| Setting | Default | Description |
|---------|---------|-------------|
| `SCAN_COOLDOWN_SECONDS` | `30` | Per-person cooldown before next scan counts |

### Motion Detection

| Setting | Default | Description |
|---------|---------|-------------|
| `SLEEP_AFTER_SECONDS` | `30` | Seconds of no motion before sleeping |
| `MOTION_THRESHOLD` | `2000` | Motion sensitivity (lower = more sensitive) |

### Registration

| Setting | Default | Description |
|---------|---------|-------------|
| `MIN_REGISTRATION_PHOTOS` | `3` | Minimum photos required |
| `MAX_REGISTRATION_PHOTOS` | `20` | Maximum photos processed |

---

## 📋 Logging

### Log File

All attendance events are written to `data/attendance.log`:

```
2026-03-23 10:10:12 | -> IN: Nandith (74%)
2026-03-23 10:11:45 | <- OUT: Nandith (69%)
2026-03-23 10:11:47 | -> IN: Raj (82%)
2026-03-23 10:42:00 | SLEEP - no motion
2026-03-23 10:43:15 | WAKE - motion detected
```

### Monitoring Logs

**On Raspberry Pi (SSH):**
```bash
tail -f data/attendance.log
```

**On Windows (PowerShell):**
```powershell
Get-Content data\attendance.log -Wait -Tail 20
```

**Via API (from any device):**
```
http://<device-ip>:5000/api/logs?n=50
```

---

## 🍓 Raspberry Pi Performance Notes

| Spec | Pi 5 (8GB) | Pi 4 (4GB) |
|------|-----------|-----------|
| Face detection per frame | ~0.8–1.5s | ~2–3s |
| Recognition matching | ~0.2s | ~0.5s |
| Effective FPS | 1–2 | ~0.5 |
| Registration (5 photos) | ~30–60s | ~1–2 min |
| Max registered faces | ~50 people | ~30 people |

### Optimization Tips for Pi

1. **Use HOG model** (default) — CNN is too slow without a GPU
2. **Increase `FRAME_SKIP`** to 3 or 4 — reduces CPU usage
3. **Keep `FACE_DETECTION_SCALE` at 0.25** — quarter resolution is much faster
4. **Limit registration photos** to 5–7 — more photos = slower matching
5. **Motion sleep/wake** saves significant CPU when nobody is around
6. **Use `opencv-python-headless`** on Pi — no GUI dependencies needed

---

## 🔄 OTA Updates (Remote Deployment)

Once the Pi is on the network, push updates without physically touching it:

```bash
# From the Pi (via SSH):
cd /path/to/FaceAttendace
git pull origin main
sudo systemctl restart face-attendance
```

Or automate with a cron job:
```bash
# Check for updates every hour
0 * * * * cd /path/to/FaceAttendace && git pull origin main && sudo systemctl restart face-attendance
```

---

## 🛡️ Best Practices

### Registration
- Take **5–7 photos** from different angles (front, slight left, slight right)
- Ensure **only one face** is clearly visible per photo
- Good lighting significantly improves recognition accuracy
- Remove glasses for some photos if the person wears them sometimes

### Deployment
- Mount the camera at **face height** (~150cm) for best detection
- Ensure **consistent lighting** — avoid backlighting (windows behind subjects)
- Change `SECRET_KEY` in `config.py` before deploying to production
- Set up the **systemd service** so the system auto-starts after power outages
- Use a **wired ethernet connection** instead of WiFi for reliability

### Database
- The SQLite database is stored in `data/attendance.db`
- Back up regularly: `cp data/attendance.db data/attendance_backup_$(date +%F).db`
- Export attendance regularly via the `/export` endpoint for external records
- The database is lightweight and can handle thousands of records

### Security
- The web interface has **no authentication** by default — it trusts the local network
- For production, consider adding a simple password or restricting access via firewall rules
- Face data (images + encodings) is stored locally and never leaves the device

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Server crashes during registration** | Registration runs in a subprocess — if dlib segfaults, the server shows an error but stays alive. Try with fewer photos (3–5). |
| **Low recognition accuracy** | Add more registration photos from different angles. Lower `RECOGNITION_TOLERANCE` to 0.45 for stricter matching. |
| **Camera not detected** | Check `CAMERA_SOURCE` in config.py. Use `0` for USB webcam, `"picamera2"` for Pi Camera. |
| **Slow on Raspberry Pi** | Increase `FRAME_SKIP` to 4, ensure `FACE_DETECTION_SCALE` is 0.25, use HOG model. |
| **"No face detected" during registration** | Ensure one face is clearly visible, good lighting, no obstructions. Avoid multiple people in frame. |
| **Sleep mode too sensitive / not sensitive enough** | Adjust `MOTION_THRESHOLD` in config.py (lower = more sensitive). |
| **dlib won't install** | Install CMake and C++ build tools first. On Pi, the setup script handles this. |

---

## 📄 License

This project is developed for internal use at Innovation Centre.

---

## 👥 Contributors

- **Nandith S Menon** ([@Nan-x3](https://github.com/Nan-x3)) — Development & Architecture
