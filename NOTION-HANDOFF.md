# Notion handoff log

## 2026-09-26: P0 Paper Detection Bench Prototype

**Read from Notion:**

- Human SOP (STK-5)
- AI Operating Procedure (STK-8)
- AI Dev Environment & Tooling (STK-4)
- STK-14 project page
- Work Queue item *P0 — Paper Detection Bench Prototype* (Ready for Claude, Physical PLC Action Allowed = No)

**Written to Notion:**

- Work item Handoff Status set to Claude Working, then Blocked (physical run only)
- Claude Report and Artifact / File filled in

**Assumptions** (all configurable in `config.yaml`, all flagged by `layout_confirmed: false`):

- Units: inches.
- Origin at the marker 0 center, +X toward marker 1, +Y toward marker 3.
- Placeholder marker centers: (0,0), (35,0), (35,25), (0,25). The printed marker size is a 3.0 in placeholder,
  sized for Ben's planned ~40 × 30 in camera field. This was changed on 2026-09-26 from 30×20 with 2 in markers.
- Placeholder paper: 11 × 8.5 in (US Letter), light paper on a darker table.
- ArUco `DICT_4X4_50`, IDs 0–3.

None of these values are claimed to be real. Ben measures them.

**Blocker:** no USB webcam or overhead bench exists yet. The laptop has only its Surface front/IR cameras,
so the 20–30 placement physical repeatability run can't be done. The software and the synthetic
closed loop are complete.

## 2026-09-28: Home bench set up

- Bench: Stopmotion Explosion HD Pro 1080p (DirectShow index 2) over a dark wood table. Markers are
  on untrimmed letter pages, in a rectangle Ben measured with a tape as 30 × 20 in (diagonals
  about 36 in). Squares are 3 in; the test sheet is US letter. `layout_confirmed: true`.
- An exposure sweep chose −5. Auto exposure clipped 29% of pixels; −4 and brighter clipped 42% and
  lost marker 0.
- Bench check, 20 live frames: calibration valid 20/20. A sheet at about 45° measured
  X 15.475, Y 9.844 in, angle −44.47°, 10.924 × 8.511 in. Frame noise 0.001 in and 0.007°.
- (Superseded by the home1 analysis below.) The first bench check suggested the tape layout might
  be small. The independent review of home1 ruled that out: the shortfall belongs to the sheet.
- Fixes: auto exposure is no longer switched off without a manual value. White page areas
  touching a marker are now ignored. Commands use `python -m` because of Smart App Control.

## 2026-09-28: home1 run, independent review, baseline fix, cage exploration

- home1: 25 placements, all detected; 244/250 frames valid. Details are in `evidence/p0-home-bench/SUMMARY.md`.
- An independent 3-lens review (stats, code, acceptance) confirmed the noise and "no stale values" claims.
  It sharpened the size-bias wording: the shortfall is a property of the sheet, and the isotropic scale is
  tied to the sheet width. It found one high-severity issue: a bumped or mis-entered marker produced VALID
  results with 0.3–0.6 in error.
- Fixed with the setup baseline (`baseline.json`, `set-baseline`). Real-frame emulation shows the worst
  undetected bump error is 0.056 in. Other fixes from the review:
  - marker size gate ±5% and paper size gate ±0.25 in
  - per-marker sizes and marker movement logged per frame
  - failed frames saved as images
  - `run_info.json` written per run
  - the report retitled as frame noise, with partial placements flagged
  - live console summarises the whole burst
- Ben's tolerance: ±⅛ in and ±1° is good; ¼–½ in overall is acceptable.
- Phase 2 exploration with one real cage: `evidence/p2-cage-exploration/NOTES.md`.
- Written to Notion: the P0 work item report, artifact paths and status. The STK-14 Critical Questions
  field has Ben's answers appended.

## 2026-09-29 to 09-30: cage position tools, corrections, warehouse white belt

- Ben's tape on the Jag 75: bottom 11.25 × 7.00 in, height 5 in. This **corrects** the earlier vision estimate
  of the floor (10.66 in, about ½ in taper, about 1 in top gap). Actual taper is about 0.18 in per side, so the top
  gap between touching inverted cages is about 0.36 in. Corrected in `evidence/p2-cage-exploration/NOTES.md`
  and in Notion.
- Ben's scope statement: the system must tell whether a cage is at the requested position within ±½ in in any
  direction.
- Added `camera_model.py`, `cage.py`, `cage_live.py` (teach target, guided moves, IN/OUT by worst footprint
  corner), `cage-check`, camera auto-search (Windows renumbered the webcam), and tests.
- Warehouse bench: white belt on the floor (⅜ in), markers on the floor at 45⅛ × 30 in, camera 48⅛ in above the
  belt, tags printed at 97% (2.91 in). Colour (saturation) segmentation plus a 3-D rim/bottom model fit measured
  the bottom as 11.21 × 6.95 in, against the tape's 11.25 × 7.00. That method is in the exploration script; it is
  not yet in `cage.py`.
- Pending: Ben's STL export of `allentown_jag75_cage_bottom.prt`; the warehouse config and baseline; the position
  test on the belt.
