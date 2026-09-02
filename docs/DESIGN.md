# Technical Design Document — Classroom Marker-Card Assessment System

> Read `PRD.md` first for full product context. This document assumes that context and focuses on system architecture, data model, CV pipeline, and API surface. Read `MARKER_GENERATION.md` for the marker-pattern generation algorithm.

## 1. System Overview

Three logical components:

1. **Mobile App (Teacher-facing)** — runs the live scanning session: camera capture, on-device (or near-device) marker detection/decoding, roster resolution, reliability-flagging UI, absentee marking.
2. **Backend API + Database** — stores roster data, session data, response data; serves the mobile app; serves an analyst-facing read layer.
3. **Admin/Roster Management** — a simpler interface (could be part of the same backend, minimal UI) for Pi Jam's monitoring team to enter/update rosters once per year per class.

```
┌─────────────────┐        ┌──────────────────┐        ┌────────────────────┐
│  Teacher Mobile  │  API   │   Backend API      │  API   │  Admin / Roster UI  │
│  App (scanning,  │◄──────►│  + Database        │◄──────►│  (Pi Jam monitoring │
│  CV pipeline)    │        │                    │        │  team)              │
└─────────────────┘        └──────────────────┘        └────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │  Analytics / Reporting │
                          │  (read-only, no PII)   │
                          └──────────────────────┘
```

## 2. Data Model

### 2.1 Core Entities

```
School
├── school_id (PK)
├── school_code (unique, human-readable, e.g. "ABC123")
├── name
└── udise_code (if applicable, Indian school ID standard)

ClassSection
├── class_id (PK)
├── school_id (FK → School)
├── grade (e.g. "7")
├── section (e.g. "A")
└── academic_year

Student
├── student_id (PK)
├── class_id (FK → ClassSection)
├── roll_number (int, unique within class_id + academic_year)
├── name                      -- ADMIN-ONLY FIELD, see §2.4 access control
└── status (active / transferred_out / inactive)

MarkerDesign
├── marker_id (PK, 1–45, fixed for the programme's lifetime — see MARKER_GENERATION.md)
├── pattern_definition (the actual bit-pattern / encodable representation)
└── design_version (see §5.4 — only relevant if the pattern set is ever regenerated)

Session
├── session_id (PK)
├── class_id (FK → ClassSection)
├── teacher_id (FK → Teacher, if you have teacher accounts — optional for v1)
├── session_date
└── status (in_progress / completed)

SessionAbsentee
├── session_id (FK → Session)
└── roll_number (int)     -- marked absent for this session, excluded from expected-response checks

Question
├── question_id (PK)
├── session_id (FK → Session)
├── sequence_number (order within the session)
└── (optional metadata: question text/label, correct_answer if auto-grading is wanted later)

Response
├── response_id (PK)
├── question_id (FK → Question)
├── school_code (denormalized, for fast filtering — see §2.3)
├── class_id (FK → ClassSection)
├── roll_number (int)
├── marker_id_detected (FK → MarkerDesign)   -- which physical card was read
├── selected_option (A / B / C / D)
├── confidence / read_quality (optional, useful for QA/debugging the CV pipeline)
└── captured_at (timestamp)
```

