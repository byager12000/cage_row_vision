# CAD models

## allentown_jag75_cage_bottom.stl

Exported by Ben from Creo, 2026-09-30. The file is in inches.

**Axes**
- X = width, Y = height (rim at Y = 0, bottom at Y = -4.975), Z = length.

**Profile**, from `section()` slices of the model:

| Height above belt (in) | Length × width (in) | Plan corner radius (in) |
|---|---|---|
| 0.02 (belt contact) | 9.29 × 4.88 | small (fillet) |
| 0.25 | 10.91 × 6.59 | 1.36 |
| 0.5 | 11.22 × 6.89 | 1.49 |
| 1.0 | 11.31 × 6.98 | 1.52 |
| 2.0 | 11.39 × 7.04 | 1.45 |
| 3.0 | 11.46 × 7.10 | 1.50 |
| 4.0 | 11.54 × 7.17 | 1.56 |
| 4.8 (wall top) | 11.60 × 7.22 | 1.61 |
| 4.9–4.975 (rim lip) | 11.75 × 7.36 | 1.77 |

- Height is 4.975 in; Ben's tape gives 5.
- The walls have a draft of about 2°, so the taper is about 0.15 in per side between 1 in and 4.8 in.
- The bottom edge is a large fillet. The belt-contact footprint is only 9.3 × 4.9 in, so the lowest edge the
  camera can see is the wall about ½ in up (11.2 × 6.9 in).

**Vision check (warehouse, 2026-09-30).** The CAD silhouette was placed with the camera model and
fitted to the camera's outline:

| Outline | Fit (rms) | 95th percentile | Notes |
|---|---|---|---|
| Colour (amber mask) | **0.11 in** | 0.21–0.31 in | whole wall visible |
| Wall edges only | 0.39 in | — | misses the lower wall on the side facing the camera |

The pose agrees with the other methods to within about 0.1–0.2 in. The vision bottom (11.18–11.21 × 6.79–6.95)
matches the model at about ½ in up, and the vision rim (11.57–11.61 × 7.31–7.38) matches the wall top and lip.
