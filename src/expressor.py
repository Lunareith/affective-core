#!/usr/bin/env python3
"""expressor.py — 主动表达门控：强度 + 冷却 + 任务检测 + 类型新颖性"""

import json
import time
from datetime import timezone
from typing import Dict, List, Any


class Expressor:
    """判断 Agent 是否应该在下一轮主动表达某个派生情绪。"""

    # 深层情绪标签（冷却时间较长）
    DEEP_LABELS = {"vulnerable", "grateful", "bittersweet", "guilty", "lonely", "overwhelmed"}

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        exp = cfg.get("expression", {})
        self.intensity_threshold = exp.get("intensity_threshold", 0.6)
        self.surface_cooldown = exp.get("surface_cooldown_seconds", 60)
        self.deep_cooldown = exp.get("deep_cooldown_seconds", 180)
        self.novelty_check = exp.get("novelty_check_enabled", True)
        self.density_fast_ms = exp.get("density_fast_threshold_ms", 30000)
        self.density_slow_ms = exp.get("density_slow_threshold_ms", 300000)

    def should_express(self, derived_emotions: List[Dict[str, Any]],
                       last_expressions: List[str],
                       last_expression_ts: float,
                       conversation_density: str = "normal",
                       is_task_mode: bool = False) -> Dict[str, Any]:
        """
        四重门控：
        1. 强度 > threshold
        2. 冷却时间到
        3. 非任务密集
        4. 类型新颖（与最近3轮不同）

        conversation_density: "fast" | "normal" | "slow"
        """
        if is_task_mode:
            return {"should_express": False, "reason": "task_mode"}

        now_ts = time.time()

        for emo in derived_emotions:
            intensity = emo.get("intensity", 0.0)
            label = emo.get("label", "")

            # 门控 1：强度
            if intensity < self.intensity_threshold:
                continue

            # 门控 2：冷却
            is_deep = label in self.DEEP_LABELS
            cooldown = self.deep_cooldown if is_deep else self.surface_cooldown
            if conversation_density == "fast":
                cooldown = int(cooldown * 0.6)
            elif conversation_density == "slow":
                cooldown = int(cooldown * 1.5)

            if now_ts - last_expression_ts < cooldown:
                continue

            # 门控 3：任务密集已在入口拦截

            # 门控 4：类型新颖性
            if self.novelty_check and label in last_expressions[-3:]:
                continue

            # 通过所有门控
            return {
                "should_express": True,
                "emotion_label": label,
                "intensity": intensity,
                "is_deep": is_deep,
                "cooldown": cooldown,
            }

        return {"should_express": False, "emotion_label": None}
