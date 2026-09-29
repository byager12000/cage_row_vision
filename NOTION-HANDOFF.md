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

## 2026-09-28: Home bench set up (not yet written to Notion)

- Bench: Stopmotion Explosion HD Pro 1080p (DirectShow index 2) over a dark wood table. Markers are
  on untrimmed letter pages, in a rectangle Ben measured with a tape as 30 × 20 in (diagonals
  about 36 in). Squares are 3 in; the test sheet is US letter. `layout_confirmed: true`.
- An exposure sweep chose −5. Auto exposure clipped 29% of pixels; −4 and brighter clipped 42% and
  lost marker 0.
- Bench check, 20 live frames: calibration valid 20/20. A sheet at about 45° measured
  X 15.475, Y 9.844 in, angle −44.47°, 10.924 × 8.511 in. Frame noise 0.001 in and 0.007°.
- Open item: the markers read about 1% small (2.95–2.99 in) and the sheet about 0.08 in short on
  its 11 in side. The tape layout is probably slightly small or out of square. It can be refined
  later from saved frames.
- Fixes: auto exposure is no longer switched off without a manual value. White page areas
  touching a marker are now ignored. Commands use `python -m` because of Smart App Control.
