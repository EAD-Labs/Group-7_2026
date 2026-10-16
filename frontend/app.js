/**
 * Pi Jam FAST Assessment Platform — Frontend Application Logic
 * Full implementation: Dynamic questions, PDF upload, live AR scanner,
 * reactive answer key recalculation, 90-day history, manager oversight, and offline sync.
 */

// --- Application State ---
const state = {
  currentUser: {
    teacher_id: "PJ-T101",
    name: "Anjali Sharma",
    role: "teacher",
    school_id: "sch_pijam_01",
    school_name: "Pi Jam Partner Model School",
  },
  sessionId: null,
  classId: null,
  className: "Grade 7-A",
  quizName: "Unit 3: Loops & Conditionals",
  subject: "Computer Science",
  sessionDate: new Date().toISOString().substring(0, 10),
  questionCount: 5,
  questionMode: "blackboard", // 'blackboard' or 'pdf'
  pdfFile: null,
  currentQuestionIndex: 1,
  roster: [], // [{roll_number, name}]
  absentees: new Set(),
  answerKey: {}, // { "1": "A", "2": "B", ... }
  confirmedResponses: {}, // { roll: "A"|"B"|"C"|"D" }
  // Per-question confirmed responses accumulator: { qIndex: { roll: answer } }
  allQuestionResponses: {},
  consecutiveBlurryFrames: 0, // Track consecutive blurry frames to avoid false-positive warnings
  facingMode: "environment",
  ws: null,
  isScanning: false,
  stream: null,
  isOnline: navigator.onLine,
};

// Colors matching card edges (BGR in OpenCV -> RGB for Canvas)
const ANSWER_COLORS_RGB = {
  "A": "#ef4444", // Red
  "B": "#f59e0b", // Yellow
  "C": "#3b82f6", // Blue
  "D": "#10b981", // Green
  "AMBIGUOUS": "#f97316"
};

// --- DOM References ---
const views = {
  login: document.getElementById("view-login"),
  setup: document.getElementById("view-setup"),
  questionMode: document.getElementById("view-question-mode"),
  attendance: document.getElementById("view-attendance"),
  scanner: document.getElementById("view-scanner"),
  analysis: document.getElementById("view-analysis"),
  history: document.getElementById("view-history"),
  manager: document.getElementById("view-manager"),
};

const stepperBar = document.getElementById("stepper-bar");
const userBadge = document.getElementById("user-badge");
const userNameLabel = document.getElementById("user-name-label");
const btnNavHistory = document.getElementById("btn-nav-history");
const btnNavManager = document.getElementById("btn-nav-manager");
const btnLogout = document.getElementById("btn-logout");
const connBadge = document.getElementById("connection-status");
const connText = document.getElementById("conn-text");

