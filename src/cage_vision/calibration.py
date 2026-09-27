"""Reference-marker detection and the image -> world (table plane) transform.

Four ArUco markers sit at measured world positions around the inspection area.
Each frame, their centers are found and a homography maps image pixels onto the
table plane in real-world units. The calibration is rebuilt from every frame, so
a bumped camera or a covered marker invalidates the result immediately instead
of silently reusing an old transform.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import MarkerConfig


@dataclass
class Calibration:
    valid: bool
    reason: str = ""
    H: np.ndarray | None = None          # image px -> world units
    H_inv: np.ndarray | None = None      # world units -> image px
    marker_corners: dict[int, np.ndarray] = field(default_factory=dict)  # id -> (4,2) image px
    size_error: float | None = None      # worst |measured - printed| marker side, world units
    marker_sizes: dict[int, float] = field(default_factory=dict)          # measured side, world units


def _dictionary(name: str) -> cv2.aruco.Dictionary:
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"unknown ArUco dictionary {name!r}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def make_detector(cfg: MarkerConfig) -> cv2.aruco.ArucoDetector:
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(_dictionary(cfg.dictionary), params)


def to_world(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def _side_length(world_quad: np.ndarray) -> float:
    return float(np.mean([np.linalg.norm(world_quad[i] - world_quad[(i + 1) % 4]) for i in range(4)]))


def calibrate(gray: np.ndarray, cfg: MarkerConfig, detector: cv2.aruco.ArucoDetector | None = None) -> Calibration:
    detector = detector or make_detector(cfg)
    corners, ids, _ = detector.detectMarkers(gray)
    wanted = set(cfg.positions)

    found: dict[int, list[np.ndarray]] = {}
    if ids is not None:
        for c, i in zip(corners, ids.flatten()):
            found.setdefault(int(i), []).append(c.reshape(4, 2).astype(np.float64))

    marker_corners = {i: v[0] for i, v in found.items() if i in wanted and len(v) == 1}

    missing = sorted(wanted - set(found))
    if missing:
        return Calibration(False, f"reference marker(s) not found: {missing}", marker_corners=marker_corners)
    dupes = sorted(i for i in wanted if len(found[i]) > 1)
    if dupes:
        return Calibration(False, f"reference marker ID seen more than once: {dupes}", marker_corners=marker_corners)

    order = sorted(wanted)
    img_pts = np.array([marker_corners[i].mean(axis=0) for i in order], dtype=np.float64)
    world_pts = np.array([cfg.positions[i] for i in order], dtype=np.float64)

    # Degenerate layout (three markers nearly collinear) gives a useless homography.
    hull = cv2.convexHull(img_pts.astype(np.float32))
    if len(hull) != 4:
        return Calibration(False, "reference markers are not in a convex quadrilateral", marker_corners=marker_corners)

    H, _ = cv2.findHomography(img_pts, world_pts, 0)
    if H is None or not np.all(np.isfinite(H)):
        return Calibration(False, "could not compute perspective transform", marker_corners=marker_corners)

    # Plausibility: four centers always fit a homography exactly, so the real check
    # is the marker squares themselves. Their size in world units must match the
    # printed size; a wrong position entry or a moved marker shows up here.
    sizes = {i: _side_length(to_world(H, marker_corners[i])) for i in order}
    size_error = float(max(abs(s - cfg.size) for s in sizes.values()))
    cal = Calibration(True, "", H, np.linalg.inv(H), marker_corners, size_error, sizes)

    lo, hi = cfg.size * (1 - cfg.size_tolerance), cfg.size * (1 + cfg.size_tolerance)
    bad = {i: round(s, 3) for i, s in sizes.items() if not lo <= s <= hi}
    if bad:
        cal.valid = False
        cal.reason = (f"marker size implausible {bad} (expected {cfg.size} +/-{cfg.size_tolerance:.0%}); "
                      "check marker positions in config or whether a marker moved")
        return cal
    return cal
