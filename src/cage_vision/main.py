"""Command-line entry point.

    cage-vision list-cameras
    cage-vision live            [--config config.yaml] [--label bench]
    cage-vision images DIR      [--config ...]   process saved images (manifest.json optional)
    cage-vision synth DIR       [--placements 25 --frames 5 --k1 0]
    cage-vision report RUN_DIR  [--config ...]
    cage-vision make-markers    [--out markers]  printable reference markers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from .config import Config, load_config
from .logger import RunLogger, summarize
from .overlay import draw
from .pipeline import Pipeline

DEFAULT_CONFIG = "config.yaml"


def _warn_layout(cfg: Config) -> None:
    if not cfg.layout_confirmed:
        print("WARNING: layout_confirmed is false - marker positions / paper size in the config are placeholders.\n"
              "         Measurements are only as good as those numbers.", file=sys.stderr)


def cmd_list_cameras(args, cfg: Config) -> int:
    from .camera import list_cameras
    for c in list_cameras(backend=cfg.camera.backend):
        print(c)
    return 0


def cmd_live(args, cfg: Config) -> int:
    from .camera import Camera
    _warn_layout(cfg)
    cam = Camera(cfg.camera)
    print("camera settings actually applied:", json.dumps(cam.actual_settings()))
    pipe = Pipeline(cfg)
    log = RunLogger(cfg.output.directory, args.label)
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
                for f in range(cfg.output.frames_per_placement):
                    fr = frame if f == 0 else cam.read()
                    if fr is None:
                        break
                    mm, cc, dd = pipe.process(fr)
                    ann = draw(fr, mm, cc, dd, cfg)
                    log.log(mm, placement, f, "camera", ann if f == 0 else None, fr if f == 0 else None)
                print(f"placement {placement}: {m.status_text}"
                      + (f"  X={m.center_x:.3f} Y={m.center_y:.3f} A={m.rotation_deg:.2f}" if m.valid else ""))
    finally:
        cam.release()
        cv2.destroyAllWindows()
        log.close()
    if placement:
        print((log.dir / "report.md").read_text(encoding="utf-8") if _report(log.dir, cfg) else "")
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

    pipe = Pipeline(cfg)
    log = RunLogger(cfg.output.directory, args.label)
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cage-vision", description="STK-14 Phase 1 paper detection bench prototype")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-cameras")
    p = sub.add_parser("live"); p.add_argument("--label", default="bench")
    p = sub.add_parser("images"); p.add_argument("dir"); p.add_argument("--label", default="images")
    p = sub.add_parser("synth"); p.add_argument("dir")
    p.add_argument("--placements", type=int, default=25); p.add_argument("--frames", type=int, default=5)
    p.add_argument("--seed", type=int, default=1); p.add_argument("--k1", type=float, default=0.0)
    p = sub.add_parser("report"); p.add_argument("run_dir")
    p = sub.add_parser("make-markers"); p.add_argument("--out", default="markers")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    return {"list-cameras": cmd_list_cameras, "live": cmd_live, "images": cmd_images, "synth": cmd_synth,
            "report": cmd_report, "make-markers": cmd_make_markers}[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
