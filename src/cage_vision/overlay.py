"""Diagnostic overlay: what the pipeline saw and what it reported."""

from __future__ import annotations

import cv2
import numpy as np

from .calibration import Calibration, to_world
from .config import Config
from .detector import Detection
from .pipeline import Measurement

GREEN, RED, AMBER, CYAN, WHITE, BLACK = (0, 200, 0), (0, 0, 230), (0, 170, 255), (255, 200, 0), (255, 255, 255), (0, 0, 0)


def _world_to_px(cal: Calibration, pts) -> np.ndarray:
    return to_world(cal.H_inv, np.asarray(pts, float))


def _text(img, s, org, color=WHITE, scale=0.7, thick=2):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, BLACK, thick + 3, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def draw(frame: np.ndarray, m: Measurement, cal: Calibration, det: Detection, cfg: Config) -> np.ndarray:
    img = frame.copy() if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    scale = max(0.5, img.shape[1] / 1920 * 0.9)
    lw = max(1, int(round(2 * scale)))

    # Reference markers
    for mid, c in cal.marker_corners.items():
        cv2.polylines(img, [c.astype(np.int32)], True, CYAN if cal.valid else RED, lw)
        _text(img, f"M{mid}", tuple(c.mean(axis=0).astype(int) + [-15, -int(25 * scale)]), CYAN, 0.6 * scale)

    if cal.valid and cal.H_inv is not None:
        # World axes from the origin
        ax_len = cfg.markers.size * 2
        o, x, y = _world_to_px(cal, [(0, 0), (ax_len, 0), (0, ax_len)]).astype(int)
        cv2.arrowedLine(img, tuple(o), tuple(x), RED, lw + 1, tipLength=0.2)
        cv2.arrowedLine(img, tuple(o), tuple(y), GREEN, lw + 1, tipLength=0.2)
        _text(img, "+X", tuple(x + [5, 0]), RED, 0.6 * scale)
        _text(img, "+Y", tuple(y + [5, 0]), GREEN, 0.6 * scale)

    for c, why in det.rejected:
        cv2.drawContours(img, [c], -1, AMBER, lw)
        _text(img, why[:60], tuple(c.reshape(-1, 2).min(axis=0)), AMBER, 0.5 * scale, 1)

    if det.detected and det.pose is not None and cal.H_inv is not None:
        p = det.pose
        cv2.polylines(img, [det.image_corners.astype(np.int32)], True, GREEN, lw + 1)
        ctr = _world_to_px(cal, [p.center])[0]
        cv2.drawMarker(img, tuple(ctr.astype(int)), GREEN, cv2.MARKER_CROSS, int(30 * scale), lw + 1)
        u = np.array([np.cos(np.radians(p.rotation_deg)), np.sin(np.radians(p.rotation_deg))])
        a, b = _world_to_px(cal, [p.center - u * p.length / 2, p.center + u * p.length / 2]).astype(int)
        cv2.line(img, tuple(a), tuple(b), GREEN, lw)

    # Status + numbers panel
    color = GREEN if m.valid else RED
    lines = [m.status_text[:90]]
    if m.valid:
        u = m.units
        lines += [f"X = {m.center_x:8.3f} {u}", f"Y = {m.center_y:8.3f} {u}", f"Angle = {m.rotation_deg:7.2f} deg",
                  f"L x W = {m.length:.3f} x {m.width:.3f} {u}"]
    else:
        lines += ["X = ---", "Y = ---", "Angle = ---"]
    if m.marker_size_error is not None:
        lines.append(f"marker size err {m.marker_size_error:.3f} {m.units}")
    if not cfg.layout_confirmed:
        lines.append("LAYOUT NOT CONFIRMED - placeholder marker/paper values")
    y0, step = int(35 * scale), int(32 * scale)
    panel_w = int(max(len(s) for s in lines) * 15 * scale) + 30
    sub = img[0:y0 + step * len(lines) - int(10 * scale), 0:min(panel_w, img.shape[1])]
    sub[:] = (sub * 0.35).astype(np.uint8)
    for i, s in enumerate(lines):
        _text(img, s, (15, y0 + i * step), color if i == 0 else (AMBER if "NOT CONFIRMED" in s else WHITE), 0.8 * scale)
    cv2.rectangle(img, (0, 0), (img.shape[1] - 1, img.shape[0] - 1), color, 6)
    return img
