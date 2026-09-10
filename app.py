"""
Face Recognition Attendance System — Flask Web Application.
Main entry point. Run with: python app.py
"""
import os
import cv2
import sys
import time
import json
import serial
import serial.tools.list_ports
import base64
import threading
import traceback
import tempfile
import subprocess
import logging
import numpy as np
from pyzbar.pyzbar import decode
from datetime import datetime
from io import BytesIO
from flask import (
    Flask, render_template, Response, request,
    jsonify, send_file
)
from config import (
    FLASK_HOST, FLASK_PORT, SECRET_KEY, CAMERA_SOURCE,
    CAMERA_RESOLUTION, FRAME_RATE, FRAME_SKIP, SCAN_COOLDOWN_SECONDS,
    SLEEP_AFTER_SECONDS, MOTION_THRESHOLD, KNOWN_FACES_DIR, MAX_FACE_PHOTOS
)
from recognition_engine import FaceRecognitionEngine
from attendance import AttendanceDB

# ── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── File Logger ──────────────────────────────────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'attendance.log')

file_logger = logging.getLogger('attendance')
file_logger.setLevel(logging.INFO)
fh = logging.FileHandler(log_file, encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
file_logger.addHandler(fh)

# ── Shared State ─────────────────────────────────────────────────────────────
db = AttendanceDB()
engine = FaceRecognitionEngine()

camera = None
camera_lock = threading.Lock()
latest_results = []          # Most recent recognition results
latest_qr_id = None          # Most recently decoded QR value
latest_qr_seen_at = 0.0      # Timestamp of the most recent QR decode
qr_unlock_times = {}         # QR value -> last door unlock timestamp
recognition_active = True    # Pause/resume toggle
frame_counter = 0
recent_events = []           # Recent IN/OUT events for on-screen display
event_display = {}           # name -> {"direction": str, "expire": float}

# Motion detection state
prev_gray = None
last_motion_time = time.time()
is_sleeping = False

# ── ESP32 Serial Door Lock Setup (Auto-Detect) ─────────────────────────────
def init_esp32():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        print(f"[Serial] Checking available port: {port.device} - {port.description}")
        try:
            ser = serial.Serial(port.device, 9600, timeout=1)
            time.sleep(2)  # Give ESP32 time to reboot upon connection
            print(f"ESP32 connected successfully on {port.device}.")
            return ser
        except Exception as e:
            print(f"[Serial] Failed to open {port.device}: {e}")
    return None

esp32 = init_esp32()
if not esp32:
    print("Warning: Could not detect or connect to ESP32 on any port.")

# ── Camera Helpers ───────────────────────────────────────────────────────────
def get_camera():
    """Initialise and return the camera (lazy singleton)."""
    global camera
    if camera is None:
        if CAMERA_SOURCE == "picamera2":
            from picamera2 import Picamera2
            cam = Picamera2()
            cam.configure(cam.create_preview_configuration(
                main={"size": CAMERA_RESOLUTION, "format": "RGB888"}
            ))
            cam.start()
            camera = cam
        else:
            camera = cv2.VideoCapture(CAMERA_SOURCE)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
    return camera


def read_frame():
    """Read a single frame from the active camera."""
    cam = get_camera()
    if CAMERA_SOURCE == "picamera2":
        frame = cam.capture_array()
        frame = cv2.flip(frame, 1)
        return True, frame
    else:
        ok, frame = cam.read()
        if ok:
            frame = cv2.flip(frame, 1)
        return ok, frame


def decode_qr_values(frame):
    """Decode QR values using several image treatments for card glare."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    variants = [gray]

    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    variants.append(enhanced)
    variants.append(cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, blockSize=31, C=5
    ))

    decoded = {}
    for image in variants:
        for barcode in decode(image):
            value = barcode.data.decode("utf-8").strip()
            if value and value not in decoded:
                decoded[value] = [(point.x, point.y) for point in barcode.polygon]

    if decoded:
        return list(decoded.items())

    detector = cv2.QRCodeDetector()
    for image in variants:
        try:
            found, values, points, _ = detector.detectAndDecodeMulti(image)
            if found:
                for index, value in enumerate(values):
                    value = value.strip()
                    if value and value not in decoded:
                        polygon = points[index].astype(int).tolist() if points is not None else None
                        decoded[value] = polygon
        except (AttributeError, cv2.error):
            value, points, _ = detector.detectAndDecode(image)
            value = value.strip()
            if value and value not in decoded:
                decoded[value] = points[0].astype(int).tolist() if points is not None else None

    return list(decoded.items())


# ── MJPEG Stream Generator ──────────────────────────────────────────────────
def generate_frames():
    """Yield JPEG frames with motion detection, recognition, and overlays."""
    global latest_results, latest_qr_id, latest_qr_seen_at, qr_unlock_times
    global frame_counter, recent_events, event_display
    global prev_gray, last_motion_time, is_sleeping

    while True:
        # ── If paused, show static screen without touching the camera ──
        if not recognition_active:
            paused_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(paused_frame, "Recognition Paused",
                        (160, 230),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 120), 2, cv2.LINE_AA)
            cv2.putText(paused_frame, "Camera is off",
                        (230, 265),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 90), 1, cv2.LINE_AA)
            latest_results = []
            _, buf = cv2.imencode('.jpg', paused_frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
            time.sleep(1.0)
            continue

        with camera_lock:
            ok, frame = read_frame()
        if not ok:
            time.sleep(0.1)
            continue

        h, w = frame.shape[:2]
        frame_counter += 1
        now = time.time()

        # ── Pyzbar QR Code Scanning & Registration Number Mapping ─────────
        try:
            qr_values = decode_qr_values(frame)

            user_map = {}
            users_path = os.path.join(os.path.dirname(__file__), "users_directory.json")
            if os.path.exists(users_path):
                with open(users_path, "r", encoding="utf-8") as json_file:
                    user_map = json.load(json_file)

            for reg_number, polygon in qr_values:
                if reg_number:
                    latest_qr_id = reg_number
                    latest_qr_seen_at = time.time()
                    person_name = user_map.get(reg_number)
                    if not person_name:
                        print(f"[QR] Ignoring unregistered QR ID: {reg_number}")
                        continue

                    print(f"[+] Scanned QR ID: {reg_number} -> {person_name}")
                    file_logger.info(f"QR Scanned: {person_name} ({reg_number})")

                    marked, direction = db.mark_attendance(person_name, 1.0)
                    if marked:
                        log_msg = f"-> IN (QR Unlocked): {person_name} [{reg_number}]"
                        print(f"  {log_msg}")
                        file_logger.info(log_msg)

                        recent_events.append({
                            "name": person_name,
                            "direction": direction or "IN",
                            "time": datetime.now().strftime("%H:%M:%S")
                        })
                        recent_events = recent_events[-10:]
                        event_display[person_name] = {
                            "direction": direction or "IN",
                            "expire": now + 3.0
                        }

                    if (esp32 and esp32.is_open
                            and now - qr_unlock_times.get(reg_number, 0) >= 2.0):
                        esp32.write(b"UNLOCK\n")
                        qr_unlock_times[reg_number] = now
                        print("  [Door] Sent UNLOCK command to ESP32.")
                    elif not esp32 or not esp32.is_open:
                        print("  [Door] ESP32 is not connected; cannot unlock.")

                    if polygon:
                        pts = np.array(polygon, dtype=np.int32)
                        cv2.polylines(frame, [pts], True, (0, 255, 0), 3)
                        top_left = (pts[0][0], max(20, pts[0][1] - 10))
                        cv2.putText(frame, f"{person_name}", top_left,
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            print(f"[QR] Failed to process QR mapping: {error}")
        except Exception:
            pass

        # ── Motion Detection ──────────────────────────────────────────────
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        motion_detected = False

        if prev_gray is not None:
            delta = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
            motion_score = cv2.countNonZero(thresh)
            if motion_score > MOTION_THRESHOLD:
                motion_detected = True
                last_motion_time = now
        else:
            last_motion_time = now

        prev_gray = gray

        # Sleep/wake logic
        was_sleeping = is_sleeping
        if now - last_motion_time > SLEEP_AFTER_SECONDS:
            is_sleeping = True
        else:
            is_sleeping = False

        if was_sleeping and not is_sleeping:
            print("[Motion] Waking up - motion detected")
            file_logger.info("WAKE - motion detected")
        elif not was_sleeping and is_sleeping:
            print("[Motion] Going to sleep - no motion")
            file_logger.info("SLEEP - no motion")

        # ── If sleeping, draw sleep overlay and skip recognition ────────
        if is_sleeping:
            # Dim the frame
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
            frame = cv2.addWeighted(frame, 0.3, overlay, 0.7, 0)
            # Sleep text
            cv2.putText(frame, "Sleeping... walk closer to wake",
                        (w // 2 - 200, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2, cv2.LINE_AA)
            latest_results = []

            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
            time.sleep(0.5)  # Slower FPS while sleeping to save CPU
            continue

        # ── Recognition (every Nth frame, only when awake) ───────────────
        if recognition_active and frame_counter % FRAME_SKIP == 0:
            results = engine.recognize_faces(frame)
            latest_results = results

            for name, _loc, confidence in results:
                if name != "Unknown":
                    marked, direction = db.mark_attendance(name, confidence)
                    if marked and direction:
                        arrow = "-> IN" if direction == "IN" else "<- OUT"
                        log_msg = f"{arrow}: {name} ({confidence:.0%})"
                        print(f"  {log_msg}")
                        file_logger.info(log_msg)
			# Trigger ESP32 Door Unlock
                        if esp32 and esp32.is_open:
                            esp32.write(b'UNLOCK\n')
                            print("  [Door] Sent UNLOCK command to ESP32.")

                        # Add only high-confidence, confirmed matches to the training set.
                        if confidence > 0.58:
                            person_dir = os.path.join(KNOWN_FACES_DIR, name)
                            os.makedirs(person_dir, exist_ok=True)
                            enforce_face_photo_limit(name, MAX_FACE_PHOTOS - 1)
                            top, right, bottom, left = _loc
                            height = bottom - top
                            width = right - left
                            y1 = max(0, top - int(height * 0.2))
                            y2 = min(frame.shape[0], bottom + int(height * 0.2))
                            x1 = max(0, left - int(width * 0.2))
                            x2 = min(frame.shape[1], right + int(width * 0.2))
                            face_crop = frame[y1:y2, x1:x2]

                            if face_crop.size > 0:
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                auto_img_path = os.path.join(
                                    person_dir, f"auto_{timestamp}.jpg"
                                )
                                cv2.imwrite(auto_img_path, face_crop)
                                print(f"  [AI Learning] Added training face for {name} ({confidence:.0%})")
                                engine.rebuild_encodings()

                        recent_events.append({
                            "name": name,
                            "direction": direction,
                            "time": datetime.now().strftime("%H:%M:%S")
                        })
                        recent_events = recent_events[-10:]
                        event_display[name] = {
                            "direction": direction,
                            "expire": now + 3.0
                        }

        # ── Draw bounding boxes ───────────────────────────────────────────
        for name, (top, right, bottom, left), confidence in latest_results:
            if name == "Unknown":
                continue

            colour = (0, 220, 100)
            cv2.rectangle(frame, (left, top), (right, bottom), colour, 2)

            event_info = event_display.get(name)
            if event_info and now < event_info["expire"]:
                dir_label = event_info["direction"]
                label = f"{name} - {dir_label} ({confidence:.0%})"
                colour = (0, 220, 100) if dir_label == "IN" else (0, 100, 255)
            elif name != "Unknown":
                label = f"{name} ({confidence:.0%})"
            else:
                label = "Unknown"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(frame, (left, bottom),
                          (left + tw + 12, bottom + th + 14), colour, -1)
            cv2.putText(frame, label, (left + 6, bottom + th + 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        # ── Cooldown info overlay (top-right) ────────────────────────────
        cooldown_y = 20
        cv2.putText(frame, f"Cooldown: {SCAN_COOLDOWN_SECONDS}s per person",
                    (w - 260, cooldown_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1, cv2.LINE_AA)

        # ── Encode & yield ───────────────────────────────────────────────
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')

        time.sleep(1.0 / FRAME_RATE)


# ═══════════════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Dashboard home page."""
    stats = db.get_stats()
    attendance = db.get_today_attendance()
    return render_template(
        'index.html',
        stats=stats,
        attendance=attendance,
        today=datetime.now().strftime("%A, %B %d, %Y"),
        recognition_active=recognition_active,
    )


@app.route('/video_feed')
def video_feed():
    """MJPEG live camera stream."""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# ── Registration ─────────────────────────────────────────────────────────────
@app.route('/register')
def register_page():
    registered = db.get_registered_persons()
    return render_template('register.html', registered=registered)


def save_user_mappings(name, mapping_ids):
    """Save QR and registration-number aliases for a person."""
    if not mapping_ids:
        return

    map_file = os.path.join(os.path.dirname(__file__), "users_directory.json")
    user_map = {}
    try:
        with open(map_file, "r", encoding="utf-8") as json_file:
            user_map = json.load(json_file)
        if not isinstance(user_map, dict):
            user_map = {}
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    for mapping_id in mapping_ids:
        user_map[mapping_id] = name
    with open(map_file, "w", encoding="utf-8") as json_file:
        json.dump(user_map, json_file, indent=4)
    print(f"[Register] Linked IDs {sorted(mapping_ids)} to '{name}'.")


def enforce_face_photo_limit(name, limit=MAX_FACE_PHOTOS):
    """Keep only the newest face photos for a person."""
    person_dir = os.path.join(KNOWN_FACES_DIR, name)
    if not os.path.isdir(person_dir):
        return 0

    image_files = [
        os.path.join(person_dir, filename)
        for filename in os.listdir(person_dir)
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))
    ]
    image_files.sort(key=lambda path: (os.path.getmtime(path), path))

    for image_path in image_files[:-limit]:
        try:
            os.remove(image_path)
        except OSError as error:
            print(f"[Register] Could not remove old face photo {image_path}: {error}")

    return min(len(image_files), limit)


