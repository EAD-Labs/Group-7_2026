"""
Pi Jam Foundation Classroom Assessment System — Database Layer
SQLite schema, migrations, connection management, and demo data seeding.
"""

import sqlite3
import os
import uuid
from datetime import datetime, timedelta
import random

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assessment.db")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "pdfs")
EXPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "exports")

# Ensure upload and export directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)


def get_db():
    """Returns a SQLite connection with dict-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_not_exists(cursor, table_name: str, column_def: str):
    """Safely adds a column to an existing table if it doesn't already exist."""
    col_name = column_def.strip().split()[0]
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if col_name not in existing_cols:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_def}")


def init_db():
    """Initializes tables, executes safe schema migrations, and seeds test data."""
    conn = get_db()
    cursor = conn.cursor()

    # 1. School table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schools (
        school_id TEXT PRIMARY KEY,
        school_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        udise_code TEXT,
        city TEXT DEFAULT 'Pune'
    )
    """)
    _add_column_if_not_exists(cursor, "schools", "city TEXT DEFAULT 'Pune'")

    # 2. Teachers and Supervisors table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        teacher_id TEXT PRIMARY KEY,
        school_id TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        subject TEXT,
        role TEXT DEFAULT 'teacher', -- 'teacher' or 'manager'
        pin TEXT DEFAULT '1234',
        created_at TEXT NOT NULL,
        FOREIGN KEY (school_id) REFERENCES schools (school_id)
    )
    """)

    # 3. Class Section table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        class_id TEXT PRIMARY KEY,
        school_id TEXT NOT NULL,
        grade TEXT NOT NULL,
        section TEXT NOT NULL,
        academic_year TEXT NOT NULL,
        max_students INTEGER DEFAULT 30,
        FOREIGN KEY (school_id) REFERENCES schools (school_id)
    )
    """)

    # 4. Student table (Admin-only PII partition)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        student_id TEXT PRIMARY KEY,
        class_id TEXT NOT NULL,
        roll_number INTEGER NOT NULL,
        name TEXT,
        status TEXT DEFAULT 'active',
        FOREIGN KEY (class_id) REFERENCES classes (class_id),
        UNIQUE(class_id, roll_number)
    )
    """)

    # 5. Assessment Session table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        class_id TEXT NOT NULL,
        teacher_id TEXT,
        quiz_name TEXT DEFAULT 'Formative Assessment',
        subject TEXT DEFAULT 'General',
        session_date TEXT NOT NULL,
        question_count INTEGER DEFAULT 5,
        question_mode TEXT DEFAULT 'blackboard', -- 'blackboard' or 'pdf'
        pdf_filename TEXT,
        pdf_path TEXT,
        status TEXT DEFAULT 'in_progress', -- 'in_progress', 'completed'
        created_at TEXT NOT NULL,
        FOREIGN KEY (class_id) REFERENCES classes (class_id),
        FOREIGN KEY (teacher_id) REFERENCES teachers (teacher_id)
    )
    """)

    # Safe migrations for sessions table in case of pre-existing DB
    _add_column_if_not_exists(cursor, "sessions", "teacher_id TEXT")
    _add_column_if_not_exists(cursor, "sessions", "quiz_name TEXT DEFAULT 'Formative Assessment'")
    _add_column_if_not_exists(cursor, "sessions", "subject TEXT DEFAULT 'General'")
    _add_column_if_not_exists(cursor, "sessions", "question_count INTEGER DEFAULT 5")
    _add_column_if_not_exists(cursor, "sessions", "question_mode TEXT DEFAULT 'blackboard'")
    _add_column_if_not_exists(cursor, "sessions", "pdf_filename TEXT")
    _add_column_if_not_exists(cursor, "sessions", "pdf_path TEXT")

    # 6. Session Absentees table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS session_absentees (
        session_id TEXT NOT NULL,
        roll_number INTEGER NOT NULL,
        PRIMARY KEY (session_id, roll_number),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    )
    """)

    # 7. Assessment Question table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        question_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        sequence_number INTEGER NOT NULL,
        prompt_text TEXT,
        correct_answer TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    )
    """)

    # 8. Assessment Responses table (Strictly Anonymized: School Code + Class ID + Roll Number only)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS responses (
        response_id TEXT PRIMARY KEY,
        question_id TEXT NOT NULL,
        school_code TEXT NOT NULL,
        class_id TEXT NOT NULL,
        roll_number INTEGER NOT NULL,
        marker_id_detected INTEGER NOT NULL,
        selected_option TEXT NOT NULL,
        confidence REAL DEFAULT 1.0,
        captured_at TEXT NOT NULL,
        FOREIGN KEY (question_id) REFERENCES questions (question_id),
        UNIQUE(question_id, roll_number)
    )
    """)

    # Create Indexes for fast analytics queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_resp_lookup ON responses (school_code, class_id, roll_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_resp_question ON responses (question_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sess_teacher ON sessions (teacher_id, session_date)")

    # Seed demo data if fresh or missing teachers
    cursor.execute("SELECT COUNT(*) FROM teachers")
    if cursor.fetchone()[0] == 0:
        seed_demo_data(cursor)

    conn.commit()
    conn.close()


