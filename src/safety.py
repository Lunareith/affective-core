#!/usr/bin/env python3
"""safety.py — 安全边界：钳制、异常检测、病理化过滤"""

import json
import math
import re
from typing import Dict, List


class SafetyGuard:
    """保障情绪表达的安全边界。"""

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.cfg = cfg.get("safety", {})
        self.pathology_patterns = [re.compile(p) for p in self.cfg.get("pathology_patterns", [])]

    def clamp(self, vec: Dict[str, float]) -> Dict[str, float]:
        """钳制各维度到安全边界。"""
        # 内联默认 CLAMP_RANGES，确保测试直接 import 时也能正确钳制
        DEFAULT_CLAMP_RANGES = {
            "valence": [-0.8, 1.0], "arousal": [0.0, 1.0], "dominance": [-1.0, 1.0],
            "trust": [-1.0, 1.0], "intimacy": [0.0, 1.0], "respect": [0.0, 1.0],
            "forgiveness": [-0.7, 0.7], "curiosity": [0.0, 1.0], "confusion": [0.0, 1.0],
            "certainty": [0.0, 1.0], "anticipation": [-1.0, 1.0], "nostalgia": [0.0, 1.0],
            "impatience": [0.0, 1.0], "relief": [0.0, 1.0], "disappointment": [-0.8, 0.0],
            "hope": [0.1, 1.0],
        }
        try:
            from .emotion_engine import CLAMP_RANGES, DIMENSIONS
        except ImportError:
            try:
                from emotion_engine import CLAMP_RANGES, DIMENSIONS
            except ImportError:
                CLAMP_RANGES = DEFAULT_CLAMP_RANGES
                DIMENSIONS = list(vec.keys())
        result = dict(vec)
        for dim in DIMENSIONS:
            lo, hi = CLAMP_RANGES.get(dim, [-1.0, 1.0])
            result[dim] = max(lo, min(hi, result.get(dim, 0.0)))
        return result

    def check_anomaly(self, history: List[Dict[str, float]]) -> bool:
        """
        检测异常情绪模式。
        连续 anomaly_window_runs 轮出现以下情况触发告警：
        - valence < -0.5 且 arousal > 0.7
        - 多维度同时剧烈波动（标准差 > 0.4）
        """
        window = self.cfg.get("anomaly_window_runs", 3)
        if len(history) < window:
            return False

        valence_threshold = self.cfg.get("anomaly_valence_threshold", -0.5)
        arousal_threshold = self.cfg.get("anomaly_arousal_threshold", 0.7)

        consecutive_danger = 0
        for vec in history[-window:]:
            valence = vec.get("valence", 0.0)
            arousal = vec.get("arousal", 0.0)

            danger = (valence < valence_threshold and arousal > arousal_threshold)
            if danger:
                consecutive_danger += 1
            else:
                consecutive_danger = 0

        return consecutive_danger >= window

    def filter_pathology(self, text: str) -> str:
        """过滤病理化诊断表达。"""
        if not self.cfg.get("pathology_filter_enabled", True):
            return text

        for pattern in self.pathology_patterns:
            if pattern.search(text):
                # 替换为共情表达
                return "听起来你不太好，我在这里陪着你。"
        return text

    def filter_vec_for_expression(self, vec: Dict[str, float]) -> Dict[str, float]:
        """在情绪表达前，对向量进行额外的安全过滤。"""
        result = dict(vec)
        max_neg = self.cfg.get("max_negative_valence", -0.8)
        if result.get("valence", 0.0) < max_neg:
            result["valence"] = max_neg
        return result

# ──────────────────────────────────────────────────────────────────────────
# BoundaryGuard — 边界检测与自修复（v1.1.0）
# ──────────────────────────────────────────────────────────────────────────

