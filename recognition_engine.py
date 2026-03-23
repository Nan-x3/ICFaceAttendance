"""
Face Recognition Engine.
Handles face encoding, storage, detection, and recognition using
the face_recognition library (dlib-based deep learning model).
"""
import os
import gc
import pickle
import shutil
import cv2
import numpy as np
import face_recognition
from config import (
    KNOWN_FACES_DIR, ENCODINGS_FILE, FACE_DETECTION_MODEL,
    RECOGNITION_TOLERANCE, FACE_DETECTION_SCALE, MAX_REGISTRATION_PHOTOS
)


class FaceRecognitionEngine:
    def __init__(self):
        self.known_encodings = []
        self.known_names = []
        os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(ENCODINGS_FILE), exist_ok=True)
        self.load_encodings()

    def load_encodings(self):
        """Load cached encodings from disk, or rebuild from images."""
        if os.path.exists(ENCODINGS_FILE):
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
                self.known_encodings = data.get("encodings", [])
                self.known_names = data.get("names", [])
            unique = len(set(self.known_names))
            print(f"[Engine] Loaded {len(self.known_encodings)} encodings for {unique} people.")
        else:
            print("[Engine] No cached encodings found. Building from images...")
            self.rebuild_encodings()

    def rebuild_encodings(self):
        """Rebuild all face encodings from images in known_faces/."""
        self.known_encodings = []
        self.known_names = []

        if not os.path.exists(KNOWN_FACES_DIR):
            return

        for person_name in sorted(os.listdir(KNOWN_FACES_DIR)):
            person_dir = os.path.join(KNOWN_FACES_DIR, person_name)
            if not os.path.isdir(person_dir):
                continue

            count = 0
            for img_file in sorted(os.listdir(person_dir)):
                if not img_file.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                    continue

                img_path = os.path.join(person_dir, img_file)
                try:
                    image = face_recognition.load_image_file(img_path)
                    encodings = face_recognition.face_encodings(image)
                    if encodings:
                        self.known_encodings.append(encodings[0])
                        self.known_names.append(person_name)
                        count += 1
                except Exception as e:
                    print(f"[Engine] Error processing {img_path}: {e}")

            if count > 0:
                print(f"[Engine]   {person_name}: {count} encodings")

        self._save_encodings()
        unique = len(set(self.known_names))
        print(f"[Engine] Built {len(self.known_encodings)} total encodings for {unique} people.")

    def _save_encodings(self):
        """Save encodings to disk for fast loading."""
        os.makedirs(os.path.dirname(ENCODINGS_FILE), exist_ok=True)
        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump({
                "encodings": self.known_encodings,
                "names": self.known_names
            }, f)

    def register_face(self, name, images):
        """
        Register a new face from a list of BGR frames.
        Processes images ONE AT A TIME to prevent dlib memory crashes.
        Returns the number of successfully encoded images.
        """
        person_dir = os.path.join(KNOWN_FACES_DIR, name)
        os.makedirs(person_dir, exist_ok=True)

        # Count existing images
        existing = len([
            f for f in os.listdir(person_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ])

        # Cap the number of photos to process
        images = images[:MAX_REGISTRATION_PHOTOS]

        count = 0
        for i, frame in enumerate(images):
            try:
                # Downscale to prevent dlib memory issues
                h, w = frame.shape[:2]
                if w > 480:
                    scale = 480 / w
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                locations = face_recognition.face_locations(rgb, model=FACE_DETECTION_MODEL)

                if len(locations) != 1:
                    print(f"[Engine]   Image {i+1}: skipped ({len(locations)} faces found)")
                    continue

                encodings = face_recognition.face_encodings(rgb, locations)
                if encodings:
                    img_path = os.path.join(person_dir, f"{existing + count + 1:03d}.jpg")
                    cv2.imwrite(img_path, frame)

                    self.known_encodings.append(encodings[0])
                    self.known_names.append(name)
                    count += 1
                    print(f"[Engine]   Image {i+1}: OK")

            except Exception as e:
                print(f"[Engine]   Image {i+1}: error - {e}")
            finally:
                # Force free memory between images to prevent dlib segfault
                gc.collect()

        if count > 0:
            self._save_encodings()
            print(f"[Engine] Registered {count} new encodings for '{name}'")

        return count

    def recognize_faces(self, frame):
        """
        Detect and recognize faces in a BGR frame.
        Returns list of (name, (top, right, bottom, left), confidence) tuples.
        """
        # Downscale for faster detection
        small = cv2.resize(frame, (0, 0),
                           fx=FACE_DETECTION_SCALE,
                           fy=FACE_DETECTION_SCALE)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        # Detect face locations and compute encodings
        locations = face_recognition.face_locations(rgb_small, model=FACE_DETECTION_MODEL)
        encodings = face_recognition.face_encodings(rgb_small, locations)

        results = []
        scale = int(1 / FACE_DETECTION_SCALE)

        for encoding, location in zip(encodings, locations):
            name = "Unknown"
            confidence = 0.0

            if self.known_encodings:
                distances = face_recognition.face_distance(self.known_encodings, encoding)
                best_idx = int(np.argmin(distances))
                best_distance = distances[best_idx]

                if best_distance < RECOGNITION_TOLERANCE:
                    name = self.known_names[best_idx]
                    confidence = round(1.0 - best_distance, 3)

            # Scale location back to original frame size
            top, right, bottom, left = location
            scaled_location = (top * scale, right * scale, bottom * scale, left * scale)
            results.append((name, scaled_location, confidence))

        return results

    def delete_person(self, name):
        """Remove a person's images and rebuild encodings."""
        person_dir = os.path.join(KNOWN_FACES_DIR, name)
        if os.path.exists(person_dir):
            shutil.rmtree(person_dir)
            print(f"[Engine] Deleted face data for '{name}'")
        self.rebuild_encodings()

    def get_registered_names(self):
        """Return list of registered person names."""
        if not os.path.exists(KNOWN_FACES_DIR):
            return []
        return sorted([
            d for d in os.listdir(KNOWN_FACES_DIR)
            if os.path.isdir(os.path.join(KNOWN_FACES_DIR, d))
        ])