### 2.2 Explicitly NOT in the schema
- **No `CardSet` / `set_id` concept.** Per PRD §6.3 and Decision D-05, the same 45 marker designs are reused across every physical set and every classroom; identity is resolved purely by (active `class_id` at scan time) + (`marker_id` detected → roll number, per that class's roster). Do not add a table or column that tries to track "which physical set is this card from" — it isn't needed and adds complexity with no resolved use case.
- **No permanent `marker_id ↔ student_id` mapping table.** The mapping is *implicit and per-session*: whichever `class_id` the teacher has selected as "active" is what a detected `marker_id` resolves against, via a simple ordinal or explicit roster-assignment rule (see §2.3 below — decide and document this mapping rule clearly, since it's the crux of the whole resolution model).
- **No student photos.** Never captured, never stored.

### 2.3 The marker_id → roll_number Resolution Rule (needs to be pinned down precisely)

The PRD establishes that "card #14 detected while Class 7A is active" resolves to "roll number 14 of Class 7A." This implies a **fixed, simple mapping rule: `roll_number == marker_id`**, scoped by whichever `class_id` is currently active in the session.

This means:
- Roll numbers in every class roster should run 1..N (N ≤ 45), matching directly to marker designs 1..45.
- `Response.roll_number` can, in fact, be derived directly from `Response.marker_id_detected` at write-time (no separate lookup table needed) — the resolution is: `roll_number = marker_id_detected`, then join against `Student` where `class_id = <session's active class_id> AND roll_number = <that value>`.
- **Edge case to design for explicitly:** what happens if `marker_id_detected` (e.g., 42) has no corresponding roll number in that class's roster (e.g., the class only has 28 students)? Per PRD §6.7, this must be flagged as an anomaly, not silently dropped or silently written as a phantom response.

*(If, on review, roll numbers are NOT guaranteed to be a clean 1..N sequence per class — e.g., a class has roll numbers 101–128 for some administrative reason — then an explicit `RosterCardMapping(class_id, roll_number, marker_id)` table entered once per class alongside the roster would be needed instead of the direct `roll_number == marker_id` shortcut. Confirm this assumption with the project owner before hard-coding the direct-equality shortcut — flagged as an open question, not to be silently assumed.)*

### 2.4 Access Control
- `Student.name` and any other PII: **admin/roster-management access only.**
- `Response`, `Session`, `Question` tables: contain no PII (school code / class / roll number / marker ID / answer only) — safe for broader analyst read access.
- Keep these on separate access paths/permissions even if they live in the same physical database, so a reporting/analytics role can never accidentally join back to `Student.name`.

### 2.5 Scale Sanity Check
Using the earlier-discussed programme scale (rough order-of-magnitude, confirm actual numbers with the project owner):
- `Student` rows: proportional to total enrolled students across all partner schools (order of 10⁵–10⁶ depending on final programme size) — trivial for any relational database.
- `Response` rows are the real volume driver: `students × questions per session × sessions per week × weeks per term`. E.g., 150,000 students × 5 questions × 2 sessions/week × 30 weeks ≈ 45M rows/year. Fine with proper indexing on `(session_id)`, `(class_id, session_date)`, and consider partitioning `Response` by academic term/date if volume grows further.
- Index `Response` on `(school_code, class_id, roll_number)` to support the "one student across all their history" query pattern described in the PRD (student/classroom/school/programme-level views).

## 3. Computer Vision Pipeline

### 3.1 Pipeline Stages
1. **Frame acquisition** — continuous camera stream while the teacher sweeps the room (model this as a video/frame-stream problem, not a single-photo problem — mirrors how Plickers itself works: teacher holds the phone steady over one area, waits for cards in view to be logged, then moves to the next area).
2. **Marker localization** — detect candidate card regions in each frame (find the rectangular/square marker pattern boundary; use standard fiducial-marker detection techniques — contour detection, corner detection, adaptive thresholding for lighting robustness).
3. **Pattern decode** — for each localized marker, decode which of the 45 designs it is (see `MARKER_GENERATION.md` for the design/decode logic) AND determine the 0°/90°/180°/270° orientation.
4. **Colour cross-check** — independently classify which of the 4 edge colours (Yellow/Green/Blue/Magenta) is at the "top" edge in HSV space; cross-check against the pattern-based orientation decode. If pattern-decode and colour-decode disagree, treat as low-confidence / flag for rescan rather than picking one arbitrarily.
5. **De-duplication across frames** — since this is a continuous sweep, the same card will appear in many consecutive frames; track detections across frames (by marker_id + rough screen position) and only commit one logged response per marker_id per question, using the majority/most-confident read across the frames it appeared in.
6. **Resolution against active roster** — apply the rule in §2.3, write `Response` rows, and compute the "missing" set (roster minus marked-absent minus successfully-read) to drive the reliability-flagging UI.

### 3.2 Lighting & Colour Robustness
- Do hue classification in HSV, not raw RGB (hue is far more lighting-invariant).
- Consider a lightweight per-session white-balance calibration step (sample a known reference patch — could be a fixed white/gray region on the card itself — before starting a scan) to correct for ambient colour temperature drift.
- Test explicitly under dim/mixed classroom lighting (tube light + daylight + old bulbs) — not just clean studio/screen conditions — before finalizing detection thresholds.

### 3.3 On-device vs Server-side Processing
- Given the "must not hard-depend on connectivity during scanning" requirement (PRD §8), lean toward **on-device detection/decoding** (e.g., using a mobile CV framework/library capable of real-time marker detection), with only the resolved (marker_id, orientation) results needing to sync to the backend afterward — not raw video.
- If on-device processing proves too heavy for low-end devices commonly used by teachers, a fallback of buffering frames and processing server-side when connectivity resumes is acceptable, but design the UI/UX so the teacher still gets *some* immediate on-device signal (at minimum, "a marker was detected here") even if full decode is deferred.

## 4. API Surface (indicative — adjust to actual backend framework choice)

```
POST   /schools                          -- admin: create school
POST   /schools/{school_id}/classes      -- admin: create class/section
POST   /classes/{class_id}/roster        -- admin: bulk upload/update roster (roll_number, name)
GET    /classes/{class_id}/roster        -- teacher app: fetch active roster for scanning

POST   /sessions                         -- teacher: start a session (class_id, date)
POST   /sessions/{session_id}/absentees  -- teacher: mark absentees before first question
POST   /sessions/{session_id}/questions  -- teacher: start a new question within the session

POST   /questions/{question_id}/responses         -- submit a batch of resolved (marker_id, orientation) reads from a scan
GET    /questions/{question_id}/responses/missing -- get roll numbers not yet successfully read, for rescan UI

GET    /sessions/{session_id}            -- session summary / completion status
GET    /analytics/...                    -- read-only aggregate endpoints (school/class/student/programme level), no PII fields exposed
```

## 5. Implementation Notes & Open Technical Decisions

### 5.1 Tech stack
Not prescribed here — choose based on team familiarity and the mobile CV library ecosystem available (native Android/iOS CV frameworks, or a cross-platform approach with a suitable marker-detection library). Whatever is chosen must support real-time or near-real-time frame processing on mid/low-end Android devices, since that's the realistic hardware profile for many partner schools.

### 5.2 Testing priorities before rollout
- Print actual sample cards on the target low-cost printer/paper stock (not a screen mockup) and test detection against those physical prints.
- Test under the worst-case lighting scenario described in the PRD, not ideal conditions.
- Test the "card physically swapped between two students" scenario (PRD §6.3 known limitation) to confirm the system fails predictably (wrong response logged, not a crash) rather than corrupting other data.
- Load-test the `Response` write path at the volume estimated in §2.5.

### 5.3 Anomaly/edge-case handling checklist (from PRD §6.7 — implement all of these, don't skip any)
- [ ] Card not detected at all during the scan window → flagged as missing, by roll number.
- [ ] Card detected, orientation ambiguous → treated as unreadable, not guessed.
- [ ] Marker ID detected with no matching roll number in the active roster → flagged as anomaly, not silently written or dropped.
- [ ] Same roll number read twice with conflicting answers in one question window → surfaced to teacher, not silently resolved by picking one.

### 5.4 Marker set versioning
The 45 marker designs are meant to be fixed for the programme's lifetime (PRD §6.1). If they are ever regenerated (e.g., design flaw found later, or the design count changes), every printed card in circulation becomes invalid simultaneously — treat this as a rare, coordinated, whole-programme event, and keep a `design_version` field on `MarkerDesign` from day one so this is possible to handle cleanly if it ever happens, rather than needing a schema migration under pressure.

## 6. Open Questions Carried Over From PRD (do not silently assume)
See `PRD.md` §10 — in particular, confirm the roll-number-to-marker-ID mapping assumption in §2.3 of this document before implementing the resolution logic, since an incorrect assumption there breaks the entire identity-resolution model.
