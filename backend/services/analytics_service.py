"""
Pi Jam Foundation Classroom Assessment System — Analytics Service
Real-time reactive score calculation, distractor analysis, and historical reporting.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from backend.database import get_db


def calculate_session_analysis(session_id: str, custom_answer_key: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Computes complete assessment analytics for a given session.
    If custom_answer_key is provided (e.g. { "1": "C", "2": "A" }), it overrides
    stored question keys dynamically without modifying raw response logs.
    """
    conn = get_db()
    cursor = conn.cursor()

    # 1. Fetch Session & Class Metadata
    cursor.execute("""
    SELECT 
        s.session_id, s.class_id, s.teacher_id, s.quiz_name, s.subject, 
        s.session_date, s.question_count, s.question_mode, s.pdf_filename, s.pdf_path,
        c.grade, c.section, sch.name as school_name, sch.school_code,
        t.name as teacher_name
    FROM sessions s
    JOIN classes c ON s.class_id = c.class_id
    JOIN schools sch ON c.school_id = sch.school_id
    LEFT JOIN teachers t ON s.teacher_id = t.teacher_id
    WHERE s.session_id = ?
    """, (session_id,))
    session_row = cursor.fetchone()
    if not session_row:
        conn.close()
        raise ValueError(f"Session '{session_id}' not found.")

    session_info = dict(session_row)

    # 2. Fetch Absentees
    cursor.execute("SELECT roll_number FROM session_absentees WHERE session_id = ?", (session_id,))
    absentees = set(r[0] for r in cursor.fetchall())

    # 3. Fetch Roster
    cursor.execute("""
    SELECT roll_number, name FROM students 
    WHERE class_id = ? AND status = 'active'
    ORDER BY roll_number ASC
    """, (session_info["class_id"],))
    roster = [dict(r) for r in cursor.fetchall()]
    total_enrolled = len(roster)
    present_rolls = [r["roll_number"] for r in roster if r["roll_number"] not in absentees]
    total_present = len(present_rolls)

    # 4. Fetch Questions
    cursor.execute("""
    SELECT question_id, sequence_number, prompt_text, correct_answer 
    FROM questions 
    WHERE session_id = ? 
    ORDER BY sequence_number ASC
    """, (session_id,))
    db_questions = [dict(r) for r in cursor.fetchall()]

    # If questions aren't created yet or fewer than question_count, fill structure
    q_count = session_info["question_count"] or 5
    questions_map = {q["sequence_number"]: q for q in db_questions}
    effective_questions = []

    for seq in range(1, q_count + 1):
        if seq in questions_map:
            q_data = questions_map[seq]
        else:
            q_data = {
                "question_id": f"q_{session_id}_{seq}",
                "sequence_number": seq,
                "prompt_text": f"Question {seq}",
                "correct_answer": None
            }
        
        # Apply custom answer key if provided
        if custom_answer_key and str(seq) in custom_answer_key:
            q_data["correct_answer"] = custom_answer_key[str(seq)]
        
        effective_questions.append(q_data)

    # 5. Fetch All Responses for this session's questions
    cursor.execute("""
    SELECT r.question_id, q.sequence_number, r.roll_number, r.selected_option, r.confidence
    FROM responses r
    JOIN questions q ON r.question_id = q.question_id
    WHERE q.session_id = ?
    """, (session_id,))
    response_rows = cursor.fetchall()
    conn.close()

    # Map responses: matrix[roll_number][seq] = selected_option
    matrix: Dict[int, Dict[int, str]] = {roll: {} for roll in present_rolls}
    participated_rolls = set()

    for row in response_rows:
        roll = row["roll_number"]
        seq = row["sequence_number"]
        opt = row["selected_option"]
        if roll in matrix:
            matrix[roll][seq] = opt
            participated_rolls.add(roll)

    # 6. Item & Distractor Analysis
    questions_analysis = []
    effective_key_dict = {}

    for q in effective_questions:
        seq = q["sequence_number"]
        corr = q["correct_answer"]
        effective_key_dict[str(seq)] = corr

        distractors = {"A": 0, "B": 0, "C": 0, "D": 0}
        total_answers_for_q = 0
        correct_count = 0

        for roll in present_rolls:
            ans = matrix[roll].get(seq)
            if ans in distractors:
                distractors[ans] += 1
                total_answers_for_q += 1
                if corr and ans == corr:
                    correct_count += 1

        accuracy = round((correct_count / total_answers_for_q * 100), 1) if total_answers_for_q > 0 else 0.0

        questions_analysis.append({
            "sequence": seq,
            "prompt": q["prompt_text"],
            "correct_answer": corr,
            "total_responses": total_answers_for_q,
            "correct_count": correct_count,
            "accuracy_percentage": accuracy,
            "distractors": distractors
        })

    # 7. Student Scorecards & Mastery Classification
    scorecards = []
    total_class_score = 0
    mastery_counts = {"high": 0, "moderate": 0, "low": 0}

    for student in roster:
        roll = student["roll_number"]
        name = student["name"]
        is_absent = roll in absentees

        if is_absent:
            scorecards.append({
                "roll_number": roll,
                "name": name,
                "is_absent": True,
                "score": 0,
                "total_questions": q_count,
                "percentage": 0,
                "mastery": "Absent",
                "breakdown": {seq: {"given": "-", "is_correct": False} for seq in range(1, q_count + 1)}
            })
            continue

        student_score = 0
        breakdown = {}

        for seq in range(1, q_count + 1):
            given = matrix[roll].get(seq, "-")
            corr = effective_key_dict.get(str(seq))
            is_corr = bool(corr and given == corr)
            if is_corr:
                student_score += 1
            breakdown[seq] = {"given": given, "is_correct": is_corr}

        pct = round((student_score / q_count * 100), 1) if q_count > 0 else 0.0
        total_class_score += pct

        if pct >= 80.0:
            mastery = "High Mastery"
            mastery_counts["high"] += 1
        elif pct >= 50.0:
            mastery = "Moderate Help"
            mastery_counts["moderate"] += 1
        else:
            mastery = "Critical Support"
            mastery_counts["low"] += 1

        scorecards.append({
            "roll_number": roll,
            "name": name,
            "is_absent": False,
            "score": student_score,
            "total_questions": q_count,
            "percentage": pct,
            "mastery": mastery,
            "breakdown": breakdown
        })

    class_avg = round(total_class_score / total_present, 1) if total_present > 0 else 0.0

    return {
        "session_id": session_id,
        "quiz_name": session_info["quiz_name"],
        "subject": session_info["subject"],
        "school_name": session_info["school_name"],
        "teacher_name": session_info["teacher_name"] or "Class Teacher",
        "class_id": session_info["class_id"],
        "class_label": f"Grade {session_info['grade']}-{session_info['section']}",
        "session_date": session_info["session_date"],
        "question_count": q_count,
        "question_mode": session_info["question_mode"],
        "pdf_filename": session_info["pdf_filename"],
        "total_enrolled": total_enrolled,
        "total_present": total_present,
        "total_absent": len(absentees),
        "total_participated": len(participated_rolls),
        "class_average_percentage": class_avg,
        "mastery_counts": mastery_counts,
        "answer_key": effective_key_dict,
        "questions": questions_analysis,
        "scorecards": scorecards
    }


