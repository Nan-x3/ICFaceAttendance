"""
Registration worker — runs in a subprocess to isolate dlib crashes.
Called by app.py with: python register_worker.py <name> <image_dir>
Processes images one by one, saves encodings, prints result as JSON.
"""
import os
import sys
import gc
import json
import glob
import pickle
import cv2
import face_recognition

# Add parent dir to path for config import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    KNOWN_FACES_DIR, ENCODINGS_FILE, FACE_DETECTION_MODEL,
    MAX_REGISTRATION_PHOTOS
)


def process_registration(name, temp_image_dir):
    """Process registration images and return count of successful encodings."""
    person_dir = os.path.join(KNOWN_FACES_DIR, name)
    os.makedirs(person_dir, exist_ok=True)

    # Load existing encodings
    known_encodings = []
    known_names = []
    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)
            known_encodings = data.get("encodings", [])
            known_names = data.get("names", [])

    # Count existing images for this person
    existing = len([
        f for f in os.listdir(person_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])

    # Get all temp images, cap at max
    image_files = sorted(glob.glob(os.path.join(temp_image_dir, "*.jpg")))
    image_files = image_files[:MAX_REGISTRATION_PHOTOS]

    count = 0
    for i, img_path in enumerate(image_files):
        try:
            frame = cv2.imread(img_path)
            if frame is None:
                print(f"  Image {i+1}: could not load", file=sys.stderr)
                continue

            # Downscale to prevent memory issues
            h, w = frame.shape[:2]
            if w > 480:
                scale = 480 / w
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb, model=FACE_DETECTION_MODEL)

            if len(locations) != 1:
                print(f"  Image {i+1}: skipped ({len(locations)} faces)", file=sys.stderr)
                del frame, rgb
                gc.collect()
                continue

            encodings = face_recognition.face_encodings(rgb, locations)
            if encodings:
                save_path = os.path.join(person_dir, f"{existing + count + 1:03d}.jpg")
                cv2.imwrite(save_path, frame)

                known_encodings.append(encodings[0])
                known_names.append(name)
                count += 1
                print(f"  Image {i+1}: OK", file=sys.stderr)

            # Free memory
            del frame, rgb, locations, encodings
            gc.collect()

        except Exception as e:
            print(f"  Image {i+1}: error - {e}", file=sys.stderr)
            gc.collect()

    # Save updated encodings
    if count > 0:
        os.makedirs(os.path.dirname(ENCODINGS_FILE), exist_ok=True)
        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump({"encodings": known_encodings, "names": known_names}, f)

    # Output result as JSON on stdout (this is what the parent process reads)
    print(json.dumps({"count": count, "name": name}))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(json.dumps({"error": "Usage: python register_worker.py <name> <temp_image_dir>"}))
        sys.exit(1)

    name = sys.argv[1]
    temp_dir = sys.argv[2]
    process_registration(name, temp_dir)
