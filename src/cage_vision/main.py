"""Command-line entry point. Run as `uv run python -m cage_vision <command>` (Smart App Control
blocks the generated cage-vision.exe launcher on Ben's laptop).

    list-cameras
    set-baseline                [--image FILE ...]   record marker positions once the bench is verified
    live                        [--label bench]
    images DIR                  [--no-baseline]      process saved images (manifest.json optional)
    synth DIR                   [--placements 25 --frames 5 --k1 0]
    report RUN_DIR
    make-markers                [--out markers]      printable reference markers (PDF)
    cage-live                   [--label cagetest]   cage position test: teach target, guided moves, IN/OUT
    cage-check                  [--teach]            no window: measure the cage now (optionally teach target)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .baseline import load_baseline, make_baseline, save_baseline
from .calibration import calibrate, make_detector
from .config import Config, load_config
from .logger import RunLogger, summarize
from .overlay import draw
from .pipeline import Pipeline

DEFAULT_CONFIG = "config.yaml"


def _warn_layout(cfg: Config) -> None:
    if not cfg.layout_confirmed:
        print("WARNING: layout_confirmed is false - marker positions / paper size in the config are placeholders.\n"
              "         Measurements are only as good as those numbers.", file=sys.stderr)


def _pick_camera(cfg: Config) -> None:
    from .camera import resolve_camera_index
    cfg.camera.index = resolve_camera_index(cfg.camera, set(cfg.markers.positions), make_detector(cfg.markers))


def _run_info(cfg: Config, **extra) -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "src"], capture_output=True, text=True).stdout.strip())
    except OSError:
        rev, dirty = "unknown", None
    return {"started": datetime.now().isoformat(timespec="seconds"), "git": rev, "src_uncommitted_changes": dirty,
            "config": asdict(cfg), "baseline": load_baseline(cfg), **extra}


def cmd_set_baseline(args, cfg: Config) -> int:
    """Record where the four markers sit in the image. Do this only after the bench layout is verified."""
    det = make_detector(cfg.markers)
    probe = cfg.markers.__class__(**{**asdict(cfg.markers), "require_baseline": False})
    frames: list[dict] = []
    if args.image:
        sources = [cv2.imread(f) for f in args.image]
        label = ", ".join(args.image)
    else:
        from .camera import Camera
        _pick_camera(cfg)
        cam = Camera(cfg.camera)
        sources = [cam.read() for _ in range(args.frames)]
        cam.release()
        label = f"camera {cfg.camera.index}, {args.frames} frames"
    for img in sources:
        if img is None:
            print("could not read a frame", file=sys.stderr)
            return 1
        cal = calibrate(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), probe, det)
        if not cal.valid:
            print(f"cannot set baseline: {cal.reason}", file=sys.stderr)
            return 1
        frames.append({i: c.mean(axis=0) for i, c in cal.marker_corners.items()})
    try:
        data = make_baseline(cfg, frames, label)
    except RuntimeError as e:
        print(f"cannot set baseline: {e}", file=sys.stderr)
        return 1
    old = load_baseline(cfg)
    path = save_baseline(cfg, data)
    print(f"baseline written to {path} ({data['frames']} frames, spread {data['spread_px']} px)")
    if old:
        print(f"  (replaced baseline from {old.get('created')})")
    return 0


def cmd_list_cameras(args, cfg: Config) -> int:
    from .camera import list_cameras
    for c in list_cameras(backend=cfg.camera.backend):
        print(c)
    return 0


def cmd_live(args, cfg: Config) -> int:
    from .camera import Camera
    _warn_layout(cfg)
    _pick_camera(cfg)
    cam = Camera(cfg.camera)
    print("camera settings actually applied:", json.dumps(cam.actual_settings()))
    pipe = Pipeline(cfg)
    if pipe.baseline is None and cfg.markers.require_baseline:
        print("WARNING: no setup baseline - every frame will be INVALID. Verify the bench, then run set-baseline.",
              file=sys.stderr)
    log = RunLogger(cfg.output.directory, args.label, _run_info(cfg, camera_actual=cam.actual_settings()))
    print(f"logging to {log.dir}")
    s = cam.actual_settings()
    if (s["width"], s["height"]) != (cfg.camera.width, cfg.camera.height):
        print(f"WARNING: asked for {cfg.camera.width}x{cfg.camera.height}, camera gave {s['width']}x{s['height']}",
              file=sys.stderr)
    print("keys: SPACE = record a placement (averages frames_per_placement frames), "
          "S = save this frame, C = camera settings dialog, Q/ESC = quit + write report")
    placement, win = 0, "cage-vision (STK-14 P0)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    try:
        while True:
            frame = cam.read()
            if frame is None:
                print("camera returned no frame", file=sys.stderr)
                break
            m, cal, det = pipe.process(frame)
            view = draw(frame, m, cal, det, cfg)
            _text_footer(view, f"placements: {placement}   focus sharpness: {_sharpness(frame):.0f} (turn ring for max)"
                               "   SPACE record  S save  C camera settings  Q quit")
            cv2.imshow(win, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("c") and not cam.open_settings_dialog():
                print("camera settings dialog not available (needs backend: dshow)", file=sys.stderr)
            if key == ord("s"):
                log.log(m, "snap", int(cv2.getTickCount() % 100000), "camera", view, frame)
            if key == ord(" "):
                placement += 1
                burst = []
                for f in range(cfg.output.frames_per_placement):
                    fr = frame if f == 0 else cam.read()
                    if fr is None:
                        break
                    mm, cc, dd = pipe.process(fr)
                    # Keep images of frame 0 and of every failed frame, so failures can be diagnosed later.
                    keep = f == 0 or not mm.valid
                    log.log(mm, placement, f, "camera", draw(fr, mm, cc, dd, cfg) if keep else None, fr if keep else None)
                    burst.append(mm)
                ok = [b for b in burst if b.valid]
                if ok:
                    print(f"placement {placement}: {len(ok)}/{len(burst)} frames valid  "
                          f"X={np.mean([b.center_x for b in ok]):.3f} Y={np.mean([b.center_y for b in ok]):.3f} "
                          f"A={np.mean([b.rotation_deg for b in ok]):.2f}"
                          + ("" if len(ok) == len(burst) else "  (some frames invalid - keep hands clear until done)"))
                else:
                    print(f"placement {placement}: 0/{len(burst)} frames valid - {burst[-1].status_text if burst else 'no frames'}")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        log.close()
    if placement:
        print((log.dir / "report.md").read_text(encoding="utf-8") if _report(log.dir, cfg) else "")
    else:
        print("No placements were recorded, so there is no report. Press SPACE in the video window "
              "after each placement; the 'placements:' counter at the bottom goes up each time.")
    print(f"run folder: {log.dir}")
    return 0


def _sharpness(frame) -> float:
    """Focus aid: variance of the Laplacian over the central half of the frame. Higher = sharper."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    return float(cv2.Laplacian(g[h // 4:3 * h // 4, w // 4:3 * w // 4], cv2.CV_64F).var())


