"""Where the camera is, from the table homography plus the measured camera height.

Only needed for objects that stand above the table (a 5 in cage rim). A point at
height h lies on a ray from the camera centre C; the table homography gives where
that ray hits the table, P0. By similar triangles the point itself is at
    N + (P0 - N) * (H - h) / H
where N is the table point directly under the camera and H the camera height.
The size correction (H - h)/H needs only H; the position needs N too.

N comes from a pinhole model (square pixels, principal point at the image centre)
fitted to the homography, with the focal length chosen so the camera sits at the
measured height H. An error in N of e moves a 5 in-high feature by e * h / H
(0.15 e for the home bench), and does not change its size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CameraModel:
    nadir: np.ndarray         # (2,) table point under the camera, world units
    height: float             # camera height above the table, world units (as measured)
    focal_px: float
    tilt_deg: float

    def to_height(self, table_pts: np.ndarray, h: float) -> np.ndarray:
        """Table-plane hit points of rays -> world XY of the features at height h on those rays."""
        return self.nadir + (np.asarray(table_pts, float) - self.nadir) * (self.height - h) / self.height

    def from_height(self, pts: np.ndarray, h: float) -> np.ndarray:
        """World XY of features at height h -> where their rays hit the table plane."""
        return self.nadir + (np.asarray(pts, float) - self.nadir) * self.height / (self.height - h)


def _decompose(Hw2i: np.ndarray, f: float, cx: float, cy: float):
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    M = np.linalg.inv(K) @ Hw2i
    lam = 2 / (np.linalg.norm(M[:, 0]) + np.linalg.norm(M[:, 1]))
    r1, r2, t = M[:, 0] * lam, M[:, 1] * lam, M[:, 2] * lam
    R = np.column_stack([r1, r2, np.cross(r1, r2)])
    U, _, Vt = np.linalg.svd(R)
    R = U @ Vt
    C = -R.T @ t
    if C[2] < 0:                       # camera must be above the table (+Z toward the camera)
        R[:, 0] *= -1
        R[:, 1] *= -1
        t = -t
        R[:, 2] = np.cross(R[:, 0], R[:, 1])
        C = -R.T @ t
    return R, C


def estimate_camera(H_img2world: np.ndarray, image_size: tuple[int, int], camera_height: float) -> CameraModel:
    Hw2i = np.linalg.inv(H_img2world)
    Hw2i = Hw2i / Hw2i[2, 2]
    w, h = image_size
    cx, cy = (w - 1) / 2, (h - 1) / 2
    lo, hi = 100.0, 20000.0
    for _ in range(100):               # camera height rises monotonically with focal length
        f = (lo + hi) / 2
        _, C = _decompose(Hw2i, f, cx, cy)
        lo, hi = (f, hi) if C[2] < camera_height else (lo, f)
    R, C = _decompose(Hw2i, f, cx, cy)
    return CameraModel(np.array(C[:2]), float(camera_height), float(f), float(np.degrees(np.arccos(abs(R[2, 2])))))