def get_teacher_historical_analytics(teacher_id: str, time_filter: str = "month") -> Dict[str, Any]:
    """
    Retrieves rolling 90-day history for a specific teacher.
    Aggregates metrics by day, week, or month.
    """
    conn = get_db()
    cursor = conn.cursor()

    cutoff_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

    cursor.execute("""
    SELECT 
        s.session_id, s.quiz_name, s.subject, s.session_date, s.question_count,
        s.question_mode, s.pdf_filename, s.status,
        c.grade, c.section, sch.name as school_name
    FROM sessions s
    JOIN classes c ON s.class_id = c.class_id
    JOIN schools sch ON c.school_id = sch.school_id
    WHERE s.teacher_id = ? AND s.session_date >= ?
    ORDER BY s.session_date DESC
    """, (teacher_id, cutoff_date))
    sessions = [dict(r) for r in cursor.fetchall()]

    # Fetch teacher profile
    cursor.execute("SELECT name, subject, school_id FROM teachers WHERE teacher_id = ?", (teacher_id,))
    t_row = cursor.fetchone()
    teacher_profile = dict(t_row) if t_row else {"name": "Teacher", "subject": "All", "school_id": ""}

    # Detailed session histories with computed averages
    history_items = []
    total_students_assessed = 0
    score_percentages = []

    for s in sessions:
        try:
            analysis = calculate_session_analysis(s["session_id"])
            avg_score = analysis["class_average_percentage"]
            participated = analysis["total_participated"]
        except Exception:
            avg_score = 0.0
            participated = 0

        score_percentages.append(avg_score)
        total_students_assessed += participated

        history_items.append({
            "session_id": s["session_id"],
            "quiz_name": s["quiz_name"],
            "subject": s["subject"],
            "class_label": f"Grade {s['grade']}-{s['section']}",
            "school_name": s["school_name"],
            "session_date": s["session_date"],
            "question_count": s["question_count"],
            "question_mode": s["question_mode"],
            "pdf_filename": s["pdf_filename"],
            "average_percentage": avg_score,
            "students_assessed": participated,
        })

    conn.close()

    overall_avg = round(sum(score_percentages) / len(score_percentages), 1) if score_percentages else 0.0

    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher_profile["name"],
        "subject": teacher_profile["subject"],
        "total_quizzes_conducted": len(sessions),
        "total_students_assessed": total_students_assessed,
        "overall_average_percentage": overall_avg,
        "time_filter": time_filter,
        "history": history_items
    }


