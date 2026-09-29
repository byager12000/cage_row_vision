"""Synthetic bench scenes with exact ground truth.

Used for regression tests and for the closed-loop check while no physical bench
exists. A top-down "table" canvas is rendered in world units (markers + paper),
then projected through a random perspective homography into a camera-sized
image with blur, noise, uneven lighting, JPEG compression and optional radial
lens distortion. Ground truth is the pose the paper was drawn at.

This proves the software math; it does NOT characterize a real webcam, real
lighting or real paper. The physical repeatability run still has to be done.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .config import Config, MarkerConfig, PaperConfig


@dataclass
class SynthLayout:
    markers: MarkerConfig
    paper: PaperConfig
    image_size: tuple[int, int] = (1920, 1080)
    px_per_unit: float = 100.0      # canvas render density (supersampled vs the camera)
    margin: float = 3.0             # world units of table drawn beyond the marker centers


@dataclass
class SceneSpec:
    paper_pose: tuple[float, float, float] | None      # (cx, cy, deg) or None for no paper
    extra_papers: list[tuple[float, float, float]] = field(default_factory=list)
    hide_markers: list[int] = field(default_factory=list)
    perspective_jitter: float = 80.0   # px
    noise_sigma: float = 3.0
    blur_sigma: float = 0.8
    distortion_k1: float = 0.0         # radial distortion (normalized coords); ~-0.05..-0.15 for cheap webcams
    table_gray: int = 60
    paper_gray: int = 225
    light_gradient: float = 0.25       # fractional brightness change across the image
    jpeg_quality: int = 92
    marker_sheets: bool = False        # draw each marker on an untrimmed 8.5 x 11 in white page


def _bounds(lay: SynthLayout) -> tuple[float, float, float, float]:
    pts = np.array(list(lay.markers.positions.values()))
    return (pts[:, 0].min() - lay.margin, pts[:, 1].min() - lay.margin,
            pts[:, 0].max() + lay.margin, pts[:, 1].max() + lay.margin)


def paper_corners(pose: tuple[float, float, float], length: float, width: float) -> np.ndarray:
    cx, cy, deg = pose
    a = np.radians(deg)
    u, v = np.array([np.cos(a), np.sin(a)]), np.array([-np.sin(a), np.cos(a)])
    c = np.array([cx, cy])
    return np.array([c + s1 * u * length / 2 + s2 * v * width / 2 for s1, s2 in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])


def render(lay: SynthLayout, spec: SceneSpec, rng: np.random.Generator,
           noise_rng: np.random.Generator | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return (camera image BGR, world->camera homography).

    `rng` drives the scene (table grain, camera geometry, lighting direction);
    `noise_rng` drives sensor noise only, so a fixed camera can be re-imaged with
    fresh noise by reusing the same `rng` seed.
    """
    noise_rng = noise_rng or rng
    x0, y0, x1, y1 = _bounds(lay)
    s = lay.px_per_unit
    cw, ch = int((x1 - x0) * s), int((y1 - y0) * s)
    # world -> canvas. Pixel i covers [i-0.5, i+0.5] (fillPoly/warpPerspective
    # convention); the -0.5 puts whole-unit world coordinates on pixel boundaries so
    # the pasted marker bitmaps land exactly where the world says they are.
    A = np.array([[s, 0, -x0 * s - 0.5], [0, s, -y0 * s - 0.5], [0, 0, 1]], float)

    grain = rng.normal(0, 6, (ch // 4 + 1, cw // 4 + 1)).astype(np.float32)
    canvas = np.clip(spec.table_gray + cv2.resize(grain, (cw, ch)), 0, 255).astype(np.uint8)

    def world_poly(pts):
        return (np.c_[pts, np.ones(len(pts))] @ A.T)[:, :2]

    for pose in ([spec.paper_pose] if spec.paper_pose else []) + spec.extra_papers:
        _fill_convex_exact(canvas, world_poly(paper_corners(pose, lay.paper.length, lay.paper.width)), spec.paper_gray)

    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, lay.markers.dictionary))
    msz = lay.markers.size
    for mid, (mx, my) in lay.markers.positions.items():
        if mid in spec.hide_markers:
            continue
        if spec.marker_sheets:
            pg = world_poly(np.array([[mx - 4.25, my - 5.5], [mx + 4.25, my + 5.5]]))
            cv2.rectangle(canvas, tuple(pg[0].astype(int)), tuple(pg[1].astype(int)), 240, -1)
        # White quiet zone, then the marker, axis-aligned in world.
        qz = world_poly(np.array([[mx - msz * 0.8, my - msz * 0.8], [mx + msz * 0.8, my + msz * 0.8]]))
        cv2.rectangle(canvas, tuple(qz[0].astype(int)), tuple(qz[1].astype(int)), 245, -1)
        side = int(round(msz * s))
        img = cv2.aruco.generateImageMarker(d, mid, side, borderBits=1)
        tl = world_poly(np.array([[mx - msz / 2, my - msz / 2]]))[0]
        r0, c0 = int(np.floor(tl[1] + 0.5 + 1e-6)), int(np.floor(tl[0] + 0.5 + 1e-6))
        canvas[r0:r0 + side, c0:c0 + side] = img

    W, Hh = lay.image_size
    src = np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
    # Fit canvas into ~88% of the frame keeping aspect, then jitter each corner.
    k = 0.88 * min(W / cw, Hh / ch)
    off = np.array([(W - cw * k) / 2, (Hh - ch * k) / 2])
    dst = src * k + off + rng.uniform(-spec.perspective_jitter, spec.perspective_jitter, (4, 2))
    Hc = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    # warpPerspective does not low-pass when shrinking; anti-alias first or edges
    # pick up a sampling-phase bias that the detector would then be blamed for.
    canvas = cv2.GaussianBlur(canvas, (0, 0), 0.5 / k)
    cam = cv2.warpPerspective(canvas, Hc, (W, Hh), flags=cv2.INTER_LINEAR, borderValue=35)

    yy, xx = np.mgrid[0:Hh, 0:W].astype(np.float32)
    gdir = rng.uniform(0, 2 * np.pi)
    ramp = ((xx / W - 0.5) * np.cos(gdir) + (yy / Hh - 0.5) * np.sin(gdir)) * spec.light_gradient
    f = cam.astype(np.float32) * (1 + ramp)
    if spec.blur_sigma > 0:
        f = cv2.GaussianBlur(f, (0, 0), spec.blur_sigma)
    f += noise_rng.normal(0, spec.noise_sigma, f.shape).astype(np.float32)
    cam = np.clip(f, 0, 255).astype(np.uint8)

    if spec.distortion_k1:
        cam = _distort(cam, spec.distortion_k1)

    ok, buf = cv2.imencode(".jpg", cam, [cv2.IMWRITE_JPEG_QUALITY, spec.jpeg_quality])
    cam = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return cv2.cvtColor(cam, cv2.COLOR_GRAY2BGR), Hc @ A


