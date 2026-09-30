# Frame noise and size-consistency report — 20260928-202328_home1

Frame-to-frame noise is the population std over each placement's burst (sheet untouched, ~2 s).
It is not re-placement repeatability, and there is no ground-truth position error unless gt columns exist.

- Placements: 25 / 25 detected
- Frames: 244 / 250 valid

Placements with some invalid frames: 10 (8/10), 11 (7/10), 12 (9/10)

## Frame-to-frame noise (sheet stationary)
- X std: mean +0.0010, std 0.0003, max |0.0019| in (n=25)
- Y std: mean +0.0009, std 0.0004, max |0.0027| in (n=25)
- Angle std: mean +0.0059, std 0.0019, max |0.0109| deg (n=25)

## Measured size vs nominal
- Length error: mean -0.0494, std 0.0062, max |0.0594| in (n=25)
- Width error: mean +0.0052, std 0.0062, max |0.0147| in (n=25)

## Failure reasons seen
- reference marker(s) not found: [0]
