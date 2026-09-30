"""Run folders: measurements CSV, annotated frames, and a repeatability report.

Layout of one run:
    runs/<YYYYmmdd-HHMMSS>_<label>/
        measurements.csv   one row per processed frame
        frames/            annotated images (plus raw frames when requested)
        report.json / report.md   written by `summarize`
"""

from __future__ import annotations

import csv
import json
import math
import statistics as st
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .geometry import angle_diff
from .pipeline import Measurement

FIELDS = ["placement", "frame", "source", "timestamp", "calibration_ok", "calibration_reason",
          "object_detected", "detection_reason", "center_x", "center_y", "rotation_deg", "length", "width",
          "marker_size_error", "marker_move_px", "marker_sizes", "warnings", "units", "gt_x", "gt_y", "gt_rotation_deg"]


class RunLogger:
    def __init__(self, root: str | Path, label: str, info: dict | None = None):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = Path(root) / f"{stamp}_{label}"
        (self.dir / "frames").mkdir(parents=True, exist_ok=True)
        if info is not None:   # makes the run self-describing: config, baseline, camera, code version
            (self.dir / "run_info.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
        self.csv_path = self.dir / "measurements.csv"
        self._fh = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._fh, fieldnames=FIELDS)
        self._w.writeheader()

    def log(self, m: Measurement, placement: int | str, frame: int, source: str = "",
            annotated: np.ndarray | None = None, raw: np.ndarray | None = None,
            gt: tuple[float, float, float] | None = None) -> None:
        row = {k: ("" if v is None else v) for k, v in asdict(m).items()}
        row.update(placement=placement, frame=frame, source=source)
        if gt is not None:
            row.update(gt_x=gt[0], gt_y=gt[1], gt_rotation_deg=gt[2])
        self._w.writerow({k: row.get(k, "") for k in FIELDS})
        self._fh.flush()
        name = f"p{placement}_f{frame:03d}" if isinstance(placement, int) else f"{placement}_f{frame:03d}"
        if annotated is not None:
            cv2.imwrite(str(self.dir / "frames" / f"{name}_annotated.jpg"), annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if raw is not None:
            cv2.imwrite(str(self.dir / "frames" / f"{name}_raw.png"), raw)

    def close(self) -> None:
        self._fh.close()


def _f(v: str) -> float | None:
    return float(v) if v not in ("", None) else None


def _stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": st.fmean(xs), "std": st.pstdev(xs) if len(xs) > 1 else 0.0,
            "max_abs": max(abs(x) for x in xs)}


