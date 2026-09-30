# Cage position test

Tolerance: every footprint corner within 0.5 in of the taught target.
Intended moves are set by hand with a tape measure (about +/-1/32 to 1/16 in).

| # | move | expected | measured | worst corner (in) | dX err | dY err | dA err (deg) |
|---|---|---|---|---|---|---|---|
| 1 | At the target (both gaps at the start gap) | IN | IN | 0.141 | -0.029 | +0.115 | -0.25 |
| 2 | Slide RIGHT 1/4 in (left gap +1/4) | IN | IN | 0.309 | -0.009 | +0.140 | -0.28 |
| 3 | Slide RIGHT 3/8 in (left gap +3/8) | IN | OUT (WRONG) | 0.557 | -0.003 | +0.186 | -1.33 |
| 4 | Slide RIGHT 5/8 in (left gap +5/8) | OUT | OUT | 0.624 | -0.143 | +0.195 | -0.99 |
| 5 | Slide RIGHT 1 in (left gap +1) | OUT | OUT | 0.977 | -0.138 | +0.219 | -0.84 |
| 6 | Back to the target | IN | IN | 0.302 | -0.113 | +0.164 | -1.04 |
| 7 | Slide AWAY from you 1/4 in (near gap +1/4) | IN | OUT (WRONG) | 0.762 | -0.157 | +0.468 | -0.36 |
| 8 | Slide AWAY 3/8 in (near gap +3/8) | IN | OUT (WRONG) | 0.899 | -0.145 | +0.492 | -0.28 |
| 9 | Slide AWAY 5/8 in (near gap +5/8) | OUT | OUT | 1.112 | -0.126 | +0.477 | -0.02 |
| 10 | Slide AWAY 1 in (near gap +1) | OUT | OUT | 1.483 | -0.116 | +0.458 | +0.31 |
| 11 | Back to the target | IN | IN | 0.156 | +0.001 | +0.099 | +0.74 |
| 12 | Twist: left-near corner stays, RIGHT end 1/4 in away from you | IN | OUT (WRONG) | 0.986 | -0.223 | +0.137 | +4.32 |
| 13 | Twist: left-near corner stays, RIGHT end 3/4 in away from you | OUT | OUT | 1.285 | -0.180 | -0.064 | +3.46 |
| 14 | Back to the target | IN | IN | 0.109 | -0.066 | +0.070 | +0.12 |

- IN/OUT correct: 10/14
- Largest move error: X 0.223 in, Y 0.492 in, angle 4.32 deg
- 'Back to the target' rows measure how well the cage is re-placed by hand plus the system's repeatability.
