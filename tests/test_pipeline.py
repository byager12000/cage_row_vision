"""End-to-end on synthetic scenes with exact ground truth.

Tolerances here are regression guards for the software math on clean-ish
synthetic images, not claims about real-bench accuracy.
"""

import copy
import csv

import cv2

import numpy as np
import pytest

from cage_vision.geometry import angle_diff
from cage_vision.logger import RunLogger, summarize
from cage_vision.pipeline import Pipeline
from cage_vision.synth import random_pose

POS_TOL = 0.02   # in
ANG_TOL = 0.1    # deg
SIZE_TOL = 0.02  # in


@pytest.mark.parametrize("seed", range(8))
def test_valid_placements_are_accurate(pipe, scene, layout, seed):
    pose = random_pose(layout, np.random.default_rng(100 + seed))
    m, _, _ = pipe.process(scene(pose, seed=seed))
    assert m.valid, m.status_text
    assert m.center_x == pytest.approx(pose[0], abs=POS_TOL)
    assert m.center_y == pytest.approx(pose[1], abs=POS_TOL)
    assert abs(angle_diff(m.rotation_deg, pose[2])) < ANG_TOL
    assert m.length == pytest.approx(11.0, abs=SIZE_TOL)
    assert m.width == pytest.approx(8.5, abs=SIZE_TOL)


def _assert_no_values(m):
    assert not m.valid
    assert m.center_x is None and m.center_y is None and m.rotation_deg is None


def test_missing_marker_invalidates_calibration(pipe, scene):
    m, _, _ = pipe.process(scene(hide_markers=[1]))
    assert not m.calibration_ok and "not found" in m.calibration_reason
    _assert_no_values(m)


def test_no_paper_reports_not_detected(pipe, scene):
    m, _, _ = pipe.process(scene(pose=None))
    assert m.calibration_ok and not m.object_detected
    _assert_no_values(m)


def test_paper_partly_outside_area_is_rejected(cfg, pipe, scene):
    xs = [p[0] for p in cfg.markers.positions.values()]
    ys = [p[1] for p in cfg.markers.positions.values()]
    m, _, _ = pipe.process(scene(pose=(max(xs) - 1.0, sum(ys) / 4, 0.0)))
    _assert_no_values(m)


def test_paper_over_a_marker_is_rejected(cfg, pipe, scene):
    mx, my = cfg.markers.positions[min(cfg.markers.positions)]
    m, _, _ = pipe.process(scene(pose=(mx + 5.0, my + 4.0, 30.0)))
    _assert_no_values(m)


def test_untrimmed_marker_sheets_are_ignored(pipe, scene):
    # Markers left on full letter pages: the page corners inside the area must not
    # become candidates or break detection of a paper placed clear of them.
    m, _, det = pipe.process(scene(pose=(17.5, 12.5, 15.0), marker_sheets=True))
    assert m.valid, m.status_text
    assert m.center_x == pytest.approx(17.5, abs=POS_TOL) and m.center_y == pytest.approx(12.5, abs=POS_TOL)
    m, _, _ = pipe.process(scene(pose=None, marker_sheets=True))
    assert not m.object_detected and "no paper-sized object" in m.detection_reason


def test_paper_touching_a_marker_sheet_is_rejected(cfg, pipe, scene):
    mx, my = cfg.markers.positions[min(cfg.markers.positions)]
    # Paper edge overlaps the page (page reaches 4.25 in right of the marker center).
    m, _, _ = pipe.process(scene(pose=(mx + 9.0, my + 9.0, 0.0), marker_sheets=True))
    _assert_no_values(m)
    assert "marker sheet" in m.detection_reason


def _baseline_for(cfg, img):
    from cage_vision.baseline import make_baseline
    from cage_vision.calibration import calibrate
    cal = calibrate(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cfg.markers)
    return make_baseline(cfg, [{i: c.mean(axis=0) for i, c in cal.marker_corners.items()}], "test")


def _bench(cfg):
    c = copy.deepcopy(cfg)
    c.markers.require_baseline = True
    return c


