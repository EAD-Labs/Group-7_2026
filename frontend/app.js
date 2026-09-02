// State Management
const state = {
  schoolId: null,
  classId: null,
  className: "Class 7A",
  sessionId: null,
  questionId: null,
  questionNumber: 1,
  totalQuestions: 5,
  roster: [],             // [{roll_number, name}]
  absentees: new Set(),   // Set of roll numbers marked absent
  answerKey: { "1": "A", "2": "B", "3": "C", "4": "D", "5": "A" },
  confirmedResponses: {}, // {roll_number: "A"|"B"|"C"|"D"}
  facingMode: "environment",
  ws: null,
  isScanning: false,
  stream: null,
  hasCompletedChimed: false,
};

// Colors matching card edges (BGR in OpenCV -> RGB for Canvas)
const ANSWER_COLORS_RGB = {
  "A": "#e74c3c", // Red
  "B": "#f1c40f", // Yellow
  "C": "#3498db", // Blue
  "D": "#2ecc71", // Green
  "AMBIGUOUS": "#f39c12"
};

// DOM Elements
const views = {
  classSelect: document.getElementById("view-class-select"),
  attendance: document.getElementById("view-attendance"),
  scanner: document.getElementById("view-scanner"),
  summary: document.getElementById("view-summary"),
  analysis: document.getElementById("view-analysis"),
};

const schoolSelect = document.getElementById("school-select");
const classSelect = document.getElementById("class-select");
const btnStartSetup = document.getElementById("btn-start-setup");
const btnBackToClass = document.getElementById("btn-back-to-class");
const btnBeginAssessment = document.getElementById("btn-begin-assessment");
const rosterGrid = document.getElementById("roster-grid");
const presentCountEl = document.getElementById("present-count");
const totalCountEl = document.getElementById("total-count");

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
const anomalyToast = document.getElementById("anomaly-toast");

const btnLockPoll = document.getElementById("btn-lock-poll");
const btnSwitchCamera = document.getElementById("btn-switch-camera");
const btnNextQuestion = document.getElementById("btn-next-question");
const btnFinishEarly = document.getElementById("btn-finish-early");
const btnStartNewSession = document.getElementById("btn-start-new-session");
const btnRecalculateScores = document.getElementById("btn-recalculate-scores");

const sessionBadge = document.getElementById("session-badge");
const activeClassLabel = document.getElementById("active-class-label");

// --- View Router ---
function switchView(viewName) {
  Object.values(views).forEach(v => {
    if (v) v.classList.remove("active");
  });
  if (views[viewName]) {
    views[viewName].classList.add("active");
  }
}

// --- Initialize App ---
async function init() {
  try {
    const res = await fetch("/api/schools");
    const schools = await res.json();
    schoolSelect.innerHTML = '<option value="">-- Choose School --</option>';
    schools.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.school_id;
      opt.textContent = `${s.name} (${s.school_code})`;
      schoolSelect.appendChild(opt);
    });

    if (schools.length > 0) {
      schoolSelect.value = schools[0].school_id;
      await onSchoolChange();
    }
  } catch (err) {
    console.error("Failed to load schools:", err);
  }
}

async function onSchoolChange() {
  const schoolId = schoolSelect.value;
  if (!schoolId) {
    classSelect.disabled = true;
    classSelect.innerHTML = '<option value="">Select a school first</option>';
    btnStartSetup.disabled = true;
    return;
  }

  try {
    const res = await fetch(`/api/schools/${schoolId}/classes`);
    const classes = await res.json();
    classSelect.innerHTML = '<option value="">-- Choose Class --</option>';
    classes.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.class_id;
      opt.textContent = `Grade ${c.grade}-${c.section} (${c.academic_year})`;
      classSelect.appendChild(opt);
    });
    classSelect.disabled = false;

    if (classes.length > 0) {
      classSelect.value = classes[0].class_id;
      state.classId = classes[0].class_id;
      state.className = `Grade ${classes[0].grade}-${classes[0].section}`;
      btnStartSetup.disabled = false;
    }
  } catch (err) {
    console.error("Failed to load classes:", err);
  }
}

