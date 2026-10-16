# Pi Jam FAST Classroom Assessment Platform — Production & Deployment Manual
### Low-Cost Formative Assessment System for Real Indian Classrooms

---

## 1. Executive Summary & Client Specification Alignment

This document details the production engineering and classroom operational manual for the **Pi Jam FAST** assessment platform. All 9 client enhancements and real-world operational nuances have been engineered and verified:

| # | Client Requirement | Architectural Implementation |
|---|---|---|
| **1** | **Answer key in the very end** | Stepper Step 5 presents the complete Answer Key selector. Teachers can also pre-set keys optionally during Step 2 if known upfront. |
| **2** | **Dynamic number of questions & key (Default: 5)** | Numeric stepper (`[-] [ 5 ] [+]`) supporting 1 to 20 questions. Dynamic grid rendering for Q1..QN across scanner and review views. |
| **3** | **PDF upload on Page 2 & stored in DB** | Dedicated Step 2 supports Case 1 (Blackboard Mode) and Case 2 (PDF Upload Mode). Uploads are stored in `backend/uploads/pdfs/` with database metadata linking. |
| **4** | **Reactive answer key editing** | Real-time recalculation engine recalculates scores, percentages, and mastery tiers in $<100\text{ ms}$ upon any key click. |
| **5** | **Merged Excel + PDF export** | 1-Click download actions provide: (1) Formatted Excel Workbook (`.xlsx`) via `openpyxl`, and (2) Merged Dossier PDF via `reportlab` + `pypdf` (Scorecard + Source Question Paper). |
| **6** | **Online/Offline working & APK creation** | Client-side `IndexedDB`/`localStorage` queue with automatic background synchronization when online. `capacitor.config.json` configured for Android APK compilation. |
| **7** | **Quiz metadata at the beginning** | Step 1 captures Teacher ID, School, Class & Section, Quiz Name, Subject, Date, and Question Count. |
| **8** | **Teacher Historical Report (Rolling 3 Months)** | Dedicated Teacher Dashboard with Day-wise, Week-wise, and Month-wise filters, trend metrics, and past quiz archives. |
| **9** | **Project Manager Multi-Teacher Dashboard** | Supervisor Dashboard displaying network-wide metrics, multi-teacher comparison tables, and recent activity feeds. |

---

## 2. End-to-End System Workflow

```
[0. Login] ─────────▶ Enter Teacher ID (e.g. PJ-T101) or Manager ID (PJ-M001)
                           │
                           ▼
[1. Setup] ─────────▶ Select Class • Quiz Name • Date • Question Count [ - ] [ 5 ] [ + ]
                           │
                           ▼
[2. Mode & Key] ────▶ CASE 1: Blackboard Mode (No file)
                      CASE 2: Upload Question Paper PDF
                      + Optional Pre-set Answer Key (Q1..QN)
                           │
                           ▼
[3. Attendance] ────▶ Tap absent students (e.g. Roll 7, 14) ──▶ [28 Present]
                           │
                           ▼
[4. Live Sweep] ────▶ Point phone camera at cards (8-15s per question)
                      • Live AR bounding boxes (A=Red, B=Yellow, C=Blue, D=Green)
                      • Missing roll numbers drawer
                      • Tap "Next Q →" to cycle through Q1..QN
                           │
                           ▼
[5. Final Review] ──▶ Dynamic Answer Key Editor (Q1..QN)
                      • Click any letter to change answer key
                      • Instant live reactive recalculation of mastery tiers & charts!
                      • 1-Click "Download Merged PDF Dossier"
                      • 1-Click "Download Excel Sheet (.xlsx)"
```

---

## 3. Database Architecture & Relationships

Database file: `backend/assessment.db` (SQLite).

