"""Shape-agnostic outline method: registration, footprint reconstruction, real warehouse frames."""

import copy
import types
from pathlib import Path

import cv2
import numpy as np
import pytest

from cage_vision.camera_model import CameraModel, estimate_camera
from cage_vision.config import load_config
from cage_vision.outline import _densify, compare, find_cages, pick, reconstruct_bottom, register, save_outline_target
from cage_vision.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
WH = ROOT / "evidence" / "p2-cage-exploration" / "warehouse-2026-09-30"
RECT = np.array([[0, 0], [11.25, 0], [11.25, 7], [0, 7]], float) + [10, 10]
TRAP = np.array([[0, 0], [12, 0], [7.5, 11], [4.5, 11]], float) + [20, 5]


def _move(pts, dx, dy, deg):
    c = pts.mean(axis=0)
    a = np.radians(deg)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return (pts - c) @ R.T + c + [dx, dy]


@pytest.mark.parametrize("poly", [RECT, TRAP], ids=["rectangle", "trapezoid"])
@pytest.mark.parametrize("deg", [0.5, 2.0, -8.0])
def test_register_recovers_rotation_and_shift(poly, deg):
    P = _densify(poly)[0]
    Q = _move(P, 0.2, -0.2, deg)
    R, t, ang, rms = register(P, Q)
    assert ang == pytest.approx(deg, abs=1e-3) and rms < 1e-3
    rng = np.random.default_rng(1)
    Qb = Q + rng.normal(0, 0.02, Q.shape)
    Qb[:25] += [0.6, 0.0]                       # a water fitting / clip on part of one side
    assert register(P, Qb)[2] == pytest.approx(deg, abs=0.25)


def test_compare_in_and_out():
    P = _densify(RECT)[0]
    target = {"bottom": P.tolist(), "centroid": list(P.mean(axis=0))}
    live = lambda Q: types.SimpleNamespace(bottom=Q, centroid=Q.mean(axis=0), partial=False)
    r = compare(target, live(_move(P, 0.3, 0.0, 0.0)), 0.5)
    assert r["in_position"] and r["max_corner_dev"] == pytest.approx(0.3, abs=1e-3)
    r = compare(target, live(_move(P, 0.0, 0.6, 0.0)), 0.5)
    assert not r["in_position"]
    r = compare(target, live(_move(P, 0.0, 0.0, 5.0)), 0.5)      # 5 deg twist moves the corners ~0.58 in
    assert not r["in_position"] and r["dangle_deg"] == pytest.approx(5.0, abs=1e-3)


@pytest.mark.parametrize("poly", [RECT, TRAP], ids=["rectangle", "trapezoid"])
def test_bottom_footprint_is_reconstructed_from_the_silhouette(poly):
    cam = CameraModel(np.array([26.0, 7.5]), 48.5, 1400.0, 9.0)
    belt, h, taper = 0.375, 5.0, 0.18
    bottom = _densify(poly)[0]
    pts, nrm = _densify(poly)
    rim = pts + taper * nrm                                            # rim = bottom offset outward by the taper
    sil = np.vstack([cam.from_height(bottom, belt), cam.from_height(rim, belt + h)])
    rec = reconstruct_bottom(cv2.convexHull(sil.astype(np.float32)).reshape(-1, 2), cam, belt, h, taper)
    assert cv2.contourArea(rec.astype(np.float32)) == pytest.approx(cv2.contourArea(poly.astype(np.float32)), rel=0.01)
    R, t, ang, rms = register(bottom, rec)
    assert rms < 0.03 and abs(ang) < 0.1 and np.linalg.norm(t) < 0.05


@pytest.fixture(scope="module")
def wh_cfg(tmp_path_factory):
    c = copy.deepcopy(load_config(ROOT / "config_warehouse.yaml"))
    c.markers.require_baseline = False
    c.cage.target_file = str(tmp_path_factory.mktemp("t") / "target.json")
    return c


def _cages(cfg, name):
    img = cv2.imread(str(WH / name))
    _, cal, _ = Pipeline(cfg, baseline=None).process(img)
    return find_cages(img, cal, estimate_camera(cal.H, (img.shape[1], img.shape[0]), cfg.camera.height_above_table), cfg)


def test_real_frames_find_all_cages_and_flag_the_cut_off_one(wh_cfg):
    three = [o for o in _cages(wh_cfg, "three_cages_exp-7.png") if not o.partial]
    assert len(three) == 3                                        # Jag 75, OptiMice, NexGen Edge (clear)
    two = _cages(wh_cfg, "two_cages_exp-7.png")
    assert sum(not o.partial for o in two) == 1 and sum(o.partial for o in two) == 1   # NexGen past the marked area


