import os
import json
import uuid
import base64
from datetime import datetime
import cv2
import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from backend.database import get_db
from core.cv_engine import CVDetector
from core.session_tracker import SessionTracker

app = FastAPI(title="Classroom Marker Assessment API")

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared detector instance
detector = CVDetector()

# In-memory active tracker cache for live sessions: {session_id: SessionTracker}
active_trackers = {}

# Pydantic Request Models
class CreateSessionRequest(BaseModel):
    class_id: str

class MarkAbsenteesRequest(BaseModel):
    absentees: List[int]

class CreateQuestionRequest(BaseModel):
    sequence_number: int
    prompt_text: Optional[str] = "Question"
    correct_answer: Optional[str] = None

class CommitResponsesRequest(BaseModel):
    responses: dict  # {roll_no: "A"|"B"|"C"|"D"}

class OfflineSyncPayload(BaseModel):
    session_id: str
    class_id: str
    session_date: str
    absentees: List[int]
    questions: List[dict]  # [{'sequence_number': 1, 'responses': {roll: ans}}]


# --- REST API Endpoints ---

@app.get("/api/schools")
def list_schools():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM schools")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


@app.get("/api/schools/{school_id}/classes")
def list_classes(school_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM classes WHERE school_id = ?", (school_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


@app.get("/api/classes/{class_id}/roster")
def get_roster(class_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT roll_number, name FROM students 
    WHERE class_id = ? AND status = 'active'
    ORDER BY roll_number ASC
    """, (class_id,))
    students = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"class_id": class_id, "students": students}


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    session_id = f"sess_{uuid.uuid4().hex[:10]}"
    now = datetime.utcnow().isoformat()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sessions (session_id, class_id, session_date, status, created_at)
    VALUES (?, ?, ?, 'in_progress', ?)
    """, (session_id, req.class_id, now[:10], now))

    # Fetch roll numbers to initialize SessionTracker
    cursor.execute("SELECT roll_number FROM students WHERE class_id = ?", (req.class_id,))
    rolls = [row[0] for row in cursor.fetchall()]
    conn.commit()
    conn.close()

    # Initialize tracker in memory
    active_trackers[session_id] = SessionTracker(active_roster=rolls)

    return {"session_id": session_id, "status": "in_progress", "total_students": len(rolls)}


@app.post("/api/sessions/{session_id}/absentees")
def mark_absentees(session_id: str, req: MarkAbsenteesRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM session_absentees WHERE session_id = ?", (session_id,))
    for roll in req.absentees:
        cursor.execute("INSERT INTO session_absentees (session_id, roll_number) VALUES (?, ?)", (session_id, roll))
    conn.commit()
    conn.close()

    if session_id in active_trackers:
        tracker = active_trackers[session_id]
        active_trackers[session_id] = SessionTracker(
            active_roster=tracker.roster,
            absentees=req.absentees
        )

    return {"session_id": session_id, "absentees_count": len(req.absentees)}


@app.post("/api/sessions/{session_id}/questions")
def create_question(session_id: str, req: CreateQuestionRequest):
    question_id = f"q_{uuid.uuid4().hex[:10]}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO questions (question_id, session_id, sequence_number, prompt_text, correct_answer)
    VALUES (?, ?, ?, ?, ?)
    """, (question_id, session_id, req.sequence_number, req.prompt_text, req.correct_answer))
    conn.commit()
    conn.close()

    if session_id in active_trackers:
        active_trackers[session_id].reset_for_new_question()

    return {"question_id": question_id, "sequence_number": req.sequence_number}


@app.post("/api/questions/{question_id}/responses")
def commit_responses(question_id: str, req: CommitResponsesRequest):
    conn = get_db()
    cursor = conn.cursor()

    # Fetch context: class_id and school_code
    cursor.execute("""
    SELECT s.class_id, sch.school_code
    FROM questions q
    JOIN sessions s ON q.session_id = s.session_id
    JOIN classes c ON s.class_id = c.class_id
    JOIN schools sch ON c.school_id = sch.school_id
    WHERE q.question_id = ?
    """, (question_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Question not found")

    class_id, school_code = row[0], row[1]
    now = datetime.utcnow().isoformat()

    inserted = 0
    for roll_no, answer in req.responses.items():
        resp_id = f"resp_{uuid.uuid4().hex[:10]}"
        cursor.execute("""
        INSERT OR REPLACE INTO responses 
        (response_id, question_id, school_code, class_id, roll_number, marker_id_detected, selected_option, confidence, captured_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?)
        """, (resp_id, question_id, school_code, class_id, int(roll_no), int(roll_no), answer, now))
        inserted += 1

    conn.commit()
    conn.close()
    return {"question_id": question_id, "committed_count": inserted}


@app.post("/api/sessions/{session_id}/sync")
def sync_offline_session(session_id: str, payload: OfflineSyncPayload):
    """
    Atomic sync endpoint for sessions captured offline in browser IndexedDB.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR REPLACE INTO sessions (session_id, class_id, session_date, status, created_at)
    VALUES (?, ?, ?, 'completed', ?)
    """, (payload.session_id, payload.class_id, payload.session_date, datetime.utcnow().isoformat()))

    # Absentees
    for r in payload.absentees:
        cursor.execute("INSERT OR IGNORE INTO session_absentees (session_id, roll_number) VALUES (?, ?)", (payload.session_id, r))

    # Questions and Responses
    total_responses = 0
    for q in payload.questions:
        q_id = f"q_sync_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO questions (question_id, session_id, sequence_number, prompt_text)
        VALUES (?, ?, ?, ?)
        """, (q_id, payload.session_id, q.get("sequence_number", 1), q.get("prompt_text", "Question")))

        for roll, ans in q.get("responses", {}).items():
            r_id = f"resp_sync_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT OR REPLACE INTO responses
            (response_id, question_id, school_code, class_id, roll_number, marker_id_detected, selected_option, confidence, captured_at)
            VALUES (?, ?, 'OFFLINE', ?, ?, ?, ?, 1.0, ?)
            """, (r_id, q_id, payload.class_id, int(roll), int(roll), ans, datetime.utcnow().isoformat()))
            total_responses += 1

    conn.commit()
    conn.close()
    return {"status": "synced", "session_id": payload.session_id, "total_responses": total_responses}


class AnswerKeyRequest(BaseModel):
    answer_key: dict  # {"1": "A", "2": "B", "3": "C", "4": "D", "5": "A"}


@app.post("/api/sessions/{session_id}/answer_key")
def save_answer_key(session_id: str, req: AnswerKeyRequest):
    conn = get_db()
    cursor = conn.cursor()
    for seq_str, correct_ans in req.answer_key.items():
        seq = int(seq_str)
        cursor.execute("SELECT question_id FROM questions WHERE session_id = ? AND sequence_number = ?", (session_id, seq))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE questions SET correct_answer = ? WHERE question_id = ?", (correct_ans, row[0]))
        else:
            q_id = f"q_{uuid.uuid4().hex[:10]}"
            cursor.execute("""
            INSERT INTO questions (question_id, session_id, sequence_number, prompt_text, correct_answer)
            VALUES (?, ?, ?, ?, ?)
            """, (q_id, session_id, seq, f"Question {seq}", correct_ans))
    conn.commit()
    conn.close()
    return {"status": "success", "session_id": session_id, "answer_key": req.answer_key}


@app.get("/api/sessions/{session_id}/analysis")
def get_session_analysis(session_id: str):
    conn = get_db()
    cursor = conn.cursor()

    # 1. Fetch class info
    cursor.execute("SELECT class_id, session_date, status FROM sessions WHERE session_id = ?", (session_id,))
    sess_row = cursor.fetchone()
    if not sess_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    class_id = sess_row[0]
    cursor.execute("SELECT roll_number FROM students WHERE class_id = ? AND status = 'active' ORDER BY roll_number", (class_id,))
    roster_rolls = [r[0] for r in cursor.fetchall()]

    # 2. Fetch absentees
    cursor.execute("SELECT roll_number FROM session_absentees WHERE session_id = ?", (session_id,))
    absentees = [r[0] for r in cursor.fetchall()]
    expected_rolls = [r for r in roster_rolls if r not in absentees]

    # 3. Fetch questions & answer key
    cursor.execute("SELECT question_id, sequence_number, correct_answer FROM questions WHERE session_id = ? ORDER BY sequence_number ASC", (session_id,))
    questions_rows = cursor.fetchall()
    question_map = {}
    for q_id, seq, ans in questions_rows:
        question_map[seq] = {"question_id": q_id, "correct_answer": ans or ""}

    total_questions = 5  # Pi Jam FAST standard is fixed 5 questions
    for s in range(1, total_questions + 1):
        if s not in question_map:
            question_map[s] = {"question_id": None, "correct_answer": ""}

    # 4. Fetch all responses for this session
    cursor.execute("""
    SELECT q.sequence_number, r.roll_number, r.selected_option
    FROM responses r
    JOIN questions q ON r.question_id = q.question_id
    WHERE q.session_id = ?
    """, (session_id,))
    resp_rows = cursor.fetchall()

    student_responses = {roll: {} for roll in expected_rolls}
    question_distributions = {seq: {"A": 0, "B": 0, "C": 0, "D": 0, "total": 0, "correct_count": 0} for seq in range(1, total_questions + 1)}

    for seq, roll, opt in resp_rows:
        if roll in student_responses:
            student_responses[roll][seq] = opt
        if seq in question_distributions and opt in question_distributions[seq]:
            question_distributions[seq][opt] += 1
            question_distributions[seq]["total"] += 1
            correct = question_map[seq]["correct_answer"]
            if correct and opt == correct:
                question_distributions[seq]["correct_count"] += 1

    # 5. Compute student scorecards & mastery
    student_scorecards = []
    total_class_score = 0
    evaluated_student_count = 0
    mastery_counts = {"high": 0, "moderate": 0, "low": 0}

    for roll in expected_rolls:
        resps = student_responses[roll]
        score = 0
        questions_answered = 0
        breakdown = {}

        for seq in range(1, total_questions + 1):
            given = resps.get(seq, "-")
            correct = question_map[seq]["correct_answer"]
            is_correct = bool(correct and given == correct)
            if is_correct:
                score += 1
            if given != "-":
                questions_answered += 1
            breakdown[seq] = {
                "given": given,
                "correct": correct,
                "is_correct": is_correct
            }

        pct = round((score / total_questions * 100.0), 1)
        if questions_answered > 0:
            total_class_score += pct
            evaluated_student_count += 1

        if pct >= 80:
            mastery = "High Mastery"
            mastery_counts["high"] += 1
        elif pct >= 40:
            mastery = "Moderate"
            mastery_counts["moderate"] += 1
        else:
            mastery = "Needs Support"
            mastery_counts["low"] += 1

        student_scorecards.append({
            "roll_number": roll,
            "score": score,
            "total_questions": total_questions,
            "percentage": pct,
            "mastery": mastery,
            "breakdown": breakdown
        })

    class_average = round(total_class_score / evaluated_student_count, 1) if evaluated_student_count > 0 else 0.0

    question_summary = []
    for seq in range(1, total_questions + 1):
        d = question_distributions[seq]
        corr = question_map[seq]["correct_answer"]
        acc = round((d["correct_count"] / d["total"] * 100.0), 1) if d["total"] > 0 else 0.0
        question_summary.append({
            "sequence": seq,
            "correct_answer": corr,
            "accuracy_percentage": acc,
            "distribution": {k: d[k] for k in ["A", "B", "C", "D"]},
            "total_responses": d["total"]
        })

    conn.close()
    return {
        "session_id": session_id,
        "class_id": class_id,
        "total_expected": len(expected_rolls),
        "total_participated": evaluated_student_count,
        "class_average_percentage": class_average,
        "mastery_counts": mastery_counts,
        "questions": question_summary,
        "scorecards": student_scorecards,
        "answer_key": {str(seq): question_map[seq]["correct_answer"] for seq in range(1, total_questions + 1)}
    }


@app.get("/api/analytics/sessions/{session_id}")
def get_session_analytics(session_id: str):
    return get_session_analysis(session_id)


def to_json_safe(obj):
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json_safe(x) for x in obj]
    return obj


@app.websocket("/api/ws/scan/{session_id}")
async def websocket_scan(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Get or initialize SessionTracker
    if session_id not in active_trackers:
        # Load from DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT s.roll_number 
        FROM sessions sess 
        JOIN students s ON sess.class_id = s.class_id 
        WHERE sess.session_id = ?
        """, (session_id,))
        rolls = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT roll_number FROM session_absentees WHERE session_id = ?", (session_id,))
        absentees = [r[0] for r in cursor.fetchall()]
        conn.close()

        if not rolls:
            rolls = list(range(1, 31))  # Default fallback
        active_trackers[session_id] = SessionTracker(active_roster=rolls, absentees=absentees)

    tracker = active_trackers[session_id]

    try:
        while True:
            # Receive frame as binary JPEG or Base64 string
            data = await websocket.receive()
            if "bytes" in data and data["bytes"]:
                nparr = np.frombuffer(data["bytes"], np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            elif "text" in data and data["text"]:
                msg = json.loads(data["text"])
                if msg.get("action") == "reset":
                    tracker.reset_for_new_question()
                    await websocket.send_json({"type": "RESET_ACK"})
                    continue
                # Base64 image
                img_b64 = msg.get("image", "")
                if "," in img_b64:
                    img_b64 = img_b64.split(",")[1]
                img_bytes = base64.b64decode(img_b64)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                continue

            if frame is None:
                continue

            # Run Computer Vision detection
            cv_res = detector.detect(frame)
            cards = cv_res["cards"]

            # Update Session Tracker
            summary = tracker.update_frame(cards)

            # Send back detections and real-time summary to frontend
            response_payload = {
                "type": "DETECTIONS",
                "cards": cards,
                "summary": summary,
                "is_blurry": bool(cv_res["is_blurry"]),
                "blur_metric": float(cv_res["blur_metric"]),
            }
            await websocket.send_json(to_json_safe(response_payload))

    except WebSocketDisconnect:
        pass


# Mount Frontend & Output static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")

if os.path.exists(output_dir):
    app.mount("/output", StaticFiles(directory=output_dir), name="output")

if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_frontend_root():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