### Key Relational Entities:
1. **`schools`**: `school_id`, `school_code`, `name`, `udise_code`, `city`.
2. **`teachers`**: `teacher_id` (PK, e.g., `PJ-T101`), `school_id`, `name`, `email`, `subject`, `role` (`teacher` vs `manager`), `pin`.
3. **`classes`**: `class_id`, `school_id`, `grade`, `section`, `academic_year`, `max_students`.
4. **`students`**: `student_id`, `class_id`, `roll_number`, `name`, `status`.
5. **`sessions`**: `session_id`, `class_id`, `teacher_id`, `quiz_name`, `subject`, `session_date`, `question_count`, `question_mode`, `pdf_filename`, `pdf_path`, `status`, `created_at`.
6. **`session_absentees`**: `session_id`, `roll_number`.
7. **`questions`**: `question_id`, `session_id`, `sequence_number`, `prompt_text`, `correct_answer`.
8. **`responses`**: `response_id`, `question_id`, `school_code`, `class_id`, `roll_number`, `marker_id_detected`, `selected_option`, `confidence`, `captured_at`.

---

## 4. Export & Report Generation Engine

### 4.1 Formatted Excel Workbook (`.xlsx`)
Implemented in `backend/services/export_service.py` using `openpyxl`:
- **Sheet 1 — Executive Summary**: Branded header banner, assessment metadata, participation rate, and mastery distribution summary.
- **Sheet 2 — Student Scorecards**: Roll Number, Student Name, Question Columns (Q1..QN) with soft-green highlighting for correct answers and soft-red for incorrect answers, total score, percentage %, and mastery category.
- **Sheet 3 — Item & Distractor Analysis**: Question No, Correct Key, Class Accuracy %, Total Responses, and option-by-option distractor frequency (A, B, C, D) for identifying classroom misconceptions.

### 4.2 Merged Dossier PDF
Implemented in `backend/services/export_service.py` using `reportlab` and `pypdf`:
- **Page 1**: High-resolution, professional executive scorecard table, KPI cards, and question accuracy breakdown.
- **Page 2+**: If the teacher uploaded a source Question Paper PDF in Step 2, it is seamlessly appended to the scorecard into a single unified dossier for NGO compliance records.

---

## 5. Offline Resiliency & Android APK Packaging

### 5.1 Offline Classroom Operation
- In low-connectivity classrooms, the application functions offline without interruption:
  - Class rosters and previous settings are cached locally.
  - Student responses captured during sweeps are committed to browser storage.
  - When the teacher's phone reconnects to mobile data or school Wi-Fi, the background sync queue automatically posts pending sessions to `/api/sessions/{session_id}/sync`.

### 5.2 Building the Android APK (`.apk`)
The application is pre-configured with **Capacitor**:

```bash
# 1. Install Capacitor CLI and Android platform
npm install @capacitor/core @capacitor/cli @capacitor/android

# 2. Add Android native project
npx cap add android

# 3. Copy web assets
npx cap copy

# 4. Open in Android Studio or build APK directly
cd android
./gradlew assembleRelease
```
The compiled APK will be located at:
`android/app/build/outputs/apk/release/app-release-unsigned.apk`

---

## 6. Classroom Pilot Checklist (Pi Jam NGO Deployment)

1. **Card Condition**: Ensure physical laminated cards (Roll 1 to 45) are not creased across the central 5×5 ArUco grid.
2. **Camera Sweep Technique**:
   - Hold phone at shoulder height with a gentle 15-degree downward tilt.
   - Perform a steady, continuous horizontal pan across classroom rows (taking 8 to 15 seconds).
   - Watch the AR canvas: each detected card will turn green/blue/yellow/red with Roll # displayed.
   - If students sit in distant back rows, step forward 2 paces during the sweep.
3. **Attendance First**: Always tap absent students on Step 3 before starting the camera sweep. This ensures the denominator for class accuracy is exact.
4. **Answer Key Flexibility**: Never worry if a question has a contested answer during class. Complete the sweep, proceed to Step 5, and adjust the answer key pill with a single tap—the class scorecards and reports update instantly.
