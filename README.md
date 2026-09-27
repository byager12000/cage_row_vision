# Cage Row Vision — Phase 1 (STK-14 / P0)

Python + OpenCV bench prototype. A fixed overhead webcam sees four ArUco reference markers
and a rectangular sheet of paper. For every frame the app reports `Object_Detected`,
`Center_X`, `Center_Y`, `Rotation_Deg`, the measured length/width, and a diagnostic overlay.

Stack page: STK-14 *Cage Row Vision Alignment & Count* → Work Queue item
*P0 — Paper Detection Bench Prototype*.

**Scope:** Phase 1 only. No cages, conveyor, PLC, or machine action.

## Status (2026-09-26)

| Part | State |
|---|---|
| Software (calibration, detection, geometry, overlay, logging, report) | Done, 31 tests pass |
| Closed loop on synthetic images with exact ground truth | Done, see `evidence/p0-synthetic/` |
| Physical bench repeatability run (20–30 placements) | **Blocked**: no USB webcam or bench yet (the laptop only has its Surface front/IR cameras) |

## Commands (run in this folder)

```
uv run pytest -q                                  # tests
uv run cage-vision list-cameras                   # which camera index is the webcam
uv run cage-vision make-markers                   # markers\marker_0..3.svg, print at 100%
uv run cage-vision live --label bench1            # live view + repeatability capture
uv run cage-vision images <folder>                # process saved images (manifest.json optional)
uv run cage-vision synth <folder> [--k1 -0.1]     # generate synthetic test scenes with ground truth
uv run cage-vision report runs\<run>              # recompute the report for a run
```

A fresh shell may need `$env:Path = "C:\Users\byage\.local\bin;" + $env:Path` first.

## How it works

1. **Calibrate (every frame):** detect ArUco markers IDs 0–3 (`DICT_4X4_50`). Build a homography
   from their image centers to the measured world positions in `config.yaml`. A plausibility
   check requires each marker's size, measured through that homography, to match the printed size.
   A wrong position entry or a bumped marker fails this check.
2. **Segment:** Otsu threshold inside the quadrilateral through the marker centers, with the markers
   masked out. The threshold also needs at least 30 grey levels of contrast, otherwise it reports
   "no object".
3. **Find the rectangle:** keep contours at least 25% of the nominal paper area that simplify to a
   convex 4-gon. Reject any contour that touches the edge of the calibrated area.
4. **Sub-pixel edges:** sample 60 intensity profiles across each side. Each edge point sits at that
   profile's own 50% crossing between paper and table levels, so it doesn't depend on the global
   threshold and tolerates uneven lighting. Fit a robust line per side and intersect the lines to get
   the corners.
5. **World geometry:** map the corners to world units. Center = diagonal intersection. Angle = long
   axis vs world +X, CCW positive, folded into [-90°, +90°) because a rectangle is 180° symmetric.
   Measured L×W must be within `size_tolerance` of nominal, and rectangularity must be ≥ 0.92.
6. **Exactly one candidate must pass.** Zero candidates gives "not detected". Two or more gives
   "ambiguous".

### Failure behaviour: no stale or fake values

The pipeline is stateless. Each frame is calibrated and measured from scratch. On any failure, X, Y,
angle, L and W are `None` (blank in the CSV, `---` on screen), the border and status turn red, and the
reason is shown. The failure causes are:

- a missing or duplicated marker
- an implausible marker size
- no contrasting object
- an object that isn't 4-sided (for example, overlapping a marker)
- an object that touches the area edge
- an object that isn't rectangular
- an object of the wrong size
- more than one candidate

Tests cover each case, including a good frame followed by bad frames.

## Synthetic closed-loop results

The scenes are rendered with random perspective, blur, noise, a lighting gradient and JPEG
compression. The scale is about 37 camera px/in, over a 30×20 in marker area at 1920×1080.
Each run has 25 placements × 3–5 frames, plus 4 negative cases.

| Case | Radial position error (max) | Angle error (max) | Size error (max) | Frame noise X/Y std | Negatives rejected |
|---|---|---|---|---|---|
| Ideal lens | 0.008 in | 0.011° | 0.003 in | < 0.001 in | 4/4 |
| Barrel distortion k1 = −0.10 (cheap webcam) | 0.061 in | 0.085° | 0.12 in | < 0.001 in | 4/4 |

**What this means:** the measurement math is sound and unbiased. The limiting factor on a real
bench will be the lens, not the algorithm. Even uncorrected distortion stays within the provisional
±1/8 in and ±0.5° target. If the physical run shows position error growing toward the edges of the
field, the next step is a one-time lens calibration (chessboard → `cv2.undistort`). It isn't built
yet because P0 doesn't need it to meet the target.

**What it does not show:** real webcam noise, auto-exposure drift, real lighting, paper curl, or a
table surface with texture or glare. Only the physical run can characterize those.

## Bench setup: what Ben needs to provide or measure

1. **Webcam:** a 1080p-class USB webcam, rigidly mounted overhead. Run `list-cameras` and set
   `camera.index`.
2. **Markers:** run `make-markers` and print the four SVGs at 100% / Actual size. **Measure the
   printed black square** and enter it as `markers.size`, because printers scale. Tape the markers
   flat around the work area. They must not move after you measure them.
3. **Marker positions:** measure the world coordinates of each marker **center** (the tick marks point
   to it) and enter them in `markers.positions`. The default convention is marker 0 = origin,
   +X toward marker 1, +Y toward marker 3.
4. **Paper:** measure the real sheet and enter `paper.length` and `paper.width`. Use a light sheet on a
   darker table (or set `polarity: dark` for the reverse).
5. **Lighting:** diffused LED, no glare on the paper. Once it's settled, set `camera.exposure` so
   exposure is locked. The `live` command prints what the camera actually accepted.
6. Set `layout_confirmed: true`. Until you do, the overlay shows a warning on every frame.

## Repeatability procedure (physical)

`uv run cage-vision live --label bench1`, then for each of 20–30 placements:

1. Move the paper to a new random position and angle, fully inside the markers.
2. Take your hands out of view and press **Space**. The app records `frames_per_placement` frames
   (default 10) of the stationary paper.

Press **Q** to finish. `runs\<stamp>_bench1\report.md` then gives:

- frame-to-frame noise (X/Y/angle std while the paper is stationary)
- measured size vs nominal across placements, which is an accuracy check that needs no ruler
- every failure reason seen

Annotated images of each placement go in `frames\`.

## Layout

```
config.yaml                  every physical value (placeholders flagged)
src/cage_vision/
  config.py                  typed config + validation
  camera.py                  capture, settings lock, camera listing
  calibration.py             ArUco detection, homography, plausibility checks
  detector.py                paper segmentation, sub-pixel edges, candidate checks
  geometry.py                rectangle pose on the world plane
  pipeline.py                one frame -> Measurement (stateless)
  overlay.py                 diagnostic drawing
  logger.py                  run folders, CSV, repeatability report
  synth.py                   synthetic scenes with exact ground truth
  main.py                    CLI
tests/                       pytest (geometry, config, end-to-end + failure cases)
evidence/p0-synthetic/       reports, CSVs and sample annotated frames from the synthetic runs
markers/                     printable marker SVGs
```

`runs/` and `test_images/` are generated and not tracked. Regenerate `test_images/` with
`cage-vision synth` (seeded, so the output is reproducible).
