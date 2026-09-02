# Product Requirements Document — Classroom Marker-Card Assessment System

## 0. Context for whoever/whatever implements this

This document assumes **zero prior knowledge** of the project. Read this entire section before writing any code.

**Who this is for:** Pi Jam Foundation, an education nonprofit, needs a way for teachers to run quick multiple-choice assessments in a physical classroom (no student devices, no internet dependency during the session) and get results captured digitally, mapped to a central student database.

**The core mechanic, in one paragraph:** Each student holds a reusable printed paper card with a unique visual marker pattern on it, with the letters A/B/C/D printed on its four edges (one letter per edge, each edge also colour-coded). When the teacher asks a multiple-choice question, each student rotates their card so their chosen answer's edge faces up (toward the ceiling). The teacher then sweeps a phone camera across the room for a few seconds. The app's computer-vision pipeline detects every card in the video/photo frames, decodes (a) which unique marker design it is and (b) which edge is facing "up" (i.e., which letter/answer), and logs a response for every student in the room in one pass — no per-student clicking, no student devices needed.

**Why this design, not OMR bubble sheets (the originally contracted approach):** The original signed HLD/contract specified OMR (Optical Mark Recognition) bubble sheets with printed QR IDs, photographed in batches of 10–12 sheets. That approach was replaced by this reusable marker-card approach because it is faster per-session (no printing per session, no batches, one camera sweep covers a whole classroom), cheaper at scale, and doesn't consume paper per assessment. **If you are an agent picking up this project fresh: the OMR approach is DEPRECATED. Build the marker-card system described here.**

**Prior art / inspiration:** This system is conceptually similar to a commercial classroom-response product called Plickers, which uses black-and-white rotatable marker cards read by a phone camera. **Important legal note carried over from the design discussion: Plickers Inc. holds an active US patent (US11308293B1) with fairly broad claims covering "camera + rotatable fiducial marker card + orientation detection + roster-matching."** No equivalent Indian patent was found during a preliminary web search (not a formal legal clearance). Since this system will be deployed only within India, the US patent likely does not create direct legal exposure, but **this has not been formally confirmed by a patent attorney or IIT Bombay's IP cell** — flag this to the project owner before wide public release or any deployment/marketing outside India. This system's own approach (colour-coded edges as a secondary cue, in addition to a black/white-style marker pattern) is a design choice made independently for computer-vision robustness reasons — it does not constitute legal design-around advice.

---

## 1. Problem Statement

Teachers in Pi Jam-partnered schools need to run quick in-class multiple-choice assessments (comprehension checks, quizzes, polls) and have the results captured centrally — without:
- Requiring every student to own a device
- Requiring reliable classroom internet during the session
- Requiring the teacher to manually record 30+ individual responses
- Printing new material for every single session (cost and logistics at scale)

## 2. Goals

- A teacher can run a full-class assessment and capture every student's answer in under ~30 seconds of active scanning.
- The system must scale to Pi Jam's full partner network (many schools, many classrooms, potentially running assessments in parallel within the same school) without requiring per-student or per-school unique printed materials.
- No student names or photographs are stored in the response data — only a composite anonymized-but-traceable ID.
- The system must degrade gracefully: if a card can't be read clearly, the app must tell the teacher immediately (before the class moves on) so it can be rescanned, rather than silently losing or misattributing a response.

## 3. Non-Goals (explicitly out of scope for this version)