def get_manager_dashboard_analytics() -> Dict[str, Any]:
    """
    Retrieves overarching supervisor dashboard across all teachers, classes, and schools.
    """
    conn = get_db()
    cursor = conn.cursor()

    # 1. Overview counts
    cursor.execute("SELECT COUNT(*) FROM schools")
    total_schools = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM teachers WHERE role = 'teacher'")
    total_teachers = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sessions")
    total_sessions = cursor.fetchone()[0]

    # 2. Per-Teacher Performance
    cursor.execute("""
    SELECT 
        t.teacher_id, t.name, t.email, t.subject, sch.name as school_name,
        COUNT(s.session_id) as total_quizzes,
        MAX(s.session_date) as last_active_date
    FROM teachers t
    JOIN schools sch ON t.school_id = sch.school_id
    LEFT JOIN sessions s ON t.teacher_id = s.teacher_id
    WHERE t.role = 'teacher'
    GROUP BY t.teacher_id
    ORDER BY total_quizzes DESC
    """)
    teachers_data = [dict(r) for r in cursor.fetchall()]

    for t in teachers_data:
        # Calculate teacher's overall student count and avg score
        cursor.execute("SELECT session_id FROM sessions WHERE teacher_id = ?", (t["teacher_id"],))
        s_ids = [r[0] for r in cursor.fetchall()]
        scores = []
        students_reached = 0
        for sid in s_ids:
            try:
                a = calculate_session_analysis(sid)
                scores.append(a["class_average_percentage"])
                students_reached += a["total_participated"]
            except Exception:
                continue
        t["avg_score"] = round(sum(scores) / len(scores), 1) if scores else 0.0
        t["students_reached"] = students_reached

    # 3. Recent 5 Completed Assessments Across All Schools
    cursor.execute("""
    SELECT 
        s.session_id, s.quiz_name, s.subject, s.session_date,
        t.name as teacher_name, sch.name as school_name,
        c.grade, c.section
    FROM sessions s
    LEFT JOIN teachers t ON s.teacher_id = t.teacher_id
    JOIN classes c ON s.class_id = c.class_id
    JOIN schools sch ON c.school_id = sch.school_id
    ORDER BY s.session_date DESC, s.created_at DESC
    LIMIT 5
    """)
    recent_feed = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "summary": {
            "total_schools": total_schools,
            "total_teachers": total_teachers,
            "total_assessments": total_sessions,
        },
        "teachers": teachers_data,
        "recent_activity": recent_feed
    }