schoolSelect.addEventListener("change", onSchoolChange);
classSelect.addEventListener("change", () => {
  state.classId = classSelect.value;
  const selectedText = classSelect.options[classSelect.selectedIndex]?.text;
  state.className = selectedText || "Class";
  btnStartSetup.disabled = !state.classId;
});

// --- Attendance View ---
btnStartSetup.addEventListener("click", async () => {
  if (!state.classId) return;

  try {
    const res = await fetch(`/api/classes/${state.classId}/roster`);
    const data = await res.json();
    state.roster = data.students || [];

    renderAttendanceRoster();
    activeClassLabel.textContent = state.className;
    sessionBadge.style.display = "flex";
    switchView("attendance");
  } catch (err) {
    console.error("Failed to load roster:", err);
    alert("Could not load class roster. Check network.");
  }
});

btnBackToClass.addEventListener("click", () => {
  switchView("classSelect");
});

function renderAttendanceRoster() {
  rosterGrid.innerHTML = "";
  state.absentees.clear();

  state.roster.forEach(s => {
    const chip = document.createElement("div");
    chip.className = "student-chip";
    chip.id = `chip-roll-${s.roll_number}`;
    chip.innerHTML = `
      <span class="roll">${s.roll_number}</span>
      <span class="status-tag">Present</span>
    `;

    chip.addEventListener("click", () => {
      if (state.absentees.has(s.roll_number)) {
        state.absentees.delete(s.roll_number);
        chip.classList.remove("absent");
        chip.querySelector(".status-tag").textContent = "Present";
      } else {
        state.absentees.add(s.roll_number);
        chip.classList.add("absent");
        chip.querySelector(".status-tag").textContent = "Absent";
      }
      updateAttendanceCounters();
    });

    rosterGrid.appendChild(chip);
  });

  updateAttendanceCounters();
}

function updateAttendanceCounters() {
  const total = state.roster.length;
  const present = total - state.absentees.size;
  presentCountEl.textContent = present;
  totalCountEl.textContent = total;
}

// --- Start Live Assessment Session ---
btnBeginAssessment.addEventListener("click", async () => {
  try {
    // 1. Create Session
    const sessRes = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_id: state.classId }),
    });
    const sessData = await sessRes.json();
    state.sessionId = sessData.session_id;

    // 2. Submit Absentees
    await fetch(`/api/sessions/${state.sessionId}/absentees`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ absentees: Array.from(state.absentees) }),
    });

    // 3. Read & Save Answer Key
    for (let i = 1; i <= 5; i++) {
      const el = document.getElementById(`key-setup-${i}`);
      if (el) state.answerKey[String(i)] = el.value;
    }
    await fetch(`/api/sessions/${state.sessionId}/answer_key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_key: state.answerKey }),
    });

    // 4. Start Question 1 of 5
    state.questionNumber = 1;
    await startQuestion(state.questionNumber);

    // 5. Open Scanner View & Start Camera
    switchView("scanner");
    await startCamera();
    connectWebSocket();
  } catch (err) {
    console.error("Failed to start session:", err);
    alert("Error initializing assessment session.");
  }
});

async function startQuestion(seq) {
  const correct = state.answerKey[String(seq)] || "A";
  const res = await fetch(`/api/sessions/${state.sessionId}/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sequence_number: seq, prompt_text: `Question ${seq}`, correct_answer: correct }),
  });
  const data = await res.json();
  state.questionId = data.question_id;
  hudQuestionLabel.textContent = `Question ${seq} of ${state.totalQuestions}`;
  state.confirmedResponses = {};
}