def test_bumped_marker_is_caught_by_baseline(cfg, scene):
    c = _bench(cfg)
    base = _baseline_for(c, scene(seed=5))
    assert Pipeline(c, baseline=base).process(scene(seed=5))[0].valid
    for bump in (0.25, 0.5):          # 0.25 in bump: silent 0.1 in error before the baseline check existed
        m, cal, _ = Pipeline(c, baseline=base).process(scene(seed=5, marker_offsets={1: (bump, 0.0)}))
        assert not m.calibration_ok and "moved relative to the others" in m.calibration_reason
        _assert_no_values(m)


def test_camera_shift_alone_is_not_an_error(cfg, scene):
    c = _bench(cfg)
    img = scene(seed=5)
    base = _baseline_for(c, img)
    shifted = cv2.warpAffine(img, np.float32([[1, 0, 25], [0, 1, -12]]), (img.shape[1], img.shape[0]),
                             borderMode=cv2.BORDER_REPLICATE)
    m, cal, _ = Pipeline(c, baseline=base).process(shifted)
    assert m.valid, m.status_text
    assert cal.relative_move_px < 0.5 and "camera or table moved" in m.warnings


def test_missing_or_stale_baseline_invalidates(cfg, scene):
    c = _bench(cfg)
    m, _, _ = Pipeline(c, baseline=None).process(scene())
    assert not m.calibration_ok and "no setup baseline" in m.calibration_reason
    base = _baseline_for(c, scene())
    c2 = copy.deepcopy(c)
    c2.markers.positions = {**c2.markers.positions, 1: (c2.markers.positions[1][0] + 0.5, c2.markers.positions[1][1])}
    m, _, _ = Pipeline(c2, baseline=base).process(scene())
    assert not m.calibration_ok and "changed since the baseline" in m.calibration_reason


def test_two_papers_is_ambiguous(pipe, scene):
    m, _, _ = pipe.process(scene(pose=(8.0, 10.0, 90.0), extra_papers=[(22.0, 10.0, 90.0)]))
    assert "ambiguous" in m.detection_reason
    _assert_no_values(m)


def test_wrong_size_object_is_rejected(cfg, scene):
    c = copy.deepcopy(cfg)
    c.paper.length, c.paper.width = 14.0, 8.5   # config says legal size, table has letter
    m, _, _ = Pipeline(c).process(scene())
    _assert_no_values(m)
    assert "size" in m.detection_reason


def test_wrong_marker_layout_invalidates_calibration(cfg, scene):
    c = copy.deepcopy(cfg)
    c.markers.positions = {0: (0, 0), 1: (60, 0), 2: (60, 40), 3: (0, 40)}  # 2x too big
    m, _, _ = Pipeline(c).process(scene())
    assert not m.calibration_ok and "marker size implausible" in m.calibration_reason
    _assert_no_values(m)


def test_no_stale_values_after_a_good_frame(pipe, scene):
    good, _, _ = pipe.process(scene())
    assert good.valid
    for bad_img in (scene(pose=None), scene(hide_markers=[0])):
        m, _, _ = pipe.process(bad_img)
        _assert_no_values(m)


def test_blank_frame_is_safe(pipe):
    m, _, _ = pipe.process(np.zeros((1080, 1920, 3), np.uint8))
    assert not m.calibration_ok
    _assert_no_values(m)


def test_logger_and_report(tmp_path, pipe, scene, layout):
    log = RunLogger(tmp_path, "t")
    pose = random_pose(layout, np.random.default_rng(7))
    for f in range(3):
        m, _, _ = pipe.process(scene(pose, seed=f))
        log.log(m, 1, f, "synth", gt=pose)
    m, _, _ = pipe.process(scene(pose=None))
    log.log(m, 2, 0, "synth")
    log.close()
    rows = list(csv.DictReader(open(log.csv_path)))
    assert rows[-1]["center_x"] == ""            # invalid frame logs blank, not a number
    rep = summarize(log.dir, 11.0, 8.5)
    assert rep["placements"] == 2 and rep["placements_detected"] == 1
    assert rep["position_error_vs_ground_truth"]["radial"]["max_abs"] < POS_TOL
    assert (log.dir / "report.md").exists()
