"""Cage pose + position check. Real-image regression uses the saved home-bench frames in evidence/."""

import copy
from pathlib import Path

import cv2
import numpy as np
import pytest

from cage_vision.cage import CagePose, check_target, detect_cage
from cage_vision.cage_live import PROTOCOL
from cage_vision.camera_model import estimate_camera
from cage_vision.config import load_config
from cage_vision.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "evidence" / "p2-cage-exploration"


@pytest.fixture(scope="module")
def bench():
    c = load_config(ROOT / "config.yaml")
    c = copy.deepcopy(c)
    c.markers.require_baseline = False          # saved frames: the live-bench baseline is not the point here
    return c


def _pose(x, y, a):
    return CagePose(True, "", np.array([x, y]), a, 11.6, 7.4)


def test_translation_in_and_out(bench):
    target = {"center": [15.0, 10.0], "angle_deg": 0.0}
    r = check_target(_pose(15.3, 10.0, 0.0), target, bench)
    assert r["in_position"] and r["max_corner_dev"] == pytest.approx(0.3)
    r = check_target(_pose(15.0, 10.6, 0.0), target, bench)
    assert not r["in_position"] and r["max_corner_dev"] == pytest.approx(0.6)


def test_rotation_moves_the_corners(bench):
    target = {"center": [15.0, 10.0], "angle_deg": 0.0}
    r = check_target(_pose(15.0, 10.0, 2.0), target, bench)
    half_diag = np.hypot(bench.cage.bottom_length, bench.cage.bottom_width) / 2
    assert r["max_corner_dev"] == pytest.approx(half_diag * np.radians(2.0), rel=1e-3)
    assert r["dangle_deg"] == pytest.approx(2.0)


def test_protocol_stays_clear_of_the_limit(bench):
    tol = bench.cage.position_tolerance
    for t in PROTOCOL:
        dev = t.expected(bench)[3]
        assert dev <= tol - 0.1 or dev >= tol + 0.1, t.label     # a hand-set move must not straddle the limit


def _run(bench, name):
    img = cv2.imread(str(EVID / name))
    _, cal, _ = Pipeline(bench, baseline=None).process(img)
    cam = estimate_camera(cal.H, (img.shape[1], img.shape[0]), bench.camera.height_above_table)
    return detect_cage(img, cal, cam, bench)


def test_real_upright_cage_is_measured(bench):
    p = _run(bench, "cage_center_up_exp-5.jpg")
    assert p.detected, p.reason
    assert p.length == pytest.approx(11.6, abs=0.1) and p.width == pytest.approx(7.4, abs=0.1)


def test_real_inverted_cage_is_refused_not_misread(bench):
    p = _run(bench, "cage_center_down_exp-5.jpg")
    assert not p.detected and "not the" in p.reason
