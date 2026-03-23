"""
Centroid Tracker with Direction Detection (v2).
Robust against small head movements — requires faces to travel a
significant distance across the virtual line and stay on the new side
for several frames before firing an IN/OUT event.
"""
import math
from collections import OrderedDict, deque


class CentroidTracker:
    def __init__(self, max_disappeared=15, direction_axis="horizontal",
                 line_position=0.5):
        """
        Args:
            max_disappeared: Frames before a tracked face is deregistered.
            direction_axis: "horizontal" or "vertical".
            line_position:  Position of the virtual line (0.0–1.0).
        """
        self.next_id = 0
        self.objects = OrderedDict()       # id -> (cx, cy)
        self.disappeared = OrderedDict()   # id -> missing frame count
        self.names = OrderedDict()         # id -> recognized name
        self.trails = OrderedDict()        # id -> deque of past centroids

        # Direction tracking state per object
        self.entered_side = OrderedDict()  # id -> side when first seen ("left"/"right" or "top"/"bottom")
        self.confirmed_side = OrderedDict()  # id -> current confirmed side
        self.frames_on_side = OrderedDict()  # id -> consecutive frames on current side
        self.has_crossed = OrderedDict()   # id -> already fired a crossing event?

        self.max_disappeared = max_disappeared
        self.direction_axis = direction_axis
        self.line_position = line_position

        # Tuning: face must be on the new side for this many consecutive frames
        self.CONFIRM_FRAMES = 5
        # Tuning: face centroid must be at least this far past the line (in pixels)
        self.MIN_CROSS_MARGIN = 30

        self.crossing_events = []

    def _get_side(self, centroid, frame_width, frame_height):
        """Determine which side of the line a centroid is on."""
        if self.direction_axis == "horizontal":
            line_x = frame_width * self.line_position
            margin = self.MIN_CROSS_MARGIN
            if centroid[0] < line_x - margin:
                return "left"
            elif centroid[0] > line_x + margin:
                return "right"
            else:
                return "centre"   # In the dead zone — don't count
        else:
            line_y = frame_height * self.line_position
            margin = self.MIN_CROSS_MARGIN
            if centroid[1] < line_y - margin:
                return "top"
            elif centroid[1] > line_y + margin:
                return "bottom"
            else:
                return "centre"

    def _register(self, centroid, name, frame_width, frame_height):
        obj_id = self.next_id
        self.objects[obj_id] = centroid
        self.disappeared[obj_id] = 0
        self.names[obj_id] = name
        self.trails[obj_id] = deque(maxlen=30)
        self.trails[obj_id].append(centroid)

        side = self._get_side(centroid, frame_width, frame_height)
        self.entered_side[obj_id] = side
        self.confirmed_side[obj_id] = side
        self.frames_on_side[obj_id] = 1
        self.has_crossed[obj_id] = False

        self.next_id += 1
        return obj_id

    def _deregister(self, obj_id):
        for d in [self.objects, self.disappeared, self.names, self.trails,
                  self.entered_side, self.confirmed_side, self.frames_on_side,
                  self.has_crossed]:
            d.pop(obj_id, None)

    def _distance(self, a, b):
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def _check_crossing(self, obj_id, current_side):
        """
        Check if the face has genuinely crossed from one side to the other.
        Only fires once per crossing.
        """
        if current_side == "centre":
            return None  # In the dead zone, ignore

        entered = self.entered_side.get(obj_id)
        if entered is None or entered == "centre":
            # First time seeing them on a definite side
            self.entered_side[obj_id] = current_side
            return None

        # Track consecutive frames on the current side
        if current_side == self.confirmed_side.get(obj_id):
            self.frames_on_side[obj_id] = self.frames_on_side.get(obj_id, 0) + 1
        else:
            self.confirmed_side[obj_id] = current_side
            self.frames_on_side[obj_id] = 1

        # Only fire if they've been on the new side long enough AND haven't fired yet
        if (current_side != entered and
                self.frames_on_side.get(obj_id, 0) >= self.CONFIRM_FRAMES and
                not self.has_crossed.get(obj_id, False)):

            self.has_crossed[obj_id] = True

            if self.direction_axis == "horizontal":
                if entered == "left" and current_side == "right":
                    return "IN"
                elif entered == "right" and current_side == "left":
                    return "OUT"
            else:
                if entered == "top" and current_side == "bottom":
                    return "IN"
                elif entered == "bottom" and current_side == "top":
                    return "OUT"

        return None

    def update(self, detections, frame_width=640, frame_height=480):
        """
        Update tracker with new detections.

        Args:
            detections: list of (name, (top, right, bottom, left), confidence)
            frame_width, frame_height: frame dimensions

        Returns:
            list of crossing events: [(name, direction, confidence), ...]
        """
        self.crossing_events = []

        # Compute centroids
        input_centroids = []
        input_names = []
        input_confidences = []

        for name, (top, right, bottom, left), confidence in detections:
            cx = (left + right) // 2
            cy = (top + bottom) // 2
            input_centroids.append((cx, cy))
            input_names.append(name)
            input_confidences.append(confidence)

        # No detections — increment disappeared counters
        if len(input_centroids) == 0:
            for obj_id in list(self.disappeared.keys()):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self._deregister(obj_id)
            return self.crossing_events

        # No existing objects — register all
        if len(self.objects) == 0:
            for i, centroid in enumerate(input_centroids):
                self._register(centroid, input_names[i], frame_width, frame_height)
            return self.crossing_events

        # Match existing objects to new detections
        obj_ids = list(self.objects.keys())
        obj_centroids = list(self.objects.values())

        # Build and sort distance pairs
        pairs = []
        for oi in range(len(obj_centroids)):
            for ii in range(len(input_centroids)):
                d = self._distance(obj_centroids[oi], input_centroids[ii])
                pairs.append((d, oi, ii))
        pairs.sort()

        used_inputs = set()
        used_objects = set()
        matches = []

        for dist, oi, ii in pairs:
            if oi in used_objects or ii in used_inputs:
                continue
            if dist > 150:
                continue
            matches.append((oi, ii))
            used_objects.add(oi)
            used_inputs.add(ii)

        # Update matched objects
        for oi, ii in matches:
            obj_id = obj_ids[oi]
            new_pos = input_centroids[ii]
            detected_name = input_names[ii]

            if detected_name != "Unknown":
                self.names[obj_id] = detected_name

            # Update position
            self.objects[obj_id] = new_pos
            self.trails[obj_id].append(new_pos)
            self.disappeared[obj_id] = 0

            # Check for line crossing
            current_side = self._get_side(new_pos, frame_width, frame_height)
            direction = self._check_crossing(obj_id, current_side)

            if direction and self.names[obj_id] != "Unknown":
                self.crossing_events.append(
                    (self.names[obj_id], direction, input_confidences[ii])
                )

        # Unmatched existing objects — disappeared
        for oi in range(len(obj_centroids)):
            if oi not in used_objects:
                obj_id = obj_ids[oi]
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self._deregister(obj_id)

        # Unmatched new detections — register
        for ii in range(len(input_centroids)):
            if ii not in used_inputs:
                self._register(input_centroids[ii], input_names[ii],
                               frame_width, frame_height)

        return self.crossing_events

    def get_tracked_objects(self):
        """Return tracked objects for drawing."""
        result = {}
        for obj_id in self.objects:
            result[obj_id] = {
                "name": self.names[obj_id],
                "centroid": self.objects[obj_id],
                "trail": list(self.trails[obj_id])
            }
        return result
