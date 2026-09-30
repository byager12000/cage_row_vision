# P0 home bench: evidence summary (2026-09-28)

**Bench**
- Camera: Stopmotion Explosion HD Pro 1080p, DirectShow index 2, 1920×1080 YUY2 (about 4.4 fps), exposure locked at −5.
  The lens is about 34¼ in above the table and about 7° from vertical.
- Surface: dark wood table. Lighting was ordinary room lighting only, with no dedicated lights. Recorded as seen, not controlled.
- Markers: ArUco `DICT_4X4_50` IDs 0–3, 3 in squares, printed from `markers/markers.pdf`, on untrimmed letter pages.
  Centres at (0,0), (30,0), (30,20), (0,20) in, measured by tape. 0 is bottom-left and 1 is bottom-right as seen standing at the table.
- Test target: a plain US letter sheet (nominal 11 × 8.5 in). It isn't perfectly flat and has some weave.

**Run `home1`** (`measurements.csv`, `report.md/json`, sample annotated frames)
- 25/25 placements detected, at angles −81° to +82°. Sheet centres covered X 9.1–20.8 in and Y 4.8–13.5 in.
  That is the central region; the untrimmed marker pages limit how close the sheet can get to the corners.
- 244/250 frames valid. The 6 invalid frames are the last 1–3 frames of placements 10–12, where marker 0 wasn't found.
  The likely cause is the operator's hand reaching in, but that's unverified because failed frames weren't saved then.
  Failed frames are saved now. Invalid frames carried no values.
- Frame-to-frame noise, with the sheet untouched over a burst of about 2 s: at most 0.002 in in X, 0.003 in in Y, and
  0.012° (sample std). This is jitter, not re-placement repeatability.
- Size consistency: the short side reads 8.490–8.515 in. The long side reads 0.036–0.059 in short (10.941–10.964 in)
  at every orientation. An independent review ruled out detector, lens and layout causes for that pattern.
  It belongs to the sheet: its length, width or flatness. With the sheet width taken as 8.500 in, the implied length
  is 10.945 in.
- Scale check against printed references: the 6 in bars on the M2/M3 marker pages measure 5.991 and 6.014 in
  through the calibration.
- Absolute position accuracy against an independent ground truth was **not** measured.

**Silent-failure check** (`marker_bump_check.json`, from `scripts/verify_marker_bump.py`)
- The independent review found that a bumped or mis-entered marker gave VALID results with errors up to 0.3–0.6 in.
  The old ±25% marker-size gate could not see it.
- Fix: the setup baseline (`baseline.json`). A marker that moves relative to the others by more than 1 px, after
  removing camera motion, invalidates every frame. Normal bench noise is ≤0.35 px, even with about 3 px of camera wobble.
- Real-frame emulation over 400 cases per size: bumps of about 0.14 in (6 px) or more are always caught. The worst
  position error from any bump that was not caught is **0.056 in**, under half of Ben's ±⅛ in tolerance.
- A marker position edited in the config after the baseline was taken is also rejected.

**Ben's stated tolerance (2026-09-28)**
- Position within about ±⅛ in and angle within about ±1°. ¼–½ in overall would also be acceptable.
- The end goal is to confirm four cages are present, pushed together, square to the conveyor and inside a box.