// --- Camera & WebSocket Streaming ---
async function startCamera() {
  if (state.stream) {
    state.stream.getTracks().forEach(t => t.stop());
  }

  const constraints = {
    video: {
      facingMode: { ideal: state.facingMode },
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
    audio: false,
  };

  try {
    state.stream = await navigator.mediaDevices.getUserMedia(constraints);
    cameraFeed.srcObject = state.stream;

    cameraFeed.onloadedmetadata = () => {
      arCanvas.width = cameraFeed.videoWidth;
      arCanvas.height = cameraFeed.videoHeight;
      state.isScanning = true;
      requestAnimationFrame(captureAndSendLoop);
    };
  } catch (err) {
    console.error("Camera access error:", err);
    alert("Could not access camera. Please allow camera permissions.");
  }
}

btnSwitchCamera.addEventListener("click", async () => {
  state.facingMode = state.facingMode === "environment" ? "user" : "environment";
  await startCamera();
});

// Capture frame canvas (offscreen)
const offscreenCanvas = document.createElement("canvas");
const offscreenCtx = offscreenCanvas.getContext("2d", { willReadFrequently: true });

let lastFrameSentTime = 0;
const FRAME_INTERVAL_MS = 90; // ~11 FPS

function captureAndSendLoop(timestamp) {
  if (!state.isScanning) return;

  if (timestamp - lastFrameSentTime >= FRAME_INTERVAL_MS) {
    if (cameraFeed.readyState === cameraFeed.HAVE_ENOUGH_DATA && state.ws && state.ws.readyState === WebSocket.OPEN) {
      offscreenCanvas.width = cameraFeed.videoWidth || 640;
      offscreenCanvas.height = cameraFeed.videoHeight || 480;
      offscreenCtx.drawImage(cameraFeed, 0, 0, offscreenCanvas.width, offscreenCanvas.height);

      offscreenCanvas.toBlob(blob => {
        if (blob && state.ws && state.ws.readyState === WebSocket.OPEN) {
          state.ws.send(blob);
          lastFrameSentTime = timestamp;
        }
      }, "image/jpeg", 0.75);
    }
  }

  requestAnimationFrame(captureAndSendLoop);
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/api/ws/scan/${state.sessionId}`;

  state.ws = new WebSocket(wsUrl);

  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "DETECTIONS") {
        renderDetections(msg.cards, msg.is_blurry);
        updateHUD(msg.summary);
      }
    } catch (e) {
      console.error("WS Parse error:", e);
    }
  };

  state.ws.onerror = (err) => {
    console.warn("WebSocket error:", err);
  };
}

// --- Augmented Reality Canvas Overlay Rendering ---
function renderDetections(cards, isBlurry) {
  if (arCanvas.width !== cameraFeed.videoWidth || arCanvas.height !== cameraFeed.videoHeight) {
    arCanvas.width = cameraFeed.videoWidth;
    arCanvas.height = cameraFeed.videoHeight;
  }

  ctx.clearRect(0, 0, arCanvas.width, arCanvas.height);

  blurWarning.style.display = isBlurry ? "block" : "none";

  if (!cards || cards.length === 0) return;

  cards.forEach(c => {
    const pts = c.corners;
    const ans = c.answer;
    const cid = c.card_id;
    const strokeColor = ANSWER_COLORS_RGB[ans] || "#10b981";

    // 1. Draw glowing marker boundary polygon
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i][0], pts[i][1]);
    }
    ctx.closePath();

    ctx.lineWidth = 4;
    ctx.strokeStyle = strokeColor;
    ctx.shadowColor = strokeColor;
    ctx.shadowBlur = 10;
    ctx.stroke();

    // 2. Draw label badge above the top-left corner
    const label = `Roll ${cid}: [${ans}]`;
    const bx = pts[0][0];
    const by = Math.max(pts[0][1] - 14, 28);

    ctx.font = "bold 18px Outfit, sans-serif";
    const textWidth = ctx.measureText(label).width;

    ctx.fillStyle = "rgba(15, 20, 28, 0.85)";
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(bx - 8, by - 22, textWidth + 16, 28, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = strokeColor;
    ctx.shadowBlur = 0;
    ctx.fillText(label, bx, by - 2);

    ctx.restore();
  });
}

// --- Update Live HUD ---
function updateHUD(summary) {
  if (!summary) return;

  hudScannedCount.textContent = summary.scanned_count;
  hudExpectedCount.textContent = summary.total_expected;
  hudProgressFill.style.width = `${summary.percentage}%`;

  missingCountEl.textContent = summary.missing_roll_numbers.length;
  missingPillsList.innerHTML = "";

  summary.missing_roll_numbers.forEach(r => {
    const chip = document.createElement("span");
    chip.className = "missing-chip";
    chip.textContent = `#${r}`;
    missingPillsList.appendChild(chip);
  });

  if (summary.anomalies && summary.anomalies.length > 0) {
    const latest = summary.anomalies[summary.anomalies.length - 1];
    anomalyToast.textContent = `⚠️ ${latest.message}`;
    anomalyToast.style.display = "block";
    clearTimeout(anomalyToast.timeoutId);
    anomalyToast.timeoutId = setTimeout(() => {
      anomalyToast.style.display = "none";
    }, 2500);
  }

  if (summary.is_complete && !state.hasCompletedChimed) {
    state.hasCompletedChimed = true;
    if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
  }

  state.confirmedResponses = summary.confirmed_responses || {};
}

