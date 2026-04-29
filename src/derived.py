#!/usr/bin/env python3
"""derived.py — 派生情绪计算：权重矩阵模式，无 eval"""

from pathlib import Path
from typing import Dict, List, Any

import yaml


class DerivedEmotions:
    """基于权重矩阵计算派生情绪强度。"""

    def __init__(self, rules_path: str = "rules/derived_emotions.yaml"):
        self.rules_path = Path(rules_path)
        self.rules: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.rules_path.exists():
            return
        with open(self.rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.rules = data.get("rules", [])
        self.meta = data.get("meta", {})

    def compute(self, vec: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        计算所有派生情绪的强度。
        返回按强度降序排列的列表：[{"label": "tender", "intensity": 0.72}, ...]
        """
        results = []
        valence = vec.get("valence", 0.0)
        inhibit_threshold = self.meta.get("valence_inhibit_threshold", -0.2)

        for rule in self.rules:
            weights = rule.get("weights", {})
            intensity = 0.0
            for dim, w in weights.items():
                intensity += vec.get(dim, 0.0) * w

            # valence 抑制：当 valence 为负时，抑制正价派生情绪
            if valence < inhibit_threshold and intensity > 0:
                intensity *= max(0.0, 1.0 + valence)

            # 钳制到 [0, 1]
            intensity = max(0.0, min(1.0, intensity))

            threshold = rule.get("threshold", 0.35)
            if intensity >= threshold:
                results.append({
                    "label": rule["label"],
                    "intensity": round(intensity, 3),
                    "description": rule.get("description", ""),
                })

        return sorted(results, key=lambda x: x["intensity"], reverse=True)
