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
- Placeholder marker centers: (0,0), (30,0), (30,20), (0,20). The printed marker size is a 2.0 in placeholder.
- Placeholder paper: 11 × 8.5 in (US Letter), light paper on a darker table.
- ArUco `DICT_4X4_50`, IDs 0–3.

None of these values are claimed to be real. Ben measures them.

**Blocker:** no USB webcam or overhead bench exists yet. The laptop has only its Surface front/IR cameras,
so the 20–30 placement physical repeatability run can't be done. The software and the synthetic
closed loop are complete.