def _fill_convex_exact(canvas: np.ndarray, poly: np.ndarray, value: float) -> None:
    """Area-coverage fill of a convex polygon (canvas px, pixel-center convention).

    Coverage = clip(0.5 + signed distance to the nearest edge), exact for straight
    edges away from corners. OpenCV's fillPoly is inclusive of boundary pixels (and
    its LINE_AA variant grows shapes), which biased synthetic ground truth ~1 px.
    """
    x0, y0 = np.floor(poly.min(axis=0)).astype(int) - 2
    x1, y1 = np.ceil(poly.max(axis=0)).astype(int) + 2
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, canvas.shape[1] - 1), min(y1, canvas.shape[0] - 1)
    yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1].astype(np.float64)
    ctr = poly.mean(axis=0)
    d = np.full(xx.shape, np.inf)
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        n = np.array([b[1] - a[1], a[0] - b[0]])
        n /= np.linalg.norm(n)
        if np.dot(ctr - a, n) < 0:
            n = -n                                   # inward normal
        d = np.minimum(d, (xx - a[0]) * n[0] + (yy - a[1]) * n[1])
    cov = np.clip(0.5 + d, 0.0, 1.0)
    roi = canvas[y0:y1 + 1, x0:x1 + 1].astype(np.float64)
    canvas[y0:y1 + 1, x0:x1 + 1] = np.round(roi * (1 - cov) + value * cov).astype(np.uint8)


