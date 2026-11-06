# Vision-Based Low-Cost Formative Classroom Assessment System
### Pi Jam FAST — Course Project ET617 | In Collaboration with Pi Jam Foundation

---

> ### 🌐 [Click Here to View the Interactive Project Introduction Webpage](https://ead-labs.github.io/Group-7_2026/)
> **A simple, visual introduction to the educational problem, target users, and application mechanic for a non-technical audience.**  
> *(If running locally or deployed on Render, also available directly at [`/intro`](http://localhost:8000/intro))*

---

[![Project Introduction Page](https://img.shields.io/badge/Project%20Overview-Webpage-indigo?style=for-the-badge&logo=googlechrome&logoColor=white)](https://ead-labs.github.io/Group-7_2026/)
[![Live App Deployment](https://img.shields.io/badge/Deployment-Render%20Cloud-black?style=for-the-badge&logo=render&logoColor=white)](https://group-7-2026.onrender.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-REST%20%26%20WebSocket-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-Headless%20CV-5C3EE8.svg?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

---

## 1. Project Purpose & Executive Overview

In resource-constrained educational environments (such as Indian Zilla Parishad and municipal government schools partnering with **Pi Jam Foundation**), running frequent, low-stakes formative assessments (comprehension polls, exit tickets) is severely hindered by:
- **Zero Student Devices:** Classrooms operate without tablets, laptops, or individual clickers for students.
- **Unreliable / Zero Internet:** Thick concrete walls create cellular dead zones; systems requiring continuous connectivity fail.
- **Why Paper OMR Sheets Fail:** High recurring paper and toner printing costs, distribution logistics, and 24–48 hour batch processing delays that eliminate opportunities for same-day remedial instruction.
- **Why Electronic Clickers Fail:** Prohibitive capital expenses ($50–$100/student), dead batteries, hardware repairs, and theft liability.
- **Why Hand-Raising Fails:** Severe peer-mimicry bias (students look at the topper and copy), social stigma, and zero longitudinal mastery records.

### The FAST Solution
**Pi Jam FAST** bridges the physical and digital classroom using **one single teacher smartphone** and **reusable, durable laminated paper cards**:
1. **Physical Cards ($Roll \equiv ID$):** Each student holds a reusable, rotation-asymmetric ArUco $5\times5$ fiducial card with 4 color-coded edge bands: **A (Red)**, **B (Yellow)**, **C (Blue)**, and **D (Green)**.
2. **Student Voting:** When a question is posed, students orient their card so their chosen answer edge points **UP** toward the ceiling. The student-facing back is mirrored so neighboring peers cannot peek.
3. **Single Continuous Camera Sweep (5–15 seconds):** The teacher pans their smartphone camera across the classroom. The local computer vision pipeline detects, rectifies, and decodes every student's answer simultaneously.
4. **Immediate Actionable Feedback:** Real-time Augmented Reality overlay, live missing roll number detection, question accuracy percentages, distractor analysis (common misconceptions), and mastery scorecards ready for Excel/PDF export—all operating 100% offline.

---

## 2. Key Features

- ⚡ **Zero Student Electronics:** 100% paper-based for students, zero screens or gadget maintenance.
- 📶 **100% Offline-Capable:** Operates fully without in-classroom Wi-Fi or cellular connectivity; queues data for optional cloud sync.
- 🎯 **Sub-Pixel ArUco Geometry & Dual-Cue Color Validation:** Combines ArUco bitgrid homography with exterior HSV color-band sampling to eliminate false positives and reject tilted ambiguous cards (~45°).
- 🛡️ **Privacy by Design:** Composite keys only (`school_code`, `class_id`, `roll_number`); no facial images or student names captured or stored.
- 📊 **Real-Time AR HUD & Missing Roll Tracker:** Displays bounding boxes with roll number badges on camera and live indicators for unread students during the sweep.
- 📈 **Mastery Scoring & Distractor Analysis:** Classifies students into High / Moderate / Support Needed tiers and tallies which wrong options confused learners most.
- 📄 **1-Click Enterprise Reports:** Exports formatted multi-sheet Excel scorecards and printable PDF assessment summaries.

---

## 3. How to Access & Run the Application

### Option A: Access Live Cloud Deployment (Render)
The application is pre-configured for automated cloud deployment on **Render**:
- **Web Application:** Open your deployed Render URL (e.g., `https://<your-app>.onrender.com`) in any modern mobile or desktop browser.
- **Project Introduction Page:** Access `https://<your-app>.onrender.com/intro` or click the `ℹ️ Overview` button in the app navigation bar.
- **Health Check Endpoint:** `https://<your-app>.onrender.com/api/health`

### Option B: Run Locally on Your Machine

#### Prerequisites
- **Python 3.10+**
- Modern web browser (Chrome, Edge, Firefox, or Safari) with camera permissions.

#### 1. Clone the Repository
```bash
git clone https://github.com/EAD-Labs/Group-7_2026.git
cd Group-7_2026
```

#### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Start the Server
```bash
python run_server.py
```
*Tip: To run with plain HTTP (e.g., for localhost-only testing without mobile SSL certificate prompts), use `python run_server.py --http`.*

#### 4. Open in Browser
- **On Laptop:** Open `https://localhost:8000` (or `http://localhost:8000` if using `--http`).
- **On Mobile Phone (Same Wi-Fi):** The console prints your local network IP and saves a terminal QR code `mobile_connect_qr.png`. Scan it with your phone camera to open the application directly.
- **Introduction Page:** Navigate to `http://localhost:8000/intro`.

---

## 4. Verification & Testing

The repository includes a complete test suite and an end-to-end synthetic 25-student classroom sweep benchmark:

### 1. Run Unit Tests
```bash
python -m unittest discover tests
```
*Verifies computer vision detector initialization, perspective rectification, and session state tracking.*

### 2. Run Synthetic 25-Student Classroom Sweep Simulation
```bash
python tests/simulate_classroom.py
```
*Synthesizes a 25-student classroom collage with variable card orientations, executes computer vision detection on CPU (< 60 ms), verifies 100% answer decode accuracy, handles marked absentees, and flags unread roll numbers.*

---

## 5. Repository Structure

```
Group-7_2026/
├── backend/
│   ├── database.py                 # SQLite database schema, seed rosters, and queries
│   ├── main.py                     # FastAPI REST API, WebSocket live scanner, static server
│   ├── services/
│   │   ├── analytics_service.py    # Mastery scorecards, distractor analysis, historical trends
│   │   └── export_service.py       # Excel and merged PDF report generators
│   └── uploads/                    # Uploaded rosters and exported scorecards (.gitkeep)
├── core/
│   ├── cv_engine.py                # Computer vision engine (ArUco 5x5, homography, HSV dual-cue)
│   └── session_tracker.py          # Session state machine, temporal debouncer, and anomaly traps
├── docs/
│   ├── index.html                  # Project Introduction Page (for non-technical audience / GitHub Pages)
│   ├── TECHNICAL_CONTEXT.md        # Comprehensive technical manual & report reference
│   ├── ARCHITECTURE.md             # System architecture & WebRTC/WebSocket data flow
│   ├── COMPUTER_VISION.md          # Mathematical formulas and CV algorithms
│   ├── PRD.md                      # Product Requirements Document
│   ├── DESIGN.md                   # System scale projections and design principles
│   ├── IMPLEMENTATION.md           # 16 classroom edge-case mitigations
│   ├── MARKER_GENERATION.md        # Mathematical fiducial bitgrid generation
│   ├── PRODUCTION_MANUAL.md        # Field deployment & teacher operating manual
│   └── PRODUCTION_ROADMAP.md       # Long-term scalability and hardware roadmap
├── frontend/
│   ├── index.html                  # Single Page Application (5-step teacher assessment wizard)
│   ├── styles.css                  # Responsive design system & glassmorphic UI
│   ├── app.js                      # WebRTC camera sweep, HTML5 Canvas AR HUD, WebSocket client
│   └── config.js                   # Environment-aware backend API & WebSocket configuration
├── scripts/
│   ├── generate_cards.py           # Generates 45 ArUco fiducial cards (front camera + back student view)
│   ├── generate_classroom_markers.py # Generates 300 DPI high-res cards with duplex registration
│   └── generate_pdfs.py            # Compiles cards into print-ready A4 PDFs
├── tests/
│   ├── test_cv_engine.py           # Unit tests for CV pipeline & session tracker
│   └── simulate_classroom.py       # 25-student synthetic classroom sweep benchmark
├── .gitignore                      # Clean repository ignore patterns (DBs, outputs, keys)
├── Procfile                        # Production web server process command
├── render.yaml                     # Render Blueprint specification
├── package.json                    # Mobile Capacitor build scripts & metadata
├── requirements.txt                # Production Python dependencies (opencv-python-headless)
└── run_server.py                   # Local development server with auto-IP & QR generation
```

---

## 6. Cloud Deployment Configuration (Render)

This project is configured out of the box for cloud hosting on **Render** using `render.yaml`:
- **Environment:** Python 3.11
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/api/health`
- **Dependencies:** Uses `opencv-python-headless` to eliminate GUI/X11 system library dependencies in cloud Linux containers.

---

## 7. Project Credits & Information

- **Course:** ET617 Educational Technology (2026)
- **Team:** FAST (Group 7)
- **Partner Organization:** Pi Jam Foundation
- **Repository:** [https://github.com/EAD-Labs/Group-7_2026](https://github.com/EAD-Labs/Group-7_2026)
- **Interactive Overview:** [https://ead-labs.github.io/Group-7_2026/](https://ead-labs.github.io/Group-7_2026/)
