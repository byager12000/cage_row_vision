import numpy as np
import pytest

from cage_vision.geometry import angle_diff, normalize_angle, rect_pose
from cage_vision.synth import paper_corners


@pytest.mark.parametrize("deg", [-89.0, -45.0, -10.0, 0.0, 12.5, 45.0, 89.9])
def test_rect_pose_recovers_pose(deg):
    c = paper_corners((5.0, -3.0, deg), 11.0, 8.5)
    p = rect_pose(c)
    assert np.allclose(p.center, [5.0, -3.0])
    assert p.length == pytest.approx(11.0)
    assert p.width == pytest.approx(8.5)
    assert angle_diff(p.rotation_deg, deg) == pytest.approx(0.0, abs=1e-9)


def test_rect_pose_ignores_corner_order():
    c = paper_corners((1.0, 2.0, 30.0), 11.0, 8.5)
    a = rect_pose(c)
    b = rect_pose(c[[2, 0, 3, 1]])
    assert np.allclose(a.center, b.center) and a.rotation_deg == pytest.approx(b.rotation_deg)


def test_angle_is_180_symmetric_and_in_range():
    assert normalize_angle(90.0) == -90.0
    assert normalize_angle(135.0) == pytest.approx(-45.0)
    assert normalize_angle(-100.0) == pytest.approx(80.0)
    assert angle_diff(89.0, -89.0) == pytest.approx(-2.0)
