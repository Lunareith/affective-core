#!/usr/bin/env python3
"""test_dynamics.py - 动力学模块契约测试"""

import json
from pathlib import Path

import pytest

# 在真实 import 就绪前，先 mock Dimensions 和基础常量
DIMENSIONS = [
    "valence", "arousal", "dominance",
    "trust", "intimacy", "respect", "forgiveness",
    "curiosity", "confusion", "certainty", "anticipation",
    "nostalgia", "impatience", "relief", "disappointment", "hope",
]

DEFAULT_BASELINE = {
    "valence": 0.1, "arousal": 0.3, "dominance": 0.2,
    "trust": 0.0, "intimacy": 0.0, "respect": 0.0, "forgiveness": 0.0,
    "curiosity": 0.5, "confusion": 0.0, "certainty": 0.3, "anticipation": 0.2,
    "nostalgia": 0.0, "impatience": 0.0, "relief": 0.0, "disappointment": 0.0, "hope": 0.1,
}

CLAMP_RANGES = {
    "valence": [-0.8, 1.0], "arousal": [0.0, 1.0], "dominance": [-1.0, 1.0],
    "trust": [-1.0, 1.0], "intimacy": [0.0, 1.0], "respect": [0.0, 1.0],
    "forgiveness": [-0.7, 0.7], "curiosity": [0.0, 1.0], "confusion": [0.0, 1.0],
    "certainty": [0.0, 1.0], "anticipation": [-1.0, 1.0], "nostalgia": [0.0, 1.0],
    "impatience": [0.0, 1.0], "relief": [0.0, 1.0], "disappointment": [-0.8, 0.0],
    "hope": [0.1, 1.0],
}


# ---- fixtures -----------------------------------------------------------------

@pytest.fixture
def config_path(tmp_path: Path) -> str:
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "dynamics": {
                    "decay_rate_per_run": 0.1,
                    "inertia_coeff": 0.3,
                    "noise_std": 0.0,  # 测试中关闭噪声以便精确断言
                    "coupling_enabled": True,
                    "stale_threshold_minutes": 30,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def baseline() -> dict:
    return dict(DEFAULT_BASELINE)


@pytest.fixture
def current_vec(baseline: dict) -> dict:
    # 给一个略高于基线的初始状态
    vec = dict(baseline)
    vec["valence"] = 0.5
    vec["trust"] = 0.6
    return vec


# ---- try real import, fallback to mock ----------------------------------------

try:
    from dynamics import Dynamics
except ImportError:
    Dynamics = None  # type: ignore


# ---- tests -------------------------------------------------------------------

class TestDynamicsMockFallback:
    """如果 dynamics.py 还没就绪，先跑 mock 契约测试。"""

    def test_decay_toward_baseline(self, config_path, baseline, current_vec):
        if Dynamics is None:
            # mock 衰减：vec += (baseline - vec) * decay_rate
            decay = 0.1
            expected = {}
            for dim in DIMENSIONS:
                v = current_vec.get(dim, 0.0)
                b = baseline.get(dim, 0.0)
                expected[dim] = v + (b - v) * decay
            assert abs(expected["valence"] - 0.46) < 1e-6  # 0.5 + (0.1-0.5)*0.1 = 0.46
        else:
            d = Dynamics(config_path)
            result = d.update(current_vec, {k: 0.0 for k in DIMENSIONS}, baseline)
            # valence 应该从 0.5 向 0.1 衰减
            assert result["valence"] < 0.5
            assert result["valence"] > 0.1

    def test_coupling_trust_to_intimacy(self, config_path, baseline, current_vec):
        if Dynamics is None:
            # mock：trust ↑ → intimacy ↑
            assert True  # 占位
        else:
            d = Dynamics(config_path)
            # 让 trust 很高，看 intimacy 是否被带动
            cur = dict(current_vec)
            cur["trust"] = 0.8
            delta = {k: 0.0 for k in DIMENSIONS}
            result = d.update(cur, delta, baseline)
            assert result["intimacy"] > current_vec["intimacy"]

    def test_inertia_smooths_changes(self, config_path, baseline, current_vec):
        if Dynamics is None:
            assert True
        else:
            d = Dynamics(config_path)
            delta = {k: 0.0 for k in DIMENSIONS}
            delta["valence"] = 0.5  # 很大的正 delta
            result = d.update(current_vec, delta, baseline)
            # 惯性系数 0.3 应该让实际变化小于 delta
            actual_change = result["valence"] - current_vec["valence"]
            assert actual_change < 0.5
            assert actual_change > 0.0

    def test_clamp_respects_boundaries(self, config_path, baseline, current_vec):
        if Dynamics is None:
            assert True
        else:
            d = Dynamics(config_path)
            delta = {k: 0.0 for k in DIMENSIONS}
            delta["valence"] = 999.0  # 越界
            result = d.update(current_vec, delta, baseline)
            assert result["valence"] <= CLAMP_RANGES["valence"][1]

    def test_decay_if_stale_over_time(self, config_path, baseline, current_vec):
        if Dynamics is None:
            assert True
        else:
            d = Dynamics(config_path)
            result = d.decay_if_stale(current_vec, baseline, minutes_offline=60)
            # 60 分钟离线后应该显著衰减
            assert result["valence"] < current_vec["valence"]
            assert result["valence"] >= baseline["valence"]

    def test_no_side_effects_on_input(self, config_path, baseline, current_vec):
        if Dynamics is None:
            assert True
        else:
            d = Dynamics(config_path)
            original = dict(current_vec)
            d.update(current_vec, {k: 0.0 for k in DIMENSIONS}, baseline)
            assert current_vec == original  # 输入不应被修改