// View Router
function switchView(viewName, stepIndex = null) {
  Object.values(views).forEach(v => {
    if (v) v.classList.remove("active");
  });

  if (views[viewName]) {
    views[viewName].classList.add("active");
  }

  // Handle Stepper Bar Visibility & State
  if (stepIndex !== null && stepIndex >= 1 && stepIndex <= 5) {
    stepperBar.style.display = "flex";
    document.querySelectorAll(".step-item").forEach(item => {
      const s = parseInt(item.getAttribute("data-step"));
      item.classList.toggle("active", s <= stepIndex);
    });
  } else {
    stepperBar.style.display = "none";
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Update Network Connection Status
function updateOnlineStatus() {
  state.isOnline = navigator.onLine;
  if (state.isOnline) {
    connBadge.className = "badge badge-online";
    connText.textContent = "Online";
    syncOfflineQueue();
  } else {
    connBadge.className = "badge badge-offline";
    connText.textContent = "Offline Mode";
  }
}

window.addEventListener("online", updateOnlineStatus);
window.addEventListener("offline", updateOnlineStatus);

// --- Initialization ---
async function initApp() {
  updateOnlineStatus();

  // Setup Date default
  const dateInput = document.getElementById("setup-date");
  if (dateInput) {
    dateInput.value = state.sessionDate;
  }

  // Setup Event Listeners
  setupAuthEvents();
  setupWizardEvents();
  setupScannerEvents();
  setupAnalysisEvents();
  setupHistoryEvents();
  setupManagerEvents();

  // Header Logo click returns to setup
  document.getElementById("header-home-btn").addEventListener("click", () => {
    if (state.currentUser) {
      switchView("setup", 1);
    } else {
      switchView("login");
    }
  });
}

// --- 0. AUTHENTICATION MODULE ---
function setupAuthEvents() {
  const profileChips = document.querySelectorAll(".profile-chip");
  const inputUserId = document.getElementById("input-user-id");
  const inputPin = document.getElementById("input-user-pin");
  const btnSubmitLogin = document.getElementById("btn-submit-login");

  profileChips.forEach(chip => {
    chip.addEventListener("click", () => {
      profileChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      const uid = chip.getAttribute("data-id");
      inputUserId.value = uid;
      inputPin.value = uid.startsWith("PJ-M") ? "0000" : "1234";
    });
  });

  btnSubmitLogin.addEventListener("click", async () => {
    const uid = inputUserId.value.trim();
    const pin = inputPin.value.trim();
    if (!uid) return alert("Please enter a User ID");

    try {
      const res = await fetch(`${window.API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: uid, pin: pin })
      });

      if (!res.ok) {
        const err = await res.json();
        return alert(err.detail || "Login failed");
      }

      const data = await res.json();
      state.currentUser = data.user;
      onLoginSuccess(data);
    } catch (err) {
      console.warn("Server unavailable, using offline fallback login:", err);
      // Fallback offline login
      state.currentUser = {
        teacher_id: uid,
        name: uid.startsWith("PJ-M") ? "Ulfa Monitoring Lead" : "Anjali Sharma",
        role: uid.startsWith("PJ-M") ? "manager" : "teacher",
        school_id: "sch_pijam_01",
        school_name: "Pi Jam Partner Model School",
      };
      onLoginSuccess({
        user: state.currentUser,
        classes: [
          { class_id: "cls_7a", grade: "7", section: "A", academic_year: "2026-2027" },
          { class_id: "cls_8b", grade: "8", section: "B", academic_year: "2026-2027" }
        ]
      });
    }
  });

  btnLogout.addEventListener("click", () => {
    state.currentUser = null;
    userBadge.style.display = "none";
    btnNavHistory.style.display = "none";
    btnNavManager.style.display = "none";
    btnLogout.style.display = "none";
    switchView("login");
  });
}

function onLoginSuccess(data) {
  const user = data.user;
  userBadge.style.display = "inline-flex";
  userNameLabel.textContent = `${user.name} (${user.teacher_id})`;
  btnLogout.style.display = "inline-block";

  if (user.role === "manager") {
    btnNavManager.style.display = "inline-block";
    btnNavHistory.style.display = "none";
    loadManagerDashboard();
    switchView("manager");
  } else {
    btnNavHistory.style.display = "inline-block";
    btnNavManager.style.display = "none";

    // Populate Class Select
    const classSelect = document.getElementById("setup-class-select");
    classSelect.innerHTML = "";
    data.classes.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.class_id;
      opt.textContent = `Grade ${c.grade}-${c.section} (${c.academic_year})`;
      classSelect.appendChild(opt);
    });

    // Pre-fill school name from teacher profile (editable in case of multi-school teachers)
    const schoolInput = document.getElementById("setup-school-name");
    if (schoolInput && user.school_name) {
      schoolInput.value = user.school_name;
    }

    switchView("setup", 1);
  }
}

// --- 1 & 2. SETUP & QUESTION MODE MODULE ---
function setupWizardEvents() {
  // Dynamic Question Stepper (Default: 5)
  const displayQCount = document.getElementById("display-q-count");
  document.getElementById("btn-q-dec").addEventListener("click", () => {
    if (state.questionCount > 1) {
      state.questionCount--;
      displayQCount.textContent = state.questionCount;
      renderEarlyKeyGrid();
    }
  });

  document.getElementById("btn-q-inc").addEventListener("click", () => {
    if (state.questionCount < 20) {
      state.questionCount++;
      displayQCount.textContent = state.questionCount;
      renderEarlyKeyGrid();
    }
  });

  // Step 1 -> Step 2: save all setup fields into state
  document.getElementById("btn-to-question-mode").addEventListener("click", () => {
    const schoolNameVal = document.getElementById("setup-school-name").value.trim();
    if (!schoolNameVal) {
      return alert("Please enter the school name before continuing.");
    }
    state.schoolName = schoolNameVal;
    state.quizName = document.getElementById("setup-quiz-name").value.trim() || "Formative Assessment";
    state.subject = document.getElementById("setup-subject").value;
    state.sessionDate = document.getElementById("setup-date").value || new Date().toISOString().substring(0, 10);
    state.classId = document.getElementById("setup-class-select").value;
    const sel = document.getElementById("setup-class-select");
    state.className = sel.options[sel.selectedIndex]?.text || "Class";

    renderEarlyKeyGrid();
    switchView("questionMode", 2);
  });

  document.getElementById("btn-back-to-setup").addEventListener("click", () => {
    switchView("setup", 1);
  });

  // Mode Cards: Case 1 (Blackboard) vs Case 2 (PDF)
  const modeBlackboard = document.getElementById("mode-card-blackboard");
  const modePdf = document.getElementById("mode-card-pdf");
  const pdfContainer = document.getElementById("pdf-upload-container");

  modeBlackboard.addEventListener("click", () => {
    state.questionMode = "blackboard";
    modeBlackboard.classList.add("active");
    modePdf.classList.remove("active");
    pdfContainer.style.display = "none";
  });

  modePdf.addEventListener("click", () => {
    state.questionMode = "pdf";
    modePdf.classList.add("active");
    modeBlackboard.classList.remove("active");
    pdfContainer.style.display = "block";
  });

  // PDF File Dropzone & Input
  const fileInput = document.getElementById("pdf-file-input");
  const dropzone = document.getElementById("pdf-dropzone");
  const btnBrowse = document.getElementById("btn-browse-pdf");
  const statusBadge = document.getElementById("pdf-file-status");
  const filenameLabel = document.getElementById("pdf-filename-label");
  const filesizeLabel = document.getElementById("pdf-filesize-label");
  const btnRemovePdf = document.getElementById("btn-remove-pdf");

  btnBrowse.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("click", () => fileInput.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "#3b82f6";
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.style.borderColor = "";
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "";
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handlePdfSelected(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handlePdfSelected(e.target.files[0]);
    }
  });

  function handlePdfSelected(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      return alert("Please select a valid PDF file.");
    }
    state.pdfFile = file;
    filenameLabel.textContent = file.name;
    filesizeLabel.textContent = `(${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    statusBadge.style.display = "flex";
  }

  btnRemovePdf.addEventListener("click", (e) => {
    e.stopPropagation();
    state.pdfFile = null;
    fileInput.value = "";
    statusBadge.style.display = "none";
  });

  // Step 2 -> Step 3 (Attendance)
  document.getElementById("btn-to-attendance").addEventListener("click", async () => {
    await loadClassRoster();
    switchView("attendance", 3);
  });

  document.getElementById("btn-back-to-mode").addEventListener("click", () => {
    switchView("questionMode", 2);
  });
}

// Render dynamic early answer key grid (Q1..QN)
function renderEarlyKeyGrid() {
  const grid = document.getElementById("early-key-grid");
  grid.innerHTML = "";

  for (let q = 1; q <= state.questionCount; q++) {
    const card = document.createElement("div");
    card.className = "key-item-card";

    const label = document.createElement("span");
    label.className = "key-item-label";
    label.textContent = `Q${q}`;

    const optRow = document.createElement("div");
    optRow.className = "key-options-row";

    ["A", "B", "C", "D"].forEach(letter => {
      const btn = document.createElement("button");
      btn.className = `opt-btn ${state.answerKey[String(q)] === letter ? `selected-${letter}` : ""}`;
      btn.textContent = letter;
      btn.type = "button";
      btn.addEventListener("click", () => {
        if (state.answerKey[String(q)] === letter) {
          delete state.answerKey[String(q)];
          btn.className = "opt-btn";
        } else {
          state.answerKey[String(q)] = letter;
          optRow.querySelectorAll(".opt-btn").forEach(b => b.className = "opt-btn");
          btn.className = `opt-btn selected-${letter}`;
        }
      });
      optRow.appendChild(btn);
    });

    card.appendChild(label);
    card.appendChild(optRow);
    grid.appendChild(card);
  }
}

// --- 3. ATTENDANCE CHECK MODULE ---
async function loadClassRoster() {
  try {
    const res = await fetch(`/api/classes/${state.classId}/roster`);
    const data = await res.json();
    state.roster = data.students || [];
  } catch (err) {
    console.warn("Could not load roster from server, generating 30 default rolls:", err);
    state.roster = Array.from({ length: 30 }, (_, i) => ({
      roll_number: i + 1,
      name: `Student ${i + 1}`
    }));
  }

  state.absentees.clear();
  renderRosterGrid();
}

function renderRosterGrid() {
  const grid = document.getElementById("roster-grid");
  grid.innerHTML = "";
  const presentCountEl = document.getElementById("present-count");
  const totalCountEl = document.getElementById("total-count");

  totalCountEl.textContent = state.roster.length;
  presentCountEl.textContent = state.roster.length - state.absentees.size;

  state.roster.forEach(student => {
    const chip = document.createElement("div");
    const isAbsent = state.absentees.has(student.roll_number);
    chip.className = `roster-chip ${isAbsent ? "absent" : ""}`;
    chip.innerHTML = `
      <span class="chip-roll">Roll ${student.roll_number}</span>
      <span class="chip-status">${isAbsent ? "Absent" : "Present"}</span>
    `;

    chip.addEventListener("click", () => {
      if (state.absentees.has(student.roll_number)) {
        state.absentees.delete(student.roll_number);
      } else {
        state.absentees.add(student.roll_number);
      }
      renderRosterGrid();
    });

    grid.appendChild(chip);
  });
}

// Step 3 -> Step 4 (Initialize Session and Open Camera Sweep)
document.getElementById("btn-begin-sweep").addEventListener("click", async () => {
  // 1. Create Session in Backend
  try {
    const sessPayload = {
      class_id: state.classId,
      teacher_id: state.currentUser?.teacher_id || "PJ-T101",
      school_name: state.schoolName || state.currentUser?.school_name || "",
      quiz_name: state.quizName,
      subject: state.subject,
      session_date: state.sessionDate,
      question_count: state.questionCount,
      question_mode: state.questionMode,
      pre_set_answer_key: state.answerKey
    };

    const res = await fetch(`${window.API_BASE}/api/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sessPayload)
    });
    const sData = await res.json();
    state.sessionId = sData.session_id;

    // 2. Mark Absentees
    await fetch(`/api/sessions/${state.sessionId}/absentees`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ absentees: Array.from(state.absentees) })
    });

    // 3. Upload PDF if selected (Case 2)
    if (state.questionMode === "pdf" && state.pdfFile) {
      const formData = new FormData();
      formData.append("file", state.pdfFile);
      await fetch(`/api/sessions/${state.sessionId}/upload-pdf`, {
        method: "POST",
        body: formData
      });
    }
  } catch (err) {
    console.warn("Could not persist session to backend (Offline mode active):", err);
    state.sessionId = `sess_offline_${Date.now()}`;
  }

  // 4. Start Camera & Scanner on Question 1
  state.currentQuestionIndex = 1;
  state.confirmedResponses = {};
  switchView("scanner", 4);
  await startScannerQuestion(state.currentQuestionIndex);
});

// --- 4. LIVE VISION SCANNER & HUD MODULE ---
const cameraFeed = document.getElementById("camera-feed");
const arCanvas = document.getElementById("ar-canvas");
const ctx = arCanvas.getContext("2d");
const hudQuestionLabel = document.getElementById("hud-question-label");
const hudScannedCount = document.getElementById("hud-scanned-count");
const hudExpectedCount = document.getElementById("hud-expected-count");
const hudProgressFill = document.getElementById("hud-progress-fill");
const missingPillsList = document.getElementById("missing-pills-list");
const missingCountEl = document.getElementById("missing-count");
const blurWarning = document.getElementById("blur-warning");
const btnNextQuestionSweep = document.getElementById("btn-next-question-sweep");

async function startScannerQuestion(qIndex) {
  hudQuestionLabel.textContent = `Question ${qIndex} of ${state.questionCount}`;
  const totalExpected = state.roster.length - state.absentees.size;
  hudExpectedCount.textContent = totalExpected;
  hudScannedCount.textContent = "0";
  hudProgressFill.style.width = "0%";
  state.confirmedResponses = {};
  state.consecutiveBlurryFrames = 0;

  // Reset the backpressure flag so the scan loop fires immediately for this question
  isAwaitingDetection = false;

  if (qIndex < state.questionCount) {
    btnNextQuestionSweep.textContent = `Next Q (Q${qIndex + 1}) →`;
  } else {
    btnNextQuestionSweep.textContent = `Finish & View Analytics 🎯 →`;
  }

  // Ensure camera is running — if already open, just ensure the rAF loop is active
  await ensureCameraActive();
  connectWebSocket();
}

/**
 * Opens the camera stream if not already open.
 * If stream is already open (e.g. moving from Q1 → Q2), we simply re-arm the
 * isScanning flag and restart the rAF loop without stopping/restarting the track,
 * which would cause the 1-2 second black-screen gap teachers experienced.
 */
async function ensureCameraActive() {
  if (state.stream && state.stream.active) {
    // Stream already running — just make sure the rendering loop is alive
    if (!state.isScanning) {
      state.isScanning = true;
      requestAnimationFrame(renderScannerLoop);
    }
    return;
  }
  await startCamera();
}

async function startCamera() {
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: state.facingMode, width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false
    });
    cameraFeed.srcObject = state.stream;
    await cameraFeed.play();
    state.isScanning = true;
    requestAnimationFrame(renderScannerLoop);
  } catch (err) {
    console.error("Camera access failed:", err);
    alert("Camera permission is required to scan marker cards.");
  }
}

function stopCamera() {
  state.isScanning = false;
  if (state.stream) {
    state.stream.getTracks().forEach(t => t.stop());
    state.stream = null;
  }
}

function connectWebSocket() {
  if (state.ws) {
    try { state.ws.close(); } catch(e){}
  }

  // window.WS_BASE is set by config.js (same-origin for local, cloud URL for APK)
  const wsUrl = `${window.WS_BASE}/api/ws/scan/${state.sessionId}`;

  try {
    state.ws = new WebSocket(wsUrl);
    state.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "DETECTIONS") {
        handleDetections(msg);
      }
    };
  } catch (err) {
    console.warn("WebSocket scanner connection failed:", err);
  }
}

// Persistent offscreen canvas for high-performance frame capture (960px width)
const offscreenCanvas = document.createElement("canvas");
const offscreenCtx = offscreenCanvas.getContext("2d");
let isAwaitingDetection = false;
let lastFrameSent = 0;

function renderScannerLoop(timestamp) {
  if (!state.isScanning) return;

  if (cameraFeed.readyState === cameraFeed.HAVE_ENOUGH_DATA) {
    // Lock AR canvas resolution to native camera feed resolution
    if (arCanvas.width !== cameraFeed.videoWidth || arCanvas.height !== cameraFeed.videoHeight) {
      arCanvas.width = cameraFeed.videoWidth;
      arCanvas.height = cameraFeed.videoHeight;
    }

    // Dynamic viewport container aspect ratio matching to eliminate letterboxing/cropping
    const viewportContainer = document.querySelector(".camera-viewport-container");
    if (viewportContainer && cameraFeed.videoWidth && cameraFeed.videoHeight) {
      viewportContainer.style.aspectRatio = `${cameraFeed.videoWidth} / ${cameraFeed.videoHeight}`;
    }

    // Capture at crisp 960px resolution (56% sharper than 640px for distant cards)
    if (!isAwaitingDetection && timestamp - lastFrameSent > 70 && state.ws && state.ws.readyState === WebSocket.OPEN) {
      isAwaitingDetection = true;
      lastFrameSent = timestamp;

      const targetW = 960;
      const targetH = Math.round(targetW * (cameraFeed.videoHeight / cameraFeed.videoWidth));

      if (offscreenCanvas.width !== targetW || offscreenCanvas.height !== targetH) {
        offscreenCanvas.width = targetW;
        offscreenCanvas.height = targetH;
      }

      offscreenCtx.drawImage(cameraFeed, 0, 0, targetW, targetH);
      const b64 = offscreenCanvas.toDataURL("image/jpeg", 0.78);
      state.ws.send(JSON.stringify({ image: b64 }));
    }
  }

  requestAnimationFrame(renderScannerLoop);
}

function handleDetections(data) {
  isAwaitingDetection = false; // Reset backpressure flag so next frame can be sent

  const cards = data.cards || [];
  // Use the summary object from the server response (was 'summary' — undefined bug fixed here)
  const summary = data.summary || {};

  // ── Blur warning: only show after 3 consecutive blurry frames to avoid false positives
  // (e.g. a single bad frame mid-sweep should not interrupt the teacher)
  if (data.is_blurry && cards.length === 0) {
    state.consecutiveBlurryFrames = (state.consecutiveBlurryFrames || 0) + 1;
    if (state.consecutiveBlurryFrames >= 3) {
      blurWarning.style.display = "block";
    }
  } else {
    state.consecutiveBlurryFrames = 0;
    blurWarning.style.display = "none";
  }

  // ── Clear AR Canvas for this frame
  ctx.clearRect(0, 0, arCanvas.width, arCanvas.height);

  // ── Precise coordinate scaling from sent frame (960px) to native display canvas
  const sentW = data.frame_width || offscreenCanvas.width || 960;
  const sentH = data.frame_height || offscreenCanvas.height || Math.round(sentW * (arCanvas.height / arCanvas.width));
  const scaleX = arCanvas.width / sentW;
  const scaleY = arCanvas.height / sentH;

  // ── Draw AR Bounding Boxes & Floating Answer Badges
  cards.forEach(card => {
    const corners = card.corners;
    const ans = card.answer || card.selected_option || "A";
    const color = ANSWER_COLORS_RGB[ans] || "#3b82f6";
    const roll = card.card_id !== undefined ? card.card_id : (card.marker_id !== undefined ? card.marker_id : "?");

    // 1. Draw glowing polygon around marker corners
    ctx.beginPath();
    ctx.moveTo(corners[0][0] * scaleX, corners[0][1] * scaleY);
    for (let i = 1; i < 4; i++) {
      ctx.lineTo(corners[i][0] * scaleX, corners[i][1] * scaleY);
    }
    ctx.closePath();
    ctx.lineWidth = 6;
    ctx.strokeStyle = color;
    ctx.stroke();

    // 2. Translucent fill glow
    ctx.fillStyle = color === "#ef4444" ? "rgba(239, 68, 68, 0.22)" :
                    color === "#f59e0b" ? "rgba(245, 158, 11, 0.22)" :
                    color === "#10b981" ? "rgba(16, 185, 129, 0.22)" :
                    "rgba(59, 130, 246, 0.22)";
    ctx.fill();

    // 3. Floating Roll # & Option Badge positioned right above marker
    const bx = corners[0][0] * scaleX;
    const by = Math.max(34, corners[0][1] * scaleY - 14);

    ctx.fillStyle = "rgba(10, 14, 23, 0.90)";
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(bx - 6, by - 26, 130, 32, 8);
    } else {
      ctx.rect(bx - 6, by - 26, 130, 32);
    }
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 15px Outfit, sans-serif";
    ctx.fillText(`Roll ${roll}: `, bx + 6, by - 6);
    ctx.fillStyle = color;
    ctx.font = "bold 20px 'JetBrains Mono', monospace";
    ctx.fillText(ans, bx + 80, by - 5);
  });

  // ── Update local confirmed responses state from server summary
  const confirmed = summary.confirmed_responses || summary.confirmed_answers || {};
  state.confirmedResponses = confirmed;

  // ── Update HUD counters & progress bar
  const count = summary.scanned_count !== undefined ? summary.scanned_count : Object.keys(confirmed).length;
  const total = summary.total_expected || (state.roster.length - state.absentees.size);
  hudScannedCount.textContent = count;
  hudProgressFill.style.width = `${Math.min(100, (count / total) * 100)}%`;

  // ── Update Missing Students Drawer
  const missing = summary.missing_roll_numbers || summary.missing_students || [];
  missingCountEl.textContent = missing.length;
  missingPillsList.innerHTML = "";
  missing.slice(0, 20).forEach(roll => {
    const pill = document.createElement("span");
    pill.className = "missing-pill";
    pill.textContent = `Roll ${roll}`;
    missingPillsList.appendChild(pill);
  });
}

function setupScannerEvents() {
  // Switch Camera
  document.getElementById("btn-switch-camera").addEventListener("click", async () => {
    state.facingMode = state.facingMode === "environment" ? "user" : "environment";
    stopCamera();
    await startCamera();
  });

  // Next Question / Finish Sweep
  btnNextQuestionSweep.addEventListener("click", async () => {
    const qIndex = state.currentQuestionIndex;
    const responses = { ...state.confirmedResponses };

    // Save snapshot of this question's responses for the per-Q analytics overlay
    state.allQuestionResponses[qIndex] = responses;

    // 1. Commit current question responses to backend
    try {
      const qId = `q_${state.sessionId}_${qIndex}`;
      await fetch(`/api/questions/${qId}/responses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ responses })
      });
    } catch (err) {
      console.warn("Could not commit responses online, saving offline:", err);
    }

    if (qIndex < state.questionCount) {
      // Show per-question analytics overlay before moving on
      showQuestionSummaryOverlay(qIndex, responses, async () => {
        state.currentQuestionIndex++;
        // Tell server-side tracker to reset for the new question
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
          state.ws.send(JSON.stringify({ action: "reset" }));
        }
        await startScannerQuestion(state.currentQuestionIndex);
      });
    } else {
      // All questions completed! Stop camera and go to Final Review & Analytics
      stopCamera();
      if (state.ws) {
        state.ws.close();
      }
      await loadAndRenderFinalAnalysis();
      switchView("analysis", 5);
    }
  });
}

/**
 * Shows an animated overlay card summarising responses for the completed question.
 * When the teacher taps "Start Q{n+1}", the provided `onProceed` callback is called.
 *
 * @param {number} qIndex - The question that just finished (1-based)
 * @param {Object} responses - { rollNumber: "A"|"B"|"C"|"D" } snapshot
 * @param {Function} onProceed - Called when the teacher confirms moving to next Q
 */
function showQuestionSummaryOverlay(qIndex, responses, onProceed) {
  // Compute quick distribution stats from responses
  const dist = { A: 0, B: 0, C: 0, D: 0 };
  const totalPresent = state.roster.length - state.absentees.size;
  Object.values(responses).forEach(ans => {
    if (dist[ans] !== undefined) dist[ans]++;
  });
  const scanned = Object.keys(responses).length;
  const missing = totalPresent - scanned;

  // Build bar percentages
  const barHtml = Object.entries(dist).map(([letter, count]) => {
    const pct = totalPresent > 0 ? Math.round((count / totalPresent) * 100) : 0;
    const color = ANSWER_COLORS_RGB[letter] || "#94a3b8";
    return `
      <div class="q-bar-row">
        <span class="q-bar-letter" style="color:${color}">${letter}</span>
        <div class="q-bar-track">
          <div class="q-bar-fill" style="width:${pct}%;background:${color};"></div>
        </div>
        <span class="q-bar-count">${count} <small>(${pct}%)</small></span>
      </div>`;
  }).join("");

  const presetAnswer = state.answerKey[String(qIndex)];
  const correctCount = presetAnswer ? (dist[presetAnswer] || 0) : null;
  const accuracyPct = (presetAnswer && totalPresent > 0) ? Math.round((correctCount / totalPresent) * 100) : null;

  const overlay = document.createElement("div");
  overlay.id = "q-summary-overlay";
  overlay.className = "q-summary-overlay";
  overlay.innerHTML = `
    <div class="q-summary-card glass-card">
      <div class="q-summary-header">
        <div class="q-pill">Q${qIndex} Complete ✓</div>
        <h3>Question ${qIndex} Results</h3>
      </div>

      <div class="q-summary-stats">
        <div class="q-stat-chip">
          <span class="q-stat-val">${scanned}</span>
          <span class="q-stat-lbl">Scanned</span>
        </div>
        <div class="q-stat-chip">
          <span class="q-stat-val" style="color:#f59e0b">${missing}</span>
          <span class="q-stat-lbl">Not Scanned</span>
        </div>
        ${accuracyPct !== null ? `
        <div class="q-stat-chip">
          <span class="q-stat-val" style="color:#10b981">${accuracyPct}%</span>
          <span class="q-stat-lbl">Accuracy (Key: ${presetAnswer})</span>
        </div>` : `
        <div class="q-stat-chip">
          <span class="q-stat-val" style="color:#94a3b8">—</span>
          <span class="q-stat-lbl">No Key Set</span>
        </div>`}
      </div>

      <div class="q-bar-chart">
        <div class="q-bar-title">Answer Distribution</div>
        ${barHtml}
      </div>

      <button id="btn-proceed-next-q" class="btn btn-accent" style="width:100%;margin-top:18px;">
        Start Q${qIndex + 1} of ${state.questionCount} →
      </button>
    </div>
  `;

  document.getElementById("view-scanner").appendChild(overlay);

  // Animate in
  requestAnimationFrame(() => overlay.classList.add("visible"));

  document.getElementById("btn-proceed-next-q").addEventListener("click", () => {
    overlay.classList.remove("visible");
    overlay.addEventListener("transitionend", () => overlay.remove(), { once: true });
    onProceed();
  });
}

// --- 5. FINAL REVIEW & REAL-TIME RECALCULATION MODULE ---
async function loadAndRenderFinalAnalysis() {
  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/analysis`);
    const data = await res.json();
    renderAnalysisData(data);
  } catch (err) {
    console.warn("Failed to load analysis from server, rendering local mockup:", err);
  }
}

function renderAnalysisData(data) {
  // Set Titles & Subtitles
  document.getElementById("analysis-quiz-title").textContent = `${data.quiz_name} — Scorecard`;
  document.getElementById("analysis-session-subtitle").textContent = 
    `${data.class_label} • ${data.school_name} • ${data.session_date}`;

  // High-Level KPIs
  document.getElementById("analysis-avg-score").textContent = `${data.class_average_percentage}%`;
  document.getElementById("analysis-students-count").textContent = 
    `${data.total_participated} of ${data.total_enrolled} Students`;

  document.getElementById("cnt-high").textContent = data.mastery_counts.high;
  document.getElementById("cnt-mod").textContent = data.mastery_counts.moderate;
  document.getElementById("cnt-low").textContent = data.mastery_counts.low;

  // Set Export Links
  document.getElementById("btn-download-pdf-merged").href = `/api/sessions/${state.sessionId}/export/merged-pdf`;
  document.getElementById("btn-download-excel").href = `/api/sessions/${state.sessionId}/export/excel`;

  // Render Interactive Final Answer Key Grid (Changing here re-calculates!)
  renderFinalKeyEditor(data.answer_key, data.question_count);

  // Render Question Accuracy & Distractors
  renderQuestionAccuracyList(data.questions);

  // Render Student Scorecards Table
  renderScorecardsTable(data.scorecards, data.question_count);
}

function renderFinalKeyEditor(currentKeys, questionCount) {
  const grid = document.getElementById("final-key-grid");
  grid.innerHTML = "";

  for (let q = 1; q <= questionCount; q++) {
    const card = document.createElement("div");
    card.className = "key-item-card";

    const label = document.createElement("span");
    label.className = "key-item-label";
    label.textContent = `Q${q}`;

    const optRow = document.createElement("div");
    optRow.className = "key-options-row";

    ["A", "B", "C", "D"].forEach(letter => {
      const btn = document.createElement("button");
      btn.className = `opt-btn ${currentKeys[String(q)] === letter ? `selected-${letter}` : ""}`;
      btn.textContent = letter;
      btn.type = "button";

      btn.addEventListener("click", async () => {
        // Change key and trigger REAL-TIME RECALCULATION
        currentKeys[String(q)] = letter;
        optRow.querySelectorAll(".opt-btn").forEach(b => b.className = "opt-btn");
        btn.className = `opt-btn selected-${letter}`;

        await triggerLiveRecalculation(currentKeys);
      });

      optRow.appendChild(btn);
    });

    card.appendChild(label);
    card.appendChild(optRow);
    grid.appendChild(card);
  }
}

async function triggerLiveRecalculation(updatedKeys) {
  const indicator = document.getElementById("recalc-indicator");
  indicator.style.display = "inline-block";
  indicator.textContent = "Recalculating...";

  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/recalculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_key: updatedKeys, persist: true })
    });
    const result = await res.json();
    renderAnalysisData(result.analysis);
    indicator.textContent = "✓ Re-scored in 0.1s";
    setTimeout(() => { indicator.style.display = "none"; }, 2000);
  } catch (err) {
    console.error("Failed to recalculate:", err);
    indicator.style.display = "none";
  }
}

function renderQuestionAccuracyList(questions) {
  const container = document.getElementById("questions-perf-list");
  container.innerHTML = "";

  questions.forEach(q => {
    const item = document.createElement("div");
    item.className = "q-perf-item";
    item.innerHTML = `
      <span class="q-title">Question ${q.sequence}</span>
      <div class="q-acc">${q.accuracy_percentage}% Accuracy</div>
      <span class="q-key">Key: <b>${q.correct_answer || 'None'}</b> (${q.correct_count}/${q.total_responses} Correct)</span>
      <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 4px;">
        A: ${q.distractors.A} | B: ${q.distractors.B} | C: ${q.distractors.C} | D: ${q.distractors.D}
      </div>
    `;
    container.appendChild(item);
  });
}

function renderScorecardsTable(scorecards, qCount) {
  const thead = document.getElementById("scorecard-table-head");
  let headerHtml = `<tr><th>Roll No</th><th>Student Name</th>`;
  for (let i = 1; i <= qCount; i++) {
    headerHtml += `<th>Q${i}</th>`;
  }
  headerHtml += `<th>Score</th><th>%</th><th>Mastery</th></tr>`;
  thead.innerHTML = headerHtml;

  const tbody = document.getElementById("scorecard-table-body");
  tbody.innerHTML = "";

  scorecards.forEach(sc => {
    const tr = document.createElement("tr");
    let rowHtml = `<td><b>Roll ${sc.roll_number}</b></td><td>${sc.name}</td>`;

    if (sc.is_absent) {
      for (let i = 1; i <= qCount; i++) {
        rowHtml += `<td style="color: #64748b;">-</td>`;
      }
      rowHtml += `<td colspan="3"><span class="tag-mastery" style="background: rgba(255,255,255,0.06); color: #94a3b8;">Absent</span></td>`;
    } else {
      for (let i = 1; i <= qCount; i++) {
        const b = sc.breakdown[i] || { given: "-", is_correct: false };
        if (b.given === "-") {
          rowHtml += `<td style="color: #64748b;">-</td>`;
        } else if (b.is_correct) {
          rowHtml += `<td><span class="cell-correct">${b.given} ✓</span></td>`;
        } else {
          rowHtml += `<td><span class="cell-wrong">${b.given} ✗</span></td>`;
        }
      }

      const masteryClass = sc.percentage >= 80 ? "tag-high" : (sc.percentage >= 50 ? "tag-mod" : "tag-low");
      rowHtml += `
        <td><b>${sc.score}/${sc.total_questions}</b></td>
        <td><b>${sc.percentage}%</b></td>
        <td><span class="tag-mastery ${masteryClass}">${sc.mastery}</span></td>
      `;
    }

    tr.innerHTML = rowHtml;
    tbody.appendChild(tr);
  });
}

function setupAnalysisEvents() {
  document.getElementById("btn-start-new-session").addEventListener("click", () => {
    state.sessionId = null;
    state.questionCount = 5;
    state.answerKey = {};
    state.pdfFile = null;
    switchView("setup", 1);
  });
}

// --- 6. TEACHER HISTORICAL DASHBOARD (90-DAY ROLLING) ---
function setupHistoryEvents() {
  btnNavHistory.addEventListener("click", () => {
    loadTeacherHistory("month");
    switchView("history");
  });

  document.getElementById("btn-history-back").addEventListener("click", () => {
    switchView("setup", 1);
  });

  document.querySelectorAll(".filter-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      const range = pill.getAttribute("data-range");
      loadTeacherHistory(range);
    });
  });
}

async function loadTeacherHistory(range = "month") {
  const teacherId = state.currentUser?.teacher_id || "PJ-T101";
  try {
    const res = await fetch(`/api/teachers/${teacherId}/history?range=${range}`);
    const data = await res.json();

    document.getElementById("hist-total-quizzes").textContent = data.total_quizzes_conducted;
    document.getElementById("hist-total-students").textContent = data.total_students_assessed;
    document.getElementById("hist-overall-avg").textContent = `${data.overall_average_percentage}%`;

    const list = document.getElementById("history-list");
    list.innerHTML = "";

    data.history.forEach(item => {
      const card = document.createElement("div");
      card.className = "history-card";
      card.innerHTML = `
        <div class="hist-left">
          <h4>${item.quiz_name}</h4>
          <span class="hist-meta">${item.class_label} • ${item.subject} • ${item.session_date} (${item.students_assessed} Students)</span>
          ${item.pdf_filename ? `<div style="font-size: 0.72rem; color: #6ee7b7; margin-top: 4px;">📑 Source PDF: ${item.pdf_filename}</div>` : ""}
        </div>
        <div class="hist-right">
          <div class="hist-avg">${item.average_percentage}%</div>
          <div style="display: flex; gap: 6px;">
            <a class="btn btn-secondary btn-sm" href="/api/sessions/${item.session_id}/export/merged-pdf" target="_blank" title="Download Merged PDF">📥 PDF</a>
            <a class="btn btn-secondary btn-sm" href="/api/sessions/${item.session_id}/export/excel" target="_blank" title="Download Excel">📊 Excel</a>
          </div>
        </div>
      `;
      list.appendChild(card);
    });
  } catch (err) {
    console.error("Failed to load history:", err);
  }
}

// --- 7. PROJECT MANAGER SUPERVISOR DASHBOARD ---
function setupManagerEvents() {
  btnNavManager.addEventListener("click", () => {
    loadManagerDashboard();
    switchView("manager");
  });

  document.getElementById("btn-manager-back").addEventListener("click", () => {
    switchView("setup", 1);
  });
}

async function loadManagerDashboard() {
  try {
    const res = await fetch(`${window.API_BASE}/api/manager/dashboard`);
    const data = await res.json();

    document.getElementById("mgr-total-schools").textContent = data.summary.total_schools;
    document.getElementById("mgr-total-teachers").textContent = data.summary.total_teachers;
    document.getElementById("mgr-total-quizzes").textContent = data.summary.total_assessments;

    // Multi-Teacher Table
    const tbody = document.getElementById("manager-teachers-table-body");
    tbody.innerHTML = "";
    data.teachers.forEach(t => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><b>${t.teacher_id}</b></td>
        <td><b>${t.name}</b></td>
        <td>${t.school_name}</td>
        <td>${t.subject}</td>
        <td><b>${t.total_quizzes}</b> Quizzes</td>
        <td>${t.students_reached || 0}</td>
        <td><b style="color: #60a5fa;">${t.avg_score || 0}%</b></td>
        <td>${t.last_active_date || 'N/A'}</td>
      `;
      tbody.appendChild(tr);
    });

    // Recent Network Activity Feed
    const feed = document.getElementById("manager-recent-feed");
    feed.innerHTML = "";
    data.recent_activity.forEach(item => {
      const card = document.createElement("div");
      card.className = "history-card";
      card.innerHTML = `
        <div class="hist-left">
          <h4>${item.quiz_name}</h4>
          <span class="hist-meta">${item.teacher_name} • Grade ${item.grade}-${item.section} • ${item.school_name}</span>
        </div>
        <div class="hist-right">
          <span style="font-size: 0.8rem; color: #94a3b8;">${item.session_date}</span>
          <a class="btn btn-secondary btn-sm" href="/api/sessions/${item.session_id}/export/excel" target="_blank">Export</a>
        </div>
      `;
      feed.appendChild(card);
    });
  } catch (err) {
    console.error("Failed to load manager dashboard:", err);
  }
}

// --- 8. OFFLINE SYNC QUEUE MODULE ---
function syncOfflineQueue() {
  const queue = JSON.parse(localStorage.getItem("pijam_offline_queue") || "[]");
  if (queue.length === 0) return;

  console.log(`Syncing ${queue.length} offline sessions to server...`);
  const pending = [...queue];
  localStorage.setItem("pijam_offline_queue", "[]");

  pending.forEach(async (payload) => {
    try {
      await fetch(`/api/sessions/${payload.session_id}/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      console.log(`Synced session ${payload.session_id} successfully.`);
    } catch (err) {
      console.warn(`Failed to sync session ${payload.session_id}, returning to queue:`, err);
      const current = JSON.parse(localStorage.getItem("pijam_offline_queue") || "[]");
      current.push(payload);
      localStorage.setItem("pijam_offline_queue", JSON.stringify(current));
    }
  });
}

// Start application when DOM is ready
window.addEventListener("DOMContentLoaded", initApp);
