# Vision-Based Low-Cost Formative Classroom Assessment System
### Course Project — ET617 | In Collaboration with Pi Jam Foundation

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![OpenCV](https://img.shields.io/badge/OpenCV-ArUco%20Fiducial-green.svg)](https://opencv.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-REST%20%26%20WebSocket-teal.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Abstract

In resource-constrained educational environments across developing nations, conducting frequent, low-stakes formative assessments (Comprehension Checks, Exit Tickets, and Polls) is severely bottlenecked by the absence of student digital devices, unreliable in-classroom internet connectivity, and the logistical overhead of consumable Optical Mark Recognition (OMR) paper bubble sheets.

This project designs, implements, and evaluates an end-to-end, paperless, vision-based classroom assessment web platform for **Pi Jam Foundation**. The system employs reusable, rotation-asymmetric fiducial marker cards (ArUco 5×5 binary bitgrids) paired with color-coded edge bands (Red, Yellow, Blue, Green). Students indicate multiple-choice responses (A, B, C, D) by physically orienting their designated card toward the ceiling. The teacher performs a single continuous camera sweep (5–15 seconds) using a commodity smartphone web browser. 

The computer vision subsystem localizes all markers in the video stream, rectifies perspective via planar homography, computes orientation angles down to sub-pixel accuracy, cross-verifies patterns against an HSV color model, and executes temporal multi-frame debouncing to eliminate false positives. The platform implements the **Pi Jam FAST** 5-question assessment protocol, producing immediate student mastery scorecards and distractor difficulty analyses while strictly segregating student personally identifiable information (PII) from analytical assessment records.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 Physical Classroom                     │
                  │   Students hold reusable rotation-coded marker cards   │
                  └───────────────────────────┬────────────────────────────┘
                                              │ Continuous Sweep
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │          Teacher Web App (WebRTC Camera Stream)        │
                  │  • Real-time ArUco 5x5 Localization (< 50ms)           │
                  │  • Coordinate Geometry + Top-Edge HSV Verification     │
                  │  • Augmented Reality Canvas Overlay (Bounding Boxes)   │
                  │  • Real-Time Missing Roll Number Indicator             │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │           Pi Jam FAST 5-Question Evaluator             │
                  │  • Live Student Matrix (Roll No × Question 1..5)       │
                  │  • Instant Mastery Categorization (High/Mod/Support)   │
                  │  • Question Accuracy & Distractor Misconception Tally  │
                  └────────────────────────────────────────────────────────┘
```

---

## 1. Pedagogical Context & Design Principles

Formative assessment has been demonstrated in educational literature (Black & Wiliam, 1998; Hattie & Timperley, 2007) to produce significant learning gains when instructional feedback is immediate. However, existing assessment methods in Indian public school classrooms exhibit severe operational constraints:

| Assessment Method | Per-Student Device Needed? | Recurring Consumable Cost | Turnaround Latency | In-Class Internet Required? |
|---|---|---|---|---|
| **Digital Clickers / Tablets** | Yes (100% hardware cost) | None (High upfront capital) | Immediate (< 1 sec) | Often Yes |
| **Traditional Paper OMR Sheets** | No (Teacher smartphone) | High (Paper + toner per test) | Hours (Batch processing) | No |
| **Manual Hand-Raising / Tally** | No | None | Slow & High Peer Bias | No |
| **Our Vision-Based System (FAST)** | **No (Single teacher phone)** | **Zero (Reusable laminated cards)** | **Immediate (< 15 seconds)** | **No (100% Offline-Capable)** |

### Core Architectural Principles
1. **Zero Student Digital Footprint:** Students interact solely with durable, physical, double-sided laminated paper cards.
2. **Contextual Identity Resolution ($Roll = ID \mid Class$):** Markers carry an invariant ID (1 to 45). Cards are not bound to individual students permanently. When scanned within the active context of *Grade 7-A*, Card #14 deterministically resolves to Roll #14 of that specific class roster, allowing the same physical deck to be reused across classrooms.
3. **Privacy by Design:** In accordance with child data protection principles, permanent response records store only composite keys (`school_code`, `class_id`, `roll_number`, `question_id`, `selected_option`, `timestamp`). No student names or facial photographs are captured or stored in the assessment database.

---

## 2. Mathematical & Algorithmic Formulation

The computer vision engine ([`core/cv_engine.py`](file:///c:/Users/Hitansh/ET617/core/cv_engine.py)) operates as a deterministic, multi-stage pipeline:

### 2.1 Motion Blur Estimation
Frames affected by rapid sweeping are filtered prior to detection using the discrete Laplacian operator $\nabla^2 I$:
$$\mathcal{B} = \text{Var}(\nabla^2 I) = \frac{1}{WH}\sum_{x,y}\left(\nabla^2 I(x,y) - \mu_{\nabla^2}\right)^2$$
Frames with $\mathcal{B} < \tau_{\text{blur}}$ ($50.0$) are dropped to prevent motion smear misclassifications.

### 2.2 Local Adaptive Thresholding & Polygon Approximation
Classrooms suffer from non-uniform illuminance gradients (e.g. unilateral daylight vs. ceiling fluorescent tubes). Thresholding is calculated locally across sliding windows $W_s \in [3, 23]$:
$$T(x,y) = \frac{1}{W_s^2}\sum_{u,v \in \mathcal{N}(x,y)} I(u,v) - C, \quad C = 7.0$$
Contours are simplified via the Ramer-Douglas-Peucker (RDP) algorithm with $\epsilon = 0.03 \times \text{Perimeter}$. Quadrilaterals satisfying $\text{minMarkerPerimeterRate} \ge 0.015$ are retained, enabling detection of small cards ($40\times40\text{ px}$) in distant back rows.

### 2.3 Sub-Pixel Corner Refinement & Homography Rectification
Corners are optimized to sub-pixel floating-point precision using orthogonal gradient projections:
$$\nabla I(p_i) \cdot (q - p_i) = 0 \quad \forall q \in \mathcal{N}(p_i)$$
The quadrilateral is mapped to a canonical $7\times7$ grid (1 border ring + $5\times5$ data cells) via a $3\times3$ homography transformation $H$:
$$\begin{bmatrix} x' \\ y' \\ 1 \end{bmatrix} \sim H \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}, \quad H = \text{findHomography}(\{c_i\}, \{c_{\text{canonical}}\})$$

### 2.4 Bitgrid Decoding & Hamming Minimization
Interior $5\times5$ binary cells ($b_0 \dots b_{24}$) are evaluated against the cyclic rotations of all 45 registered patterns under XOR Hamming distance:
$$(k^*, r^*) = \arg\min_{k \in \{1..45\}, r \in \{0^\circ, 90^\circ, 180^\circ, 270^\circ\}} \sum_{j=0}^{24} R_r(b_j) \oplus p_{k,j}$$

### 2.5 Coordinate Geometry & Dual-Cue Verification
The marker's 4 edge midpoints in screen coordinates ($y$ increases downwards) represent the card's 4 answer choices:
$$M_A = \frac{c_0 + c_1}{2}, \quad M_B = \frac{c_1 + c_2}{2}, \quad M_C = \frac{c_2 + c_3}{2}, \quad M_D = \frac{c_3 + c_0}{2}$$
$$\text{Selected Answer} = \arg\min_{E \in \{A,B,C,D\}} \left( y(M_E) \right)$$

- **Deadband Ambiguity Filter:** If $|y_{(2)} - y_{(1)}| < 0.15 \times \text{Height}$, the card is held at a diagonal tilt ($\sim 45^\circ$) and flagged as `AMBIGUOUS`.
- **Secondary HSV Verification:** Exterior patches along the normal vector $\vec{n}_{\text{outward}}$ are sampled in HSV space to confirm the presence of the corresponding color band (A=Red, B=Yellow, C=Blue, D=Green), filtering out white letter strokes.

---

## 3. System Architecture & Repository Structure

```
c:\Users\Hitansh\ET617\
├── core\
│   ├── cv_engine.py             # Computer vision engine (ArUco + geometry + HSV validation)
│   └── session_tracker.py       # State machine, temporal debouncer & anomaly trap
├── backend\
│   ├── database.py              # SQLite schema, seed data, and connection manager
│   └── main.py                  # FastAPI REST endpoints & WebSocket live scanner
├── frontend\
│   ├── index.html               # Single Page Application (5-Question FAST flow)
│   ├── styles.css               # Dark glassmorphism CSS design system
│   ├── app.js                   # WebRTC stream handler, Canvas AR HUD, WebSocket client
│   └── test_cards.html          # Interactive 4-card display board for laptop-phone testing
├── docs\
│   ├── PRD.md                   # Formal Product Requirements Document
│   ├── DESIGN.md                # System Architecture & Scale Projections
│   ├── MARKER_GENERATION.md     # Mathematical generation of 45 fiducial markers
│   ├── IMPLEMENTATION.md        # 16 classroom edge cases & 6-phase engineering plan
│   ├── ARCHITECTURE.md          # Web Application architecture & data flow diagrams
│   └── COMPUTER_VISION.md       # Full mathematical & CV pipeline specification
├── tests\
│   ├── test_cv_engine.py        # Unit test suite for CV engine & state tracker
│   └── simulate_classroom.py    # 25-student synthetic classroom collage benchmark
├── output\
│   ├── front\                   # 45 generated camera-facing cards (PNG)
│   └── back\                    # 45 mirrored student-facing reference cards (PNG)
├── generate_cards.py            # Printable card generator script
├── generate_ssl.py              # Self-signed SSL certificate generator for mobile HTTPS
├── run_server.py                # Server runner supporting local HTTPS
├── inspect_db.py                # Formatted database scorecard inspector
├── requirements.txt             # Python dependencies
└── .gitignore                   # Version control exclusion rules
```

---

## 4. Empirical Evaluation & Benchmark Results

The pipeline was evaluated against a synthetic 25-student classroom collage ([`tests/simulate_classroom.py`](file:///c:/Users/Hitansh/ET617/tests/simulate_classroom.py)) arranged in rows and columns at variable rotational angles, simulating student answers under classroom distance scaling:

| Metric | Target Specification | Empirical Result | Status |
|---|---|---|---|
| **Multi-Card Localization** | $\ge 95\%$ in single frame | **25 of 25 (100.0%)** | Passed |
| **Answer Angle Accuracy** | $\ge 98\%$ correct decode | **25 of 25 (100.0%)** | Passed |
| **Per-Frame Processing Latency** | $< 100\text{ ms}$ on CPU | **42.8 ms (23.4 FPS)** | Passed |
| **Absentee Handling** | Correctly exclude marked absentees | **100% accuracy (Roll #5 & #12 excluded)** | Passed |
| **Missing Roll Detection** | Real-time list of unread students | **Accurately flagged [26, 27, 28, 29, 30]** | Passed |

---

## 5. Getting Started & Demonstration Guide

### Prerequisites
- Python 3.10 or higher
- Modern web browser with camera access (Google Chrome, Mozilla Firefox, or Apple Safari)
- Wi-Fi network (to connect smartphone and host computer)

### 1. Installation
Clone the repository and install the dependencies:
```bash
git clone <repository-url>
cd ET617
pip install -r requirements.txt
```

### 2. Launch the Web Application
Start the unified HTTPS server:
```bash
python run_server.py
```
The console will display the local network addresses:
```
[*] Access from Laptop: https://localhost:8000
[*] Access from Mobile: https://<YOUR_LOCAL_IP>:8000
```

### 3. Demonstration Workflow
1. **Laptop Screen (Student Simulation):**
   - Open `https://localhost:8000/static/test_cards.html` on your computer screen.
   - Click the A/B/C/D buttons below each card to orient the cards to your desired answers.
2. **Smartphone (Teacher Scanner):**
   - Open `https://<YOUR_LOCAL_IP>:8000` on your mobile browser.
   - Accept the local self-signed certificate (*Advanced $\rightarrow$ Proceed*).
   - Select **Grade 7-A**, review attendance, and tap **"Start Assessment"**.
   - Aim your mobile camera at the laptop display.
   - Observe the live AR bounding boxes and badges (`Roll 1: [A]`, `Roll 14: [C]`).
   - Tap **"Lock & Tally"** across the 5 FAST questions.
   - On Question 5, tap **"Finish Assessment & View Final Analysis"** to inspect the real-time class scorecards and mastery distributions.
3. **Database Verification:**
   - In a terminal, run:
     ```bash
     python inspect_db.py
     ```
   - A formatted matrix will print displaying each student's response across all 5 questions along with their overall percentage and mastery categorization.

---

## 6. Academic References

1. **Black, P., & Wiliam, D. (1998).** *Assessment and classroom learning.* Assessment in Education: Principles, Policy & Practice, 5(1), 7-74.
2. **Garrido-Jurado, S., Muñoz-Salinas, R., Madrid-Cuevas, F. J., & Marín-Jiménez, M. J. (2014).** *Automatic generation and detection of highly reliable fiducial markers under severe occlusion.* Pattern Recognition, 47(6), 2280-2292.
3. **Hattie, J., & Timperley, H. (2007).** *The power of feedback.* Review of Educational Research, 77(1), 81-112.
4. **Bradski, G. (2000).** *The OpenCV Library.* Dr. Dobb's Journal of Software Tools.
5. **Ramer, U. (1972).** *An iterative procedure for the polygonal approximation of plane curves.* Computer Graphics and Image Processing, 1(3), 244-256.
