from pathlib import Path

import numpy as np
import pytest

from cage_vision.config import Config, load_config
from cage_vision.pipeline import Pipeline
from cage_vision.synth import SceneSpec, SynthLayout, layout_from_config, render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cfg() -> Config:
    return load_config(ROOT / "config.yaml")


@pytest.fixture(scope="session")
def layout(cfg) -> SynthLayout:
    return layout_from_config(cfg)


@pytest.fixture(scope="session")
def pipe(cfg) -> Pipeline:
    return Pipeline(cfg)


@pytest.fixture
def scene(layout):
    def _scene(pose=(15.0, 10.0, 20.0), seed=0, **kw):
        img, _ = render(layout, SceneSpec(pose, **kw), np.random.default_rng(seed))
        return img
    return _scene
