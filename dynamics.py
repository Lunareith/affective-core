#!/usr/bin/env python3
"""dynamics.py — 情绪动力学：衰减、惯性、耦合(快照计算)、噪声、钳制"""

import json
import math
import random
from typing import Dict

from emotion_engine import DIMENSIONS, DEFAULT_BASELINE, CLAMP_RANGES


class Dynamics:
    """计算情绪状态的动力学变化。"""

    # 耦合矩阵：源维度 → {目标维度: 系数}
    COUPLING = {
        "trust": {"intimacy": 0.25},
        "intimacy": {"respect": 0.15},
        "disappointment": {"trust": -0.30, "hope": -0.15},
        "curiosity": {"anticipation": 0.20},
        "confusion": {"certainty": -0.25},
        "relief": {"valence": 0.35},
        "forgiveness": {"trust": 0.20},
    }

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        dyn = cfg.get("dynamics", {})
        self.decay_rate = dyn.get("decay_rate_per_run", 0.1)
        self.inertia = dyn.get("inertia_coeff", 0.3)
        self.noise_std = dyn.get("noise_std", 0.02)
        self.coupling_on = dyn.get("coupling_enabled", True)

    def update(self, current_vec: Dict[str, float], delta: Dict[str, float],
               baseline: Dict[str, float]) -> Dict[str, float]:
        """
        完整动力学更新管线：
        delta → 衰减 → 耦合(快照) → 惯性 → 噪声 → 钳制
        """
        new_vec = {}

        # 1. 应用 delta
        for dim in DIMENSIONS:
            new_vec[dim] = current_vec.get(dim, 0.0) + delta.get(dim, 0.0)

        # 2. 衰减向 baseline
        for dim in DIMENSIONS:
            base = baseline.get(dim, DEFAULT_BASELINE[dim])
            new_vec[dim] = new_vec[dim] + (base - new_vec[dim]) * self.decay_rate

        # 3. 耦合（快照计算，避免顺序副作用）
        if self.coupling_on:
            new_vec = self._apply_coupling(new_vec)

        # 4. 惯性平滑
        for dim in DIMENSIONS:
            old = current_vec.get(dim, 0.0)
            new_vec[dim] = new_vec[dim] * (1 - self.inertia) + old * self.inertia

        # 5. 噪声
        for dim in DIMENSIONS:
            new_vec[dim] += random.gauss(0, self.noise_std)

        # 6. 钳制
        for dim in DIMENSIONS:
            lo, hi = CLAMP_RANGES.get(dim, [-1.0, 1.0])
            new_vec[dim] = max(lo, min(hi, new_vec[dim]))

        return new_vec

    def _apply_coupling(self, vec: Dict[str, float]) -> Dict[str, float]:
        """基于原始快照计算耦合增量，一次性应用。"""
        snapshot = {k: v for k, v in vec.items()}
        deltas = {dim: 0.0 for dim in DIMENSIONS}

        for src, targets in self.COUPLING.items():
            if src not in snapshot:
                continue
            for tgt, coeff in targets.items():
                if tgt in deltas:
                    deltas[tgt] += snapshot[src] * coeff

        for dim in DIMENSIONS:
            vec[dim] += max(-0.1, min(0.1, deltas[dim]))

        return vec

    def decay_if_stale(self, current_vec: Dict[str, float], baseline: Dict[str, float],
                       minutes_offline: float) -> Dict[str, float]:
        """用户长时间未回复时的批量衰减补偿。"""
        new_vec = dict(current_vec)
        for dim in DIMENSIONS:
            base = baseline.get(dim, DEFAULT_BASELINE[dim])
            new_vec[dim] = new_vec[dim] + (base - new_vec[dim]) * self.decay_rate * (minutes_offline / 5)
            lo, hi = CLAMP_RANGES.get(dim, [-1.0, 1.0])
            new_vec[dim] = max(lo, min(hi, new_vec[dim]))
        return new_vec
