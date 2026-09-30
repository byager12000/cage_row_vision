"""Real-frame check of the setup-baseline gate: what does a bumped marker do?

For each saved raw frame of a bench run, the image patch around one marker is
shifted by d px (a physically bumped marker page: the image moves, config and
baseline do not). Reports how often the gate catches it and the worst paper
position error when it does not.

    uv run python scripts/verify_marker_bump.py runs/<run>/frames [out.json]
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from cage_vision.baseline import load_baseline
from cage_vision.config import load_config
from cage_vision.pipeline import Pipeline


def bump(img: np.ndarray, corners: np.ndarray, dx: float, dy: float, half: int = 90) -> np.ndarray:
    out = img.copy()
    x0, y0 = (corners.mean(axis=0) - half).astype(int)
    x1, y1 = x0 + 2 * half, y0 + 2 * half
    patch = img[y0:y1, x0:x1]
    out[y0:y1, x0:x1] = cv2.warpAffine(patch, np.float32([[1, 0, dx], [0, 1, dy]]), (2 * half, 2 * half),
                                       flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return out


def main() -> int:
    frames_dir = Path(sys.argv[1])
    cfg = load_config("config.yaml")
    base = load_baseline(cfg)
    if base is None:
        sys.exit("no baseline.json - run set-baseline first")
    pipe = Pipeline(cfg, baseline=base)
    imgs = [cv2.imread(f) for f in sorted(glob.glob(str(frames_dir / "*_raw.png")))]
    ref = [pipe.process(i) for i in imgs]
    if not all(r[0].valid for r in ref):
        sys.exit("not every reference frame is VALID against the baseline - bench changed?")
    ppi = float(np.mean([np.linalg.norm(c[0] - c[1]) for r in ref for c in r[1].marker_corners.values()])) / cfg.markers.size
    rows = []
    for d in (2, 3, 4, 5, 6, 7, 8, 10, 12):
        caught = total = 0
        worst = 0.0
        for k in sorted(cfg.markers.positions):
            for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                for (m0, cal0, _), img in zip(ref, imgs):
                    m, _, _ = pipe.process(bump(img, cal0.marker_corners[k], dx, dy))
                    total += 1
                    if not m.calibration_ok:
                        caught += 1
                    elif m.valid:
                        worst = max(worst, float(np.hypot(m.center_x - m0.center_x, m.center_y - m0.center_y)))
        rows.append({"bump_px": d, "bump_in": round(d / ppi, 3), "caught": caught, "total": total,
                     "worst_undetected_position_error_in": round(worst, 4)})
        print(f"bump {d:2d} px (~{d / ppi:.2f} in): caught {caught}/{total}; worst undetected error {worst:.3f} in")
    result = {"frames": len(imgs), "px_per_in": round(ppi, 1), "max_relative_move_px": cfg.markers.max_relative_move_px,
              "rows": rows, "worst_undetected_position_error_in": max(r["worst_undetected_position_error_in"] for r in rows)}
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"worst undetected position error: {result['worst_undetected_position_error_in']:.3f} in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
