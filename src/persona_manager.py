#!/usr/bin/env python3
"""persona_manager.py — 人格差异化配置管理器"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional


class PersonaManager:
    """
    从 JSON 配置加载人格模板，支持多种人格预设。
    每种人格有不同的表达阈值和话术风格。
    """

    # 内置默认模板（当 persona_templates.json 不存在时使用）
    DEFAULT_TEMPLATES: Dict[str, Dict] = {
        "lively": {
            "name": "活泼型",
            "description": "热情开朗，情绪外露，喜欢用感叹句和 emoji",
            "thresholds": {
                "intensity": 0.5,
                "surface_cooldown_seconds": 45,
                "deep_cooldown_seconds": 120,
            },
            "style_modifiers": {
                "punctuation_bias": "exclamation",
                "emoji_chance": 0.6,
                "sentence_ending": ["~", "！", "呀", "呢"],
                "tone_boost": {
                    "valence": 0.1,
                    "arousal": 0.15,
                },
            },
            "constraints": {
                "max_negative_valence": -0.6,
                "arousal_ceiling": 0.9,
            },
        },
        "calm": {
            "name": "冷静型",
            "description": "理性克制，情绪内敛，句式平稳",
            "thresholds": {
                "intensity": 0.65,
                "surface_cooldown_seconds": 90,
                "deep_cooldown_seconds": 240,
            },
            "style_modifiers": {
                "punctuation_bias": "period",
                "emoji_chance": 0.1,
                "sentence_ending": ["。", "，"],
                "tone_boost": {
                    "valence": 0.0,
                    "arousal": -0.15,
                },
            },
            "constraints": {
                "max_negative_valence": -0.8,
                "arousal_ceiling": 0.6,
            },
        },
        "tsundere": {
            "name": "傲娇型",
            "description": "嘴硬心软，否认式关怀，反差表达",
            "thresholds": {
                "intensity": 0.55,
                "surface_cooldown_seconds": 50,
                "deep_cooldown_seconds": 150,
            },
            "style_modifiers": {
                "punctuation_bias": "mixed",
                "emoji_chance": 0.3,
                "sentence_ending": ["哼", "…", "。"],
                "tone_boost": {
                    "valence": 0.05,
                    "arousal": 0.1,
                },
                "negation_patterns": [
                    "才不是因为{reason}呢",
                    "别误会，我{action}只是因为{excuse}",
                    "哼，{denial}",
                ],
            },
            "constraints": {
                "max_negative_valence": -0.5,
                "arousal_ceiling": 0.85,
            },
        },
        "steady": {
            "name": "稳重型",
            "description": "温和可靠，情绪稳定，给人以安全感",
            "thresholds": {
                "intensity": 0.7,
                "surface_cooldown_seconds": 120,
                "deep_cooldown_seconds": 300,
            },
            "style_modifiers": {
                "punctuation_bias": "period",
                "emoji_chance": 0.15,
                "sentence_ending": ["。", "吧", "就好"],
                "tone_boost": {
                    "valence": 0.05,
                    "arousal": -0.2,
                },
            },
            "constraints": {
                "max_negative_valence": -0.7,
                "arousal_ceiling": 0.5,
            },
        },
    }

    def __init__(
        self,
        templates_path: Optional[str] = None,
        active_persona: Optional[str] = None,
    ):
        """
        Args:
            templates_path: persona_templates.json 路径，默认搜索当前目录和 workspace
            active_persona: 当前激活的人格 key，None 时使用默认（calm）
        """
        self.templates: Dict[str, Dict] = {}
        self._active_key: str = active_persona or "calm"
        self._load_templates(templates_path)

    # ------------------------------------------------------------------
    # 配置加载
    # ------------------------------------------------------------------
    def _load_templates(self, path: Optional[str]) -> None:
        """加载外部 JSON 配置；失败则回退到内置默认值。"""
        searched_paths: List[Path] = []

        if path:
            searched_paths.append(Path(path))
        else:
            # 默认搜索路径
            searched_paths.extend([
                Path("persona_templates.json"),
                Path("config/persona_templates.json"),
                Path.cwd() / "persona_templates.json",
            ])

        for p in searched_paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.templates = data.get("templates", {})
                    # 合并缺省项：如果外部配置缺少某些字段，用内置补齐
                    for key, default in self.DEFAULT_TEMPLATES.items():
                        if key not in self.templates:
                            self.templates[key] = default
                        else:
                            self._merge_defaults(self.templates[key], default)
                    return
                except (json.JSONDecodeError, OSError):
                    continue

        # 全部搜索失败 → 回退到内置
        self.templates = dict(self.DEFAULT_TEMPLATES)

    @staticmethod
    def _merge_defaults(target: Dict, default: Dict) -> None:
        """深度合并：target 缺少的 key 用 default 补齐。"""
        for k, v in default.items():
            if k not in target:
                target[k] = v
            elif isinstance(v, dict) and isinstance(target.get(k), dict):
                PersonaManager._merge_defaults(target[k], v)

    # ------------------------------------------------------------------
    # 人格查询与切换
    # ------------------------------------------------------------------
    @property
    def active(self) -> Dict:
        """返回当前激活的人格完整配置。"""
        return self.templates.get(self._active_key, self.DEFAULT_TEMPLATES["calm"])

    def switch(self, persona_key: str) -> bool:
        """切换人格，返回是否成功。"""
        if persona_key not in self.templates:
            return False
        self._active_key = persona_key
        return True

    def list_personas(self) -> List[Dict[str, str]]:
        """列出所有人格预设（仅 name + key）。"""
        return [
            {"key": k, "name": v.get("name", k), "description": v.get("description", "")}
            for k, v in self.templates.items()
        ]

    # ------------------------------------------------------------------
    # 应用人格约束到情绪向量
    # ------------------------------------------------------------------
    def apply_constraints(self, vec: Dict[str, float]) -> Dict[str, float]:
        """应用当前人格的硬约束到情绪向量。"""
        result = dict(vec)

        # 1. style_modifiers 中的 tone_boost（先应用）
        boosts = self.active.get("style_modifiers", {}).get("tone_boost", {})
        for dim, boost in boosts.items():
            if dim in result:
                result[dim] = max(-1.0, min(1.0, result[dim] + boost))

        # 2. 硬约束（后应用，确保不被 tone_boost 突破）
        constraints = self.active.get("constraints", {})
        max_neg = constraints.get("max_negative_valence")
        if max_neg is not None and result.get("valence", 0.0) < max_neg:
            result["valence"] = max_neg

        arousal_cap = constraints.get("arousal_ceiling")
        if arousal_cap is not None and result.get("arousal", 0.0) > arousal_cap:
            result["arousal"] = arousal_cap

        return result

    # ------------------------------------------------------------------
    # 表达参数查询
    # ------------------------------------------------------------------
    def expression_params(self) -> Dict[str, float]:
        """返回当前人格的表达参数（供 Expressor 使用）。"""
        thresholds = self.active.get("thresholds", {})
        return {
            "intensity_threshold": thresholds.get("intensity", 0.6),
            "surface_cooldown_seconds": thresholds.get("surface_cooldown_seconds", 60),
            "deep_cooldown_seconds": thresholds.get("deep_cooldown_seconds", 180),
        }

    def should_express_override(
        self,
        emotion_label: str,
        intensity: float,
        last_expressions: List[str],
    ) -> Optional[Dict[str, str]]:
        """
        人格对表达的最终否决/改写权。
        返回 None 表示不干预；返回 dict 表示改写后的表达建议。
        """
        style = self.active.get("style_modifiers", {})

        # 傲娇型：对深层情绪的否定式改写
        if self._active_key == "tsundere" and emotion_label in {"vulnerable", "grateful", "lonely"}:
            negation_pool = style.get("negation_patterns", [])
            if negation_pool:
                pattern = random.choice(negation_pool)
                return {
                    "emotion_label": emotion_label,
                    "rewrite_hint": pattern,
                    "reason": "tsundere_negation",
                }

        # 冷静型：过滤过于兴奋的情绪标签
        if self._active_key == "calm" and emotion_label in {"excited", "surprised"}:
            return {
                "emotion_label": emotion_label,
                "rewrite_hint": "suppress",
                "reason": "calm_suppress_high_arousal",
            }

        return None

    # ------------------------------------------------------------------
    # 话术风格查询
    # ------------------------------------------------------------------
    def style_hints(self) -> Dict[str, any]:
        """返回当前人格的文本风格提示（供下游渲染使用）。"""
        style = self.active.get("style_modifiers", {})
        return {
            "punctuation_bias": style.get("punctuation_bias", "period"),
            "emoji_chance": style.get("emoji_chance", 0.0),
            "sentence_endings": style.get("sentence_ending", [""]),
        }