@app.route('/api/register', methods=['POST'])
def api_register():
    """Register a new person. Pauses recognition during processing."""
    global recognition_active
    was_active = recognition_active

    try:
        data = request.get_json(force=True)
        name = data.get('name', '').strip()
        qr_id = data.get('qr_id', '').strip()
        registration_number = data.get('registration_number', '').strip()
        images_b64 = data.get('images', [])
        mapping_ids = {value for value in (qr_id, registration_number) if value}

        if not name:
            return jsonify({"error": "Name is required"}), 400
        if not images_b64:
            if not (qr_id and registration_number):
                return jsonify({"error": "Provide a QR code and registration number, or capture at least 3 photos."}), 400
            person_dir = os.path.join(KNOWN_FACES_DIR, name)
            photo_count = enforce_face_photo_limit(name)
            db.register_person(name, photo_count)
            save_user_mappings(name, mapping_ids)
            return jsonify({"success": True,
                            "message": f"Registered '{name}' with QR and registration number."})

        # Pause recognition during registration
        recognition_active = False
        print(f"[Register] Pausing recognition for '{name}' registration...")

        # Save images to a temp directory
        temp_dir = tempfile.mkdtemp(prefix="face_reg_")
        saved = 0
        for b64 in images_b64:
            if ',' in b64:
                b64 = b64.split(',', 1)[1]
            raw = base64.b64decode(b64)
            arr = np.frombuffer(raw, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                # Downscale before saving
                h, w = img.shape[:2]
                if w > 640:
                    scale = 640 / w
                    img = cv2.resize(img, (int(w * scale), int(h * scale)))
                cv2.imwrite(os.path.join(temp_dir, f"{saved:03d}.jpg"), img)
                saved += 1

        if saved == 0:
            recognition_active = was_active
            return jsonify({"error": "Could not decode images"}), 400

        print(f"[Register] Spawning worker for '{name}' with {saved} images...")

        # Run registration in a SEPARATE PROCESS
        worker_path = os.path.join(os.path.dirname(__file__), "register_worker.py")
        result = subprocess.run(
            [sys.executable, worker_path, name, temp_dir],
            capture_output=True, text=True, timeout=120
        )

        # Clean up temp dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

        if result.returncode != 0:
            print(f"[Register] Worker crashed (exit {result.returncode})")
            print(f"[Register] stderr: {result.stderr}")
            recognition_active = was_active
            return jsonify({"error": "Face processing failed (dlib crash). "
                                     "Try with fewer photos (3-5) and ensure only your face is visible."}), 500

        # Parse worker output
        try:
            output = json.loads(result.stdout.strip())
        except (json.JSONDecodeError, ValueError):
            print(f"[Register] Worker output: {result.stdout}")
            print(f"[Register] Worker stderr: {result.stderr}")
            recognition_active = was_active
            return jsonify({"error": "Registration process returned invalid output."}), 500

        count = output.get("count", 0)
        if count > 0:
            photo_count = enforce_face_photo_limit(name)
            engine.rebuild_encodings()
            db.register_person(name, photo_count)
            save_user_mappings(name, mapping_ids)

            recognition_active = was_active
            print(f"[Register] Done. Resuming recognition.")
            return jsonify({"success": True,
                            "message": f"Registered '{name}' with {count} photo(s)."})

        recognition_active = was_active
        return jsonify({"error": "No face detected in the provided images. "
                                 "Make sure only one face is clearly visible."}), 400

    except subprocess.TimeoutExpired:
        recognition_active = was_active
        return jsonify({"error": "Registration timed out. Try with fewer photos."}), 500
    except Exception as e:
        recognition_active = was_active
        traceback.print_exc()
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500


# ── Attendance History ───────────────────────────────────────────────────────
@app.route('/attendance')
def attendance_page():
    date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    records = db.get_attendance_by_date(date)
    return render_template('attendance.html', records=records, selected_date=date)


@app.route('/api/attendance/today')
def api_today():
    return jsonify(db.get_today_attendance())


@app.route('/api/stats')
def api_stats():
    return jsonify(db.get_stats())


@app.route('/api/status')
def api_status():
    """Return system status including sleep/wake state."""
    return jsonify({
        "sleeping": is_sleeping,
        "recognition_active": recognition_active,
        "registered": len(set(engine.known_names)),
        "uptime_seconds": int(time.time() - last_motion_time) if is_sleeping else 0
    })


@app.route('/kiosk')
def kiosk_page():
    """Fullscreen kiosk view for Pi monitor — camera feed + recent events."""
    stats = db.get_stats()
    return render_template('kiosk.html', stats=stats)


@app.route('/api/events')
def api_events():
    """Return recent IN/OUT crossing events."""
    return jsonify(recent_events)


@app.route('/api/logs')
def api_logs():
    """Return the last N lines from the attendance log file."""
    n = request.args.get('n', 50, type=int)
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return jsonify({"lines": [l.strip() for l in lines[-n:]]})
    except FileNotFoundError:
        return jsonify({"lines": []})


# ── Export ───────────────────────────────────────────────────────────────────
@app.route('/export')
def export():
    start = request.args.get('start')
    end = request.args.get('end')
    csv_text = db.export_csv(start, end)

    buf = BytesIO()
    buf.write(csv_text.encode('utf-8'))
    buf.seek(0)

    fname = f"attendance_{start or 'all'}_to_{end or 'all'}.csv"
    return send_file(buf, mimetype='text/csv',
                     as_attachment=True, download_name=fname)


# ── Controls ─────────────────────────────────────────────────────────────────
@app.route('/api/recognition/toggle', methods=['POST'])
def toggle_recognition():
    global recognition_active
    recognition_active = not recognition_active
    return jsonify({"active": recognition_active})


@app.route('/api/capture_frame')
def capture_frame():
    """Capture a single frame and return as base64."""
    with camera_lock:
        ok, frame = read_frame()
    if ok:
        _, buf = cv2.imencode('.jpg', frame)
        b64 = base64.b64encode(buf).decode('utf-8')
        return jsonify({"image": f"data:image/jpeg;base64,{b64}"})
    return jsonify({"error": "Camera capture failed"}), 500


@app.route('/api/qr/latest')
def latest_qr():
    """Return a recently scanned QR value for the registration form."""
    if latest_qr_id and time.time() - latest_qr_seen_at <= 5:
        return jsonify({"qr_id": latest_qr_id})
    return jsonify({"qr_id": None})


@app.route('/api/delete_person', methods=['POST'])
def api_delete_person():
    data = request.get_json(force=True)
    name = data.get('name')
    if name:
        engine.delete_person(name)
        db.delete_person(name)
        map_file = os.path.join(os.path.dirname(__file__), "users_directory.json")
        try:
            with open(map_file, "r", encoding="utf-8") as json_file:
                user_map = json.load(json_file)
            user_map = {
                mapping_id: mapped_name
                for mapping_id, mapped_name in user_map.items()
                if mapped_name != name
            }
            with open(map_file, "w", encoding="utf-8") as json_file:
                json.dump(user_map, json_file, indent=4)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return jsonify({"success": True})
    return jsonify({"error": "Name is required"}), 400


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    banner = f"""
╔══════════════════════════════════════════════════╗
║   Face Recognition Attendance System             ║
║   Dashboard →  http://localhost:{FLASK_PORT}               ║
║   LAN access → http://<your-ip>:{FLASK_PORT}          ║
╚══════════════════════════════════════════════════╝
"""
    print(banner)
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, threaded=True)
