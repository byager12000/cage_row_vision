"""Rectangle geometry on the world (table) plane."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RectPose:
    center: np.ndarray        # (2,) world units
    rotation_deg: float       # long axis vs world +X, CCW positive, in [-90, 90)
    length: float             # mean long side
    width: float              # mean short side
    corners: np.ndarray       # (4,2) world units, consistent winding


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Return 4 points in consistent winding order starting from the one nearest the centroid's angle 0."""
    pts = np.asarray(pts, dtype=np.float64).reshape(4, 2)
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    return pts[np.argsort(ang)]


def normalize_angle(deg: float) -> float:
    """A rectangle looks the same rotated 180 deg; fold into [-90, 90)."""
    return float((deg + 90.0) % 180.0 - 90.0)


def rect_pose(world_corners: np.ndarray) -> RectPose:
    q = order_quad(world_corners)
    edges = [q[(i + 1) % 4] - q[i] for i in range(4)]
    lens = np.array([np.linalg.norm(e) for e in edges])
    # Opposite edges 0/2 and 1/3. The long pair is the one with the larger mean.
    pair_a = (lens[0] + lens[2]) / 2
    pair_b = (lens[1] + lens[3]) / 2
    if pair_a >= pair_b:
        long_edges, length, width = (edges[0], -edges[2]), pair_a, pair_b
    else:
        long_edges, length, width = (edges[1], -edges[3]), pair_b, pair_a
    # Average the two long edges (same direction after flipping one) for the axis.
    axis = long_edges[0] / np.linalg.norm(long_edges[0]) + long_edges[1] / np.linalg.norm(long_edges[1])
    rotation = normalize_angle(np.degrees(np.arctan2(axis[1], axis[0])))
    # Diagonal intersection == centroid of the corners for a parallelogram; for a
    # slightly non-parallel quad the diagonal intersection is the better center.
    center = _diagonal_intersection(q)
    return RectPose(center, rotation, float(length), float(width), q)


def _diagonal_intersection(q: np.ndarray) -> np.ndarray:
    p, r = q[0], q[2] - q[0]
    s, d = q[1], q[3] - q[1]
    denom = r[0] * d[1] - r[1] * d[0]
    if abs(denom) < 1e-12:
        return q.mean(axis=0)
    t = ((s[0] - p[0]) * d[1] - (s[1] - p[1]) * d[0]) / denom
    return p + t * r


def angle_diff(a: float, b: float) -> float:
    """Smallest signed difference between two rectangle angles (180 deg symmetric)."""
    return normalize_angle(a - b)
