"""One frame in, one measurement out. Stateless by design.

Nothing from a previous frame is carried forward: if this frame's calibration or
detection fails, the measurement values are None, never last-known values.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime

import cv2
import numpy as np

from .baseline import load_baseline
from .calibration import Calibration, calibrate, make_detector
from .config import Config
from .detector import Detection, detect_paper


@dataclass
class Measurement:
    timestamp: str
    calibration_ok: bool
    calibration_reason: str
    object_detected: bool
    detection_reason: str
    center_x: float | None
    center_y: float | None
    rotation_deg: float | None
    length: float | None
    width: float | None
    marker_size_error: float | None
    marker_move_px: float | None       # worst marker move vs setup baseline (after removing camera motion)
    marker_sizes: str                  # JSON {id: measured side} - per-marker, not just the worst
    warnings: str
    units: str

    @property
    def valid(self) -> bool:
        return self.calibration_ok and self.object_detected

    @property
    def status_text(self) -> str:
        if not self.calibration_ok:
            return f"CALIBRATION INVALID: {self.calibration_reason}"
        if not self.object_detected:
            return f"NO OBJECT: {self.detection_reason}"
        return "VALID"


class Pipeline:
    def __init__(self, cfg: Config, baseline: dict | None = ...):
        self.cfg = cfg
        self.aruco = make_detector(cfg.markers)
        # Loaded once: the baseline describes the fixed bench, not the frame.
        self.baseline = load_baseline(cfg) if baseline is ... else baseline

    def process(self, frame: np.ndarray) -> tuple[Measurement, Calibration, Detection]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        cal = calibrate(gray, self.cfg.markers, self.aruco, self.baseline)
        det = detect_paper(gray, cal, self.cfg.markers, self.cfg.paper) if cal.valid else Detection(False, "calibration invalid")
        p = det.pose if det.detected else None
        m = Measurement(
            timestamp=datetime.now().isoformat(timespec="milliseconds"),
            calibration_ok=cal.valid,
            calibration_reason=cal.reason,
            object_detected=det.detected,
            detection_reason=det.reason,
            center_x=float(p.center[0]) if p else None,
            center_y=float(p.center[1]) if p else None,
            rotation_deg=p.rotation_deg if p else None,
            length=p.length if p else None,
            width=p.width if p else None,
            marker_size_error=cal.size_error,
            marker_move_px=cal.relative_move_px,
            marker_sizes=json.dumps({k: round(v, 4) for k, v in cal.marker_sizes.items()}) if cal.marker_sizes else "",
            warnings="; ".join(cal.warnings),
            units=self.cfg.units,
        )
        return m, cal, det
