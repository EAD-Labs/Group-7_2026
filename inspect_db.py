import sqlite3
import os

def inspect():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "assessment.db")
    if not os.path.exists(db_path):
        print("[-] Database does not exist yet. Run the server and complete an assessment first.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n" + "=" * 75)
    print("           PI JAM FAST ASSESSMENT -- DATABASE REPORT CARD          ")
    print("=" * 75)

    # Fetch all sessions
    cursor.execute("SELECT * FROM sessions ORDER BY created_at DESC")
    sessions = cursor.fetchall()
    if not sessions:
        print("\nNo assessment sessions recorded in the database yet.\n")
        conn.close()
        return

    print(f"\nTotal Assessment Sessions in DB: {len(sessions)}")

    # Inspect the most recent 2 sessions
    for sess_idx, s in enumerate(sessions[:2]):
        sess_id = s["session_id"]
        class_id = s["class_id"]
        date_str = s["session_date"]

        # Fetch absentees
        cursor.execute("SELECT roll_number FROM session_absentees WHERE session_id = ?", (sess_id,))
        absentees = [r[0] for r in cursor.fetchall()]

        # Fetch questions and their answer keys
        cursor.execute("""
        SELECT question_id, sequence_number, correct_answer 
        FROM questions WHERE session_id = ? 
        ORDER BY sequence_number ASC
        """, (sess_id,))
        questions = cursor.fetchall()
        q_map = {q["sequence_number"]: {"id": q["question_id"], "key": q["correct_answer"] or "-"} for q in questions}

        total_q = max(5, max(q_map.keys()) if q_map else 5)

        # Fetch all student responses
        cursor.execute("""
        SELECT q.sequence_number, r.roll_number, r.selected_option
        FROM responses r
        JOIN questions q ON r.question_id = q.question_id
        WHERE q.session_id = ?
        ORDER BY r.roll_number ASC, q.sequence_number ASC
        """, (sess_id,))
        responses = cursor.fetchall()

        # Build matrix: roll_no -> {q_seq: answer}
        matrix = {}
        for seq, roll, opt in responses:
            if roll not in matrix:
                matrix[roll] = {}
            matrix[roll][seq] = opt

        print("\n" + "-" * 75)
        print(f"SESSION #{sess_idx + 1}: {sess_id} | Class: {class_id} | Date: {date_str}")
        print(f"Students Responded: {len(matrix)} | Absentees: {absentees if absentees else 'None'}")
        
        # Display Answer Key
        keys_str = " | ".join([f"Q{i}: [{q_map.get(i, {}).get('key', '-')}]" for i in range(1, total_q + 1)])
        print(f"Answer Key: {keys_str}")
        print("-" * 75)

        if not matrix:
            print("  (No responses captured for this session yet)")
            continue

        # Print Formatted Student Scorecard Matrix
        header = f"| {'Roll No':^9} | " + " | ".join([f" Q{i} " for i in range(1, total_q + 1)]) + f" | {'Score':^7} | {'Mastery':^13} |"
        sep = "+" + "-" * 11 + "+" + "+".join(["-" * 6 for _ in range(total_q)]) + "+" + "-" * 9 + "+" + "-" * 15 + "+"

        print(sep)
        print(header)
        print(sep)

        total_scores = 0
        students_scored = 0

        for roll in sorted(matrix.keys()):
            resps = matrix[roll]
            row_items = []
            score = 0
            for i in range(1, total_q + 1):
                ans = resps.get(i, "-")
                key = q_map.get(i, {}).get("key", "-")
                if key != "-" and ans == key:
                    score += 1
                    row_items.append(f"{ans}*") # asterisk indicates correct
                else:
                    row_items.append(f" {ans} ")

            pct = round(score / total_q * 100.0)
            total_scores += pct
            students_scored += 1

            if pct >= 80:
                mastery = "High"
            elif pct >= 40:
                mastery = "Moderate"
            else:
                mastery = "Needs Help"

            row_str = f"|  Roll {roll:02d}  | " + " | ".join([f"{item:^4}" for item in row_items]) + f" |  {score}/{total_q}  | {mastery:^13} |"
            print(row_str)

        print(sep)
        print("(* indicates answer matched the Answer Key)")

        # Summary statistics
        class_avg = round(total_scores / students_scored, 1) if students_scored > 0 else 0
        print(f"\nClass Average Score: {class_avg}% across {students_scored} students")

    conn.close()
    print("\n" + "=" * 75 + "\n")

if __name__ == "__main__":
    inspect()