- Open-ended/free-text answer capture (multiple choice A–D only, for now).
- Student-facing app or device — students only ever hold a physical paper card.
- Real-time internet connectivity requirement during scanning — capture should work with on-device processing and can sync results afterward if offline (design the sync layer to tolerate this, even if full offline-first isn't in the very first release).
- Cross-country patent/IP legal clearance — this is a business/legal task for the project owner, not an engineering task.

## 4. Users / Roles

| Role | Description |
|---|---|
| **Teacher** | Runs the in-classroom session: selects school/class/section in-app, asks questions, scans the room, sees/rescans flagged failures, marks absentees. |
| **Pi Jam Monitoring Team (Admin)** | Enters/maintains the class roster (roll number → student) once per year per class. Not involved in day-to-day sessions. |
| **Pi Jam Program Analyst** | Consumes aggregated response data across schools/classes/programme for reporting — read-only access to a dashboard, not part of the live capture flow. |

## 5. Core Concepts & Terminology

- **Marker Design**: One of a fixed set of **45 unique visual patterns** (see `MARKER_GENERATION.md` for how these are generated). Each design is printed with A/B/C/D labels around its four edges and a distinct colour per edge (see §7).
- **Card**: One physical printed instance of a marker design.
- **Set**: One complete physical collection of all 45 marker designs (cards numbered/labelled 1–45), i.e., one full stack a teacher can hand out to one classroom.
- **Session**: One live in-classroom scanning activity for a specific School + Class/Section, on a specific date, potentially covering multiple questions.
- **Response**: One (student, question, selected answer) record produced by a scan.

## 6. Functional Requirements

### 6.1 Marker Design Pool
- Exactly **45 unique marker designs** must exist, fixed for the life of the programme (or versioned if ever regenerated — see `MARKER_GENERATION.md` for the versioning implication).
- 45 = average class size of ~30 students + a buffer of 15, to comfortably cover larger-than-average classes without redesigning cards.
- These 45 designs are **not unique per student or per school** — the same 45 visual patterns are reused everywhere. A school prints **`m` physical sets** of these same 45 designs, where `m` = the number of classrooms that may run assessments *in parallel* at the same time in that school (e.g., if 6 teachers might all be running a session simultaneously, the school needs 6 physical sets — but still only 45 unique designs).
- **Design uniqueness scope:** Identity resolution never depends on which physical *set* a card came from — see §6.3. There is intentionally no "set ID" printed on the card or tracked in the data model. (This was evaluated and explicitly rejected — see §12, Decision Log, D-05.)

### 6.2 Card Physical Design
Each card has:
- A machine-readable marker pattern (unique per design, 1 of 45) printed in the center — see `MARKER_GENERATION.md`.
- The letters **A, B, C, D** printed near each of the four edges, one letter per edge.
- Each edge/letter also has a **distinct background colour** as a secondary, redundant visual/CV cue (recommended palette: **Yellow, Green, Blue, Magenta** — chosen for print consistency on cheap presses and maximum hue separation under variable lighting; see §7 for rationale).
- The same colour-to-letter mapping is printed on the **back of the card** too, purely for the student's own reference (so they know which way to rotate it) — this is not read by the CV system.
- A small printed **card number (1–45)**, human-readable, so teachers/admins can physically sort and hand out cards by number without needing the app.

### 6.3 Identity Resolution Model
- The durable identifier for any response is the composite: **`School Code` + `Class/Section` + `Roll Number`** (e.g. `ABC123-7A-14`). This triple is globally unique across the entire institution/programme (School Code disambiguates roll-number collisions across schools; Class/Section disambiguates across classes within a school).
- **Card → student mapping is entirely session-contextual, not stored permanently.** Before scanning, the teacher selects School + Class/Section in the app. From that point, "card #14 detected" is interpreted as "roll number 14 of [selected class]" — because the roster (which was entered once at the start of the year, see §6.4) says roll #14 in that class exists and is expected to hold card #14.
- Because of this, the *same physical card #14* can be used in Class 6B in period 1 and handed to a completely different classroom in period 2 — the app doesn't need to know or care which physical set a card came from. This was a deliberate simplification (see Decision Log D-05) — do not add a "set ID" concept to the schema.
- The only assumption this model depends on: **exactly one classroom's roster is "active" for a given physical set of cards at any moment** (i.e., you don't have two teachers simultaneously scanning with cards drawn from the same physical set into two different "active class" contexts). This is naturally satisfied since a physical set of cards is a physical object that can only be in one room at a time.

