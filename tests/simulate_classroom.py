import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import time

from core.cv_engine import CVDetector
from core.session_tracker import SessionTracker
from backend.database import get_db, init_db


def create_synthetic_classroom(rows=5, cols=5, card_px=180):
    """
    Creates a simulated classroom image containing rows x cols cards (e.g. 25 cards)
    each held with a specific rotation (answer A, B, C, or D).
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    canvas_w = cols * (card_px + 40) + 40
    canvas_h = rows * (card_px + 40) + 40

    # Classroom background
    canvas = np.full((canvas_h, canvas_w, 3), 235, dtype=np.uint8)

    # Angle mapping to answers: 0->A, 90->B, 180->C, 270->D
    rotations = [0, 90, 180, 270]
    ground_truth = {}

    card_id = 1
    for r in range(rows):
        for c in range(cols):
            if card_id > 45:
                break

            card_path = os.path.join(base_dir, "output", "front", f"card_{card_id:02d}_front.png")
            if not os.path.exists(card_path):
                continue

            card_img = cv2.imread(card_path)
            # Pick a deterministic answer based on card_id
            angle = rotations[(card_id - 1) % 4]
            expected_answer = ["A", "B", "C", "D"][(card_id - 1) % 4]
            ground_truth[card_id] = expected_answer

            # Rotate card
            h, w = card_img.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            rotated = cv2.warpAffine(card_img, M, (w, h), borderValue=(255, 255, 255))

            # Resize to simulate classroom distance
            resized = cv2.resize(rotated, (card_px, card_px))

            # Paste into canvas
            x = 40 + c * (card_px + 40)
            y = 40 + r * (card_px + 40)
            canvas[y:y + card_px, x:x + card_px] = resized

            card_id += 1

    return canvas, ground_truth


def test_classroom_sweep():
    print("==================================================")
    print("   Pi Jam Classroom Sweep End-to-End Simulation   ")
    print("==================================================")

    init_db()
    detector = CVDetector()

    print("\n[Step 1] Synthesizing 25-student classroom collage...")
    classroom_img, ground_truth = create_synthetic_classroom(rows=5, cols=5, card_px=180)
    print(f"  -> Generated canvas dimensions: {classroom_img.shape[1]}x{classroom_img.shape[0]} px")
    print(f"  -> Expected students present: {len(ground_truth)} cards")

    # Save debug snapshot
    debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(debug_dir, exist_ok=True)
    debug_path = os.path.join(debug_dir, "simulated_classroom_25_cards.jpg")
    cv2.imwrite(debug_path, classroom_img)
    print(f"  -> Saved simulation snapshot to: {debug_path}")

    print("\n[Step 2] Initializing Active Classroom Session...")
    active_roster = list(range(1, 31)) # 30 students in Class 7A
    absentees = [5, 12]                 # Student 5 and 12 marked absent
    tracker = SessionTracker(active_roster=active_roster, absentees=absentees, debounce_frames=2)
    print(f"  -> Active Class Roster: {len(active_roster)} students")
    print(f"  -> Marked Absentees: {absentees}")
    print(f"  -> Expected to respond: {len(tracker.expected_students)} students")

    print("\n[Step 3] Running Computer Vision Multi-Card Detection...")
    t0 = time.time()
    cv_res = detector.detect(classroom_img)
    dt = (time.time() - t0) * 1000
    detected_cards = cv_res["cards"]
    print(f"  -> Processing time: {dt:.1f} ms")
    print(f"  -> Cards localized in frame: {len(detected_cards)} of {len(ground_truth)}")

    # Feed into tracker across 2 frames to satisfy debouncing
    for _ in range(2):
        summary = tracker.update_frame(detected_cards)

    print("\n[Step 4] Validating Accuracy of Answers (A/B/C/D):")
    correct = 0
    for card in detected_cards:
        cid = card["card_id"]
        detected_ans = card["answer"]
        expected_ans = ground_truth.get(cid)
        is_match = (detected_ans == expected_ans)
        if is_match:
            correct += 1
        print(f"  Card #{cid:02d}: Expected=[{expected_ans}] Detected=[{detected_ans}] {'[PASS]' if is_match else '[FAIL]'}")

    accuracy = (correct / len(detected_cards) * 100.0) if detected_cards else 0
    print(f"\n[Detection Accuracy]: {correct}/{len(detected_cards)} ({accuracy:.1f}%)")

    print("\n[Step 5] Session Summary & Missing Roll Numbers:")
    print(f"  -> Scanned: {summary['scanned_count']} / {summary['total_expected']} ({summary['percentage']}%)")
    print(f"  -> Missing Roll Numbers: {summary['missing_roll_numbers']}")
    print(f"  -> Vote Distribution: {summary['distribution']}")

    assert accuracy == 100.0, f"Expected 100% accuracy, got {accuracy}%"
    assert summary["scanned_count"] >= 23, "Expected at least 23 present students scanned"
    print("\nSUCCESS: ALL END-TO-END VERIFICATION CHECKS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    test_classroom_sweep()
