"""Setup baseline: where each reference marker sits in the image once the bench is verified."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import Config


def load_baseline(cfg: Config) -> dict | None:
    if not cfg.markers.baseline_file:
        return None
    p = Path(cfg.markers.baseline_file)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def make_baseline(cfg: Config, centers_per_frame: list[dict[int, np.ndarray]], source: str) -> dict:
    """Median marker centers over several frames; refuses if the frames disagree (something is moving)."""
    ids = sorted(cfg.markers.positions)
    stack = np.array([[f[i] for i in ids] for f in centers_per_frame], dtype=np.float64)   # (frames, 4, 2)
    med = np.median(stack, axis=0)
    spread = float(np.linalg.norm(stack - med, axis=2).max())
    if spread > cfg.markers.max_relative_move_px:
        raise RuntimeError(f"marker positions moved {spread:.2f} px during baseline capture - keep the bench still")
    return {
        "created": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "frames": len(centers_per_frame),
        "spread_px": round(spread, 3),
        "positions": {str(i): list(cfg.markers.positions[i]) for i in ids},
        "centers_px": {str(i): [round(float(v), 3) for v in med[k]] for k, i in enumerate(ids)},
    }


def save_baseline(cfg: Config, data: dict) -> Path:
    p = Path(cfg.markers.baseline_file or "baseline.json")
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p