def summarize(run_dir: str | Path, nominal_length: float, nominal_width: float) -> dict:
    run_dir = Path(run_dir)
    with open(run_dir / "measurements.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    units = rows[0]["units"] if rows else ""

    by_p: dict[str, list[dict]] = {}
    for r in rows:
        by_p.setdefault(r["placement"], []).append(r)

    placements = []
    for pid, rs in by_p.items():
        ok = [r for r in rs if r["object_detected"] == "True" and r["calibration_ok"] == "True"]
        entry = {"placement": pid, "frames": len(rs), "valid_frames": len(ok),
                 "failures": sorted({r["calibration_reason"] or r["detection_reason"] for r in rs if r not in ok})}
        if ok:
            xs, ys = [_f(r["center_x"]) for r in ok], [_f(r["center_y"]) for r in ok]
            angs = [_f(r["rotation_deg"]) for r in ok]
            a0 = angs[0]
            angs_u = [a0 + angle_diff(a, a0) for a in angs]  # unwrap around +/-90
            entry.update(
                x_mean=st.fmean(xs), y_mean=st.fmean(ys), angle_mean=st.fmean(angs_u),
                x_std=st.pstdev(xs), y_std=st.pstdev(ys), angle_std=st.pstdev(angs_u),
                length_mean=st.fmean(_f(r["length"]) for r in ok), width_mean=st.fmean(_f(r["width"]) for r in ok),
            )
            if ok[0]["gt_x"]:
                gx, gy, ga = _f(ok[0]["gt_x"]), _f(ok[0]["gt_y"]), _f(ok[0]["gt_rotation_deg"])
                entry.update(err_x=entry["x_mean"] - gx, err_y=entry["y_mean"] - gy,
                             err_angle=angle_diff(entry["angle_mean"], ga))
        placements.append(entry)

    good = [p for p in placements if p["valid_frames"]]
    report = {
        "run": run_dir.name, "units": units,
        "placements": len(placements), "placements_detected": len(good),
        "frames": len(rows), "frames_valid": sum(p["valid_frames"] for p in placements),
        # Frame-to-frame noise with the paper stationary (camera + detection jitter)
        "within_placement_std": {
            "x": _stats([p["x_std"] for p in good]), "y": _stats([p["y_std"] for p in good]),
            "angle": _stats([p["angle_std"] for p in good]),
        },
        # Measured size vs nominal across all placements: a scale/perspective accuracy check
        # that needs no ruler (only the paper's true size).
        "size_error": {
            "length": _stats([p["length_mean"] - nominal_length for p in good]),
            "width": _stats([p["width_mean"] - nominal_width for p in good]),
        },
        "failures": sorted({f for p in placements for f in p["failures"]}),
        "per_placement": placements,
    }
    if any("err_x" in p for p in good):
        e = [p for p in good if "err_x" in p]
        report["position_error_vs_ground_truth"] = {
            "x": _stats([p["err_x"] for p in e]), "y": _stats([p["err_y"] for p in e]),
            "radial": _stats([math.hypot(p["err_x"], p["err_y"]) for p in e]),
            "angle": _stats([p["err_angle"] for p in e]),
        }

    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _fmt(s: dict, unit: str) -> str:
    if not s.get("n"):
        return "n/a"
    return f"mean {s['mean']:+.4f}, std {s['std']:.4f}, max |{s['max_abs']:.4f}| {unit} (n={s['n']})"


def _markdown(r: dict) -> str:
    u = r["units"]
    partial = [p for p in r["per_placement"] if 0 < p["valid_frames"] < p["frames"]]
    out = [f"# Frame noise and size-consistency report — {r['run']}", "",
           "Frame-to-frame noise is the population std over each placement's burst (sheet untouched, ~2 s).",
           "It is not re-placement repeatability, and there is no ground-truth position error unless gt columns exist.", "",
           f"- Placements: {r['placements_detected']} / {r['placements']} detected",
           f"- Frames: {r['frames_valid']} / {r['frames']} valid", ""]
    if partial:
        out += ["Placements with some invalid frames: "
                + ", ".join(f"{p['placement']} ({p['valid_frames']}/{p['frames']})" for p in partial), ""]
    out += ["## Frame-to-frame noise (sheet stationary)",
           f"- X std: {_fmt(r['within_placement_std']['x'], u)}",
           f"- Y std: {_fmt(r['within_placement_std']['y'], u)}",
           f"- Angle std: {_fmt(r['within_placement_std']['angle'], 'deg')}", "",
           "## Measured size vs nominal",
           f"- Length error: {_fmt(r['size_error']['length'], u)}",
           f"- Width error: {_fmt(r['size_error']['width'], u)}", ""]
    if "position_error_vs_ground_truth" in r:
        g = r["position_error_vs_ground_truth"]
        out += ["## Error vs ground truth",
                f"- X: {_fmt(g['x'], u)}", f"- Y: {_fmt(g['y'], u)}",
                f"- Radial: {_fmt(g['radial'], u)}", f"- Angle: {_fmt(g['angle'], 'deg')}", ""]
    if r["failures"]:
        out += ["## Failure reasons seen", *[f"- {f}" for f in r["failures"]], ""]
    return "\n".join(out)
