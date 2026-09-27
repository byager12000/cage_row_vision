import pytest
import yaml

from cage_vision.config import load_config


def _write(tmp_path, data):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_shipped_config_loads(cfg):
    assert sorted(cfg.markers.positions) == [0, 1, 2, 3]
    assert cfg.layout_confirmed is False  # placeholders until Ben measures the bench


def test_requires_four_markers(tmp_path):
    with pytest.raises(ValueError, match="exactly 4"):
        load_config(_write(tmp_path, {"markers": {"positions": {0: [0, 0], 1: [1, 0], 2: [1, 1]}}}))


def test_rejects_unknown_keys(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        load_config(_write(tmp_path, {"markers": {"positions": {0: [0, 0], 1: [1, 0], 2: [1, 1], 3: [0, 1]},
                                                  "sizee": 2}}))


def test_length_must_be_long_side(tmp_path):
    with pytest.raises(ValueError, match="long side"):
        load_config(_write(tmp_path, {"markers": {"positions": {0: [0, 0], 1: [1, 0], 2: [1, 1], 3: [0, 1]}},
                                      "paper": {"length": 8.5, "width": 11}}))
