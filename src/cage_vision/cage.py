"""One semi-transparent cage, upright: find its top rim, measure its pose, check it against a target.

The rim sits `cage.height` above the table, so the outline is found on the table-plane
rectified image and then moved to rim height with the camera model (see camera_model.py).
Semi-transparent plastic on a dark surface shows as a band brighter than the local
background (rim lip, walls seen edge-on); the outer edge of that band is the rim.

Position is judged the way the machine needs it: the cage is IN when every corner of
its footprint is within `position_tolerance` of where that corner is at the target.
A rigid move shifts every feature of the cage equally, so corners of the measured rim
give the same answer as corners of the bottom.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .calibration import Calibration
from .camera_model import CameraModel
from .config import Config
from .geometry import angle_diff, normalize_angle

PPI = 25.0          # rectified table-plane resolution for the cage search


@dataclass
class CagePose:
    detected: bool
    reason: str = ""
    center: np.ndarray | None = None      # world XY at rim height
    angle_deg: float | None = None        # long axis vs +X, CCW, [-90, 90)
    length: float | None = None
    width: float | None = None
    outline_img: np.ndarray | None = None  # (n,2) image px, for the overlay
    rejected: list[str] = field(default_factory=list)


def _rect_frame(cfg: Config) -> tuple[np.ndarray, int, int]:
    pts = np.array(list(cfg.markers.positions.values()), float)
    x0, y0 = pts.min(axis=0) - 3
    x1, y1 = pts.max(axis=0) + 3
    A = np.array([[PPI, 0, -x0 * PPI], [0, -PPI, y1 * PPI], [0, 0, 1.0]])     # world -> rectified px (y up)
    return A, int((x1 - x0) * PPI), int((y1 - y0) * PPI)


def _fit_rect(pts: np.ndarray, iters: int = 3) -> tuple[np.ndarray, float, float, float]:
    """Robust rectangle fit to an outline with rounded corners: side medians over the middle of each side."""
    (cx, cy), (a, b), ang = cv2.minAreaRect(pts.astype(np.float32))
    theta = np.radians(ang if a >= b else ang + 90)
    c = np.array([cx, cy])
    for _ in range(iters):
        u, v = np.array([np.cos(theta), np.sin(theta)]), np.array([-np.sin(theta), np.cos(theta)])
        d = pts - c
        x, y = d @ u, d @ v
        L, W = np.ptp(x), np.ptp(y)
        right = np.median(x[(x > 0) & (np.abs(y) < 0.35 * W)])
        left = np.median(x[(x < 0) & (np.abs(y) < 0.35 * W)])
        far_sel, near_sel = (y > 0) & (np.abs(x) < 0.35 * L), (y < 0) & (np.abs(x) < 0.35 * L)
        far, near = np.median(y[far_sel]), np.median(y[near_sel])
        # angle refinement: slope of the two long sides
        slopes = []
        for sel in (far_sel, near_sel):
            if sel.sum() > 10:
                slopes.append(np.polyfit(x[sel], y[sel], 1)[0])
        c = c + u * (right + left) / 2 + v * (far + near) / 2
        theta += np.arctan(np.mean(slopes)) if slopes else 0.0
    return c, float(normalize_angle(np.degrees(theta))), float(right - left), float(far - near)


def detect_cage(frame: np.ndarray, cal: Calibration, cam: CameraModel, cfg: Config) -> CagePose:
    cc = cfg.cage
    if not cal.valid:
        return CagePose(False, "calibration invalid")
    if cc.orientation != "upright":
        return CagePose(False, "only upright cages are supported so far (rim on top)")
    A, W_px, H_px = _rect_frame(cfg)
    rect = cv2.warpPerspective(frame, A @ cal.H, (W_px, H_px), flags=cv2.INTER_LINEAR)
    g = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)
    lift = g.astype(np.float32) - cv2.medianBlur(g, 51).astype(np.float32)
    bright = cv2.dilate((g > 200).astype(np.uint8), np.ones((15, 15), np.uint8))   # paper / marker pages
    cand = ((lift > cc.lift_threshold) & (bright == 0)).astype(np.uint8) * 255
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    contours, _ = cv2.findContours(cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    A_inv = np.linalg.inv(A)
    def px2table(p):
        q = np.c_[p, np.ones(len(p))] @ A_inv.T
        return q[:, :2] / q[:, 2:]

    exp_area = cc.rim_length * cc.rim_width
    found, rejected = [], []
    for c in contours:
        if cv2.contourArea(c) / PPI ** 2 < 0.3 * exp_area:
            continue
        pts = c.reshape(-1, 2).astype(np.float64)
        if pts[:, 0].min() < 3 or pts[:, 1].min() < 3 or pts[:, 0].max() > W_px - 4 or pts[:, 1].max() > H_px - 4:
            rejected.append("cage-sized region touches the edge of the search area")
            continue
        world = cam.to_height(px2table(pts), cc.height)
        center, ang, L, Wd = _fit_rect(world)
        if abs(L - cc.rim_length) > cc.size_tolerance or abs(Wd - cc.rim_width) > cc.size_tolerance:
            rejected.append(f"outline {L:.2f} x {Wd:.2f} in is not the {cc.rim_length} x {cc.rim_width} in rim")
            continue
        found.append((center, ang, L, Wd, pts))
    if len(found) != 1:
        reason = (f"{len(found)} cage-like outlines - ambiguous" if found else
                  (rejected[0] if rejected else "no cage found"))
        return CagePose(False, reason, rejected=rejected)
    center, ang, L, Wd, pts = found[0]
    img_pts = cv2.perspectiveTransform(px2table(pts).reshape(-1, 1, 2), cal.H_inv).reshape(-1, 2)
    return CagePose(True, "", center, ang, L, Wd, img_pts, rejected)


def footprint_corners(center: np.ndarray, angle_deg: float, length: float, width: float) -> np.ndarray:
    t = np.radians(angle_deg)
    u, v = np.array([np.cos(t), np.sin(t)]), np.array([-np.sin(t), np.cos(t)])
    return np.array([center + su * u * length / 2 + sv * v * width / 2 for su, sv in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])


def check_target(pose: CagePose, target: dict, cfg: Config) -> dict:
    """Deviation from the taught target. Corners use the cage's bottom footprint (rigid move = same for any feature)."""
    cc = cfg.cage
    tc, ta = np.array(target["center"]), float(target["angle_deg"])
    da = angle_diff(pose.angle_deg, ta)
    now = footprint_corners(pose.center, ta + da, cc.bottom_length, cc.bottom_width)
    then = footprint_corners(tc, ta, cc.bottom_length, cc.bottom_width)
    corner_dev = float(np.linalg.norm(now - then, axis=1).max())
    d = pose.center - tc
    return {"dx": float(d[0]), "dy": float(d[1]), "dangle_deg": float(da), "max_corner_dev": corner_dev,
            "in_position": corner_dev <= cc.position_tolerance}


def load_target(cfg: Config) -> dict | None:
    p = Path(cfg.cage.target_file)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_target(cfg: Config, poses: list[CagePose]) -> dict:
    centers = np.array([p.center for p in poses])
    a0 = poses[0].angle_deg
    angs = [a0 + angle_diff(p.angle_deg, a0) for p in poses]
    data = {"center": [round(float(v), 4) for v in np.median(centers, axis=0)],
            "angle_deg": round(float(normalize_angle(np.median(angs))), 4),
            "frames": len(poses), "spread_in": round(float(np.linalg.norm(centers - np.median(centers, axis=0), axis=1).max()), 4)}
    Path(cfg.cage.target_file).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