def seed_demo_data(cursor):
    """Seeds realistic schools, classes, teachers, students, and 90-day historical sessions."""
    now_iso = datetime.utcnow().isoformat()

    # 1. Schools
    cursor.execute("""
    INSERT OR IGNORE INTO schools (school_id, school_code, name, udise_code, city)
    VALUES 
        ('sch_pijam_01', 'PIJAM01', 'Pi Jam Partner Model School — Kothrud', '27250100101', 'Pune'),
        ('sch_pijam_02', 'PIJAM02', 'Pi Jam Innovation Academy — Camp', '27250100102', 'Pune')
    """)

    # 2. Teachers
    cursor.execute("""
    INSERT OR IGNORE INTO teachers (teacher_id, school_id, name, email, subject, role, pin, created_at)
    VALUES 
        ('PJ-T101', 'sch_pijam_01', 'Anjali Sharma', 'anjali.sharma@pijam.org', 'Computer Science & Math', 'teacher', '1234', ?),
        ('PJ-T102', 'sch_pijam_01', 'Rajesh Kulkarni', 'rajesh.k@pijam.org', 'Science', 'teacher', '1234', ?),
        ('PJ-T103', 'sch_pijam_02', 'Priya Verma', 'priya.v@pijam.org', 'Computer Science', 'teacher', '1234', ?),
        ('PJ-M001', 'sch_pijam_01', 'Ulfa Monitoring Lead', 'ulfa.lead@pijam.org', 'Project Oversight', 'manager', '0000', ?)
    """, (now_iso, now_iso, now_iso, now_iso))

    # 3. Classes
    cursor.execute("""
    INSERT OR IGNORE INTO classes (class_id, school_id, grade, section, academic_year, max_students)
    VALUES 
        ('cls_7a', 'sch_pijam_01', '7', 'A', '2026-2027', 30),
        ('cls_8b', 'sch_pijam_01', '8', 'B', '2026-2027', 30),
        ('cls_6a', 'sch_pijam_02', '6', 'A', '2026-2027', 30)
    """)

    # 4. Students for cls_7a, cls_8b, cls_6a (Roll 1 to 30)
    for cls in ['cls_7a', 'cls_8b', 'cls_6a']:
        for roll in range(1, 31):
            std_id = f"std_{cls}_{roll:02d}"
            cursor.execute("""
            INSERT OR IGNORE INTO students (student_id, class_id, roll_number, name, status)
            VALUES (?, ?, ?, ?, 'active')
            """, (std_id, cls, roll, f"Student {roll}"))

    # 5. Historical Sessions across 90 days for Teacher PJ-T101 and PJ-T102
    historical_configs = [
        # (days_ago, teacher_id, class_id, quiz_name, subject, question_count, key)
        (2, 'PJ-T101', 'cls_7a', 'Scratch Loops & Iterations', 'Computer Science', 5, ['A', 'B', 'C', 'D', 'A']),
        (8, 'PJ-T101', 'cls_7a', 'Variables & Operators Check', 'Computer Science', 5, ['B', 'B', 'A', 'C', 'D']),
        (15, 'PJ-T101', 'cls_7a', 'Conditionals If-Else', 'Computer Science', 5, ['C', 'A', 'D', 'B', 'A']),
        (35, 'PJ-T101', 'cls_7a', 'Algorithms & Flowcharts', 'Computer Science', 5, ['A', 'C', 'B', 'D', 'B']),
        (65, 'PJ-T101', 'cls_7a', 'Digital Literacy Baseline', 'Computer Science', 5, ['D', 'A', 'B', 'C', 'C']),
        (5, 'PJ-T102', 'cls_8b', 'Photosynthesis & Plant Biology', 'Science', 5, ['B', 'C', 'A', 'D', 'B']),
        (20, 'PJ-T102', 'cls_8b', 'Forces & Motion Mid-Term', 'Science', 5, ['C', 'C', 'B', 'A', 'D']),
        (12, 'PJ-T103', 'cls_6a', 'Intro to Binary & Numbers', 'Computer Science', 5, ['A', 'A', 'C', 'D', 'B']),
    ]

    for days_ago, t_id, c_id, q_name, subj, q_cnt, ans_key in historical_configs:
        sess_dt = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        sess_id = f"sess_hist_{t_id}_{days_ago}d"
        cursor.execute("""
        INSERT OR IGNORE INTO sessions (session_id, class_id, teacher_id, quiz_name, subject, session_date, question_count, question_mode, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'blackboard', 'completed', ?)
        """, (sess_id, c_id, t_id, q_name, subj, sess_dt, q_cnt, (datetime.utcnow() - timedelta(days=days_ago)).isoformat()))

        # Mark roll 5 & 12 as absent
        cursor.execute("INSERT OR IGNORE INTO session_absentees (session_id, roll_number) VALUES (?, ?)", (sess_id, 5))
        cursor.execute("INSERT OR IGNORE INTO session_absentees (session_id, roll_number) VALUES (?, ?)", (sess_id, 12))

        # Add questions and synthetic responses
        for q_seq in range(1, q_cnt + 1):
            q_id = f"q_{sess_id}_{q_seq}"
            corr_ans = ans_key[q_seq - 1]
            cursor.execute("""
            INSERT OR IGNORE INTO questions (question_id, session_id, sequence_number, prompt_text, correct_answer)
            VALUES (?, ?, ?, ?, ?)
            """, (q_id, sess_id, q_seq, f"Question {q_seq}", corr_ans))

            for roll in range(1, 31):
                if roll in (5, 12):
                    continue
                # 75% probability of correct answer
                chosen = corr_ans if random.random() < 0.75 else random.choice(['A', 'B', 'C', 'D'])
                resp_id = f"resp_{q_id}_{roll}"
                cursor.execute("""
                INSERT OR IGNORE INTO responses (response_id, question_id, school_code, class_id, roll_number, marker_id_detected, selected_option, confidence, captured_at)
                VALUES (?, ?, 'PIJAM01', ?, ?, ?, ?, 0.98, ?)
                """, (resp_id, q_id, c_id, roll, roll, chosen, sess_dt))


# Auto-initialize on import
init_db()
