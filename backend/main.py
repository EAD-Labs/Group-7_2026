"""
Pi Jam Foundation Classroom Assessment System — FastAPI Application
REST APIs, File Uploads, Real-time Recalculation, WebSocket CV Scanner, and Static Asset Server.
"""

import os
import json
import uuid
import base64
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.database import get_db, UPLOAD_DIR, EXPORT_DIR
from backend.services.analytics_service import (
    calculate_session_analysis,
    get_teacher_historical_analytics,
    get_manager_dashboard_analytics,
)
from backend.services.export_service import (
    generate_excel_scorecard,
    generate_merged_pdf,
)
from core.cv_engine import CVDetector
from core.session_tracker import SessionTracker

app = FastAPI(
    title="Pi Jam FAST Assessment Platform API",
    description="Vision-based low-cost formative assessment system for real classrooms.",
    version="2.0.0"
)

# Enable CORS for local network and mobile devices
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared detector instance for marker localization
detector = CVDetector()

# In-memory active tracker cache for live sessions: {session_id: SessionTracker}
active_trackers: Dict[str, SessionTracker] = {}


# --- Health Check (used by Railway/Render deployment health checks) ---

@app.get("/api/health")
def health_check():
    """
    Lightweight liveness endpoint.
    Railway, Render, and load balancers poll this every 30s to confirm the server is running.
    Returns server status and environment type.
    """
    return {
        "status": "ok",
        "service": "Pi Jam FAST Assessment API",
        "version": "2.0.0",
        "environment": os.environ.get("PIJAM_ENV", "development"),
    }



# --- Pydantic Schemas ---

class LoginRequest(BaseModel):
    user_id: str  # Teacher ID (e.g. 'PJ-T101') or Manager ID ('PJ-M001')
    pin: Optional[str] = "1234"


class CreateSessionRequest(BaseModel):
    class_id: str
    teacher_id: Optional[str] = "PJ-T101"
    quiz_name: Optional[str] = "Formative Assessment"
    subject: Optional[str] = "Computer Science"
    session_date: Optional[str] = None
    question_count: Optional[int] = 5
    question_mode: Optional[str] = "blackboard"  # "blackboard" or "pdf"
    pre_set_answer_key: Optional[Dict[str, str]] = None  # e.g. {"1": "A", "2": "C"}


class MarkAbsenteesRequest(BaseModel):
    absentees: List[int]


class CreateQuestionRequest(BaseModel):
    sequence_number: int
    prompt_text: Optional[str] = "Question"
    correct_answer: Optional[str] = None


class CommitResponsesRequest(BaseModel):
    responses: Dict[str, str]  # {roll_no: "A"|"B"|"C"|"D"}


class AnswerKeyRequest(BaseModel):
    answer_key: Dict[str, str]  # {"1": "A", "2": "B", ...}


class RecalculateRequest(BaseModel):
    answer_key: Dict[str, str]
    persist: Optional[bool] = False


class OfflineSyncPayload(BaseModel):
    session_id: str
    class_id: str
    teacher_id: Optional[str] = "PJ-T101"
    quiz_name: Optional[str] = "Offline Assessment"
    subject: Optional[str] = "General"
    session_date: str
    question_count: int = 5
    question_mode: str = "blackboard"
    answer_key: Optional[Dict[str, str]] = None
    absentees: List[int]
    questions: List[Dict[str, Any]]  # [{'sequence_number': 1, 'responses': {roll: ans}}]


# --- Authentication & Profile Endpoints ---

@app.post("/api/auth/login")
def login(req: LoginRequest):
    """
    Authenticates teacher or supervisor by ID.
    Returns teacher profile, assigned schools, and classes.
    """
    clean_id = req.user_id.strip()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT t.teacher_id, t.school_id, t.name, t.email, t.subject, t.role, t.pin,
           sch.name as school_name, sch.school_code
    FROM teachers t
    JOIN schools sch ON t.school_id = sch.school_id
    WHERE LOWER(t.teacher_id) = LOWER(?)
    """, (clean_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail=f"User ID '{req.user_id}' not found in registry.")

    user = dict(row)
    # Check PIN if configured
    if req.pin and user.get("pin") and req.pin.strip() != user["pin"].strip():
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid security PIN.")

    # Fetch classes available for this teacher's school
    cursor.execute("""
    SELECT class_id, grade, section, academic_year, max_students
    FROM classes
    WHERE school_id = ?
    ORDER BY grade ASC, section ASC
    """, (user["school_id"],))
    classes = [dict(c) for c in cursor.fetchall()]
    conn.close()

    return {
        "status": "success",
        "user": {
            "teacher_id": user["teacher_id"],
            "name": user["name"],
            "email": user["email"],
            "subject": user["subject"],
            "role": user["role"],
            "school_id": user["school_id"],
            "school_name": user["school_name"],
            "school_code": user["school_code"]
        },
        "classes": classes
    }


@app.get("/api/teachers")
def list_teachers():
    """Lists registered teachers for quick selection in school mode."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT t.teacher_id, t.name, t.subject, t.role, sch.name as school_name
    FROM teachers t
    JOIN schools sch ON t.school_id = sch.school_id
    ORDER BY t.role DESC, t.name ASC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# --- School & Roster Endpoints ---