def _distort(img: np.ndarray, k1: float) -> np.ndarray:
    h, w = img.shape[:2]
    f = max(w, h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xn, yn = (xx - w / 2) / f, (yy - h / 2) / f
    # For each output (distorted) pixel, sample the undistorted source (first-order inverse).
    r2 = xn * xn + yn * yn
    scale = 1 / (1 + k1 * r2)
    mx, my = xn * scale * f + w / 2, yn * scale * f + h / 2
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderValue=35)


def random_pose(lay: SynthLayout, rng: np.random.Generator, edge: float = 2.8) -> tuple[float, float, float]:
    pts = np.array(list(lay.markers.positions.values()))
    lo, hi = pts.min(axis=0) + edge, pts.max(axis=0) - edge
    for _ in range(10000):
        pose = (rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1]), rng.uniform(-90, 90))
        c = paper_corners(pose, lay.paper.length, lay.paper.width)
        if np.all(c >= lo) and np.all(c <= hi):
            return tuple(float(v) for v in pose)
    raise RuntimeError("paper does not fit inside the marker area with this layout")


def layout_from_config(cfg: Config) -> SynthLayout:
    return SynthLayout(cfg.markers, cfg.paper, (cfg.camera.width, cfg.camera.height))


def make_suite(cfg: Config, out_dir: str | Path, placements: int = 25, frames: int = 5,
               seed: int = 1, distortion_k1: float = 0.0) -> Path:
    """Write placement images + negative cases, with manifest.json ground truth."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lay = layout_from_config(cfg)
    rng = np.random.default_rng(seed)
    manifest = []
    for p in range(1, placements + 1):
        pose = random_pose(lay, rng)
        spec = SceneSpec(pose, distortion_k1=distortion_k1)
        # Fixed camera per placement (same scene seed); fresh sensor noise per frame.
        for f in range(frames):
            img, _ = render(lay, spec, np.random.default_rng([seed, p]), np.random.default_rng([seed, p, f]))
            name = f"p{p:02d}_f{f:02d}.png"
            cv2.imwrite(str(out / name), img)
            manifest.append({"file": name, "placement": p, "frame": f, "expect": "valid", "gt": list(pose)})

    neg_pose = random_pose(lay, rng)
    ids = sorted(cfg.markers.positions)
    xs = [v[0] for v in cfg.markers.positions.values()]
    negatives = {
        "neg_no_paper": SceneSpec(None),
        "neg_marker_hidden": SceneSpec(neg_pose, hide_markers=[ids[2]]),
        "neg_paper_off_edge": SceneSpec((max(xs) - 1.0, neg_pose[1], 0.0)),
        "neg_two_papers": SceneSpec(neg_pose, extra_papers=[_far_pose(lay, neg_pose, rng)]),
    }
    for name, spec in negatives.items():
        img, _ = render(lay, spec, rng)
        cv2.imwrite(str(out / f"{name}.png"), img)
        manifest.append({"file": f"{name}.png", "placement": name, "frame": 0, "expect": "invalid", "gt": None})

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return out


def _far_pose(lay: SynthLayout, other: tuple[float, float, float], rng) -> tuple[float, float, float]:
    # Two full sheets rarely fit; a second sheet anywhere is still "ambiguous" if it
    # passes the size check, so place it where it does not overlap the first.
    for _ in range(2000):
        p = random_pose(lay, rng, edge=2.8)
        if np.hypot(p[0] - other[0], p[1] - other[1]) > lay.paper.length:
            return p
    return (other[0], other[1] + lay.paper.width + 1, other[2])
