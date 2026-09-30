# Jag 75 position test, run 2 (2026-09-30 ~14:38–14:51)

**Run:** `runs/20260930-143818_belt_test` (not tracked). This folder holds the `target.json` that the run used, plus
JPEG copies of trial frames 1, 4, 5, 9 and 10.

**Setup:** after the camera was re-aimed, the baseline was re-recorded and the reference was taught in a blue-tape
box drawn around the cage. The reference centre is (24.69, 14.16) in. Marker 3 sits 18 px from the top edge of
the picture, and the overlay now warns about it.

## What happened

- 10 of 14 moves were recorded. **All 10 IN/OUT calls were correct.**
- The program then crashed. The traceback went to the launcher console, which was waiting on "press any key", so
  the operator's next Space press closed it and the error was lost. Trials were only written at the end, so no
  summary was saved.

## Re-measured from the saved frames

The frames were re-measured with the tape handling of the time ("subtract") and with the new default ("recolor").

| Move | Intended | subtract | recolor (new default) |
|---|---|---|---|
| Right ¼ / ⅜ / ⅝ / 1 in | 0.25 / 0.375 / 0.625 / 1.0 | 0.21 / 0.25 / 0.36 / 0.47 in, with a fake −0.5° to −5° twist | **0.22 / 0.35 / 0.63 / 1.01 in**, twist ≤ 0.4° |
| Away ¼ / ⅜ / ⅝ / 1 in | 0.25 / 0.375 / 0.625 / 1.0 | 0.28 / 0.37 / **−0.65 / −0.73** in (fit 0.42–0.45) | 0.32 / 0.46 / 0.75 / 1.12 in (fit ≤ 0.08) |

- **Right slides.** The "pivoting" reported earlier was the side strips of the tape box bending the outline. With
  recolor, the slides come out straight and within 0.03 in.
- **Away ⅝ and 1 in.** The far end of the cage slid over the top strip of the tape box. Blue seen *through* the
  plastic was cut out, which split the cage region, and the match slid the wrong way. The calls happened to be
  right. Recolor paints tape belt-white before edge detection, so the cage walls stay intact.
- **Still open.** With recolor, the away moves read 0.07–0.12 in long, growing with distance. That is either how
  the moves were set, or a small scale difference front-to-back. The next run will tell.

## Fixes (committed with this note)

- `cage.tape_mode: recolor` is the new default. Tape is painted belt-white before edges are found; `subtract` is
  still available.
- The live loop is guarded per frame. Errors go to `errors.txt` in the run folder and the session continues.
  `compare()` returns OUT, instead of crashing, when no rigid fit exists within ±30°.
- `trials.csv`, `summary.md`, `target.json` and `protocol.json` are written after every move and every teach.
- The launcher console stays open after the test ends (`cmd /k`), so keypresses cannot close it and hide an error.
- Outlines with zero area are skipped (a divide-by-zero guard).
- An overlay warning appears when a marker tag is within 40 px of the picture edge.
- The reference was re-taught with recolor from this run's trial-1 frame, so the location is unchanged (within
  0.04 in).
- New regression tests from these frames: tape under the cage, and a no-fit reading OUT without crashing.