def _text_footer(img, s):
    h = img.shape[0]
    cv2.putText(img, s, (15, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(img, s, (15, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)


def _report(run_dir: Path, cfg: Config) -> dict:
    return summarize(run_dir, cfg.paper.length, cfg.paper.width)


def cmd_images(args, cfg: Config) -> int:
    """Process a folder of saved frames. With manifest.json, also check expectations + ground truth."""
    _warn_layout(cfg)
    src = Path(args.dir)
    man_path = src / "manifest.json"
    if man_path.exists():
        entries = json.loads(man_path.read_text(encoding="utf-8"))
    else:
        files = sorted(p for p in src.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"))
        entries = [{"file": p.name, "placement": p.stem, "frame": 0, "expect": None, "gt": None} for p in files]

    if args.no_baseline:   # synthetic scenes: each render has its own camera, so a bench baseline is meaningless
        cfg.markers.require_baseline = False
        pipe = Pipeline(cfg, baseline=None)
    else:
        pipe = Pipeline(cfg)
    log = RunLogger(cfg.output.directory, args.label, _run_info(cfg, source=str(src)))
    mismatches = []
    for e in entries:
        img = cv2.imread(str(src / e["file"]))
        if img is None:
            mismatches.append(f"{e['file']}: unreadable")
            continue
        m, cal, det = pipe.process(img)
        save = e["frame"] == 0
        log.log(m, e["placement"], e["frame"], e["file"], draw(img, m, cal, det, cfg) if save else None,
                gt=tuple(e["gt"]) if e.get("gt") else None)
        if e.get("expect") == "valid" and not m.valid:
            mismatches.append(f"{e['file']}: expected valid, got {m.status_text}")
        if e.get("expect") == "invalid" and m.valid:
            mismatches.append(f"{e['file']}: expected INVALID but reported X={m.center_x:.3f} Y={m.center_y:.3f}")
    log.close()
    rep = _report(log.dir, cfg)
    print(f"run: {log.dir}")
    print((log.dir / "report.md").read_text(encoding="utf-8"))
    if mismatches:
        print("EXPECTATION MISMATCHES:")
        for s in mismatches:
            print("  " + s)
    (log.dir / "expectation_mismatches.json").write_text(json.dumps(mismatches, indent=1), encoding="utf-8")
    return 1 if mismatches else 0


def cmd_synth(args, cfg: Config) -> int:
    from .synth import make_suite
    out = make_suite(cfg, args.dir, args.placements, args.frames, args.seed, args.k1)
    print(f"synthetic suite written to {out}")
    return 0


def cmd_report(args, cfg: Config) -> int:
    _report(Path(args.run_dir), cfg)
    print((Path(args.run_dir) / "report.md").read_text(encoding="utf-8"))
    return 0


def cmd_make_markers(args, cfg: Config) -> int:
    """Printable markers: one vector PDF, one US-letter page per marker, true size at 100%."""
    from .markers import write_marker_pdf
    path = write_marker_pdf(cfg, Path(args.out) / "markers.pdf")
    print(f"wrote {path}  ({len(cfg.markers.positions)} pages, black square = {cfg.markers.size:g} {cfg.units})")
    return 0


def cmd_cage_live(args, cfg: Config) -> int:
    from .cage_live import run_cage_live
    _pick_camera(cfg)
    return run_cage_live(cfg, args.label, _run_info(cfg))


def cmd_cage_check(args, cfg: Config) -> int:
    from .cage_live import run_cage_check
    _pick_camera(cfg)
    return run_cage_check(cfg, args.teach, args.frames, args.save)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cage_vision", description="STK-14 Phase 1 paper detection bench prototype")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-cameras")
    p = sub.add_parser("set-baseline"); p.add_argument("--image", nargs="+"); p.add_argument("--frames", type=int, default=15)
    p = sub.add_parser("live"); p.add_argument("--label", default="bench")
    p = sub.add_parser("images"); p.add_argument("dir"); p.add_argument("--label", default="images")
    p.add_argument("--no-baseline", action="store_true", help="synthetic scenes only: skip the bench baseline check")
    p = sub.add_parser("synth"); p.add_argument("dir")
    p.add_argument("--placements", type=int, default=25); p.add_argument("--frames", type=int, default=5)
    p.add_argument("--seed", type=int, default=1); p.add_argument("--k1", type=float, default=0.0)
    p = sub.add_parser("report"); p.add_argument("run_dir")
    p = sub.add_parser("make-markers"); p.add_argument("--out", default="markers")
    p = sub.add_parser("cage-live"); p.add_argument("--label", default="cagetest")
    p = sub.add_parser("cage-check"); p.add_argument("--teach", action="store_true")
    p.add_argument("--frames", type=int, default=10); p.add_argument("--save")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    return {"list-cameras": cmd_list_cameras, "set-baseline": cmd_set_baseline, "live": cmd_live, "images": cmd_images, "synth": cmd_synth,
            "report": cmd_report, "make-markers": cmd_make_markers, "cage-live": cmd_cage_live,
            "cage-check": cmd_cage_check}[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
