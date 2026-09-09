"""
Configuration for Face Recognition Attendance System.
Adjust these settings for your environment (Windows dev vs Raspberry Pi).
"""
import os

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------
# Camera Settings
# ---------------------
# 0 = default USB/laptop webcam (Windows/Linux)
# "picamera2" = Raspberry Pi Camera Module
CAMERA_SOURCE = "picamera2"
CAMERA_RESOLUTION = (640, 480)
FRAME_RATE = 24

# ---------------------
# Face Recognition
# ---------------------
# "hog" = faster, good for RPi CPU  |  "cnn" = more accurate, needs GPU
FACE_DETECTION_MODEL = "hog"
# Lower = stricter matching. 0.5 is a good default. Range: 0.3 (very strict) to 0.7 (lenient)
RECOGNITION_TOLERANCE = 0.5
# Process every Nth frame (higher = faster, lower = more responsive)
FRAME_SKIP = 2
# Downscale factor for face detection (0.25 = quarter resolution, much faster)
FACE_DETECTION_SCALE = 0.25

# ---------------------
# File Paths
# ---------------------
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
ENCODINGS_FILE = os.path.join(BASE_DIR, "encodings", "encodings.pkl")
DATABASE_PATH = os.path.join(BASE_DIR, "data", "attendance.db")

# ---------------------
# Attendance Rules
# ---------------------
# Seconds before the same person can be scanned again (IN or OUT)
# After this cooldown, the next scan alternates direction automatically.
SCAN_COOLDOWN_SECONDS = 30

# ---------------------
# Flask Web Server
# ---------------------
FLASK_HOST = "0.0.0.0"   # 0.0.0.0 = accessible from LAN
FLASK_PORT = 5000
SECRET_KEY = "face-attendance-secret-change-this-on-pi"

# ---------------------
# Registration
# ---------------------
MIN_REGISTRATION_PHOTOS = 3
MAX_REGISTRATION_PHOTOS = 20

# ---------------------
# Motion Detection (Sleep/Wake)
# ---------------------
# Seconds of no motion before entering sleep mode (stops recognition)
SLEEP_AFTER_SECONDS = 30
# Motion sensitivity — lower = more sensitive. Range: 500–5000
MOTION_THRESHOLD = 2000