@app.get("/api/schools")
def list_schools():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM schools ORDER BY name ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


@app.get("/api/schools/{school_id}/classes")
def list_classes(school_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM classes WHERE school_id = ? ORDER BY grade ASC, section ASC", (school_id,))
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


# --- Assessment Session Lifecycle Endpoints ---

@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    """
    Initializes a new assessment session with dynamic questions,
    metadata, and optional pre-set answer key.
    """
    session_id = f"sess_{uuid.uuid4().hex[:10]}"
    now = datetime.utcnow().isoformat()
    sess_date = req.session_date or now[:10]
    q_count = max(1, min(req.question_count or 5, 25))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sessions (
        session_id, class_id, teacher_id, quiz_name, subject, 
        session_date, question_count, question_mode, status, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)
    """, (
        session_id, req.class_id, req.teacher_id, req.quiz_name, req.subject,
        sess_date, q_count, req.question_mode, now
    ))

    # Pre-populate question entries
    pre_key = req.pre_set_answer_key or {}
    for seq in range(1, q_count + 1):
        q_id = f"q_{session_id}_{seq}"
        corr = pre_key.get(str(seq))
        cursor.execute("""
        INSERT INTO questions (question_id, session_id, sequence_number, prompt_text, correct_answer)
        VALUES (?, ?, ?, ?, ?)
        """, (q_id, session_id, seq, f"Question {seq}", corr))

    # Fetch roll numbers to initialize SessionTracker
    cursor.execute("SELECT roll_number FROM students WHERE class_id = ?", (req.class_id,))
    rolls = [row[0] for row in cursor.fetchall()]
    if not rolls:
        rolls = list(range(1, 31))  # Fallback 1 to 30

    conn.commit()
    conn.close()

    # Initialize tracker in memory
    active_trackers[session_id] = SessionTracker(active_roster=rolls)

    return {
        "session_id": session_id,
        "quiz_name": req.quiz_name,
        "question_count": q_count,
        "question_mode": req.question_mode,
        "status": "in_progress",
        "total_students": len(rolls)
    }


@app.post("/api/sessions/{session_id}/upload-pdf")
async def upload_question_pdf(session_id: str, file: UploadFile = File(...)):
    """
    Uploads question paper PDF for archival and merges into the final report.
    Stores in backend/uploads/pdfs/{session_id}_{filename}.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Sanitize filename
    clean_name = os.path.basename(file.filename)
    dest_filename = f"{session_id}_{clean_name}"
    dest_path = os.path.join(UPLOAD_DIR, dest_filename)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Update session in DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE sessions 
    SET pdf_filename = ?, pdf_path = ?, question_mode = 'pdf'
    WHERE session_id = ?
    """, (clean_name, dest_path, session_id))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "session_id": session_id,
        "filename": clean_name,
        "size_bytes": os.path.getsize(dest_path)
    }


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
    conn = get_db()
    cursor = conn.cursor()
    # Check if question exists
    cursor.execute("SELECT question_id FROM questions WHERE session_id = ? AND sequence_number = ?", (session_id, req.sequence_number))
    row = cursor.fetchone()

    if row:
        question_id = row[0]
        if req.correct_answer:
            cursor.execute("UPDATE questions SET correct_answer = ? WHERE question_id = ?", (req.correct_answer, question_id))
    else:
        question_id = f"q_{session_id}_{req.sequence_number}"
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
        resp_id = f"resp_{question_id}_{roll_no}"
        cursor.execute("""
        INSERT OR REPLACE INTO responses 
        (response_id, question_id, school_code, class_id, roll_number, marker_id_detected, selected_option, confidence, captured_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?)
        """, (resp_id, question_id, school_code, class_id, int(roll_no), int(roll_no), answer, now))
        inserted += 1

    conn.commit()
    conn.close()
    return {"question_id": question_id, "committed_count": inserted}


@app.post("/api/sessions/{session_id}/answer_key")
def save_answer_key(session_id: str, req: AnswerKeyRequest):
    """
    Persists updated answer key to database and returns newly recalculated analysis.
    """
    conn = get_db()
    cursor = conn.cursor()

    for seq_str, correct_ans in req.answer_key.items():
        seq = int(seq_str)
        cursor.execute("SELECT question_id FROM questions WHERE session_id = ? AND sequence_number = ?", (session_id, seq))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE questions SET correct_answer = ? WHERE question_id = ?", (correct_ans, row[0]))
        else:
            q_id = f"q_{session_id}_{seq}"
            cursor.execute("""
            INSERT INTO questions (question_id, session_id, sequence_number, prompt_text, correct_answer)
            VALUES (?, ?, ?, ?, ?)
            """, (q_id, session_id, seq, f"Question {seq}", correct_ans))

    cursor.execute("UPDATE sessions SET status = 'completed' WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

    # Recalculate analysis
    analysis = calculate_session_analysis(session_id)
    return {"status": "success", "session_id": session_id, "analysis": analysis}


@app.post("/api/sessions/{session_id}/recalculate")
def recalculate_live(session_id: str, req: RecalculateRequest):
    """
    Instant reactive recalculation endpoint.
    Recalculates scores, mastery, and charts on the fly when the teacher edits the key.
    """
    if req.persist:
        # Also persist to DB
        return save_answer_key(session_id, AnswerKeyRequest(answer_key=req.answer_key))

    # Real-time computation without modifying database
    analysis = calculate_session_analysis(session_id, custom_answer_key=req.answer_key)
    return {"status": "recalculated", "analysis": analysis}


@app.get("/api/sessions/{session_id}/analysis")
def get_session_analysis_endpoint(session_id: str):
    """Returns detailed assessment scorecard and distractor analysis."""
    try:
        return calculate_session_analysis(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Export Endpoints (Excel & Merged PDF) ---

@app.get("/api/sessions/{session_id}/export/excel")
def export_excel(session_id: str):
    """Generates and serves downloadable Excel spreadsheet (.xlsx)."""
    try:
        file_path = generate_excel_scorecard(session_id)
        filename = os.path.basename(file_path)
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Excel report: {str(e)}")


@app.get("/api/sessions/{session_id}/export/merged-pdf")
def export_merged_pdf(session_id: str):
    """
    Generates unified dossier PDF:
    Page 1: Performance Scorecard Table
    Page 2+: Uploaded Question Paper PDF
    """
    try:
        file_path = generate_merged_pdf(session_id)
        filename = os.path.basename(file_path)
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate merged PDF: {str(e)}")


# --- Historical & Supervisor Dashboards ---

@app.get("/api/teachers/{teacher_id}/history")
def get_teacher_history(teacher_id: str, range: Optional[str] = Query("month", pattern="^(day|week|month)$")):
    """Retrieves 90-day assessment archive for teacher."""
    return get_teacher_historical_analytics(teacher_id, time_filter=range)


@app.get("/api/manager/dashboard")
def get_manager_dashboard():
    """Supervisor view of all schools, teachers, and aggregate metrics."""
    return get_manager_dashboard_analytics()


# --- Offline Synchronization Endpoint ---

@app.post("/api/sessions/{session_id}/sync")
def sync_offline_session(session_id: str, payload: OfflineSyncPayload):
    """
    Atomic sync endpoint for sessions captured offline in browser IndexedDB.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR REPLACE INTO sessions (
        session_id, class_id, teacher_id, quiz_name, subject, 
        session_date, question_count, question_mode, status, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
    """, (
        payload.session_id, payload.class_id, payload.teacher_id,
        payload.quiz_name, payload.subject, payload.session_date,
        payload.question_count, payload.question_mode, datetime.utcnow().isoformat()
    ))

    # Absentees
    for r in payload.absentees:
        cursor.execute("INSERT OR IGNORE INTO session_absentees (session_id, roll_number) VALUES (?, ?)", (payload.session_id, r))

    # Questions and Responses
    total_responses = 0
    for q in payload.questions:
        seq = q.get("sequence_number", 1)
        q_id = f"q_{payload.session_id}_{seq}"
        corr = payload.answer_key.get(str(seq)) if payload.answer_key else None

        cursor.execute("""
        INSERT OR REPLACE INTO questions (question_id, session_id, sequence_number, prompt_text, correct_answer)
        VALUES (?, ?, ?, ?, ?)
        """, (q_id, payload.session_id, seq, f"Question {seq}", corr))

        for roll, ans in q.get("responses", {}).items():
            r_id = f"resp_{q_id}_{roll}"
            cursor.execute("""
            INSERT OR REPLACE INTO responses
            (response_id, question_id, school_code, class_id, roll_number, marker_id_detected, selected_option, confidence, captured_at)
            VALUES (?, ?, 'OFFLINE', ?, ?, ?, ?, 1.0, ?)
            """, (r_id, q_id, payload.class_id, int(roll), int(roll), ans, datetime.utcnow().isoformat()))
            total_responses += 1

    conn.commit()
    conn.close()
    return {"status": "synced", "session_id": payload.session_id, "total_responses": total_responses}


# --- Computer Vision WebSocket Endpoint ---

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
                "frame_width": int(cv_res.get("frame_width", frame.shape[1])),
                "frame_height": int(cv_res.get("frame_height", frame.shape[0])),
            }
            await websocket.send_json(to_json_safe(response_payload))

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as e:
        print(f"WebSocket session closed: {e}")


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
