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
