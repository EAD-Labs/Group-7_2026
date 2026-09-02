import sqlite3
import os
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assessment.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. School table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schools (
        school_id TEXT PRIMARY KEY,
        school_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        udise_code TEXT
    )
    """)

    # 2. Class Section table
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

    # 3. Student table (Admin-only PII partition)
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

    # 4. Assessment Session table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        class_id TEXT NOT NULL,
        session_date TEXT NOT NULL,
        status TEXT DEFAULT 'in_progress',
        created_at TEXT NOT NULL,
        FOREIGN KEY (class_id) REFERENCES classes (class_id)
    )
    """)

    # 5. Session Absentees table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS session_absentees (
        session_id TEXT NOT NULL,
        roll_number INTEGER NOT NULL,
        PRIMARY KEY (session_id, roll_number),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    )
    """)

    # 6. Assessment Question table
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

    # 7. Assessment Responses table (Strictly Anonymized: School Code + Class ID + Roll Number only)
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

    # Seed demo data if database is fresh
    cursor.execute("SELECT COUNT(*) FROM schools")
    if cursor.fetchone()[0] == 0:
        seed_demo_data(cursor)

    conn.commit()
    conn.close()


def seed_demo_data(cursor):
    school_id = "sch_pijam_01"
    cursor.execute("""
    INSERT INTO schools (school_id, school_code, name, udise_code)
    VALUES (?, ?, ?, ?)
    """, (school_id, "PIJAM01", "Pi Jam Partner Model School", "27250100101"))

    class_id = "cls_7a"
    cursor.execute("""
    INSERT INTO classes (class_id, school_id, grade, section, academic_year, max_students)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (class_id, school_id, "7", "A", "2026-2027", 30))

    # Seed 30 students (Roll 1 to 30)
    for roll in range(1, 31):
        std_id = f"std_7a_{roll:02d}"
        cursor.execute("""
        INSERT INTO students (student_id, class_id, roll_number, name, status)
        VALUES (?, ?, ?, ?, 'active')
        """, (std_id, class_id, roll, f"Student {roll}"))


# Initialize on import
init_db()
