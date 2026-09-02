# Marker Design Generation — Algorithm & Requirements

> Context: read `PRD.md` and `DESIGN.md` first. This document specifies how to generate the **45 unique marker designs** referenced throughout this project.

## 1. Important framing note

This project needs a fiducial-marker system: small printed patterns that a camera can (a) detect the presence and boundary of, (b) decode to one of N unique IDs, and (c) determine the rotational orientation of (which edge is "up"). This is a **well-established, generic computer-vision problem** with open, non-proprietary solutions (e.g., the ArUco marker library and AprilTag are widely used open-source fiducial marker systems built on exactly this kind of grid-based binary pattern + rotation-decoding approach). **Do not copy Plickers' specific visual design or specific patented decode method** — implement using the generic, well-known approach described below, which predates and is independent of any single company's product. (See `PRD.md` §0 for the IP context on why this distinction matters.)

## 2. Requirements for the marker set

1. **45 unique designs**, fixed for the programme's lifetime (barring a rare, deliberate full regeneration — see `DESIGN.md` §5.4).
2. Each design must be **unambiguously distinguishable from every other design**, even under moderate image noise/blur/lighting variation.
3. Each design must be **unambiguously decodable to exactly one of 4 rotational orientations** (0°/90°/180°/270°) — i.e., no design may look identical (or too similar) to itself when rotated, since orientation IS the answer signal (A/B/C/D).
4. The pattern must be simple enough to print reliably at small size on cheap paper/printers and still decode correctly from a phone camera at typical classroom distances.

## 3. The General Algorithm (grid-based binary marker generation)

This is the standard approach used by open fiducial marker systems (e.g., ArUco-style generation):

### Step 1 — Define the grid
- Choose a square grid of `n × n` cells (a common choice is 5×5 or 6×6 internal data cells, surrounded by a solid black border ring for fast localization in-frame). Larger `n` gives more possible unique codes but makes each cell smaller and harder to resolve at a distance/low resolution — for a pool of only 45 designs, a small grid (5×5 = 25 data bits, or even smaller) is more than sufficient and will be far more robust to print/camera limitations than a larger grid.
- Each interior cell is binary: black or white (this keeps printing and camera thresholding simple and robust — avoid grayscale/multi-level cells, which are more error-prone under variable lighting).
- Surround the data grid with a solid black border (a full ring of black cells) — this is what the CV localization step (Design doc §3.1, stage 2) uses to quickly find "there is a marker here" in a frame, before attempting to decode the interior bits.

### Step 2 — Enumerate candidate bit patterns
- For an `n × n` interior grid, there are `2^(n×n)` raw possible bit patterns. Generate this full candidate space (or a large random sample of it, if `n` is large enough that full enumeration is impractical).

### Step 3 — Discard rotationally self-similar patterns
- For each candidate pattern, compute its bit pattern under all 4 rotations (0°/90°/180°/270°).
- **Any pattern that is identical to itself under a 90°, 180°, or 270° rotation must be discarded** — the whole point of these markers is that rotation encodes the answer, so a pattern that can't distinguish its own rotations is useless (the CV system would have no way to tell "card facing up" from "card facing right").
- Additionally, **each surviving pattern's 4 rotations should be treated as belonging to the same "marker family"** — you don't want two different marker_ids in your final set of 45 to be rotations of each other, since then a card just held at a different angle could be misidentified as a completely different student's card. Deduplicate: keep only one representative bit pattern per rotation-family.

### Step 4 — Maximize inter-marker distance
- Among the surviving, deduplicated candidate patterns, you likely have far more than 45 to choose from (even a modest 5×5 grid yields thousands of valid rotation-safe candidates). Don't pick the first 45 — **select the 45 that are maximally different from each other**, measured by Hamming distance (number of differing bits) between every pair of candidates, across all 4 rotations of each.
- This is the standard technique used by open marker-generation libraries: greedily or iteratively build the set by starting with one pattern, then repeatedly adding whichever remaining candidate maximizes the *minimum* Hamming distance to every pattern already in the set (a max-min selection). This directly maximizes robustness — the larger the minimum distance between any two markers in your final set of 45, the more bit-errors (from print defects, blur, poor lighting) the system can tolerate before confusing one marker for another.
- A reasonable target: don't stop at "45 patterns that happen to be different" — explicitly check and report the *minimum pairwise Hamming distance* across your final chosen set of 45, so you know your system's real error tolerance before printing anything.

### Step 5 — Assign marker_id 1–45 and colour/letter labels
- Assign each of the 45 final patterns a `marker_id` (1–45) — this is the human-readable card number printed on the card and referenced throughout `DESIGN.md`'s data model.
- Each card gets the same fixed A/B/C/D + Yellow/Green/Blue/Magenta edge labelling described in `PRD.md` §7 — this labelling is **identical across all 45 designs** (every card has A=one specific edge orientation with Yellow, etc. — consistent across the whole set), only the interior marker pattern differs between designs. Do not vary the letter/colour assignment per design; that would need to be tracked per-card and adds needless complexity for zero benefit.

### Step 6 — Store the definitive pattern set
- Persist the final 45 chosen bit patterns (and their canonical 0° orientation) as static reference data — this is the `pattern_definition` field on `MarkerDesign` in `DESIGN.md` §2.1. This set, once finalized and printed, must not silently change (see `DESIGN.md` §5.4 on versioning).

## 4. Decode-side logic (mirrors generation logic)

Given a localized marker region in a camera frame:
1. Extract the grid of cells from the localized region (perspective-correct if the card is viewed at an angle).
2. Read the binary value of each interior cell (black/white via adaptive thresholding, robust to uneven lighting).
3. Compare the read bit pattern against all 4 rotations of all 45 known reference patterns from Step 6 above.
4. The best match (lowest Hamming distance) identifies both **which marker_id** it is AND **which rotation** matched — that rotation directly gives you the orientation (and therefore the A/B/C/D answer, combined with the fixed letter/colour labelling from Step 5).
5. If the best match's Hamming distance is above some acceptable error threshold (i.e., no confident match), treat as unreadable — do not force a low-confidence match (this feeds into `DESIGN.md` §5.3's anomaly-handling checklist: "card detected, orientation ambiguous → treat as unreadable").
6. Cross-check against the independent colour-edge classification (`DESIGN.md` §3.1 stage 4) — if pattern-decode and colour-decode disagree on orientation, also treat as unreadable/flag for rescan rather than trusting either signal alone.

## 5. Practical implementation notes

- There is no need to hand-design these 45 patterns manually — this is a mechanical generate-and-select process (Steps 1–4) that should be scripted once, offline, before any card is printed. Treat this as a one-time build tool/script, not part of the live app.
- Suggested starting grid size: 5×5 interior cells (25 bits) is very likely more than sufficient for 45 well-separated, rotation-safe designs with a comfortable minimum Hamming distance — this keeps each cell as large as possible on a small printed card, which helps camera decode reliability at classroom scanning distances. Only increase grid size if the Step 4 distance-maximization result on a 5×5 grid turns out too weak (i.e., minimum pairwise distance too small for reliable real-world decoding) — verify this with the actual selection script before committing.
- Test the finalized 45-pattern set against real printed samples and real camera captures (per `DESIGN.md` §5.2) before finalizing — synthetic/simulated confidence in the pattern set is not a substitute for testing actual print+camera round-trip decode accuracy.
