"""Shape-agnostic cage outlines and taught-outline position checks.

Works for any footprint (rectangle, OptiMice triangle, ...) and any plastic
(amber, lightly tinted, clear), on a light belt:

1. Find cages by their sharp wall edges (Canny on the floor-plane rectified image),
   close the edges into loops and fill them. Shadows and lighting gradients give
   soft edges and are not picked up; the belt's hinge lines are too weak.
2. Rebuild the bottom footprint from the outline. Each outline point is either the
   rim (cage height above the belt) or the bottom (on the belt), whichever projects
   further out for that side as seen from the camera (camera_model.py). Rim points
   are moved to their true position and pulled in by the wall taper.
3. Compare a live footprint with a taught one by a rigid 2-D fit (ICP). The cage is
   IN when every point of the taught outline has moved by no more than the tolerance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .calibration import Calibration
from .camera_model import CameraModel
from .config import Config

PPI = 20.0


@dataclass
class CageOutline:
    bottom: np.ndarray        # (n,2) reconstructed bottom footprint, world units, CCW, densely sampled
    silhouette: np.ndarray    # (m,2) outline as seen, projected on the marker plane
    img_outline: np.ndarray   # (m,2) image px
    centroid: np.ndarray      # (2,) of the bottom footprint
    area: float
    partial: bool = False     # outline cut open by the edge of the marked area: never judged, reported instead


def _frame(cfg: Config):
    pts = np.array(list(cfg.markers.positions.values()), float)
    x0, y0 = pts.min(axis=0) - 4
    x1, y1 = pts.max(axis=0) + 4
    A = np.array([[PPI, 0, -x0 * PPI], [0, -PPI, y1 * PPI], [0, 0, 1.0]])
    return A, int((x1 - x0) * PPI), int((y1 - y0) * PPI)


def _px_to_world(A_inv: np.ndarray, p: np.ndarray) -> np.ndarray:
    q = np.c_[p, np.ones(len(p))] @ A_inv.T
    return q[:, :2] / q[:, 2:]


def _densify(poly: np.ndarray, step: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """Points every `step` along a closed polygon, with the outward normal of their edge (polygon made CCW)."""
    P = poly.reshape(-1, 2).astype(float)
    if cv2.contourArea(P.astype(np.float32), oriented=True) < 0:
        P = P[::-1]
    pts, nrm = [], []
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        L = np.linalg.norm(b - a)
        if L < 1e-9:
            continue
        n = max(1, int(L / step))
        t = (b - a) / L
        pts.append(a + np.outer(np.arange(n) / n, b - a))
        nrm.append(np.repeat([[t[1], -t[0]]], n, axis=0))
    return np.vstack(pts), np.vstack(nrm)


def _clip(poly: np.ndarray, n: np.ndarray, h: float) -> np.ndarray:
    """Sutherland-Hodgman: keep the part of a convex polygon with x.n <= h."""
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        da, db = a @ n - h, b @ n - h
        if da <= 0:
            out.append(a)
        if da * db < 0:
            out.append(a + (b - a) * da / (da - db))
    return np.array(out)


def reconstruct_bottom(silhouette: np.ndarray, cam: CameraModel, belt: float, height: float, taper: float,
                       n_dirs: int = 360) -> np.ndarray:
    """Convex silhouette on the marker plane -> bottom footprint on the belt. Exact for convex cages.

    Works on support functions (the outline's extent in each direction n). A point at height z
    projects to k*p + (1-k)*N with k = H/(H-z), so a shape's projected extent is k*h(n) + (1-k)*N.n.
    The rim is the bottom grown by the taper: h_rim = h_bottom + taper. The silhouette is the hull
    of both projections, so its extent is the larger of the two; each branch is increasing in
    h_bottom, so h_bottom = the smaller of the two inversions. The bottom is then the intersection
    of the half-planes x.n <= h_bottom(n).
    (A point-by-point rim/bottom split pushed the corner-edge stretches of the outline outward:
    +10% area on a synthetic rectangle seen from the side.)
    """
    S = cv2.convexHull(silhouette.astype(np.float32)).reshape(-1, 2).astype(float)
    H = cam.height
    kb, kr = H / (H - belt), H / (H - belt - height)
    th = np.linspace(0, 2 * np.pi, n_dirs, endpoint=False)
    dirs = np.c_[np.cos(th), np.sin(th)]
    hS = (S @ dirs.T).max(axis=0)
    Nn = dirs @ cam.nadir
    hB = np.minimum((hS - (1 - kb) * Nn) / kb, (hS - (1 - kr) * Nn) / kr - taper)
    c = S.mean(axis=0)
    r = np.ptp(S, axis=0).max() * 2
    poly = np.array([c + [-r, -r], c + [r, -r], c + [r, r], c + [-r, r]])
    for n, h in zip(dirs, hB):
        poly = _clip(poly, n, h)
        if len(poly) < 3:
            return S                                     # degenerate input: fall back to the silhouette
    return _densify(poly)[0]


def find_cages(frame: np.ndarray, cal: Calibration, cam: CameraModel, cfg: Config) -> list[CageOutline]:
    cc = cfg.cage
    A, W, H = _frame(cfg)
    A_inv = np.linalg.inv(A)
    rect = cv2.warpPerspective(frame, A @ cal.H, (W, H), flags=cv2.INTER_LINEAR)
    L = cv2.cvtColor(rect, cv2.COLOR_BGR2LAB)[..., 0]
    roi = np.zeros(L.shape, np.uint8)
    corners_px = cv2.perspectiveTransform(np.array(list(cfg.markers.positions.values()), float).reshape(-1, 1, 2), A).reshape(-1, 2)
    cv2.fillConvexPoly(roi, cv2.convexHull(corners_px.astype(np.int32)), 255)
    roi = cv2.erode(roi, np.ones((int(2 * PPI) | 1, int(2 * PPI) | 1), np.uint8))   # stay 1 in off the marker tags
    edges = cv2.Canny(cv2.GaussianBlur(L, (3, 3), 0), cc.edge_low, cc.edge_high)
    edges[roi == 0] = 0
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    flood = closed.copy()
    ff_mask = np.zeros((H + 2, W + 2), np.uint8)
    cv2.floodFill(flood, ff_mask, (0, 0), 255)
    filled = cv2.bitwise_or(closed, cv2.bitwise_not(flood))
    if cc.ignore_color:
        # Reference tape (blue/green) laid against a cage gets swallowed into its outline. Remove strongly
        # coloured non-amber pixels AFTER the wall loops are filled: the loop is never cut open, and the
        # hull of what remains still spans the cage. (2026-09-30 run: blue tape touching the Jag 75 bent
        # the outline and caused 4 false OUT calls.)
        hsv = cv2.cvtColor(rect, cv2.COLOR_BGR2HSV)
        tape = np.zeros(L.shape, bool)
        for lo, hi in cc.ignore_hues:
            tape |= (hsv[..., 0] >= lo) & (hsv[..., 0] <= hi)
        tape &= (hsv[..., 1] > cc.ignore_min_sat) & (hsv[..., 2] > 40)
        tape = cv2.dilate(tape.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        filled[tape > 0] = 0
    filled = cv2.morphologyEx(filled, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    n, lab = cv2.connectedComponents(filled)
    masks = []
    for i in range(1, n):
        m = (lab == i).astype(np.uint8)
        if m.sum() / PPI ** 2 < cc.min_area:
            continue
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = max(cs, key=cv2.contourArea)
        if cv2.contourArea(c) / cv2.contourArea(cv2.convexHull(c)) < 0.93:     # touching cages: split at the neck
            dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
            k, seeds = cv2.connectedComponents((dist > 0.6 * dist.max()).astype(np.uint8))
            markers = seeds.astype(np.int32)
            markers[(cv2.dilate(m, np.ones((5, 5), np.uint8)) - m) > 0] = k
            ws = cv2.watershed(cv2.cvtColor(m * 255, cv2.COLOR_GRAY2BGR), markers)
            masks += [((ws == j) & (m > 0)).astype(np.uint8) for j in range(1, k)]
        else:
            masks.append(m)
    out = []
    for m in masks:
        if m.sum() / PPI ** 2 < cc.min_area:
            continue
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        hull_px = cv2.convexHull(max(cs, key=cv2.contourArea)).reshape(-1, 2).astype(float)
        sil = _px_to_world(A_inv, hull_px)
        bottom = reconstruct_bottom(sil, cam, cc.base_height, cc.height, cc.taper)
        mom = cv2.moments(bottom.astype(np.float32))
        img = cv2.perspectiveTransform(sil.reshape(-1, 1, 2), cal.H_inv).reshape(-1, 2)
        out.append(CageOutline(bottom, sil, img, np.array([mom["m10"] / mom["m00"], mom["m01"] / mom["m00"]]),
                               float(cv2.contourArea(bottom.astype(np.float32)))))

    # Cages whose wall edges do not close into a loop (typically: part of the cage is outside the marked
    # area, where edges are masked) are reported as partial instead of being silently ignored.
    found = np.zeros(L.shape, np.uint8)
    for m in masks:
        found |= m
    grow = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    n2, lab2, stats2, _ = cv2.connectedComponentsWithStats(grow)
    for i in range(1, n2):
        if stats2[i, cv2.CC_STAT_AREA] / PPI ** 2 < cc.min_area:
            continue
        comp = lab2 == i
        if (found[comp] > 0).mean() > 0.2:
            continue                                                      # a found cage
        pts = np.column_stack(np.nonzero(comp & (edges > 0)))[:, ::-1].astype(np.float32)
        (_, _), (a, b), _ = cv2.minAreaRect(pts)
        if min(a, b) / PPI < 3.0:
            continue                                                      # a straight line: belt edge, tape
        hull_px = cv2.convexHull(pts).reshape(-1, 2).astype(float)
        sil = _px_to_world(A_inv, hull_px)
        mom = cv2.moments(sil.astype(np.float32))
        img = cv2.perspectiveTransform(sil.reshape(-1, 1, 2), cal.H_inv).reshape(-1, 2)
        out.append(CageOutline(sil, sil, img, np.array([mom["m10"] / mom["m00"], mom["m01"] / mom["m00"]]),
                               float(cv2.contourArea(sil.astype(np.float32))), partial=True))
    return out


def _normals(pts: np.ndarray) -> np.ndarray:
    """Unit normals of an ordered closed outline (central differences)."""
    tng = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    tng /= np.linalg.norm(tng, axis=1, keepdims=True) + 1e-12
    return np.c_[tng[:, 1], -tng[:, 0]]


def _rot(a: float) -> np.ndarray:
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def register(taught: np.ndarray, live: np.ndarray, max_angle_deg: float = 30.0, iters: int = 60,
             huber: float = 0.08):
    """Rigid 2-D fit taught -> live. Returns (R, t, angle_deg, rms).

    Point-to-line ICP: each taught point is pulled onto the *line* of the nearest live
    edge (not onto a live point), so points can slide along straight sides and the
    rotation is recovered exactly. Huber weights down-weight things that come and go
    (water fittings, clips) without throwing away the corners that carry the rotation.
    (A point-to-point, 10%-trimmed version under-reported a 2 deg twist as 0.4-1 deg.)
    """
    nl = _normals(live)
    full = taught
    taught = taught[::2]
    ct, cl = taught.mean(axis=0), live.mean(axis=0)

    def coarse(a0):
        m = taught @ _rot(a0).T + (cl - _rot(a0) @ ct)
        return np.sqrt(((m[:, None, :] - live[None, :, :]) ** 2).sum(axis=2).min(axis=1)).mean()

    starts = sorted(np.radians(np.arange(-max_angle_deg, max_angle_deg + 0.1, 10.0)), key=coarse)[:2]
    best = None
    for a0 in starts:
        a, t = a0, cl - _rot(a0) @ ct
        for _ in range(iters):
            R = _rot(a)
            moved = taught @ R.T + t
            d2 = ((moved[:, None, :] - live[None, :, :]) ** 2).sum(axis=2)
            j = d2.argmin(axis=1)
            n = nl[j]
            r = np.einsum("ij,ij->i", moved - live[j], n)                     # signed distance to the live edge line
            w = np.where(np.abs(r) <= huber, 1.0, huber / (np.abs(r) + 1e-12))
            c = moved.mean(axis=0)
            lever = np.c_[-(moved[:, 1] - c[1]), moved[:, 0] - c[0]]          # d(moved)/d(angle) about c
            J = np.c_[np.einsum("ij,ij->i", lever, n), n]                     # [d r/d angle, d r/d tx, d r/d ty]
            sw = np.sqrt(w)
            delta, *_ = np.linalg.lstsq(J * sw[:, None], -r * sw, rcond=None)
            da, dt = delta[0], delta[1:]
            # apply: rotate about c by da, then shift by dt
            a += da
            t = _rot(da) @ (t - c) + c + dt
            if abs(da) < 1e-9 and np.linalg.norm(dt) < 1e-7:
                break
        R = _rot(a)
        ang = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
        moved = full @ R.T + t
        d = np.sqrt(((moved[:, None, :] - live[None, :, :]) ** 2).sum(axis=2).min(axis=1))
        rms = float(np.sqrt(np.mean(np.sort(d)[: int(0.9 * len(d))] ** 2)))
        if abs(ang) <= max_angle_deg and (best is None or rms < best[3]):
            best = (R, t, ang, rms)
    return best


def compare(target: dict, live: CageOutline, tolerance: float) -> dict:
    """Deviation of a live cage from the taught outline: how far each taught outline point moved."""
    taught = np.array(target["bottom"])
    R, t, ang, rms = register(taught, live.bottom)
    moved = taught @ R.T + t
    dev = np.linalg.norm(moved - taught, axis=1)
    c0 = np.array(target["centroid"])
    d = R @ c0 + t - c0
    return {"dx": float(d[0]), "dy": float(d[1]), "dangle_deg": ang, "max_corner_dev": float(dev.max()),
            "in_position": bool(dev.max() <= tolerance), "fit_rms": rms}


def pick(outlines: list[CageOutline], target: dict | None, max_dist: float = 4.0) -> CageOutline | None:
    """The cage to judge: nearest to the target (within max_dist), or the largest one when no target yet."""
    outlines = [o for o in outlines if not o.partial]
    if not outlines:
        return None
    if target is None:
        return max(outlines, key=lambda o: o.area)
    c0 = np.array(target["centroid"])
    best = min(outlines, key=lambda o: np.linalg.norm(o.centroid - c0))
    return best if np.linalg.norm(best.centroid - c0) <= max_dist else None


def save_outline_target(cfg: Config, outlines: list[CageOutline]) -> dict:
    """Teach: median-aligned outline from several frames of the same cage."""
    ref = outlines[0]
    Rs = [register(ref.bottom, o.bottom) for o in outlines]
    t_med = np.median([r[1] for r in Rs], axis=0)
    a_med = np.radians(np.median([r[2] for r in Rs]))
    R = np.array([[np.cos(a_med), -np.sin(a_med)], [np.sin(a_med), np.cos(a_med)]])
    bottom = ref.bottom @ R.T + t_med
    mom = cv2.moments(bottom.astype(np.float32))
    spread = max(np.linalg.norm(r[1] + r[0] @ ref.centroid - (t_med + R @ ref.centroid)) for r in Rs)
    data = {"created": datetime.now().isoformat(timespec="seconds"), "method": "outline",
            "cage_height": cfg.cage.height, "frames": len(outlines), "spread_in": round(float(spread), 4),
            "centroid": [float(mom["m10"] / mom["m00"]), float(mom["m01"] / mom["m00"])],
            "area": float(cv2.contourArea(bottom.astype(np.float32))),
            "bottom": [[round(float(x), 4), round(float(y), 4)] for x, y in bottom]}
    Path(cfg.cage.target_file).write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data
