"""Cage position test with a taught outline: any cage shape (selected by cage.method: outline).

    cage-live  [--label NAME] [--height H]   window + guided trials (T teach, SPACE record, N skip, Q quit)
    cage-check [--teach] [--height H]        no window: find cages, optionally teach, compare with the target
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from .cage import load_target
from .cage_live import AMBER, BLACK, CYAN, GREEN, RED, TRIAL_FIELDS, WHITE, _summary
from .camera_model import estimate_camera
from .config import Config
from .logger import RunLogger
from .outline import compare, find_cages, pick, save_outline_target
from .pipeline import Pipeline


FRACTIONS = {0.125: "1/8", 0.25: "1/4", 0.375: "3/8", 0.5: "1/2", 0.625: "5/8", 0.75: "3/4", 1.0: "1"}


def _rot(a: float) -> np.ndarray:
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


@dataclass
class OTrial:
    """A guided move relative to the taught target. World axes: +X = right (toward marker 1), +Y = away from you."""
    label: str
    dx: float = 0.0
    dy: float = 0.0
    pivot: tuple | None = None      # twist: world point that stays put
    angle_deg: float = 0.0          # twist: CCW rotation about the pivot

    def expected(self, target: dict) -> tuple[float, float, float, float]:
        """(dx, dy of the taught centroid, dangle_deg, worst outline-point move) for this move."""
        P, c = np.array(target["bottom"]), np.array(target["centroid"])
        if self.pivot is not None:
            pv, R = np.array(self.pivot), _rot(np.radians(self.angle_deg))
            moved, cc = (P - pv) @ R.T + pv, R @ (c - pv) + pv
            return float(cc[0] - c[0]), float(cc[1] - c[1]), self.angle_deg, float(np.linalg.norm(moved - P, axis=1).max())
        return self.dx, self.dy, 0.0, float(np.hypot(self.dx, self.dy))


def build_protocol(target: dict | None, cfg: Config) -> list[OTrial]:
    """Guided moves. Slides use world directions (right / away from you, measured at BOTH ends of the side so the
    cage cannot pivot). Twists are built from the taught outline, so they work whichever way the cage lies:
    the near-left corner stays, the near-right corner moves away from you by d. d is picked so the worst outline
    point clearly stays IN (<= tol - 0.15) or clearly goes OUT (>= tol + 0.2).
    (The first version assumed the cage lay left-right; with its long side running away from you the
    'right end' was ambiguous and the twist expectations were wrong.)"""
    tol = cfg.cage.position_tolerance
    both = "measure the gap at BOTH ends of that side"
    trials = [OTrial("At the target (note both gaps on each side: this is the start)")]
    for d in (0.25, 0.375, 0.625, 1.0):
        trials.append(OTrial(f"Slide RIGHT {FRACTIONS[d]} in: left gap +{FRACTIONS[d]} ({both})", dx=d))
    trials.append(OTrial("Back to the target (start gaps)"))
    for d in (0.25, 0.375, 0.625, 1.0):
        trials.append(OTrial(f"Slide AWAY from you {FRACTIONS[d]} in: near gap +{FRACTIONS[d]} ({both})", dy=d))
    trials.append(OTrial("Back to the target (start gaps)"))
    if target is not None:
        P = np.array(target["bottom"], np.float32)
        corners = cv2.boxPoints(cv2.minAreaRect(P))
        near = corners[np.argsort(corners[:, 1])[:2]]
        nl, nr = near[np.argsort(near[:, 0])]
        side = float(np.linalg.norm(nr - nl))
        cands = []
        for d in sorted(FRACTIONS):
            ang = float(np.degrees(np.arctan2(d, side)))
            t = OTrial(f"Twist: keep the NEAR-LEFT corner in place, move the NEAR-RIGHT corner {FRACTIONS[d]} in AWAY from you",
                       pivot=(float(nl[0]), float(nl[1])), angle_deg=ang)
            cands.append((d, t, t.expected(target)[3]))
        ins = [c for c in cands if c[2] <= tol - 0.15]
        outs = [c for c in cands if c[2] >= tol + 0.2]
        if ins:
            trials.append(ins[-1][1])
        if outs:
            trials.append(outs[0][1])
        trials.append(OTrial("Back to the target (start gaps)"))
    return trials


def measure(cam_read, pipe: Pipeline, cfg: Config, n: int):
    """n frames -> list of (frame, cal, camera model, [CageOutline], reason)."""
    out = []
    for _ in range(n):
        frame = cam_read()
        if frame is None:
            break
        _, cal, _ = pipe.process(frame)
        if not cal.valid:
            out.append((frame, cal, None, [], f"calibration invalid: {cal.reason}"))
            continue
        cm = estimate_camera(cal.H, (frame.shape[1], frame.shape[0]), cfg.camera.height_above_table)
        cages = find_cages(frame, cal, cm, cfg)
        out.append((frame, cal, cm, cages, "" if cages else "no cage found"))
    return out


def load_outline_target(cfg: Config) -> dict | None:
    t = load_target(cfg)
    return t if t is not None and t.get("method") == "outline" else None


def draw(frame, cal, cm, cages, reason, cfg: Config, target: dict | None, lines_extra: list[str]):
    img = frame.copy()

    def bottom_to_img(pts):
        table = cm.from_height(np.asarray(pts, float), cfg.cage.base_height)
        return cv2.perspectiveTransform(table.reshape(-1, 1, 2), cal.H_inv).reshape(-1, 2).astype(np.int32)

    col, res = RED, None
    if cm is not None and target is not None:
        cv2.polylines(img, [bottom_to_img(target["bottom"])], True, CYAN, 2, cv2.LINE_AA)
    chosen = pick(cages, target) if cages else None
    partial = [o for o in cages if o.partial]
    for o in partial:
        cv2.polylines(img, [o.img_outline.astype(np.int32).reshape(-1, 1, 2)], True, AMBER, 2, cv2.LINE_AA)
    for o in cages:
        if o is not chosen and not o.partial:
            cv2.polylines(img, [o.img_outline.astype(np.int32).reshape(-1, 1, 2)], True, (160, 160, 160), 1, cv2.LINE_AA)
    if chosen is not None:
        if target is not None:
            res = compare(target, chosen, cfg.cage.position_tolerance)
        col = GREEN if (res is None or res["in_position"]) else RED
        cv2.polylines(img, [chosen.img_outline.astype(np.int32).reshape(-1, 1, 2)], True, col, 2, cv2.LINE_AA)
        cv2.polylines(img, [bottom_to_img(chosen.bottom)], True, col, 1, cv2.LINE_AA)
        lines = [f"CAGE  centre X {chosen.centroid[0]:7.3f}  Y {chosen.centroid[1]:7.3f} in   footprint {chosen.area:.0f} sq in"]
        if res:
            lines.insert(0, ("IN POSITION" if res["in_position"] else "OUT OF POSITION")
                         + f"   worst point moved {res['max_corner_dev']:.3f} in (limit {cfg.cage.position_tolerance})")
            lines.append(f"vs taught: dX {res['dx']:+.3f}  dY {res['dy']:+.3f} in  dA {res['dangle_deg']:+.2f} deg"
                         f"   fit {res['fit_rms']:.3f} in")
        else:
            lines.insert(0, "NO TARGET - place the cage at the target and press T")
    else:
        lines = [f"NO CAGE: {reason or 'none near the taught target'}"[:95]]
    if partial:
        lines.append(f"{len(partial)} cage(s) at the edge of the marked area (orange) - move fully between the markers")
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


def burst_result(meas, target: dict, cfg: Config):
    """Median over a burst of per-frame comparisons with the taught outline."""
    rs = []
    for _, _, _, cages, _ in meas:
        o = pick(cages, target)
        if o is not None:
            rs.append(compare(target, o, cfg.cage.position_tolerance))
    if not rs:
        return None, 0
    med = {k: float(np.median([r[k] for r in rs])) for k in ("dx", "dy", "dangle_deg", "max_corner_dev", "fit_rms")}
    med["in_position"] = med["max_corner_dev"] <= cfg.cage.position_tolerance
    return med, len(rs)


def teach(meas, cfg: Config) -> dict | None:
    got = []
    for _, _, _, cages, _ in meas:
        o = pick(cages, None) if not got else pick(cages, {"centroid": list(got[0].centroid)})
        if o is not None:
            got.append(o)
    if len(got) < max(3, int(0.8 * len(meas))):
        print(f"teach failed: cage seen in only {len(got)}/{len(meas)} frames")
        return None
    t = save_outline_target(cfg, got)
    print(f"target taught: centre ({t['centroid'][0]:.3f}, {t['centroid'][1]:.3f}) in, footprint {t['area']:.1f} sq in, "
          f"frame spread {t['spread_in']:.3f} in  -> {cfg.cage.target_file}")
    return t


def run_live(cfg: Config, label: str, run_info: dict) -> int:
    from .camera import Camera
    if not cfg.camera.height_above_table:
        print("set camera.height_above_table in the config (tape: marker plane to lens)", file=sys.stderr)
        return 1
    cam = Camera(cfg.camera)
    pipe = Pipeline(cfg)
    log = RunLogger(cfg.output.directory, label, {**run_info, "camera_actual": cam.actual_settings()})
    target = load_outline_target(cfg)
    rows: list[dict] = []
    k = 0
    protocol = build_protocol(target, cfg)
    win = "cage position test - taught outline (STK-14)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    print("keys: T = teach target, SPACE = record the current trial, N = skip trial, Q = quit")
    try:
        while True:
            meas = measure(cam.read, pipe, cfg, 1)
            if not meas:
                print("camera returned no frame", file=sys.stderr)
                break
            nxt = (f"NEXT {k + 1}/{len(protocol)}: {protocol[k].label}, hands clear, SPACE" if k < len(protocol)
                   else "All trials done - Q to finish")
            if target is None:
                nxt = "NEXT: put the cage at the target, hands clear, press T"
            cv2.imshow(win, draw(*meas[0], cfg, target, [nxt]))
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("t"):
                target = teach(measure(cam.read, pipe, cfg, 10), cfg) or target
                protocol = build_protocol(target, cfg)          # twists depend on how the taught cage lies
                k = 0
            if key == ord("n") and k < len(protocol):
                k += 1
            if key == ord(" ") and k < len(protocol) and target is not None:
                burst = measure(cam.read, pipe, cfg, 10)
                med, nvalid = burst_result(burst, target, cfg)
                t = protocol[k]
                edx, edy, eda, edev = t.expected(target)
                row = {"trial": k + 1, "label": t.label, "frames_valid": nvalid, "intended_dx": edx, "intended_dy": edy,
                       "intended_dangle": eda, "intended_corner": edev, "expected_in": edev <= cfg.cage.position_tolerance}
                if med:
                    row.update(measured_dx=med["dx"], measured_dy=med["dy"], measured_dangle=med["dangle_deg"],
                               measured_corner=med["max_corner_dev"], in_position=med["in_position"],
                               correct=med["in_position"] == row["expected_in"], err_dx=med["dx"] - edx,
                               err_dy=med["dy"] - edy, err_dangle=med["dangle_deg"] - eda, rim_length="", rim_width="",
                               reason="")
                    print(f"trial {k + 1}: {'IN' if med['in_position'] else 'OUT'} "
                          f"(expected {'IN' if row['expected_in'] else 'OUT'})  dX {med['dx']:+.3f} dY {med['dy']:+.3f} in "
                          f"dA {med['dangle_deg']:+.2f} deg  (intended {edx:+.3f} {edy:+.3f} {eda:+.2f})  "
                          f"worst point {med['max_corner_dev']:.3f}")
                else:
                    row["reason"] = burst[-1][4] if burst else "no frames"
                    print(f"trial {k + 1}: no cage near the target - {row['reason'] or 'moved more than 4 in?'}")
                cv2.imwrite(str(log.dir / "frames" / f"trial{k + 1:02d}_raw.png"), burst[0][0])
                cv2.imwrite(str(log.dir / "frames" / f"trial{k + 1:02d}_annotated.jpg"), draw(*burst[0], cfg, target, [t.label]))
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
        (log.dir / "target.json").write_text(json.dumps(target, indent=1), encoding="utf-8")
        (log.dir / "protocol.json").write_text(json.dumps([asdict(t) for t in protocol], indent=1), encoding="utf-8")
        print((log.dir / "summary.md").read_text(encoding="utf-8"))
    print(f"run folder: {log.dir}")
    return 0


def run_check(cfg: Config, do_teach: bool, frames: int, save_dir: str | None) -> int:
    from .camera import Camera
    cam = Camera(cfg.camera)
    pipe = Pipeline(cfg)
    try:
        meas = measure(cam.read, pipe, cfg, frames)
    finally:
        cam.release()
    if not meas:
        print("camera returned no frames")
        return 1
    target = load_outline_target(cfg)
    last = meas[-1]
    whole = [o for o in last[3] if not o.partial]
    print(f"cages found: {len(whole)}" + ("" if last[3] else f" - {last[4]}"))
    for o in sorted(whole, key=lambda o: o.centroid[0]):
        print(f"   centre ({o.centroid[0]:.2f}, {o.centroid[1]:.2f}) in, footprint {o.area:.1f} sq in")
    for o in [o for o in last[3] if o.partial]:
        print(f"   PARTIAL cage near ({o.centroid[0]:.1f}, {o.centroid[1]:.1f}) in: at the edge of the marked area, not judged")
    if do_teach:
        target = teach(meas, cfg) or target
    if save_dir:
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(Path(save_dir) / "cage_check_raw.png"), last[0])
        cv2.imwrite(str(Path(save_dir) / "cage_check.jpg"), draw(*last, cfg, target, []))
    if target is not None:
        med, nvalid = burst_result(meas, target, cfg)
        if med is None:
            print("no cage within 4 in of the taught target")
            return 1
        print(f"{'IN POSITION' if med['in_position'] else 'OUT OF POSITION'} ({nvalid}/{len(meas)} frames): "
              f"dX {med['dx']:+.3f} dY {med['dy']:+.3f} in, dA {med['dangle_deg']:+.2f} deg, "
              f"worst point moved {med['max_corner_dev']:.3f} in (limit {cfg.cage.position_tolerance}), "
              f"fit {med['fit_rms']:.3f} in")
    return 0
