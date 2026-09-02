# Computer Vision Model & Pipeline Specification

> **Document Status:** Complete Technical Specification  
> **Target System:** Web-Based Classroom Marker-Card Scanner  
> **Related Documents:** [`PRD.md`](file:///c:/Users/Hitansh/ET617/docs/PRD.md), [`DESIGN.md`](file:///c:/Users/Hitansh/ET617/docs/DESIGN.md), [`MARKER_GENERATION.md`](file:///c:/Users/Hitansh/ET617/docs/MARKER_GENERATION.md), [`ARCHITECTURE.md`](file:///c:/Users/Hitansh/ET617/docs/ARCHITECTURE.md), [`IMPLEMENTATION.md`](file:///c:/Users/Hitansh/ET617/docs/IMPLEMENTATION.md)

---

## 1. Computer Vision Pipeline Overview

The computer vision subsystem is a **real-time, multi-stage hybrid pipeline** that runs on each incoming video frame. It is designed to operate with sub-50ms latency on standard commodity mobile and laptop web browsers.

```
                    ┌──────────────────────────────────────┐
                    │       Raw Video Frame (RGB / YUV)    │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: Pre-Processing & Luminance Normalization                           │
│ • Direct Y-plane extraction (or RGB -> Grayscale conversion)                │
│ • Motion blur detection via Laplacian variance: Var(∇²I)                    │
│ • Contrast-Limited Adaptive Histogram Equalization (CLAHE) for dim rooms    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: Multi-Scale Candidate Polygon Localization                         │
│ • Sliding-window local adaptive thresholding: T(x, y) = Mean(N(x, y)) - C   │
│ • Border contour tracking & Douglas-Peucker polygon approximation           │
│ • Strict 4-corner convex quadrilateral validation                           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: Sub-Pixel Corner Refinement & Homography Rectification              │
│ • Corner sub-pixel localization using spatial gradient dot-products         │
│ • Quadrilateral perspective homography warp: H · [x, y, 1]ᵀ -> Canonical Box │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: Fiducial Bitgrid Decoding (ArUco 5x5 Dictionary)                   │
│ • 5x5 data cell binary sampling (Otsu local binarization per cell)          │
│ • 4-rotation Hamming distance evaluation against 45 canonical patterns      │
│ • Rejection thresholding (Min Hamming distance ≤ Max allowable error bits)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: Dual-Cue Orientation & Answer Resolution                           │
│ • Primary Cue: Coordinate geometry of 4 marker edge midpoints               │
│ • Secondary Cue: HSV Color Band classification of the uppermost edge        │
│ • Deadband filter for diagonal holds (Ambiguity Rejection)                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 6: Temporal Aggregation & Multi-Frame Smoothing                       │
│ • Frame-to-frame de-bouncing (Requires ≥ 3 stable frames)                   │
│ • Sliding time-window tracking per Card ID (Handles vote changes)           │
│ • Output: Confirmed Cards, Missing Roster List, Anomalies                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Stage-by-Stage Technical & Mathematical Details

### Stage 1: Pre-Processing & Motion Blur Filter
1. **Luminance Extraction:**
   When reading from mobile camera hardware (via WebRTC / CameraX), frames stream in YUV color space (`YUV_420_888`). The $Y$ channel contains the exact physical luminance. Bypassing RGB conversion and processing the $Y$ channel directly reduces memory copy overhead by 66%.
2. **Motion Blur Estimation (Laplacian Variance):**
   When a teacher pans the camera too rapidly, edge contrast blurs. We compute the variance of the 2D Laplacian operator over the grayscale frame $I$:
   $$\nabla^2 I = \frac{\partial^2 I}{\partial x^2} + \frac{\partial^2 I}{\partial y^2}$$
   $$\text{Blur Metric } \mathcal{B} = \text{Var}(\nabla^2 I) = \frac{1}{WH} \sum_{x,y} \left( \nabla^2 I(x, y) - \mu_{\nabla^2} \right)^2$$
   - If $\mathcal{B} < \tau_{\text{blur}}$ (empirically set to $85.0$): The frame is flagged as blurry, discarded from the state machine, and the teacher HUD displays *"Sweep slower"*.

---

### Stage 2: Adaptive Thresholding & Marker Localization
Standard global thresholding (e.g. Otsu) fails in real classrooms due to cast shadows from window light or desks. The pipeline uses **Local Adaptive Thresholding**:
$$T(x, y) = \frac{1}{W_s^2} \sum_{u, v \in N(x, y)} I(u, v) - C$$
To ensure small cards in the back row (occupying only $40\times40$ pixels) are detected alongside large cards in the front row ($300\times300$ pixels), the threshold window size $W_s$ slides across multiple scales:
- `adaptiveThreshWinSizeMin` = 3
- `adaptiveThreshWinSizeMax` = 23
- `adaptiveThreshWinSizeStep` = 10
- `adaptiveThreshConstant` ($C$) = 7

Contour boundaries are extracted and simplified using the **Ramer-Douglas-Peucker (RDP)** polygon approximation. A candidate region is retained only if:
1. It has exactly **4 vertices** (convex quadrilateral).
2. Its perimeter ratio relative to the total image size satisfies:
   $$\text{minMarkerPerimeterRate} \le \frac{\text{Perimeter}}{2(W + H)} \le \text{maxMarkerPerimeterRate}$$
   We configure $\text{minMarkerPerimeterRate} = 0.015$ (enables detection down to 1.5% of the frame dimension).

---

### Stage 3: Sub-Pixel Corner Refinement & Homography
To accurately decode markers viewed at oblique angles, corner positions $(x_i, y_i)$ are refined to sub-pixel floating-point precision:
$$\nabla I(p_i) \cdot (q - p_i) = 0 \quad \forall q \in N(p_i)$$
Using OpenCV's `CORNER_REFINE_SUBPIX`, corner coordinates achieve $\pm 0.1$ pixel precision.

The 4 refined corners $c_0, c_1, c_2, c_3$ are mapped to a canonical square grid using a $3\times3$ homography matrix $H$:
$$\begin{bmatrix} x' \\ y' \\ 1 \end{bmatrix} \sim H \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}$$
$$H = \text{findHomography}(\{c_0, c_1, c_2, c_3\}, \{(0,0), (S,0), (S,S), (0,S)\})$$
The interior image is warped via `warpPerspective` to obtain an un-distorted $7\times7$ cell patch (1 border ring + $5\times5$ data grid).

---

### Stage 4: Fiducial Bitgrid Decoding (ArUco 5x5)
The canonical ArUco $5\times5$ dictionary contains predefined binary matrix patterns designed with high inter-marker Hamming distance:
1. The $7\times7$ grid is sampled at the center of each cell:
   - Outer ring ($1\text{ cell}$ border): Must be predominantly **black** (0).
   - Interior ($5\times5$ cells): 25 binary bits ($b_0, b_1, \dots, b_{24}$).
2. The sampled 25-bit word $B$ is tested against all 4 cyclic rotations ($R_0, R_{90}, R_{180}, R_{270}$) for all 45 registered card patterns:
   $$\mathcal{D}_{\text{Hamming}}(B, P_k) = \sum_{j=0}^{24} b_j \oplus p_{k, j}$$
3. The pattern $k$ and rotation $r$ with the minimum Hamming distance are selected:
   $$(k^*, r^*) = \arg\min_{k \in \{1..45\}, r \in \{0, 90, 180, 270\}} \mathcal{D}_{\text{Hamming}}(R_r(B), P_k)$$
4. **Error Rejection Threshold:** If $\min \mathcal{D}_{\text{Hamming}} > \tau_{\text{error}}$ (set to $1\text{ bit}$ for $5\times5$ grid), the detection is classified as noise and rejected.

---

### Stage 5: Dual-Cue Orientation & Answer Resolution

```
                             Card Layout (Upright)
                        ┌──────────────────────────────┐
                        │        TOP EDGE: [A]         │
                        │    (Red / Yellow Band)       │
                        ├───────┬──────────────┬───────┤
                        │       │ c0        c1 │       │
                        │ LEFT  │   ArUco 5x5  │ RIGHT │
                        │  [D]  │    Marker    │  [B]  │
                        │(Green)│ c3        c2 │(Yellow│
                        ├───────┴──────────────┴───────┤
                        │       BOTTOM EDGE: [C]       │
                        │         (Blue Band)          │
                        └──────────────────────────────┘
```

#### 1. Primary Cue: Coordinate Geometry
In screen space, image coordinate $y$ begins at 0 at the top and increases downward.
The 4 edges of the physical card correspond to the marker's 4 sides:
- **Edge A (Top):** Midpoint $M_A = \frac{c_0 + c_1}{2}$
- **Edge B (Right):** Midpoint $M_B = \frac{c_1 + c_2}{2}$
- **Edge C (Bottom):** Midpoint $M_C = \frac{c_2 + c_3}{2}$
- **Edge D (Left):** Midpoint $M_D = \frac{c_3 + c_0}{2}$

The card edge pointing toward the ceiling is the one with the lowest vertical coordinate:
$$\text{Candidate Answer} = \arg\min_{E \in \{A, B, C, D\}} \left( y(M_E) \right)$$

#### 2. Ambiguity & Deadband Filter (Edge Case E-03)
If a student holds the card diagonally at $\sim 45^\circ$, the two uppermost midpoints will have nearly identical $y$ coordinates:
Let $y_{(1)}$ be the lowest $y$, and $y_{(2)}$ be the second lowest $y$.
$$\Delta y = y_{(2)} - y_{(1)}$$
- If $\Delta y < 0.15 \times \text{MarkerHeight}$:
  **Status: `AMBIGUOUS`.** The model rejects the classification and instructs the state machine to hold until the student straightens the card.

#### 3. Secondary Cue: HSV Color Band Verification
To verify the answer under heavy perspective or sensor noise:
1. We project an exterior sampling region centered at $M_{\text{candidate}}$ just outside the marker border:
   $$P_{\text{sample}} = M_{\text{candidate}} + \vec{n}_{\text{outward}} \cdot d_{\text{band}}$$
2. The $15\times15$ pixel patch at $P_{\text{sample}}$ is transformed to **HSV** (Hue, Saturation, Value).
3. The median Hue $H \in [0^\circ, 360^\circ)$ and Saturation $S \in [0, 1]$ are evaluated:

| Expected Answer | Target Color | Expected Hue Range |
|---|---|---|
| **A** | Red / Orange | $H \in [345^\circ, 360^\circ] \cup [0^\circ, 25^\circ]$ |
| **B** | Yellow | $H \in [35^\circ, 85^\circ]$ |
| **C** | Blue | $H \in [190^\circ, 260^\circ]$ |
| **D** | Green | $H \in [90^\circ, 160^\circ]$ |

If $S > 0.30$ (colored band confirmed) and the observed Hue matches the target range, confidence is scored as **$1.0$ (Dual Verified)**. If pattern and color conflict, the detection is quarantined as `AMBIGUOUS`.

---

### Stage 6: Temporal Aggregation & Debouncing

```
Raw Frame Detections  ──► [ Sliding Window Buffer (5 Frames) ]
                                      │
                                      ▼
                            [ Stability Evaluator ]
                 Did Card ID #i show same answer for ≥ 3 frames?
                                      │
                         ┌────────────┴────────────┐
                        YES                        NO
                         │                         │
                         ▼                         ▼
               [ CONFIRMED STATE ]         [ PENDING STATE ]
               Emit to Session Tracker     Wait for next frame
```

1. **State Persistence:**
   Each card ID maintains a state tuple:
   $$S_i = \left( \text{status: } \{\text{MISSING, PENDING, CONFIRMED}\}, \text{ answer: } A/B/C/D, \text{ confidence: } [0, 1], \text{ last\_seen: } t \right)$$
2. **Answer Transitions (Vote Changes):**
   If a student rotates their card from A to C:
   - Frame 1: C detected $\rightarrow$ Counter for C = 1 (State remains A).
   - Frame 2: C detected $\rightarrow$ Counter for C = 2 (State remains A).
   - Frame 3: C detected $\rightarrow$ Counter for C = 3 $\rightarrow$ **State shifts to C.**
   - UI triggers an audible chime / visual flash to indicate updated response.

---

## 3. Tuned Hyperparameters Reference

| Parameter Name | Target Function | Tuned Value | Rationale |
|---|---|---|---|
| `adaptiveThreshWinSizeMin` | Low-contrast edge search | `3` | Picks up fine edges of distant markers. |
| `adaptiveThreshWinSizeMax` | Broad gradient search | `23` | Adapts to large cards close to camera. |
| `adaptiveThreshWinSizeStep` | Threshold multi-scale step | `10` | Balances speed (2 scales) vs robustness. |
| `adaptiveThreshConstant` | Noise suppression offset | `7.0` | Prevents camera sensor noise from creating false contours. |
| `minMarkerPerimeterRate` | Detection distance limit | `0.015` | Enables card detection at 6–8 meters (~40px card size). |
| `maxMarkerPerimeterRate` | Close-up card limit | `4.0` | Allows cards occupying up to 80% of frame. |
| `cornerRefinementMethod` | Angular precision | `CORNER_REFINE_SUBPIX` | Eliminates rotational jitter on tilted cards. |
| `maxErroneousBitsInBorderRate` | Finger occlusion handling | `0.35` | Tolerates thumbs partially covering the outer black ring. |
| `deadbandThresholdRate` | Diagonal hold rejection | `0.15` | Rejects ambiguous $45^\circ$ holds. |
| `temporalDebounceFrames` | Temporal smoothing | `3` | Prevents single-frame flicker from recording incorrect votes. |
