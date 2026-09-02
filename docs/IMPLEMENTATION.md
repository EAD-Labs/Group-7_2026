# Comprehensive Implementation Plan — Web-Based Classroom Marker Assessment System

> **Document Status:** Draft for Review  
> **Audience:** Engineers, Project Leads, QA, and Educational Field Coordinators  
> **Context References:** [`PRD.md`](file:///c:/Users/Hitansh/ET617/docs/PRD.md), [`DESIGN.md`](file:///c:/Users/Hitansh/ET617/docs/DESIGN.md), [`MARKER_GENERATION.md`](file:///c:/Users/Hitansh/ET617/docs/MARKER_GENERATION.md)

---

## 1. Executive Summary & Non-Technical Overview

### 1.1 The Vision
The **Pi Jam Foundation Classroom Assessment System** allows teachers in partner schools to conduct rapid, paperless, low-cost multiple-choice assessments (comprehension checks, exit tickets, polls) in physical classrooms where:
- Students have **no digital devices** (no phones, tablets, or clickers).
- Classroom **internet connectivity is unreliable, slow, or absent**.
- Teachers cannot afford to spend minutes recording manual responses or grading papers.
- Printing per-session OMR sheets is cost-prohibitive and environmentally wasteful.

### 1.2 The User Journey (Teacher Experience)
1. **Setup (Before Class):**
   - The teacher opens the Web App on any device with a camera (smartphone, tablet, or laptop).
   - The teacher selects their **School** and **Class/Section** (e.g., *Grade 7, Section A*).
   - The app loads that class's roster (Roll Numbers 1 to $N$).
   - The teacher does a 10-second attendance check: taps any students who are absent today so the system does not wait for their responses.
2. **Assessment Question:**
   - The teacher projects or verbally asks a multiple-choice question with options **A, B, C, and D**.
   - Each student holds up their designated reusable laminated card (numbered 1 to 45), rotated so that their chosen answer's letter and color face **UP** toward the ceiling.
3. **Live Camera Sweep (5 to 15 seconds):**
   - The teacher taps **"Start Scan"**. The web app opens the camera viewfinder with a live Augmented Reality (AR) HUD.
   - The teacher smoothly pans the camera across the classroom.
   - As each card enters the camera's field of view, a glowing bounding box appears around it on screen with the detected Roll Number and Answer badge (e.g., `Roll 14: [B]`).
   - A live progress counter updates continuously: **`Scanned: 28 / 30 | Missing: #7, #19`**.
4. **Instant Completion & Rescan:**
   - If 2 students are missing (e.g., blocked by someone's arm or held too low), the teacher immediately points the camera specifically at those two desks.
   - Once all present students are captured (or the teacher chooses to lock the poll), the results are instantly tallied into a visual summary (e.g., *A: 12, B: 14, C: 2, D: 0*).
5. **Zero-Friction Storage & Sync:**
   - The responses are saved immediately to local storage on the device (zero internet needed).
   - When the teacher connects to Wi-Fi later in the day, the session automatically synchronizes to the central Pi Jam database.

---

## 2. Exhaustive Edge Cases & Architectural Solutions

Real classroom environments present significant optical, behavioral, physical, and network challenges. The system is designed to handle every one of them deterministically:

### 2.1 Physical & Human Edge Cases

| # | Edge Case Scenario | Real-World Cause | Technical Detection | Architectural Solution |
|---|---|---|---|---|
| **E-01** | **Finger Occlusion** | Student holds the card with fingers covering part of the black outer border or inner pattern. | Marker contour extraction fails or exceeds bit error threshold. | 1. ArUco parameter `maxErroneousBitsInBorderRate = 0.35` allows partial border occlusion.<br>2. Card layout leaves a white margin between the color band and marker border.<br>3. Multi-frame accumulation ensures that as the student adjusts their grip, the card is captured cleanly in adjacent frames. |
| **E-02** | **Extreme Tilt / Off-Axis Perspective** | Student sits in extreme left/right corner; card is viewed at a $45^\circ$ angle. | Bounding box is a distorted trapezoid rather than a square. | OpenCV's `detectMarkers` performs quadrilateral contour fitting followed by perspective homography transformation (`warpPerspective`) to flatten the marker before sampling grid bits. |
| **E-03** | **Ambiguous Diagonal Hold ($45^\circ$ Hold)** | Student holds the card tilted at $\sim 45^\circ$ such that edges A and B are at nearly equal height. | Top-edge angle falls in deadband zones ($30^\circ$–$60^\circ$, $120^\circ$–$150^\circ$, etc.), or vertical difference between the two highest edge midpoints is $< \epsilon$. | **Never guess.** System flags detection as `AMBIGUOUS` and withholds confirmation until the card stabilizes within $\pm 25^\circ$ of a cardinal angle. Visual cue stays yellow/neutral on screen. |
| **E-04** | **Student Changes Answer Mid-Sweep** | Student initially holds "A", sees their friend hold "C", and rotates the card. | Detected answer for Card ID shifts from A to C across consecutive frames. | **Sliding Time-Window Filter:** A response is updated if a new answer is observed continuously for $\ge 3$ consecutive frames ($\sim 300\text{ms}$). The latest stable answer replaces the prior read, and the UI flashes to signal the update. |
| **E-05** | **Rogue / Out-of-Roster Card** | Card #42 is scanned, but the active class only has 28 students. | `marker_id > class.max_roll` or `marker_id` not found in `active_roster`. | **Anomaly Trap:** Displayed on teacher's HUD in orange alert badge: *"Card #42 is not in this class roster!"* Response is quarantined in an anomaly log and **not** written to the active question tally. |
| **E-06** | **Duplicate Card Conflict** | Two physical sets got mixed up; two students hold "Card #14" with different answers. | Single frame (or near-simultaneous frames) contains two distinct marker locations sharing the identical `marker_id`. | **Conflict Alert:** App displays a red warning: *"Duplicate Card #14 detected at two positions!"* System prompts the teacher to inspect the physical cards. Both reads are held pending until resolved. |
| **E-07** | **Distant / Small Cards (Back Row)** | In a 45-student hall, back-row cards appear only 35–60 pixels wide on camera. | Perimeter of contour is smaller than default detector threshold. | Set `minMarkerPerimeterRate = 0.015` (enables detection down to $\sim 40\text{px}$). Enable full 1080p camera stream (`1920x1080`) rather than standard 720p. |
| **E-08** | **Motion Blur During Camera Sweep** | Teacher sweeps the phone across the room too fast. | Image gradients are smeared; high frequency edges disappear. | Compute Laplacian variance of each frame: $\sigma^2 = \text{Var}(\nabla^2 I)$. If $\sigma^2 < \tau_{\text{blur}}$, drop the frame from processing and display an onscreen toast: *"Sweep more slowly"*. |

### 2.2 Environmental & Lighting Edge Cases

| # | Edge Case Scenario | Real-World Cause | Technical Solution |
|---|---|---|---|
| **E-09** | **Direct Sunlight Glare & Reflection** | Glossy laminated cards reflect bright sunlight from windows directly into the lens, washing out black cells. | 1. Adaptive local thresholding with sliding window sizes (`winSizeMin=3, winSizeMax=23, step=10`).<br>2. Card printing specification mandates **matte lamination** or 300 GSM unlaminated matte cardstock to prevent specular reflection. |
| **E-10** | **Dimly Lit Classrooms** | Single low-wattage ceiling bulb; low dynamic range and high sensor noise. | Dynamic Contrast Enhancement (CLAHE - Contrast Limited Adaptive Histogram Equalization) applied to the luminance channel prior to thresholding. |
| **E-11** | **Cast Shadows Across Card** | A student's head or arm casts a shadow dividing the card into bright and dark halves. | Global thresholding (Otsu) fails completely on shadowed cards. The OpenCV ArUco detector uses **local adaptive thresholding** ($T(x,y) = \text{mean}(N(x,y)) - C$), which evaluates each pixel relative to its immediate neighborhood, neutralizing broad shadows. |

### 2.3 Web Platform & Device Edge Cases

| # | Edge Case Scenario | Technical Cause | Technical Solution |
|---|---|---|---|
| **E-12** | **Camera Permission Denied / Revoked** | User denies `getUserMedia` or browser security blocks camera access. | Clear, friendly error modal with animated instructions on how to toggle site camera permissions in Chrome/Firefox/Safari. |
| **E-13** | **Wrong Camera Selected** | Device defaults to front-facing selfie camera instead of high-res rear camera. | Force camera constraint: `facingMode: { exact: "environment" }`, with graceful fallback to `{ ideal: "environment" }`. |
| **E-14** | **Device Thermal Throttling / Lag** | Continuous 30 FPS computer vision overheats budget Android phones. | Frame-Skipping Governor: Decouple camera rendering from CV processing. Render preview at 30 FPS, but throttle CV analysis to 10–12 FPS in a dedicated Web Worker. |
| **E-15** | **Zero Internet During Class** | Total loss of network connection while teacher is in class. | **PWA Offline-First:** All assets cached via Service Worker. All responses written to browser `IndexedDB`. Zero network requests made during live scanning. |
| **E-16** | **Screen Orientation Change** | Teacher rotates phone between portrait and landscape during sweep. | Use `screen.orientation` API to detect orientation changes and dynamically rotate canvas coordinates to keep AR bounding boxes perfectly aligned. |

---

## 3. Step-by-Step Implementation Plan

The project will be executed in **6 distinct, sequential phases**. Each phase produces a verifiable milestone before the next begins.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Hardened Computer Vision Core & Dual-Verification Engine           │
│ • ArUco 5x5 detector tuning for distant & tilted cards                      │
│ • HSV top-edge color verification module                                    │
│ • Multi-card tracking & temporal de-bouncing                                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Classroom Session State Machine & Anomaly Engine                   │
│ • Class roster mapping (Roll # == Card ID)                                  │
│ • Real-time missing student computation                                     │
│ • Conflict, duplicate, and rogue card detection                             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Backend REST API & Database Schema                                 │
│ • FastAPI service with SQLite/PostgreSQL storage                            │
│ • School, ClassSection, Student, Session, Question, Response tables         │
│ • Offline sync ingestion endpoint (`/sessions/{id}/sync`)                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Modern Web Application Frontend (SPA / PWA)                        │
│ • Responsive teacher interface (Desktop, Tablet, Mobile)                    │
│ • Fullscreen WebRTC Camera Viewfinder with Canvas AR HUD                    │
│ • Live Roster status grid & Missing Roll Number indicator                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: Dual Processing Pipeline (Client Wasm + Backend WebSocket)         │
│ • OpenCV.js in Web Worker for zero-server client-side scanning              │
│ • WebSocket streaming fallback for server-assisted high-res processing      │
│ • IndexedDB local offline storage with automatic background synchronization │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 6: End-to-End Verification, Simulation & Benchmarking                 │
│ • Synthetic multi-card classroom simulation suite (30-card stress test)     │
│ • Lighting & blur benchmark suite                                           │
│ • Teacher walkthrough & validation                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Phase 1: Hardened Computer Vision Core & Dual-Verification Engine
**Objective:** Deliver an optimized Python and JavaScript CV module capable of detecting small, tilted, and occluded cards while cross-verifying pattern orientation against edge colors.

- **Tasks:**
  1. Optimize detector parameters:
     - Enable sub-pixel refinement (`CORNER_REFINE_SUBPIX`).
     - Set `minMarkerPerimeterRate = 0.015` to capture back-row students.
     - Configure multi-scale adaptive thresholding windows.
  2. Implement **Dual-Cue Verification**:
     - Extract the marker's 4 corners: $c_0, c_1, c_2, c_3$.
     - Primary Cue: Calculate edge midpoint closest to image top ($y = 0$).
     - Secondary Cue: Sample a $15 \times 15$ pixel region outside that top edge in HSV color space.
     - Validate that Hue matches expected color (Top = Red/Yellow, etc.).
     - If pattern and color conflict, return `AMBIGUOUS`.
  3. Implement **Temporal Frame Aggregator**:
     - Track detections across a sliding window of 5 frames.
     - Require at least 3 consistent detections before confirming a response.
- **Verification:** Run automated test scripts on rotated, scaled, and tilted card images; achieve 100% precision with zero false orientation classifications.

---

### Phase 2: Classroom Session State Machine & Anomaly Engine
**Objective:** Model the full logic of an active classroom quiz session in pure business logic.

- **Tasks:**
  1. Build the `SessionTracker` class:
     - Inputs: `active_roster` (e.g., Roll 1 to 32), `absentees` (e.g., [4, 18]).
     - Expected count = $\text{len}(\text{roster}) - \text{len}(\text{absentees})$.
  2. Maintain 4 state sets:
     - `CONFIRMED`: `{roll_no: {'answer': 'B', 'confidence': 0.98, 'timestamp': ...}}`
     - `PENDING`: Detected in 1 frame, waiting for 2nd/3rd frame debounce.
     - `MISSING`: Students in roster not yet detected.
     - `ANOMALIES`: Out-of-roster IDs (e.g., Card 40 in a 25-student class) or duplicate positions for the same ID.
  3. Provide real-time summary statistics for UI consumption:
     - `scanned_count`, `missing_roll_numbers`, `poll_distribution` (`{'A': 10, 'B': 14, ...}`).
- **Verification:** Unit tests simulating stream of simulated card events including answer flips, late arrivals, and rogue cards.

---

### Phase 3: Backend REST API & Database Schema
**Objective:** Implement the relational database model and API endpoints matching [`DESIGN.md`](file:///c:/Users/Hitansh/ET617/docs/DESIGN.md).

- **Tasks:**
  1. Initialize SQLite database with SQLAlchemy / Tortoise ORM models:
     - `School`, `ClassSection`, `Student` (PII stored with restricted access).
     - `Session`, `SessionAbsentee`, `Question`, `Response` (Anonymized response records: School Code + Class ID + Roll Number only).
  2. Build FastAPI endpoints:
     - `GET /api/classes/{id}/roster` (Fetch roster for teacher app).
     - `POST /api/sessions` (Create assessment session).
     - `POST /api/sessions/{id}/absentees` (Mark absent students).
     - `POST /api/questions/{id}/responses` (Commit responses for a question).
     - `POST /api/sessions/{id}/sync` (Bulk ingestion endpoint for offline-queued sessions).
     - `GET /api/analytics/...` (Read-only aggregation without student names).
- **Verification:** Automated API integration tests verifying clean CRUD and privacy separation.

---

### Phase 4: Modern Web Application Frontend (SPA / PWA)
**Objective:** Deliver an intuitive, high-aesthetic web interface for teachers that runs smoothly on desktop and mobile browsers.

- **Tasks:**
  1. Create the application shell:
     - Clean modern styling (custom CSS design system with curated palettes, responsive layout, glassmorphism UI cards).
     - Views: Class Selector $\rightarrow$ Attendance Checklist $\rightarrow$ Live Scanner $\rightarrow$ Question Summary Dashboard.
  2. Build the **Camera Viewfinder with Canvas AR HUD**:
     - WebRTC `navigator.mediaDevices.getUserMedia` video stream.
     - Synchronized overlay `<canvas>` directly over the `<video>` element.
     - Draw color-coded bounding polylines around detected cards.
     - Render floating badges: `Roll 14: [B]` (using edge colors: Red, Yellow, Blue, Green).
  3. Build the **Teacher Control Panel**:
     - Progress ring showing `% Scanned`.
     - Live pill tags showing missing roll numbers (e.g., `Missing: #7, #19`).
     - "Done / Lock Poll" button that vibrates device on completion.
- **Verification:** Interactive testing on Chrome desktop and mobile browser simulator.

---

### Phase 5: Client-Server Integration & Synchronization
**Objective:** Enable high-performance real-time processing and offline-first resilience.

- **Tasks:**
  1. Implement **In-Browser OpenCV.js Web Worker**:
     - Compile/load lightweight OpenCV WebAssembly.
     - Video frames offloaded from main UI thread to Web Worker via `OffscreenCanvas` / `ImageBitmap`.
     - Ensures 30 FPS buttery UI preview while CV runs at ~12 FPS in background.
  2. Implement **WebSocket Streaming Route (Optional / Server-Assisted)**:
     - For ultra-low-end devices, allow streaming frames over WebSocket to local backend.
  3. Implement **IndexedDB Offline Storage**:
     - All session metadata and responses committed immediately to browser `IndexedDB`.
     - Auto-sync service worker detects network reconnection and fires background sync.
- **Verification:** Disconnect Wi-Fi during live scanning; verify that all assessment data persists locally and syncs successfully upon reconnecting.

---

### Phase 6: End-to-End Verification & Real-World Simulation Suite
**Objective:** Validate system performance, edge cases, and user flow end-to-end.

- **Tasks:**
  1. Synthetic 45-Card Classroom Generator:
     - Script that creates multi-card collage images simulating a full classroom of 30–45 students at varying scales, rotations, and lighting conditions.
  2. Automated End-to-End test:
     - Feed synthetic classroom video through the pipeline.
     - Assert 100% correct detection of all present cards and accurate reporting of missing roll numbers.
  3. Document walkthrough and operations manual.
- **Verification:** Complete end-to-end execution passes all thresholds without error.

---

## 4. Architectural & Implementation Alignment Check

| Item | Architectural Specification | Implementation Alignment | Verification Status |
|---|---|---|---|
| **Identity Resolution** | `Roll Number == Card ID` within active `class_id` context. No permanent student-to-card binding. | State tracker directly maps `marker_id` to `roll_number`. Roster limits validated. | Aligned |
| **Privacy Separation** | Zero student names or photos in `Response` table. | Schema stores only `(school_code, class_id, roll_number, selected_option, timestamp)`. | Aligned |
| **Edge-Color Verification** | Top edge color cross-checks marker rotation. | HSV color sampler verifies color band at top edge. Disagreements flagged as `AMBIGUOUS`. | Aligned |
| **Offline Resilience** | Must not depend on internet during live scanning. | PWA with Service Worker + `IndexedDB` local storage; deferred batch sync. | Aligned |
| **Web Platform** | Pure Web App (no mobile native compilation required). | WebRTC camera feed + HTML5 Canvas AR + WebAssembly / WebSocket processing. | Aligned |
