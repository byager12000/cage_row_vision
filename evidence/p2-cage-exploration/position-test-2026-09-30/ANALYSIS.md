# Jag 75 position test on the warehouse belt (2026-09-30), analysis

**Run:** `runs/20260930-135545_jag75_pos`. This folder has its `summary.md`, `trials.csv`, `target.json`,
`run_info.json`, plus JPEG copies of the raw trial frames.

**Setup:** the Jag 75 was upright on the white belt, with its long side running away from the operator. The target
was taught with **T**; there were 14 guided moves, each measured by hand with a tape. The reference marks were
blue painter's tape laid **against** the cage.

## As run: 10/14 IN/OUT calls correct, all 4 misses were false OUTs

| Cause | Effect | How we know |
|---|---|---|
| Blue tape touching the cage | The tape was swallowed into the cage outline, which bent the outline and the fit (0.07–0.21 in rms) | The overlays show the outline bulging over the tape. With the tape erased or rejected, the fit is 0.024–0.046 in |
| Start of the "away" series | All four away moves read about +0.30 in beyond intended | Successive away steps measured +0.15 / +0.23 / +0.36 in against +⅛ / +¼ / +⅜ intended (within 0.02–0.03 in). Only the series start was off, probably because the gap was taken to the curved bottom edge versus the wall (the CAD shows the wall bulging about ½ in beyond the belt contact) |
| Twist instructions | Written for a cage lying left-right. With the long side away from the operator, "right end" was ambiguous | The actual twists were about 5.8° and 7.6°, which moves the corners 0.9–1.2 in, so OUT was the correct call |

## Re-measured from the saved frames, with tape rejection (re-taught from trial 1)

| Trial | Intended | Measured | Worst point | Call |
|---|---|---|---|---|
| 2: right ¼ | +0.25, 0 | +0.29, +0.02, +0.2° | 0.31 | IN ✓ |
| 3: right ⅜ | +0.375, 0 | +0.42, +0.06, **−1.0°** | 0.53 | OUT: the cage also turned 1°, so the worst corner really moved more than ½ in |
| 4: right ⅝ | +0.625, 0 | +0.53, +0.08, −0.6° | 0.60 | OUT ✓ |
| 5: right 1 | +1.0, 0 | +0.93, +0.08, −0.5° | 0.98 | OUT ✓ |
| 6: back | 0 | −0.07, +0.05, −0.8° | 0.17 | IN ✓ |
| 7–10: away | +¼ … +1 | +0.55 … +1.29 | — | constant +0.30 start offset (see above) |
| 11: back | 0 | +0.04, −0.02, +1.1° | 0.17 | IN ✓ |
| 14: back | 0 | — | — | refused: marker 0 partly covered (read 2.76 in against 2.91). Correct |

**Conclusion.** Hand-set moves are measured to about 0.04–0.09 in, which includes how precisely the cage was placed
by hand. Consecutive steps are measured to 0.02–0.03 in. At no point did an out-of-position cage read IN.

## Changes made after this run

- **Tape rejection** (`cage.ignore_color`, on by default). Strong blue/green pixels (hue 35–135, saturation > 80) are
  removed from a cage region *after* its wall loop is filled, so the loop is never cut open.
- **Guided moves built from the taught outline** (`outline_live.build_protocol`). Slides still use world directions but
  say "measure the gap at BOTH ends of that side". Twists pivot on the near-left corner and move the near-right
  corner away. The size is chosen so the worst outline point is clearly IN (≤ 0.35 in) or clearly OUT (≥ 0.7 in)
  for however the cage lies. The protocol used is saved to `protocol.json` in each run.
- **Regression tests** use the frames in this folder (`tests/test_outline.py`).

## For the next run

- Measure each move against a fixed straightedge at **both ends** of the side, to the **same point** on the cage
  each time.
- Keep tape at least 1 in off the cage if you can. It is rejected now, but clean is better.
- Keep hands and feet off the marker tags until the console prints the result.
