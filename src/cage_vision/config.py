"""Configuration: every physical value lives here, never hard-coded in the pipeline.

Values that depend on the physical bench (marker positions, paper size, camera)
are loaded from ``config.yaml``. Anything Ben has not measured yet is flagged by
``layout_confirmed: false`` and the app says so on every frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CameraConfig:
    index: int = 0                  # OpenCV device index (see `cage-vision list-cameras`)
    backend: str = "dshow"          # dshow | msmf | any
    fourcc: str | None = "MJPG"     # USB 2.0 webcams only deliver 1080p at full rate as MJPG
    width: int = 1920
    height: int = 1080
    lock_settings: bool = True      # turn off auto exposure / focus / white balance if the camera allows
    exposure: float | None = None   # camera-specific units; None = leave as the camera set it
    focus: float | None = None
    white_balance: float | None = None
    warmup_frames: int = 10         # frames discarded after opening so exposure settles


@dataclass
class MarkerConfig:
    dictionary: str = "DICT_4X4_50"
    # World position of each reference marker's CENTER, in `units`.
    # Measured by Ben on the bench. Key = marker ID.
    positions: dict[int, tuple[float, float]] = field(default_factory=dict)
    # Printed black-square side length, in `units`. Used as a plausibility check only.
    size: float = 2.0
    size_tolerance: float = 0.25     # fraction; measured side may differ by this much


@dataclass
class PaperConfig:
    length: float = 11.0             # nominal long side, `units`
    width: float = 8.5               # nominal short side, `units`
    size_tolerance: float = 0.5      # units; measured L/W must be within this of nominal
    polarity: str = "bright"         # bright = paper lighter than table; dark = darker
    threshold: str = "otsu"          # otsu | fixed
    fixed_threshold: int = 128
    min_rectangularity: float = 0.92  # contour area / fitted-quad area
    border_margin_px: int = 4        # a contour touching the image edge is rejected (partly out of view)
    marker_mask_pad: float = 0.35    # fraction of marker size added around each marker when masking


@dataclass
class OutputConfig:
    directory: str = "runs"
    frames_per_placement: int = 10   # frames averaged for one repeatability placement


@dataclass
class Config:
    units: str = "in"
    layout_confirmed: bool = False   # set true once Ben has measured marker positions + paper
    camera: CameraConfig = field(default_factory=CameraConfig)
    markers: MarkerConfig = field(default_factory=MarkerConfig)
    paper: PaperConfig = field(default_factory=PaperConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def validate(self) -> None:
        ids = list(self.markers.positions)
        if len(ids) != 4:
            raise ValueError(f"markers.positions must list exactly 4 marker IDs, got {ids}")
        if self.paper.length < self.paper.width:
            raise ValueError("paper.length must be the long side (length >= width)")
        if self.paper.polarity not in ("bright", "dark"):
            raise ValueError("paper.polarity must be 'bright' or 'dark'")
        if self.paper.threshold not in ("otsu", "fixed"):
            raise ValueError("paper.threshold must be 'otsu' or 'fixed'")


def _build(cls: type, data: dict[str, Any] | None) -> Any:
    data = data or {}
    kwargs: dict[str, Any] = {}
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"unknown {cls.__name__} keys: {sorted(unknown)}")
    for name, value in data.items():
        default = known[name].default_factory() if callable(known[name].default_factory) else None  # type: ignore[misc]
        if is_dataclass(default):
            kwargs[name] = _build(type(default), value)
        else:
            kwargs[name] = value
    obj = cls(**kwargs)
    if isinstance(obj, MarkerConfig):
        obj.positions = {int(k): (float(v[0]), float(v[1])) for k, v in obj.positions.items()}
    return obj


def load_config(path: str | Path) -> Config:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = _build(Config, raw)
    cfg.validate()
    return cfg