// --- Lock Poll & Commit Question ---
btnLockPoll.addEventListener("click", async () => {
  if (!state.questionId) return;

  state.isScanning = false;
  if (state.ws) {
    state.ws.close();
  }

  try {
    await fetch(`/api/questions/${state.questionId}/responses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ responses: state.confirmedResponses }),
    });

    renderSummaryView();
    switchView("summary");
  } catch (err) {
    console.error("Failed to commit responses:", err);
    renderSummaryView();
    switchView("summary");
  }
});

// --- Render Single Question Summary ---
function renderSummaryView() {
  const counts = { "A": 0, "B": 0, "C": 0, "D": 0 };
  const responsesGrid = document.getElementById("summary-responses-grid");
  responsesGrid.innerHTML = "";

  Object.entries(state.confirmedResponses).forEach(([roll, ans]) => {
    if (counts[ans] !== undefined) counts[ans]++;

    const item = document.createElement("div");
    item.className = "response-card-mini";
    item.innerHTML = `
      <span class="roll">Roll ${roll}</span>
      <span class="ans-badge ans-${ans}">${ans}</span>
    `;
    responsesGrid.appendChild(item);
  });

  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  ["A", "B", "C", "D"].forEach(letter => {
    const val = counts[letter];
    const pct = total > 0 ? (val / total * 100).toFixed(0) : 0;
    const bar = document.getElementById(`bar-${letter}`);
    const valEl = document.getElementById(`val-${letter}`);

    bar.style.height = `${Math.max(pct, 12)}%`;
    valEl.textContent = val;
  });

  const correctAns = state.answerKey[String(state.questionNumber)] || "A";
  document.getElementById("summary-key-letter").textContent = correctAns;
  document.getElementById("summary-question-title").textContent = 
    `Question ${state.questionNumber} of ${state.totalQuestions} Completed!`;
  document.getElementById("summary-session-info").textContent = 
    `${total} of ${state.roster.length - state.absentees.size} students responded.`;

  // Button handling for 5-question limit
  if (state.questionNumber < state.totalQuestions) {
    btnNextQuestion.textContent = `Proceed to Question ${state.questionNumber + 1} of ${state.totalQuestions} →`;
    btnFinishEarly.style.display = "block";
  } else {
    btnNextQuestion.textContent = `Finish Assessment & View Final Analysis 🎯 →`;
    btnFinishEarly.style.display = "none";
  }
}

// Handle Proceed / Finish on Question Summary
btnNextQuestion.addEventListener("click", async () => {
  if (state.questionNumber < state.totalQuestions) {
    state.questionNumber += 1;
    state.hasCompletedChimed = false;

    await startQuestion(state.questionNumber);
    switchView("scanner");
    await startCamera();
    connectWebSocket();
  } else {
    // 5th Question reached! Finish assessment & view analysis
    await loadAndRenderAnalysis();
  }
});

btnFinishEarly.addEventListener("click", async () => {
  await loadAndRenderAnalysis();
});

// --- Final Analysis Dashboard ---
async function loadAndRenderAnalysis() {
  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/analysis`);
    const data = await res.json();
    renderAnalysisView(data);
    switchView("analysis");
  } catch (err) {
    console.error("Failed to load analysis:", err);
    alert("Could not load analysis report.");
  }
}

function renderAnalysisView(data) {
  document.getElementById("analysis-session-subtitle").textContent = 
    `${state.className} • ${data.total_participated} of ${data.total_expected} Students Assessed`;

  document.getElementById("analysis-avg-score").textContent = `${data.class_average_percentage}%`;
  document.getElementById("analysis-students-count").textContent = data.total_participated;

  document.getElementById("cnt-high").textContent = data.mastery_counts.high;
  document.getElementById("cnt-mod").textContent = data.mastery_counts.moderate;
  document.getElementById("cnt-low").textContent = data.mastery_counts.low;

  // Set values in Answer Key editor
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`key-edit-${i}`);
    if (el && data.answer_key[String(i)]) {
      el.value = data.answer_key[String(i)];
    }
  }

  // Question-by-Question list
  const qList = document.getElementById("questions-perf-list");
  qList.innerHTML = "";
  data.questions.forEach(q => {
    const item = document.createElement("div");
    item.className = "q-perf-item";
    item.innerHTML = `
      <span class="q-title">Q${q.sequence}</span>
      <div class="q-acc">${q.accuracy_percentage}%</div>
      <span class="q-key">Key: <b>${q.correct_answer || 'N/A'}</b> (${q.total_responses} votes)</span>
    `;
    qList.appendChild(item);
  });

  // Scorecards table
  const tbody = document.getElementById("scorecard-table-body");
  tbody.innerHTML = "";
  data.scorecards.forEach(sc => {
    const tr = document.createElement("tr");

    let cellsHtml = `<td><b>Roll ${sc.roll_number}</b></td>`;
    for (let i = 1; i <= 5; i++) {
      const b = sc.breakdown[i] || { given: "-", is_correct: false };
      if (b.given === "-") {
        cellsHtml += `<td class="cell-unanswered">-</td>`;
      } else if (b.is_correct) {
        cellsHtml += `<td><span class="cell-correct">${b.given} ✓</span></td>`;
      } else {
        cellsHtml += `<td><span class="cell-wrong">${b.given} ✗</span></td>`;
      }
    }

    const masteryClass = sc.percentage >= 80 ? "tag-high" : (sc.percentage >= 40 ? "tag-mod" : "tag-low");
    cellsHtml += `
      <td><b>${sc.score}/${sc.total_questions}</b> (${sc.percentage}%)</td>
      <td><span class="tag-mastery ${masteryClass}">${sc.mastery}</span></td>
    `;

    tr.innerHTML = cellsHtml;
    tbody.appendChild(tr);
  });
}

// Recalculate Scores from Analysis View
btnRecalculateScores.addEventListener("click", async () => {
  const updatedKey = {};
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`key-edit-${i}`);
    if (el) updatedKey[String(i)] = el.value;
  }

  try {
    await fetch(`/api/sessions/${state.sessionId}/answer_key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_key: updatedKey }),
    });
    state.answerKey = updatedKey;
    await loadAndRenderAnalysis();
  } catch (err) {
    console.error("Failed to update answer key:", err);
  }
});

// Start New Assessment
btnStartNewSession.addEventListener("click", () => {
  state.sessionId = null;
  state.questionId = null;
  state.questionNumber = 1;
  switchView("classSelect");
});

// Start initialization on page load
window.addEventListener("DOMContentLoaded", init);
