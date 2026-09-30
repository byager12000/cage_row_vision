# Phase 2 exploration: real cages (2026-09-28 to 2026-09-30)

This is exploratory evidence, not a Phase 2 deliverable.

The cage is an Allentown Jag 75: amber-tinted, semi-transparent shoebox, upright unless noted. Ben's tape gives
a height of 5 in and a bottom of **11.25 × 7.00 in** (measured 2026-09-29).

## Method (both benches)

- The floor/table-plane calibration comes from the four markers.
- A feature at height h lies on a ray that hits the marker plane at P0. Its true position is N + (P0 − N)·(H − h)/H,
  where N is the point under the camera and H is the camera height. N is estimated from a pinhole model fitted to
  the homography and to Ben's camera height (`src/cage_vision/camera_model.py`). The size correction doesn't depend on N.

## 1. Home bench: dark wood, room light (2026-09-28)

The camera was 34¼ in above the table. The outline was taken as rim/wall brightness above the local wood level,
and the rim was measured with side medians, assuming the whole outline is the rim.

| | Upright, off-centre | Upright, centred |
|---|---|---|
| Outer outline read as if at table height (wrong) | 13.56 × 8.96 in | 13.60 × 8.64 in |
| Top rim, corrected to 5 in | 11.58 in long | **11.61 × 7.38 in** |

With Ben's bottom tape measurement, that gives a **wall taper of about 0.18 in per side**.

**CORRECTION (2026-09-29).** Earlier versions of this note reported "floor 10.66 in long, taper about ½ in
per end, floor width about 6.4 in", from the upside-down shot. That was wrong: the outline edge chosen was not
the floor edge at the height assumed. Ben's tape gives 11.25 × 7.00 in. The upside-down measurement is not used.
The detector now refuses an upside-down cage instead of misreading it.

## 2. Warehouse: white modular belt (2026-09-30)

**Setup**
- Markers are taped to the floor at 45⅛ × 30 in centres. The tags printed at 97%: squares measure 2.91 in,
  and the camera reads 2.87–2.89 in.
- The belt lies on the floor: its surface is ⅜ in above the marker plane.
- The camera is 48⅛ in above the belt (48½ in above the markers), about 9° from vertical. It is the Stopmotion
  1080p, now on DirectShow index 0.
- Exposure is locked at −7: mean 174, 0.2% clipped. Auto exposure gives mean 144.

**Segmentation.** On a white belt the cage is *darker and amber*, not brighter:

| | Brightness (L) | Saturation (S) | b\* |
|---|---|---|---|
| Belt | 243 | 12 | 133 |
| Cage interior | 198 | 46 | 144 |
| Cage rim | 187 | 46 | 143 |
| Concrete floor | 126 | 45 | 135 |

The cage mask is saturation > 25 and L > 150, inside the marker rectangle. The single region found was about
118 sq in, and it barely changed from S > 25 to S > 30.

**3-D fit.** The cage was about 15 in from the point under the camera. On the side facing that point, the
*bottom* edge sits outside the rim in the image, so the outline mixes rim and bottom. A rim-only box read
**13.19 × 9.72 in**. The fitted model is a bottom rectangle at belt height plus a rim rectangle 5 in higher
(0.18 in taper), with walls between. Its predicted silhouette (the convex hull of both projected rectangles) was
fitted to the outline for x, y, angle and bottom L/W (trimmed loss, Nelder–Mead). The script is
`warehouse-2026-09-30/fit3d_exploration.py`.

| Result | Value |
|---|---|
| Bottom | **11.21 × 6.95 in** (Ben's tape: 11.25 × 7.00) |
| Rim | 11.57 × 7.31 in |
| Pose | X 12.80, Y 14.83 in, angle +66.7° |
| Fit residual | 0.061 in rms |

The overlay (`fit3d.jpg`) shows the outline following the rim on the far sides and the bottom on the near sides,
as the geometry predicts. A bottom within 0.05 in of the tape also supports the 45⅛ × 30 layout; the marker-size
shortfall is the print scale.

## Implications for the row check

- Measure at the correct height, with a 3-D model. Rim and bottom project differently depending on where the cage
  sits relative to the camera.
- Pressed cages touch at their rims. Inverted cages from the washer have their rims on the belt, so neighbouring
  tops (bottoms) show about a 2 × 0.18 ≈ **0.36 in** gap even when the rims touch. *(Corrected from "about 1 in".)*
- The alignment bar at the station is a better "square to the conveyor" reference than the markers.
- A CAD model (STL export of `allentown_jag75_cage_bottom.prt`, pending from Ben) will replace the assumed
  5 in height and 0.18 in taper with exact geometry.

## Images

- Home bench: `cage1_exp-5.jpg` (upright, off-centre), `cage_center_up_exp-5.jpg` and `cage_center_down_exp-5.jpg`,
  with `*_measured.jpg` showing the outlines used.
- Warehouse: `warehouse-2026-09-30/` holds `raw_exp-7.png`, `seg2.jpg` (the mask) and `fit3d.jpg`
  (green = rim model, blue = bottom model, red = observed outline).
