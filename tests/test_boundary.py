#!/usr/bin/env python3
"""test_boundary.py — 边界检测与自修复单元测试"""

import random
import json
from pathlib import Path

import pytest

from safety import BoundaryGuard


ALL_DIMS = [
    "valence", "arousal", "dominance",
    "trust", "intimacy", "respect", "forgiveness",
    "curiosity", "confusion", "certainty", "anticipation",
    "nostalgia", "impatience", "relief", "disappointment", "hope",
]


def _make_vec(**overrides) -> dict:
    base = {
        "valence": 0.1, "arousal": 0.3, "dominance": 0.2,
        "trust": 0.0, "intimacy": 0.0, "respect": 0.0, "forgiveness": 0.0,
        "curiosity": 0.5, "confusion": 0.0, "certainty": 0.3, "anticipation": 0.2,
        "nostalgia": 0.0, "impatience": 0.0, "relief": 0.0, "disappointment": 0.0, "hope": 0.1,
    }
    base.update(overrides)
    return base


@pytest.fixture
def config_path(tmp_path: Path) -> str:
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "dimensions": {
                    "all": ALL_DIMS,
                    "baseline": {
                        "valence": 0.1, "arousal": 0.3, "dominance": 0.2,
                        "trust": 0.0, "intimacy": 0.0, "respect": 0.0, "forgiveness": 0.0,
                        "curiosity": 0.5, "confusion": 0.0, "certainty": 0.3, "anticipation": 0.2,
                        "nostalgia": 0.0, "impatience": 0.0, "relief": 0.0, "disappointment": 0.0, "hope": 0.1,
                    },
                    "clamp": {
                        "valence": [-0.8, 1.0], "arousal": [0.0, 1.0], "dominance": [-1.0, 1.0],
                        "trust": [-1.0, 1.0], "intimacy": [0.0, 1.0], "respect": [0.0, 1.0],
                        "forgiveness": [-0.7, 0.7], "curiosity": [0.0, 1.0], "confusion": [0.0, 1.0],
                        "certainty": [0.0, 1.0], "anticipation": [-1.0, 1.0], "nostalgia": [0.0, 1.0],
                        "impatience": [0.0, 1.0], "relief": [0.0, 1.0], "disappointment": [-0.8, 0.0],
                        "hope": [0.1, 1.0],
                    },
                },
                "boundary": {
                    "lock_consecutive_runs": 5,
                    "lock_epsilon": 0.001,
                    "lock_perturbation_std": 0.05,
                    "oscillation_window_runs": 4,
                    "oscillation_amplitude": 0.5,
                    "freeze_threshold": 0.05,
                    "freeze_curiosity_offset": 0.3,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(p)


# ---- lock detection ----------------------------------------------------------

class TestLockDetection:

    def test_locked_after_unchanged_runs(self, config_path: str):
        guard = BoundaryGuard(config_path)
        vec = _make_vec(valence=0.3)
        for _ in range(6):
            repaired, diag = guard.detect_and_repair(vec)
        assert diag["locked"]["valence"] is True
        assert any("lock_repair" in r for r in diag["repairs_applied"])

    def test_not_locked_when_value_changes(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for i in range(6):
            vec = _make_vec(valence=0.3 + i * 0.01)
            _, diag = guard.detect_and_repair(vec)
        assert diag["locked"]["valence"] is False

    def test_lock_perturbation_small(self, config_path: str):
        guard = BoundaryGuard(config_path)
        vec = _make_vec(valence=0.3)
        for _ in range(6):
            repaired, diag = guard.detect_and_repair(vec)
        # 微扰应在合理范围内
        assert abs(repaired["valence"] - 0.3) < 0.2

    def test_lock_affects_only_locked_dim(self, config_path: str):
        guard = BoundaryGuard(config_path)
        vec = _make_vec(valence=0.3, arousal=0.5)
        for _ in range(6):
            # 给 arousal 加微小变化，避免被锁定
            vec2 = dict(vec)
            vec2["arousal"] = vec["arousal"] + random.uniform(-0.01, 0.01)
            repaired, diag = guard.detect_and_repair(vec2)
        # arousal 没被锁定，不应被微扰
        assert "lock_repair:arousal" not in str(diag["repairs_applied"])


# ---- oscillation detection ---------------------------------------------------

class TestOscillationDetection:

    def test_oscillation_detected(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for v in [0.6, -0.6, 0.6, -0.6]:
            _, diag = guard.detect_and_repair(_make_vec(valence=v))
        assert diag["oscillating"]["valence"] is True
        assert guard.get_coupling_factor("valence") < 1.0

    def test_oscillation_reduces_coupling(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for v in [0.6, -0.6, 0.6, -0.6]:
            guard.detect_and_repair(_make_vec(valence=v))
        factor = guard.get_coupling_factor("valence")
        # 4 轮内触发 1 次振荡 → 1.0 * 0.7 = 0.7
        assert factor == pytest.approx(0.7, abs=0.01)

    def test_oscillation_multiple_windows(self, config_path: str):
        guard = BoundaryGuard(config_path)
        # 连续触发振荡，耦合因子持续衰减
        for _ in range(2):
            for v in [0.6, -0.6, 0.6, -0.6]:
                guard.detect_and_repair(_make_vec(valence=v))
        factor = guard.get_coupling_factor("valence")
        # 多次振荡触发 → 因子远小于 1.0
        assert factor < 0.5
        assert factor > 0.1  # 不会降到 0（max 0.1）

    def test_no_oscillation_for_stable_values(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for v in [0.6, 0.61, 0.62, 0.63]:
            _, diag = guard.detect_and_repair(_make_vec(valence=v))
        assert diag["oscillating"]["valence"] is False

    def test_oscillation_below_amplitude_ignored(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for v in [0.3, -0.3, 0.3, -0.3]:
            _, diag = guard.detect_and_repair(_make_vec(valence=v))
        # amplitude 0.3 < 0.5，不应触发
        assert diag["oscillating"]["valence"] is False


# ---- freeze detection --------------------------------------------------------

class TestFreezeDetection:

    def test_frozen_all_near_zero(self, config_path: str):
        guard = BoundaryGuard(config_path)
        vec = _make_vec(**{d: 0.01 for d in ALL_DIMS})
        repaired, diag = guard.detect_and_repair(vec)
        assert diag["frozen"] is True
        assert repaired["curiosity"] > 0.0

    def test_not_frozen_when_values_present(self, config_path: str):
        guard = BoundaryGuard(config_path)
        vec = _make_vec(valence=0.3, arousal=0.5)
        _, diag = guard.detect_and_repair(vec)
        assert diag["frozen"] is False

    def test_freeze_injects_curiosity(self, config_path: str):
        guard = BoundaryGuard(config_path)
        vec = _make_vec(**{d: 0.01 for d in ALL_DIMS})
        repaired, diag = guard.detect_and_repair(vec)
        assert "freeze_repair:curiosity" in str(diag["repairs_applied"])


# ---- diagnostics -------------------------------------------------------------

class TestDiagnostics:

    def test_reset_coupling_factors(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for v in [0.6, -0.6, 0.6, -0.6]:
            guard.detect_and_repair(_make_vec(valence=v))
        guard.reset_coupling_factors()
        assert guard.get_coupling_factor("valence") == 1.0

    def test_reset_window(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for _ in range(3):
            guard.detect_and_repair(_make_vec())
        guard.reset_window()
        _, diag = guard.detect_and_repair(_make_vec())
        # 窗口清空后只有1个元素，锁定检测不会执行，locked为空字典
        assert diag.get("locked", {}).get("valence") is not True

    def test_diagnostics_structure(self, config_path: str):
        guard = BoundaryGuard(config_path)
        _, diag = guard.detect_and_repair(_make_vec())
        assert "locked" in diag
        assert "oscillating" in diag
        assert "frozen" in diag
        assert "repairs_applied" in diag
        assert "coupling_factors" in diag


# ---- clamping ----------------------------------------------------------------

class TestBoundaryClamping:

    def test_repair_respects_clamp(self, config_path: str):
        guard = BoundaryGuard(config_path)
        # hope 下界 0.1，冻结注入不应突破
        vec = _make_vec(**{d: 0.01 for d in ALL_DIMS})
        repaired, _ = guard.detect_and_repair(vec)
        assert repaired.get("hope", 0.0) >= 0.1

    def test_valence_not_below_floor(self, config_path: str):
        guard = BoundaryGuard(config_path)
        vec = _make_vec(**{d: 0.01 for d in ALL_DIMS})
        repaired, _ = guard.detect_and_repair(vec)
        assert repaired.get("valence", 0.0) >= -0.8


# ---- integration -------------------------------------------------------------

class TestIntegration:

    def test_multiple_repairs_can_coexist(self, config_path: str):
        guard = BoundaryGuard(config_path)
        # 先制造振荡
        for v in [0.6, -0.6, 0.6, -0.6]:
            guard.detect_and_repair(_make_vec(valence=v))
        # 再制造锁定
        vec = _make_vec(valence=0.3)
        for _ in range(6):
            repaired, diag = guard.detect_and_repair(vec)
        # 可能同时有锁定和振荡历史
        assert len(diag["repairs_applied"]) >= 1

    def test_window_does_not_grow_unbounded(self, config_path: str):
        guard = BoundaryGuard(config_path)
        for i in range(20):
            guard.detect_and_repair(_make_vec(valence=i * 0.01))
        # 窗口不应无限增长，内部实现有 pop
        assert len(guard._window) <= max(guard.lock_runs, guard.osc_window) + 1