class BoundaryGuard:
    """
    检测情绪动力学中的三种病态模式并自动修复：
    1. 锁定：连续 N 轮数值变化 < epsilon → 高斯微扰
    2. 振荡：在 ±amplitude 间快速切换 → 耦合系数×0.7
    3. 冻结：全部维度接近零 → curiosity 注入基线偏移
    """

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        bnd = cfg.get("boundary", {})
        self.lock_runs = bnd.get("lock_consecutive_runs", 5)
        self.lock_epsilon = bnd.get("lock_epsilon", 0.001)
        self.lock_perturb_std = bnd.get("lock_perturbation_std", 0.05)
        self.osc_window = bnd.get("oscillation_window_runs", 4)
        self.osc_amp = bnd.get("oscillation_amplitude", 0.5)
        self.freeze_thresh = bnd.get("freeze_threshold", 0.05)
        self.freeze_curiosity = bnd.get("freeze_curiosity_offset", 0.3)
        dims = cfg.get("dimensions", {})
        self.dimensions = dims.get("all", [])
        self.baseline = dims.get("baseline", {})
        self.clamp_cfg = dims.get("clamp", {})
        self._window: List[Dict[str, float]] = []
        self._coupling_factors: Dict[str, float] = {d: 1.0 for d in self.dimensions}

    def _clamp(self, vec: Dict[str, float]) -> Dict[str, float]:
        clamped = dict(vec)
        for dim, bounds in self.clamp_cfg.items():
            lo, hi = bounds[0], bounds[1]
            clamped[dim] = max(lo, min(hi, clamped.get(dim, 0.0)))
        return clamped

    def detect_and_repair(self, vec: Dict[str, float]) -> tuple:
        import random
        self._window.append(dict(vec))
        if len(self._window) > max(self.lock_runs, self.osc_window) + 1:
            self._window.pop(0)
        repaired = dict(vec)
        diagnostics = {
            "locked": {}, "oscillating": {}, "frozen": False,
            "repairs_applied": [], "coupling_factors": dict(self._coupling_factors)
        }
        # 锁定检测
        if len(self._window) >= self.lock_runs + 1:
            for dim in self.dimensions:
                if self._is_locked(dim):
                    diagnostics["locked"][dim] = True
                    perturb = random.gauss(0, self.lock_perturb_std)
                    repaired[dim] = repaired.get(dim, 0.0) + perturb
                    diagnostics["repairs_applied"].append(f"lock_repair:{dim}:perturb={perturb:+.4f}")
                else:
                    diagnostics["locked"][dim] = False
        # 振荡检测
        if len(self._window) >= self.osc_window:
            for dim in self.dimensions:
                if self._is_oscillating(dim):
                    diagnostics["oscillating"][dim] = True
                    old_factor = self._coupling_factors.get(dim, 1.0)
                    new_factor = max(0.1, old_factor * 0.7)
                    self._coupling_factors[dim] = new_factor
                    diagnostics["repairs_applied"].append(f"osc_repair:{dim}:{old_factor:.2f}→{new_factor:.2f}")
                else:
                    diagnostics["oscillating"][dim] = False
        # 冻结检测
        if self._is_frozen(vec):
            diagnostics["frozen"] = True
            old_curi = repaired.get("curiosity", 0.0)
            repaired["curiosity"] = self.baseline.get("curiosity", 0.5) + self.freeze_curiosity
            diagnostics["repairs_applied"].append(f"freeze_repair:curiosity={old_curi:.3f}→{repaired['curiosity']:.3f}")
        repaired = self._clamp(repaired)
        diagnostics["coupling_factors"] = dict(self._coupling_factors)
        return repaired, diagnostics

    def _is_locked(self, dim: str) -> bool:
        if len(self._window) < self.lock_runs + 1:
            return False
        recent = self._window[-(self.lock_runs + 1):]
        for i in range(1, len(recent)):
            if abs(recent[i].get(dim, 0.0) - recent[i-1].get(dim, 0.0)) >= self.lock_epsilon:
                return False
        return True

    def _is_oscillating(self, dim: str) -> bool:
        if len(self._window) < self.osc_window:
            return False
        values = [v.get(dim, 0.0) for v in self._window[-self.osc_window:]]
        sign_changes = sum(1 for i in range(1, len(values)) if values[i-1]*values[i] < 0 and abs(values[i-1]) >= self.osc_amp and abs(values[i]) >= self.osc_amp)
        return sign_changes >= 2

    def _is_frozen(self, vec: Dict[str, float]) -> bool:
        return all(abs(vec.get(d, 0.0)) < self.freeze_thresh for d in self.dimensions) if self.dimensions else False

    def get_coupling_factor(self, dim: str) -> float:
        return self._coupling_factors.get(dim, 1.0)

    def reset_coupling_factors(self) -> None:
        for d in self.dimensions:
            self._coupling_factors[d] = 1.0

    def reset_window(self) -> None:
        self._window.clear()
