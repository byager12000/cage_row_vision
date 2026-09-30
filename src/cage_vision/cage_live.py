"""Cage position test: teach a target, then move the cage by known amounts and score IN/OUT.

Commands (see main.py):
    cage-live  [--label cagetest]   window + guided trials (T teach, SPACE record, N skip, Q quit)
    cage-check [--teach]            no window: measure the cage now (and optionally teach it as the target)
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .cage import CagePose, check_target, detect_cage, footprint_corners, load_target, save_target
from .camera_model import estimate_camera
from .config import Config
from .geometry import angle_diff
from .logger import RunLogger
from .pipeline import Pipeline

GREEN, RED, AMBER, CYAN, WHITE, BLACK = (0, 200, 0), (0, 0, 230), (0, 170, 255), (255, 200, 0), (255, 255, 255), (0, 0, 0)


@dataclass
class Trial:
    label: str
    dx: float = 0.0          # intended move from the target, +X = toward marker 1 (right)
    dy: float = 0.0          # +Y = toward marker 3 (away from you)
    twist_in: float = 0.0    # right end moved away from you by this, pivoting on the left-near corner

    def expected(self, cfg: Config) -> tuple[float, float, float, float]:
        """(dx, dy, dangle_deg, max corner move) of the cage centre for this trial."""
        L, W = cfg.cage.bottom_length, cfg.cage.bottom_width
        if self.twist_in:
            a = np.arctan2(self.twist_in, L)
            pivot = np.array([-L / 2, -W / 2])                       # left-near corner, cage frame
            c = pivot + np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]) @ -pivot
            corners = [np.array([sx * L / 2, sy * W / 2]) for sx in (-1, 1) for sy in (-1, 1)]
            rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
            dev = max(np.linalg.norm(pivot + rot @ (k - pivot) - k) for k in corners)
            return float(c[0]), float(c[1]), float(np.degrees(a)), float(dev)
        return self.dx, self.dy, 0.0, float(np.hypot(self.dx, self.dy))


PROTOCOL = [
    Trial("At the target (both gaps at the start gap)"),
    Trial("Slide RIGHT 1/4 in (left gap +1/4)", dx=0.25),
    Trial("Slide RIGHT 3/8 in (left gap +3/8)", dx=0.375),
    Trial("Slide RIGHT 5/8 in (left gap +5/8)", dx=0.625),
    Trial("Slide RIGHT 1 in (left gap +1)", dx=1.0),
    Trial("Back to the target"),
    Trial("Slide AWAY from you 1/4 in (near gap +1/4)", dy=0.25),
    Trial("Slide AWAY 3/8 in (near gap +3/8)", dy=0.375),
    Trial("Slide AWAY 5/8 in (near gap +5/8)", dy=0.625),
    Trial("Slide AWAY 1 in (near gap +1)", dy=1.0),
    Trial("Back to the target"),
    Trial("Twist: left-near corner stays, RIGHT end 1/4 in away from you", twist_in=0.25),
    Trial("Twist: left-near corner stays, RIGHT end 3/4 in away from you", twist_in=0.75),
    Trial("Back to the target"),
]


def _measure(cam_read, pipe: Pipeline, cfg: Config, n: int):
    """n frames -> list of (frame, CagePose, cal, camera model). Invalid calibrations give undetected poses."""
    out = []
    for _ in range(n):
        frame = cam_read()
        if frame is None:
            break
        m, cal, _ = pipe.process(frame)
        if cal.valid:
            cm = estimate_camera(cal.H, (frame.shape[1], frame.shape[0]), cfg.camera.height_above_table)
            pose = detect_cage(frame, cal, cm, cfg)
        else:
            cm, pose = None, CagePose(False, f"calibration invalid: {cal.reason}")
        out.append((frame, pose, cal, cm))
    return out


def _median_pose(poses: list[CagePose]) -> CagePose:
    c = np.median([p.center for p in poses], axis=0)
    a0 = poses[0].angle_deg
    a = float(np.median([a0 + angle_diff(p.angle_deg, a0) for p in poses]))
    return CagePose(True, "", c, a, float(np.median([p.length for p in poses])), float(np.median([p.width for p in poses])))


def _draw(frame, pose: CagePose, cal, cm, cfg: Config, target: dict | None, lines_extra: list[str]):
    img = frame.copy()
    h = cfg.cage.height
    def rim_to_img(corners):
        table = cm.from_height(corners, h)
        return cv2.perspectiveTransform(table.reshape(-1, 1, 2), cal.H_inv).reshape(-1, 2).astype(np.int32)
    res = None
    if target is not None and cm is not None and cal.valid:
        tc = footprint_corners(np.array(target["center"]), target["angle_deg"], cfg.cage.rim_length, cfg.cage.rim_width)
        cv2.polylines(img, [rim_to_img(tc)], True, CYAN, 2, cv2.LINE_AA)
    if pose.detected:
        if target is not None:
            res = check_target(pose, target, cfg)
        col = GREEN if (res is None or res["in_position"]) else RED
        cv2.polylines(img, [pose.outline_img.astype(np.int32).reshape(-1, 1, 2)], True, col, 2, cv2.LINE_AA)
        cv2.polylines(img, [rim_to_img(footprint_corners(pose.center, pose.angle_deg, pose.length, pose.width))], True, col, 1, cv2.LINE_AA)
        lines = [f"CAGE  X {pose.center[0]:7.3f}  Y {pose.center[1]:7.3f} in  angle {pose.angle_deg:+.2f} deg",
                 f"rim {pose.length:.2f} x {pose.width:.2f} in"]
        if res:
            lines.insert(0, ("IN POSITION" if res["in_position"] else "OUT OF POSITION")
                         + f"   worst corner {res['max_corner_dev']:.3f} in (limit {cfg.cage.position_tolerance})")
            lines.append(f"vs target: dX {res['dx']:+.3f}  dY {res['dy']:+.3f} in  dA {res['dangle_deg']:+.2f} deg")
        else:
            lines.insert(0, "NO TARGET - place the cage at the target and press T")
    else:
        col = RED
        lines = [f"NO CAGE: {pose.reason}"[:95]]
    lines += lines_extra
    scale = img.shape[1] / 1920
    y = int(40 * scale)
    band = img[0:y + int(34 * scale) * len(lines), :]
    band[:] = (band * 0.35).astype(np.uint8)
    for i, s in enumerate(lines):
        c = col if i == 0 else (AMBER if s.startswith("NEXT") else WHITE)
        cv2.putText(img, s, (15, y + i * int(34 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.85 * scale, BLACK, 5, cv2.LINE_AA)
        cv2.putText(img, s, (15, y + i * int(34 * scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.85 * scale, c, 2, cv2.LINE_AA)
    cv2.rectangle(img, (0, 0), (img.shape[1] - 1, img.shape[0] - 1), col, 6)
    return img


TRIAL_FIELDS = ["trial", "label", "frames_valid", "intended_dx", "intended_dy", "intended_dangle", "intended_corner",
                "expected_in", "measured_dx", "measured_dy", "measured_dangle", "measured_corner", "in_position",
                "correct", "err_dx", "err_dy", "err_dangle", "rim_length", "rim_width", "reason"]


def _summary(rows: list[dict], cfg: Config) -> str:
    ok = [r for r in rows if r["frames_valid"]]
    lines = ["# Cage position test", "",
             f"Tolerance: every footprint corner within {cfg.cage.position_tolerance} in of the taught target.",
             "Intended moves are set by hand with a tape measure (about +/-1/32 to 1/16 in).", "",
             "| # | move | expected | measured | worst corner (in) | dX err | dY err | dA err (deg) |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r["frames_valid"]:
            lines.append(f"| {r['trial']} | {r['label']} | - | NO CAGE | - | - | - | - |")
            continue
        lines.append(f"| {r['trial']} | {r['label']} | {'IN' if r['expected_in'] else 'OUT'} | "
                     f"{'IN' if r['in_position'] else 'OUT'}{'' if r['correct'] else ' (WRONG)'} | "
                     f"{r['measured_corner']:.3f} | {r['err_dx']:+.3f} | {r['err_dy']:+.3f} | {r['err_dangle']:+.2f} |")
    if ok:
        lines += ["", f"- IN/OUT correct: {sum(r['correct'] for r in ok)}/{len(ok)}",
                  f"- Largest move error: X {max(abs(r['err_dx']) for r in ok):.3f} in, Y {max(abs(r['err_dy']) for r in ok):.3f} in, "
                  f"angle {max(abs(r['err_dangle']) for r in ok):.2f} deg",
                  "- 'Back to the target' rows measure how well the cage is re-placed by hand plus the system's repeatability."]
    return "\n".join(lines) + "\n"


def run_cage_live(cfg: Config, label: str, run_info: dict) -> int:
    from .camera import Camera
    if not cfg.camera.height_above_table:
        print("set camera.height_above_table in config.yaml (tape: table to lens)", file=sys.stderr)
        return 1
    cam = Camera(cfg.camera)
    pipe = Pipeline(cfg)
    log = RunLogger(cfg.output.directory, label, {**run_info, "camera_actual": cam.actual_settings()})
    target = load_target(cfg)
    rows: list[dict] = []
    k = 0
    win = "cage position test (STK-14)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    print("keys: T = teach target, SPACE = record the current trial, N = skip trial, Q = quit")
    try:
        while True:
            (frame, pose, cal, cm), = _measure(cam.read, pipe, cfg, 1) or [(None, None, None, None)]
            if frame is None:
                print("camera returned no frame", file=sys.stderr)
                break
            nxt = (f"NEXT {k + 1}/{len(PROTOCOL)}: {PROTOCOL[k].label}, hands clear, SPACE" if k < len(PROTOCOL)
                   else "All trials done - Q to finish")
            if target is None:
                nxt = "NEXT: put the cage at the target, lay the reference tape, hands clear, press T"
            cv2.imshow(win, _draw(frame, pose, cal, cm, cfg, target, [nxt]))
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("t"):
                got = [p for _, p, _, _ in _measure(cam.read, pipe, cfg, 10) if p.detected]
                if len(got) < 8:
                    print(f"teach failed: cage seen in only {len(got)}/10 frames")
                    continue
                target = save_target(cfg, got)
                print(f"target taught: {target}")
            if key == ord("n") and k < len(PROTOCOL):
                k += 1
            if key == ord(" ") and k < len(PROTOCOL) and target is not None:
                meas = _measure(cam.read, pipe, cfg, 10)
                got = [p for _, p, _, _ in meas if p.detected]
                t = PROTOCOL[k]
                edx, edy, eda, edev = t.expected(cfg)
                row = {"trial": k + 1, "label": t.label, "frames_valid": len(got), "intended_dx": edx, "intended_dy": edy,
                       "intended_dangle": eda, "intended_corner": edev, "expected_in": edev <= cfg.cage.position_tolerance}
                if got:
                    med = _median_pose(got)
                    r = check_target(med, target, cfg)
                    row.update(measured_dx=r["dx"], measured_dy=r["dy"], measured_dangle=r["dangle_deg"],
                               measured_corner=r["max_corner_dev"], in_position=r["in_position"],
                               correct=r["in_position"] == row["expected_in"], err_dx=r["dx"] - edx, err_dy=r["dy"] - edy,
                               err_dangle=r["dangle_deg"] - eda, rim_length=med.length, rim_width=med.width, reason="")
                    print(f"trial {k + 1}: {'IN' if r['in_position'] else 'OUT'} (expected {'IN' if row['expected_in'] else 'OUT'})  "
                          f"dX {r['dx']:+.3f} dY {r['dy']:+.3f} in dA {r['dangle_deg']:+.2f} deg  "
                          f"(intended {edx:+.3f} {edy:+.3f} {eda:+.2f})  worst corner {r['max_corner_dev']:.3f}")
                else:
                    row["reason"] = meas[-1][1].reason if meas else "no frames"
                    print(f"trial {k + 1}: no cage - {row['reason']}")
                f0, p0, c0, m0 = meas[0]
                cv2.imwrite(str(log.dir / "frames" / f"trial{k + 1:02d}_raw.png"), f0)
                cv2.imwrite(str(log.dir / "frames" / f"trial{k + 1:02d}_annotated.jpg"), _draw(f0, p0, c0, m0, cfg, target, [t.label]))
                rows.append(row)
                k += 1
    finally:
        cam.release()
        cv2.destroyAllWindows()
        log.close()
    if rows:
        with open(log.dir / "trials.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=TRIAL_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({f: r.get(f, "") for f in TRIAL_FIELDS})
        (log.dir / "summary.md").write_text(_summary(rows, cfg), encoding="utf-8")
        (log.dir / "target.json").write_text(json.dumps(target, indent=2), encoding="utf-8")
        print((log.dir / "summary.md").read_text(encoding="utf-8"))
    print(f"run folder: {log.dir}")
    return 0


def run_cage_check(cfg: Config, teach: bool, frames: int, save_dir: str | None) -> int:
    from .camera import Camera
    cam = Camera(cfg.camera)
    pipe = Pipeline(cfg)
    try:
        meas = _measure(cam.read, pipe, cfg, frames)
    finally:
        cam.release()
    got = [p for _, p, _, _ in meas if p.detected]
    print(f"cage seen in {len(got)}/{len(meas)} frames" + ("" if got else f" - {meas[-1][1].reason}"))
    if save_dir:
        f0, p0, c0, m0 = meas[-1]
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(Path(save_dir) / "cage_check_raw.png"), f0)
        cv2.imwrite(str(Path(save_dir) / "cage_check.jpg"), _draw(f0, p0, c0, m0, cfg, load_target(cfg), []))
    if not got:
        return 1
    med = _median_pose(got)
    spread = max(np.linalg.norm(p.center - med.center) for p in got)
    print(f"cage at X {med.center[0]:.3f} Y {med.center[1]:.3f} in, angle {med.angle_deg:+.2f} deg, "
          f"rim {med.length:.2f} x {med.width:.2f} in (frame spread {spread:.3f} in)")
    if teach:
        print("target taught:", save_target(cfg, got))
    target = load_target(cfg)
    if target:
        r = check_target(med, target, cfg)
        print(f"{'IN POSITION' if r['in_position'] else 'OUT OF POSITION'}: dX {r['dx']:+.3f} dY {r['dy']:+.3f} in, "
              f"dA {r['dangle_deg']:+.2f} deg, worst corner {r['max_corner_dev']:.3f} in (limit {cfg.cage.position_tolerance})")
    return 0
