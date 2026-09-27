"""Find the paper rectangle inside the calibrated area.

Classical vision only: threshold -> contours -> 4-sided polygon -> per-side line
fit for sub-pixel corners -> map to world -> dimensional/rectangularity checks.
Exactly one candidate must pass; zero or several is a failed detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .calibration import Calibration, to_world
from .config import MarkerConfig, PaperConfig
from .geometry import RectPose, order_quad, rect_pose


@dataclass
class Detection:
    detected: bool
    reason: str = ""
    pose: RectPose | None = None
    image_corners: np.ndarray | None = None      # (4,2) px, for the overlay
    rejected: list[tuple[np.ndarray, str]] = field(default_factory=list)  # (contour px, why) for debug


def _roi_polygon(cal: Calibration, markers: MarkerConfig) -> np.ndarray:
    """Calibrated area = quadrilateral through the reference-marker centers."""
    centers = np.array([cal.marker_corners[i].mean(axis=0) for i in sorted(markers.positions)])
    return order_quad(centers).astype(np.int32)


def _mask(gray: np.ndarray, cal: Calibration, markers: MarkerConfig, paper: PaperConfig) -> tuple[np.ndarray, np.ndarray]:
    roi = np.zeros(gray.shape, np.uint8)
    cv2.fillConvexPoly(roi, _roi_polygon(cal, markers), 255)
    # Knock out each marker plus a pad so its black/white pattern is never a candidate.
    for c in cal.marker_corners.values():
        ctr = c.mean(axis=0)
        grown = ctr + (c - ctr) * (1 + 2 * paper.marker_mask_pad)
        cv2.fillConvexPoly(roi, grown.astype(np.int32), 0)
    return roi, _roi_polygon(cal, markers)


EDGE_HALF_WIDTH = 6.0   # px sampled either side of the rough edge
EDGE_SAMPLES = 60       # profiles per side


def _edge_points(gray: np.ndarray, a: np.ndarray, b: np.ndarray, outward: np.ndarray) -> np.ndarray:
    """Sub-pixel edge points along side a->b at the local 50% intensity crossing.

    Each profile runs from inside the paper to the table along the outward normal.
    The crossing level is the midpoint of that profile's own inside/outside levels,
    so it does not depend on the global threshold and tolerates a lighting gradient.
    """
    t = np.linspace(0.12, 0.88, EDGE_SAMPLES)
    s = np.arange(-EDGE_HALF_WIDTH, EDGE_HALF_WIDTH + 0.25, 0.25)
    base = a[None, :] + t[:, None] * (b - a)[None, :]                       # (N,2)
    xy = base[:, None, :] + s[None, :, None] * outward[None, None, :]      # (N,S,2)
    prof = cv2.remap(gray.astype(np.float32), xy[..., 0].astype(np.float32), xy[..., 1].astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    k = max(2, len(s) // 6)
    inside, outside = prof[:, :k].mean(axis=1), prof[:, -k:].mean(axis=1)
    pts = []
    for i in range(len(t)):
        contrast = inside[i] - outside[i]
        if abs(contrast) < 20:
            continue
        mid = (inside[i] + outside[i]) / 2
        p = (prof[i] - mid) * np.sign(contrast)   # >0 on the paper side
        idx = np.nonzero((p[:-1] > 0) & (p[1:] <= 0))[0]
        if len(idx) != 1:                          # none or several crossings: noisy profile, skip
            continue
        j = idx[0]
        frac = p[j] / (p[j] - p[j + 1])
        off = s[j] + frac * (s[j + 1] - s[j])
        pts.append(base[i] + off * outward)
    return np.array(pts)


def _refine_corners(gray: np.ndarray, approx: np.ndarray) -> np.ndarray | None:
    """Sub-pixel corners: 50%-crossing edge points per side -> robust line fit -> intersect."""
    q = approx.reshape(4, 2).astype(np.float64)
    ctr = q.mean(axis=0)
    lines = []
    for k in range(4):
        a, b = q[k], q[(k + 1) % 4]
        ab = b - a
        L = np.linalg.norm(ab)
        if L < 1e-6:
            return None
        u = ab / L
        n = np.array([-u[1], u[0]])
        if np.dot((a + b) / 2 - ctr, n) < 0:
            n = -n
        pts = _edge_points(gray, a, b, n)
        if len(pts) < EDGE_SAMPLES // 3:
            return None
        vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).flatten()
        lines.append((np.array([x0, y0], float), np.array([vx, vy], float)))
    out = []
    for k in range(4):
        (p1, d1), (p2, d2) = lines[k - 1], lines[k]
        A = np.array([d1, -d2]).T
        if abs(np.linalg.det(A)) < 1e-9:
            return None
        t = np.linalg.solve(A, p2 - p1)
        out.append(p1 + t[0] * d1)
    return np.array(out)


def detect_paper(gray: np.ndarray, cal: Calibration, markers: MarkerConfig, paper: PaperConfig) -> Detection:
    if not cal.valid or cal.H is None:
        return Detection(False, "no valid calibration")

    roi, roi_poly = _mask(gray, cal, markers, paper)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    vals = blur[roi > 0]
    if vals.size == 0:
        return Detection(False, "calibrated area is empty")
    if paper.threshold == "otsu":
        thr, _ = cv2.threshold(vals.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        thr = paper.fixed_threshold
    # Otsu always finds *a* split; if the area is uniform (no paper), the split is
    # between noise levels. Require real contrast between the two classes.
    hi_cls, lo_cls = vals[vals > thr], vals[vals <= thr]
    if hi_cls.size == 0 or lo_cls.size == 0 or float(hi_cls.mean() - lo_cls.mean()) < 30:
        return Detection(False, "no contrasting object in calibrated area")

    mode = cv2.THRESH_BINARY if paper.polarity == "bright" else cv2.THRESH_BINARY_INV
    _, binary = cv2.threshold(blur, thr, 255, mode)
    binary = cv2.bitwise_and(binary, roi)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    nominal_area = paper.length * paper.width
    passed: list[tuple[RectPose, np.ndarray]] = []
    rejected: list[tuple[np.ndarray, str]] = []

    for c in contours:
        world_area = abs(cv2.contourArea(to_world(cal.H, c.reshape(-1, 2)).astype(np.float32)))
        if world_area < 0.25 * nominal_area:
            continue  # specks, glare, tape; not worth reporting
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            rejected.append((c, f"not 4-sided ({len(approx)} vertices) - overlapping a marker or leaving the area?"))
            continue
        # Touching the calibrated-area edge = partly outside; its size would be wrong.
        dist = min(abs(cv2.pointPolygonTest(roi_poly, (float(x), float(y)), True)) for x, y in c.reshape(-1, 2)[::5])
        if dist < paper.border_margin_px:
            rejected.append((c, "touches edge of calibrated area"))
            continue
        img_corners = _refine_corners(gray, approx)
        if img_corners is None:
            rejected.append((c, "corner refinement failed"))
            continue
        pose = rect_pose(to_world(cal.H, img_corners))
        quad_area = abs(cv2.contourArea(pose.corners.astype(np.float32)))
        rectness = world_area / quad_area if quad_area > 0 else 0.0
        if rectness < paper.min_rectangularity:
            rejected.append((c, f"not rectangular enough ({rectness:.2f})"))
            continue
        dl, dw = pose.length - paper.length, pose.width - paper.width
        if abs(dl) > paper.size_tolerance or abs(dw) > paper.size_tolerance:
            rejected.append((c, f"size {pose.length:.2f} x {pose.width:.2f} vs nominal "
                                f"{paper.length} x {paper.width}"))
            continue
        passed.append((pose, img_corners))

    if len(passed) == 1:
        pose, img_corners = passed[0]
        return Detection(True, "", pose, img_corners, rejected)
    if len(passed) > 1:
        rejected += [(ic.reshape(-1, 1, 2).astype(np.int32), "ambiguous candidate") for _, ic in passed]
        return Detection(False, f"{len(passed)} paper-like objects - ambiguous", rejected=rejected)
    reason = rejected[0][1] if rejected else "no paper-sized object found"
    return Detection(False, reason, rejected=rejected)
