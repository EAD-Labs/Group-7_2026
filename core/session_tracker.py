import time
from collections import deque, Counter


class SessionTracker:
    """
    Classroom Session State Machine & Anomaly Engine.
    Tracks responses across consecutive frames for an active class roster:
    - Debounces jitter across frames (sliding window)
    - Smoothly detects student vote changes mid-sweep
    - Flags out-of-roster rogue cards
    - Identifies duplicate card conflicts
    - Computes real-time confirmed responses and missing roll numbers
    """

    def __init__(self, active_roster, absentees=None, debounce_frames=3, window_size=5):
        """
        active_roster: list of integer roll numbers (e.g., list(range(1, 31)))
        absentees: list of integer roll numbers marked absent
        debounce_frames: minimum consecutive consistent frames to lock/update an answer
        window_size: sliding history window per card
        """
        self.roster = sorted(list(set(active_roster)))
        self.absentees = set(absentees or [])
        self.expected_students = [r for r in self.roster if r not in self.absentees]
        self.debounce_frames = debounce_frames
        self.window_size = window_size

        # Card state tracking:
        # history: {card_id: deque of (answer, timestamp)}
        self.history = {}
        # confirmed: {card_id: {'answer': str, 'confidence': float, 'timestamp': float}}
        self.confirmed = {}
        # anomalies: list of dicts describing out-of-roster or duplicate events
        self.anomalies = []

    def reset_for_new_question(self):
        """Clears response state for a new question while preserving roster and absentees."""
        self.history.clear()
        self.confirmed.clear()
        self.anomalies.clear()

    def update_frame(self, detected_cards, timestamp=None):
        """
        Ingests the detected cards from a single frame and updates the state machine.
        detected_cards: list of dicts from CVDetector.detect(frame)['cards']
        """
        if timestamp is None:
            timestamp = time.time()

        seen_in_this_frame = set()

        for card in detected_cards:
            cid = card["card_id"]
            ans = card["answer"]

            # Anomaly check 1: Duplicate card in same frame
            if cid in seen_in_this_frame:
                self.anomalies.append({
                    "type": "DUPLICATE_CARD",
                    "card_id": cid,
                    "timestamp": timestamp,
                    "message": f"Card #{cid} detected twice in the same frame!"
                })
                continue

            seen_in_this_frame.add(cid)

            # Anomaly check 2: Out of active roster
            if cid not in self.roster:
                self.anomalies.append({
                    "type": "ROGUE_CARD",
                    "card_id": cid,
                    "timestamp": timestamp,
                    "message": f"Card #{cid} is not in the active class roster!"
                })
                continue

            # Check 3: Student was marked absent
            if cid in self.absentees:
                self.anomalies.append({
                    "type": "ABSENT_STUDENT_DETECTED",
                    "card_id": cid,
                    "timestamp": timestamp,
                    "message": f"Card #{cid} belongs to an absentee student!"
                })

            # Ignore ambiguous readings in history accumulator
            if ans == "AMBIGUOUS":
                continue

            # Update sliding window history
            if cid not in self.history:
                self.history[cid] = deque(maxlen=self.window_size)
            self.history[cid].append((ans, timestamp))

            # Evaluate debouncing for this card
            recent_answers = [a for a, t in self.history[cid]]
            if len(recent_answers) >= self.debounce_frames:
                # Count frequency in recent frames
                counts = Counter(recent_answers)
                most_common_ans, count = counts.most_common(1)[0]

                if count >= self.debounce_frames:
                    # Lock in or update confirmed answer
                    prev_ans = self.confirmed.get(cid, {}).get("answer")
                    if prev_ans != most_common_ans:
                        self.confirmed[cid] = {
                            "answer": most_common_ans,
                            "confidence": float(count / len(recent_answers)),
                            "timestamp": timestamp,
                            "updated": prev_ans is not None,
                        }

        return self.get_summary()

    def get_summary(self):
        """
        Returns full real-time snapshot of the classroom scanning session.
        """
        confirmed_ids = set(self.confirmed.keys())
        expected_ids = set(self.expected_students)

        missing_roll_numbers = sorted(list(expected_ids - confirmed_ids))
        scanned_count = len(confirmed_ids.intersection(expected_ids))
        total_expected = len(expected_ids)
        percentage = round((scanned_count / total_expected * 100.0), 1) if total_expected > 0 else 100.0

        # Answer distribution (A, B, C, D counts)
        distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
        for info in self.confirmed.values():
            ans = info["answer"]
            if ans in distribution:
                distribution[ans] += 1

        return {
            "scanned_count": scanned_count,
            "total_expected": total_expected,
            "percentage": percentage,
            "is_complete": scanned_count >= total_expected and total_expected > 0,
            "missing_roll_numbers": missing_roll_numbers,
            "confirmed_responses": {
                roll_no: self.confirmed[roll_no]["answer"]
                for roll_no in sorted(confirmed_ids)
                if roll_no in self.roster
            },
            "distribution": distribution,
            "anomalies": self.anomalies[-5:] if self.anomalies else [],
        }