### 6.4 Roster Management (Admin flow)
- Pi Jam's monitoring team enters, once per year per class: the list of roll numbers and the student's name (name is stored for admin/roster-management purposes only — **never included in the exported/analytics response records**, see §6.6).
- Roster edits (add/remove/transfer student) should be supported mid-year for real-world churn (transfers, new admissions) but are expected to be infrequent, admin-only operations.

### 6.5 Session Flow (Teacher-facing)
1. Teacher opens app, selects School (if managing multiple) → Class/Section.
2. App loads that class's roster (roll numbers 1–N) and the current absentee list is confirmed/updated by the teacher (mark absentees before the first question of the session).
3. Teacher (verbally/on a projector, outside the scope of this app) asks a multiple-choice question.
4. Students rotate their physical card to their chosen answer's edge/colour.
5. Teacher opens the in-app scanner and sweeps the camera across the room for a few seconds.
6. The app detects cards in the frame stream, decodes (marker ID, orientation) pairs, resolves each against the active roster.
7. **Reliability check:** any roll number in the active roster whose card was NOT successfully read (occluded, blurry, bad angle, card not detected at all) is shown to the teacher immediately, by roll number, before the question is considered "closed."
8. Teacher can point the camera again at just the flagged students to pick up the missing reads, without re-scanning the whole room.
9. Once all expected students (roster minus marked-absent) have a logged response (or the teacher explicitly chooses to move on, e.g. accepting a partial result), the question is marked complete and the session can move to the next question.
10. At session end, all `Response` rows for that session are available for sync/export.

### 6.6 Data Captured & Privacy
- No student name or photograph is ever stored in a `Response` record.
- The permanent identity trail is School Code + Class/Section + Roll Number only.
- Roster data (which does include student name, for admin purposes) is stored separately from response/assessment data and should be access-controlled distinctly (roster = admin-only; responses = broader analyst access is fine since they carry no name/photo).

