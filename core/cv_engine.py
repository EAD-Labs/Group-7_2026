import cv2
import numpy as np
import math


class CVDetector:
    """
    Computer Vision Engine for Classroom Marker Cards.
    Implements:
    - Tuned ArUco 5x5 detection for distant/small cards (back-row detection)
    - Sub-pixel corner refinement
    - Coordinate geometry orientation solver
    - Deadband ambiguity rejection for diagonal (45 deg) holds
    - Secondary HSV top-edge color verification
    - Laplacian variance motion blur estimation
    """

    # Expected Hue ranges in OpenCV HSV (H: 0-180, S: 0-255, V: 0-255)
    # Card edges: A=Red, B=Yellow, C=Blue, D=Green
    COLOR_HUE_RANGES = {
        "A": [((0, 70, 70), (12, 255, 255)), ((170, 70, 70), (180, 255, 255))],  # Red (wraps around 0/180)
        "B": [((18, 70, 70), (35, 255, 255))],                                    # Yellow (~20-35)
        "C": [((95, 70, 70), (135, 255, 255))],                                   # Blue (~100-130)
        "D": [((40, 70, 70), (85, 255, 255))],                                    # Green (~45-80)
    }

    # BGR Display Colors for Visual HUD
    DISPLAY_COLORS = {
        "A": (60, 76, 231),    # Red
        "B": (15, 196, 241),   # Yellow
        "C": (219, 152, 52),   # Blue
        "D": (113, 204, 46),   # Green
        "AMBIGUOUS": (0, 165, 255) # Orange
    }

    def __init__(self, min_marker_perimeter=0.015, blur_threshold=50.0, deadband_rate=0.15):
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
        self.params = cv2.aruco.DetectorParameters()

        # Tuned parameters for distant / classroom cards
        self.params.minMarkerPerimeterRate = min_marker_perimeter
        self.params.maxMarkerPerimeterRate = 4.0
        self.params.adaptiveThreshWinSizeMin = 3
        self.params.adaptiveThreshWinSizeMax = 23
        self.params.adaptiveThreshWinSizeStep = 10
        self.params.adaptiveThreshConstant = 7.0
        self.params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.params.cornerRefinementWinSize = 5
        self.params.maxErroneousBitsInBorderRate = 0.35

        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.params)
        self.blur_threshold = blur_threshold
        self.deadband_rate = deadband_rate

    def estimate_blur(self, gray_image):
        """Calculates Laplacian variance. Low values indicate motion blur."""
        laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
        return float(laplacian.var())

    def get_orientation_and_deadband(self, c):
        """
        Calculates the 4 card edge midpoints and determines which edge is uppermost.
        Rejects ambiguous (diagonal ~45 deg) holds where two top midpoints differ by < epsilon.
        c: 4 corner points (shape (4, 2)) in order [TL, TR, BR, BL] of the marker.
        Returns (candidate_answer, is_ambiguous, angle_deg)
        """
        # Marker edge midpoints in screen coordinates
        midpoints = {
            "A": (c[0] + c[1]) / 2.0,  # Top edge
            "B": (c[1] + c[2]) / 2.0,  # Right edge
            "C": (c[2] + c[3]) / 2.0,  # Bottom edge
            "D": (c[3] + c[0]) / 2.0,  # Left edge
        }

        # Marker height proxy
        marker_height = np.linalg.norm(c[3] - c[0])
        epsilon = max(marker_height * self.deadband_rate, 4.0)

        # Sort edges by y-coordinate ascending (smallest y is closest to the top of screen)
        sorted_edges = sorted(midpoints.items(), key=lambda item: item[1][1])
        top_edge, top_pt = sorted_edges[0]
        second_edge, second_pt = sorted_edges[1]

        # Calculate angle of marker top vector
        dx = c[1][0] - c[0][0]
        dy = c[1][1] - c[0][1]
        angle = float(np.degrees(np.arctan2(dy, dx)) % 360)

        # Check deadband: if difference between two uppermost points is < epsilon
        diff_y = second_pt[1] - top_pt[1]
        is_ambiguous = diff_y < epsilon

        return top_edge, is_ambiguous, angle, midpoints

    def sample_edge_color(self, image_hsv, midpoint, center, marker_size):
        """
        Samples a strip along the edge band perpendicular to the outward vector,
        filtering out white letter glyphs to capture the true background color.
        """
        h, w = image_hsv.shape[:2]
        direction = midpoint - center
        norm = np.linalg.norm(direction)
        if norm == 0:
            return None, None

        unit_vec = direction / norm
        perp_vec = np.array([-unit_vec[1], unit_vec[0]])
        sample_dist_px = marker_size * 0.42

        hues = []
        sats = []

        # Sample 5 points across the color band strip
        offsets = [-0.15, -0.08, 0.0, 0.08, 0.15]
        for off in offsets:
            pt = midpoint + unit_vec * sample_dist_px + perp_vec * (marker_size * off)
            sx, sy = int(round(pt[0])), int(round(pt[1]))

            if 2 <= sx < w - 2 and 2 <= sy < h - 2:
                patch = image_hsv[sy - 2:sy + 3, sx - 2:sx + 3]
                for p in patch.reshape(-1, 3):
                    # Filter out white/gray letter strokes (Saturation must be >= 50)
                    if p[1] >= 50:
                        hues.append(p[0])
                        sats.append(p[1])

        if not hues:
            return None, None

        return float(np.median(hues)), float(np.median(sats))

    def verify_color(self, candidate_letter, hue, sat):
        """
        Verifies if the sampled Hue matches the expected color for the candidate letter.
        """
        if hue is None or sat is None or sat < 40:  # If desaturated (white/gray/black), color is unverified
            return False, "Unverified (Low Saturation)"

        ranges = self.COLOR_HUE_RANGES.get(candidate_letter, [])
        for (lower, upper) in ranges:
            if lower[0] <= hue <= upper[0]:
                return True, "Match"

        return False, "Mismatch"

    def detect(self, frame):
        """
        Runs complete CV detection on a single frame.
        Returns:
            dict containing:
                'cards': list of detected cards
                'blur_metric': float
                'is_blurry': bool
        """
        if frame is None or frame.size == 0:
            return {"cards": [], "blur_metric": 0.0, "is_blurry": True}

        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        else:
            gray = frame
            hsv = cv2.cvtColor(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2HSV)

        blur_metric = self.estimate_blur(gray)
        is_blurry = blur_metric < self.blur_threshold

        corners_list, ids, _ = self.detector.detectMarkers(gray)
        cards = []

        if ids is not None and len(ids) > 0:
            flat_ids = np.ravel(ids)
            for i, cid in enumerate(flat_ids):
                c = np.squeeze(corners_list[i])
                center = np.mean(c, axis=0)

                top_edge, is_ambiguous, angle, midpoints = self.get_orientation_and_deadband(c)

                # Color sampling for dual-verification
                marker_size = float(np.linalg.norm(c[1] - c[0]))
                hue, sat = self.sample_edge_color(hsv, midpoints[top_edge], center, marker_size)
                color_matched, color_status = self.verify_color(top_edge, hue, sat)

                # Final answer determination
                if is_ambiguous:
                    final_answer = "AMBIGUOUS"
                    confidence = 0.50
                elif color_matched:
                    final_answer = top_edge
                    confidence = 0.99  # Dual-verified
                else:
                    final_answer = top_edge
                    confidence = 0.90  # Pattern-verified only

                cards.append({
                    "card_id": int(cid),
                    "answer": str(final_answer),
                    "candidate_letter": str(top_edge),
                    "is_ambiguous": bool(is_ambiguous),
                    "color_matched": bool(color_matched),
                    "confidence": float(confidence),
                    "angle_deg": float(angle),
                    "corners": c.tolist(),
                    "center": [float(center[0]), float(center[1])],
                })

        # Sort cards by card_id
        cards.sort(key=lambda x: x["card_id"])
        return {
            "cards": cards,
            "blur_metric": float(blur_metric),
            "is_blurry": bool(is_blurry),
        }