def test_real_unmoved_cage_is_in_position(wh_cfg):
    jag_two = min((o for o in _cages(wh_cfg, "two_cages_exp-7.png") if not o.partial), key=lambda o: o.centroid[0])
    target = save_outline_target(wh_cfg, [jag_two])
    r = compare(target, pick(_cages(wh_cfg, "three_cages_exp-7.png"), target), 0.5)
    assert r["in_position"] and r["max_corner_dev"] < 0.2


# ---- guided-move protocol and reference-tape rejection (2026-09-30 position test) ----

from cage_vision.outline_live import build_protocol

PT = ROOT / "evidence" / "p2-cage-exploration" / "position-test-2026-09-30" / "frames"


@pytest.mark.parametrize("deg", [0.0, 90.0, 30.0], ids=["long-side-near", "short-side-near", "angled"])
def test_twist_moves_stay_clear_of_the_limit(wh_cfg, deg):
    P = _move(_densify(np.array([[0, 0], [11.31, 0], [11.31, 6.98], [0, 6.98]], float) + [18, 10])[0], 0, 0, deg)
    target = {"bottom": P.tolist(), "centroid": list(P.mean(axis=0))}
    twists = [t for t in build_protocol(target, wh_cfg) if t.pivot is not None]
    assert len(twists) == 2
    devs = [t.expected(target)[3] for t in twists]
    assert devs[0] <= 0.35 and devs[1] >= 0.7                    # one clearly IN, one clearly OUT


def _pt_cages(cfg, n):
    img = cv2.imread(str(PT / f"trial{n}_raw.jpg"))
    _, cal, _ = Pipeline(cfg, baseline=None).process(img)
    return find_cages(img, cal, estimate_camera(cal.H, (img.shape[1], img.shape[0]), cfg.camera.height_above_table), cfg)


def test_reference_tape_touching_the_cage_is_ignored(wh_cfg):
    target = save_outline_target(wh_cfg, [pick(_pt_cages(wh_cfg, "01"), None)])
    r2 = compare(target, pick(_pt_cages(wh_cfg, "02"), target), 0.5)      # slide right 1/4 by hand
    r5 = compare(target, pick(_pt_cages(wh_cfg, "05"), target), 0.5)      # slide right 1 by hand
    r6 = compare(target, pick(_pt_cages(wh_cfg, "06"), target), 0.5)      # back to the target
    assert r2["dx"] == pytest.approx(0.25, abs=0.06) and r2["fit_rms"] < 0.06
    assert r5["dx"] == pytest.approx(1.0, abs=0.1) and not r5["in_position"]
    assert r6["in_position"] and r6["max_corner_dev"] < 0.25
    off = copy.deepcopy(wh_cfg)
    off.cage.ignore_color = False                                          # tape swallowed into the outline
    r7_raw = compare(target, pick(_pt_cages(off, "07"), target), 0.5)
    r7 = compare(target, pick(_pt_cages(wh_cfg, "07"), target), 0.5)
    assert r7["fit_rms"] < 0.06 < r7_raw["fit_rms"]


# ---- run 2 (2026-09-30 afternoon): tape seen THROUGH the cage, and a no-fit must not crash ----

PT2 = ROOT / "evidence" / "p2-cage-exploration" / "position-test-2026-09-30-run2"


def _pt2(cfg, n):
    img = cv2.imread(str(PT2 / "frames" / f"trial{n}_raw.jpg"))
    _, cal, _ = Pipeline(cfg, baseline=None).process(img)
    return find_cages(img, cal, estimate_camera(cal.H, (img.shape[1], img.shape[0]), cfg.camera.height_above_table), cfg)


def test_tape_under_the_cage_does_not_cut_it(wh_cfg):
    import json
    target = json.loads((PT2 / "target.json").read_text())
    r10 = compare(target, pick(_pt2(wh_cfg, "10"), target), 0.5)          # slid 1 in away, far end over the tape
    assert r10["dy"] == pytest.approx(1.0, abs=0.2) and r10["fit_rms"] < 0.15 and not r10["in_position"]
    r5 = compare(target, pick(_pt2(wh_cfg, "05"), target), 0.5)           # slid 1 in right inside the tape box
    assert r5["dx"] == pytest.approx(1.0, abs=0.1) and abs(r5["dangle_deg"]) < 1.0


def test_compare_without_a_rigid_fit_is_out_not_a_crash():
    P = _densify(RECT)[0]
    target = {"bottom": P.tolist(), "centroid": list(P.mean(axis=0))}
    turned = types.SimpleNamespace(bottom=_move(P, 0, 0, 60.0), centroid=P.mean(axis=0), partial=False)
    r = compare(target, turned, 0.5)                                         # 60 deg: beyond the +/-30 deg search
    assert not r["in_position"]