### 6.7 Reliability / Error Handling
- Unreadable card (occluded, wrong angle, out of focus, or simply not detected in any frame during the scan) → flagged to teacher with the roll number missing, immediately, not after the fact.
- Card detected but orientation ambiguous (e.g., held at an angle where two edges are equally "up") → treat as unreadable, flag for rescan rather than guessing.
- A marker ID detected that does **not** correspond to any roll number in the currently active roster (e.g., roster only has 28 students but card #40 was somehow scanned) → flag as an anomaly, do not silently drop or silently create a phantom response.
- Duplicate detection: if the same roll number is read twice with two different answers within the same question-scan window (e.g., a card moved and got re-read), the app should surface this ambiguity rather than silently picking one.

## 7. Marker Card Visual Design Details

- Colour palette for the 4 answer edges: **Yellow (~60° hue) / Green (~120°, biased cool+saturated) / Blue (~240°) / Magenta (~300°)**. Rationale: these are close to evenly spaced (~90°+ apart) around the hue wheel for maximum CV distinguishability, are print-consistent on cheap CMYK presses (avoiding the ink-mixing instability of "pure red"), and hold up better than a naive Red/Green/Blue/Yellow set under mixed/warm classroom lighting (tungsten bulbs shift red toward orange, risking confusion with yellow).
- Colour is a **secondary/redundant cue** to the marker pattern + printed letter — the system should NOT rely on colour alone for orientation detection if the marker pattern itself is legible; colour should improve robustness in poor-pattern-visibility conditions (dim light, printer variance, minor camera blur), and give a fast/cheap first-pass orientation hint that the CV pipeline can cross-check against the pattern-based decode.
- See `MARKER_GENERATION.md` for the actual visual pattern generation algorithm (this is the harder CV problem: designing 45 patterns that are each reliably distinguishable from the other 44, and where each of the 4 physical rotations of a pattern is unambiguous).

## 8. Non-Functional Requirements

- **Scan latency:** a full classroom (~30–45 students) should be scannable in well under a minute of active camera sweeping.
- **Lighting robustness:** must be tested and tuned under dim/mixed-source classroom lighting (fluorescent tubes, single bulbs, window daylight mixed with tube light) — not just under studio/screen conditions.
- **Print robustness:** must be tested against actual low-cost print runs (matte paper, standard office/school printers), not just digital mockups, since ink rendering differs from screen colour.
- **Offline tolerance:** capture should not hard-fail if there's no internet at the moment of scanning; sync of completed session data can happen when connectivity is available (full offline-first architecture is a stretch goal, not a hard v1 requirement, but do not architect anything that assumes constant connectivity during scanning).
- **Scale:** design the backend data model to comfortably support many schools × many classes × many sessions × multiple questions per session, without needing schema changes as the programme grows (see `DESIGN.md` for volume estimates and indexing guidance).

## 9. Success Metrics (for the client / programme, not strictly engineering KPIs, but useful context)
- % of card scans successfully read on first sweep (target: high; anything requiring frequent manual rescans indicates a marker-design or CV-pipeline problem worth revisiting).
- Time per question from "teacher opens scanner" to "all responses logged" (should trend toward well under a minute per question as the CV pipeline matures).
- Zero incidents of student names/photos appearing in exported analytics data (a hard privacy requirement, not just a nice-to-have).

## 10. Open Questions (flag these back to the project owner — do not silently assume answers)

1. Should the system support offline-first capture with deferred sync as a v1 requirement, or is "sync at session end, assuming connectivity by then" acceptable for launch?
2. What's the target maximum `m` (parallel classroom sets) per school — does the printing/logistics plan need this number to size initial print runs?
3. Formal IP clearance (see §0) — has this been done or is it still pending?
4. Is roster data entry going to have any tooling (CSV upload, simple admin UI) or is it a fully manual, non-Pi-Jam-app-mediated process for now?

## 11. Glossary
- **Marker Design**: One of the 45 fixed unique visual patterns.
- **Card**: A physical printed instance of a Marker Design.
- **Set**: A full stack of all 45 Cards (one of each design), used to serve one classroom at a time.
- **Roster**: The roll-number-to-student mapping for one class, entered once per year.
- **Session**: One live scanning activity, scoped to a specific class on a specific date.
- **Response**: One logged (student, question, answer) record.

## 12. Decision Log (carried over from design discussion — keep updated)

| ID | Decision | Rationale |
|---|---|---|
| D-01 *(superseded)* | Original HLD: OMR bubble sheets + QR ID, batches of 10-12 | Signed contract baseline; since replaced |
| D-02 | Pivot to Plickers-style reusable rotating marker cards | Faster per-session capture, no per-session printing, scales better |
| D-03 *(superseded)* | Considered: ~500 unique cards per school, permanently assigned per student | Client's originally stated preference; later reconsidered in favor of D-04 |
| D-04 | Final: 45 unique marker designs, reused across all classrooms/schools, `m` physical sets per school for parallel classrooms | Matches how Plickers itself works at scale; drastically lower printing cost/complexity than per-student unique IDs; identity resolved contextually via teacher's classroom selection, not via the card itself |
| D-05 | No "set ID" needed/tracked — identical card numbers across different physical sets are NOT distinguished in the data model | Classroom selection in-app is already the sole disambiguator; adding set IDs was evaluated and found unnecessary since two classrooms scanning "card #14" simultaneously already resolve correctly to two different students via the active-roster context |
| D-06 | Colour-coded edges (Yellow/Green/Blue/Magenta) added as secondary cue alongside the printed marker pattern | Easier, more lighting-tolerant CV classification than pattern-orientation-only decoding |
| D-07 | No student names/photos stored in response data; identity is School Code + Class/Section + Roll Number only | Privacy requirement |
