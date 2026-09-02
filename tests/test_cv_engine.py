import unittest
import os
import cv2
import numpy as np

from core.cv_engine import CVDetector
from core.session_tracker import SessionTracker


class TestCVEngineAndTracker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.detector = CVDetector()
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.card14_path = os.path.join(cls.base_dir, "output", "front", "card_14_front.png")
        cls.card14_img = cv2.imread(cls.card14_path)

    def test_single_card_upright(self):
        """Card 14 upright should decode as ID=14 and Answer=A with color matched."""
        self.assertIsNotNone(self.card14_img, "Card 14 image not found in output/front/")
        result = self.detector.detect(self.card14_img)
        cards = result["cards"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["card_id"], 14)
        self.assertEqual(cards[0]["answer"], "A")
        self.assertTrue(cards[0]["color_matched"], "Red color band on top should match A")

    def test_rotations_all_four_answers(self):
        """Rotations 0, 90, 180, 270 deg should yield A, B, C, D respectively."""
        h, w = self.card14_img.shape[:2]
        center = (w // 2, h // 2)

        expected_answers = {
            0: "A",
            90: "B",
            180: "C",
            270: "D",
        }

        for angle, expected_ans in expected_answers.items():
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rot = cv2.warpAffine(self.card14_img, M, (w, h), borderValue=(255, 255, 255))
            result = self.detector.detect(rot)
            cards = result["cards"]
            self.assertEqual(len(cards), 1, f"Failed detection at angle {angle}")
            self.assertEqual(cards[0]["card_id"], 14)
            self.assertEqual(cards[0]["answer"], expected_ans, f"Expected {expected_ans} at angle {angle}, got {cards[0]['answer']}")

    def test_session_tracker_debouncing_and_missing(self):
        """Verify session tracker manages roster, debounces over 3 frames, and tracks missing."""
        roster = list(range(1, 11))  # Roll 1 to 10
        absentees = [3]              # Roll 3 is absent
        tracker = SessionTracker(active_roster=roster, absentees=absentees, debounce_frames=3)

        summary = tracker.get_summary()
        self.assertEqual(summary["total_expected"], 9)
        self.assertEqual(summary["scanned_count"], 0)
        self.assertEqual(len(summary["missing_roll_numbers"]), 9)
        self.assertNotIn(3, summary["missing_roll_numbers"])

        # Frame 1: Card 14 appears (Rogue card, not in roster 1-10)
        tracker.update_frame([{"card_id": 14, "answer": "A"}])
        summary = tracker.get_summary()
        self.assertEqual(summary["scanned_count"], 0)
        self.assertTrue(any(a["type"] == "ROGUE_CARD" for a in summary["anomalies"]))

        # Frames 1-3: Card 1 appears with 'A' consistently for 3 frames
        for _ in range(3):
            tracker.update_frame([{"card_id": 1, "answer": "A"}])

        summary = tracker.get_summary()
        self.assertEqual(summary["scanned_count"], 1)
        self.assertEqual(summary["confirmed_responses"][1], "A")
        self.assertNotIn(1, summary["missing_roll_numbers"])


if __name__ == "__main__":
    unittest.main()
