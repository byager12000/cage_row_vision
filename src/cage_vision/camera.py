"""Webcam capture with settings locked where the camera allows it.

Nothing here assumes a particular webcam: index, backend, resolution and the
locked values all come from config. What the camera actually accepted is
reported back, because many UVC webcams silently ignore some properties.
"""

from __future__ import annotations

import cv2
import numpy as np

from .config import CameraConfig

_BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}


def list_cameras(max_index: int = 6, backend: str = "dshow") -> list[dict]:
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, _BACKENDS[backend])
        if cap.isOpened():
            ok, frame = cap.read()
            found.append({"index": i, "opened": True, "frame": ok,
                          "resolution": f"{frame.shape[1]}x{frame.shape[0]}" if ok else "?"})
        cap.release()
    return found


class Camera:
    def __init__(self, cfg: CameraConfig):
        self.cfg = cfg
        self.cap = cv2.VideoCapture(cfg.index, _BACKENDS[cfg.backend])
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open camera index {cfg.index} (backend {cfg.backend})")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        if cfg.lock_settings:
            self._lock()
        for _ in range(cfg.warmup_frames):
            self.cap.read()

    def _lock(self) -> None:
        c, cfg = self.cap, self.cfg
        # DirectShow: 0.25 = manual exposure, 0.75 = auto (OpenCV's historic mapping).
        c.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        if cfg.exposure is not None:
            c.set(cv2.CAP_PROP_EXPOSURE, cfg.exposure)
        c.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        if cfg.focus is not None:
            c.set(cv2.CAP_PROP_FOCUS, cfg.focus)
        c.set(cv2.CAP_PROP_AUTO_WB, 0)
        if cfg.white_balance is not None:
            c.set(cv2.CAP_PROP_WB_TEMPERATURE, cfg.white_balance)

    def actual_settings(self) -> dict:
        g = self.cap.get
        return {"width": int(g(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(g(cv2.CAP_PROP_FRAME_HEIGHT)),
                "auto_exposure": g(cv2.CAP_PROP_AUTO_EXPOSURE), "exposure": g(cv2.CAP_PROP_EXPOSURE),
                "autofocus": g(cv2.CAP_PROP_AUTOFOCUS), "focus": g(cv2.CAP_PROP_FOCUS),
                "auto_wb": g(cv2.CAP_PROP_AUTO_WB), "wb_temperature": g(cv2.CAP_PROP_WB_TEMPERATURE)}

    def read(self) -> np.ndarray | None:
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        self.cap.release()
