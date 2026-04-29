#!/usr/bin/env python3
"""test_persona_manager.py — 人格差异化配置单元测试"""

import json
from pathlib import Path

import pytest

from persona_manager import PersonaManager


# ---- fixtures -----------------------------------------------------------------

@pytest.fixture
def minimal_templates_path(tmp_path: Path) -> str:
    """只包含 lively 和 calm 两个模板的最小配置。"""
    p = tmp_path / "persona_templates.json"
    p.write_text(
        json.dumps(
            {
                "templates": {
                    "lively": {
                        "name": "活泼型",
                        "thresholds": {"intensity": 0.5, "surface_cooldown_seconds": 45},
                        "style_modifiers": {
                            "tone_boost": {"valence": 0.1, "arousal": 0.15},
                            "emoji_chance": 0.6,
                        },
                        "constraints": {"max_negative_valence": -0.6, "arousal_ceiling": 0.9},
                    },
                    "calm": {
                        "name": "冷静型",
                        "thresholds": {"intensity": 0.65, "surface_cooldown_seconds": 90},
                        "style_modifiers": {
                            "tone_boost": {"valence": 0.0, "arousal": -0.15},
                            "emoji_chance": 0.1,
                        },
                        "constraints": {"max_negative_valence": -0.8, "arousal_ceiling": 0.6},
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def sample_vec() -> dict:
    return {
        "valence": -0.5, "arousal": 0.8, "dominance": 0.2,
        "trust": 0.3, "intimacy": 0.2, "respect": 0.1, "forgiveness": 0.0,
        "curiosity": 0.4, "confusion": 0.1, "certainty": 0.3, "anticipation": 0.2,
        "nostalgia": 0.0, "impatience": 0.1, "relief": 0.2, "disappointment": -0.2, "hope": 0.3,
    }


# ---- init / load --------------------------------------------------------------

class TestPersonaManagerInit:

    def test_loads_external_config(self, minimal_templates_path: str):
        """应正确加载外部 JSON 配置。"""
        pm = PersonaManager(templates_path=minimal_templates_path)
        assert "lively" in pm.templates
        assert "calm" in pm.templates
        assert pm.active["name"] == "冷静型"  # 默认 calm

    def test_fallback_to_builtin_when_file_missing(self, tmp_path: Path):
        """文件不存在时应回退到内置默认模板。"""
        pm = PersonaManager(templates_path=str(tmp_path / "nonexistent.json"))
        assert "lively" in pm.templates
        assert "calm" in pm.templates
        assert "tsundere" in pm.templates
        assert "steady" in pm.templates

    def test_active_persona_override(self, minimal_templates_path: str):
        """active_persona 参数应覆盖默认值。"""
        pm = PersonaManager(
            templates_path=minimal_templates_path, active_persona="lively"
        )
        assert pm.active["name"] == "活泼型"


# ---- switch / list ------------------------------------------------------------

class TestSwitchAndList:

    def test_switch_valid(self, minimal_templates_path: str):
        """切换到存在的 persona 应成功。"""
        pm = PersonaManager(templates_path=minimal_templates_path)
        assert pm.switch("lively") is True
        assert pm.active["name"] == "活泼型"

    def test_switch_invalid(self, minimal_templates_path: str):
        """切换到不存在的 persona 应失败。"""
        pm = PersonaManager(templates_path=minimal_templates_path)
        assert pm.switch("nonexistent") is False
        assert pm.active["name"] == "冷静型"  # 保持不变

    def test_list_personas(self, minimal_templates_path: str):
        """list_personas 应返回所有模板概要。"""
        pm = PersonaManager(templates_path=minimal_templates_path)
        personas = pm.list_personas()
        keys = {p["key"] for p in personas}
        assert "lively" in keys
        assert "calm" in keys


# ---- apply constraints --------------------------------------------------------

class TestApplyConstraints:

    def test_calm_caps_arousal(self, minimal_templates_path: str, sample_vec: dict):
        """冷静型的 arousal_ceiling=0.6 应把高 arousal 钳制下来。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="calm")
        result = pm.apply_constraints(dict(sample_vec))
        assert result["arousal"] <= 0.6

    def test_lively_allows_higher_arousal(self, minimal_templates_path: str, sample_vec: dict):
        """活泼型的 tone_boost 提升 arousal，但 arousal_ceiling=0.9 会钳制上限。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="lively")
        result = pm.apply_constraints(dict(sample_vec))
        # 0.8 + 0.15 = 0.95，但被 ceiling 0.9 钳制
        assert result["arousal"] == pytest.approx(0.9, abs=1e-6)
        assert result["arousal"] <= 0.9

    def test_valence_floor(self, minimal_templates_path: str, sample_vec: dict):
        """max_negative_valence 应钳制负向 valence。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="lively")
        result = pm.apply_constraints(dict(sample_vec))
        assert result["valence"] >= -0.6  # lively 的 floor 是 -0.6

    def test_calm_allows_lower_valence(self, minimal_templates_path: str, sample_vec: dict):
        """冷静型的 max_negative_valence=-0.8 应允许更负的 valence。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="calm")
        result = pm.apply_constraints(dict(sample_vec))
        assert result["valence"] == pytest.approx(-0.5, abs=1e-6)

    def test_tone_boost_applied(self, minimal_templates_path: str, sample_vec: dict):
        """tone_boost 应正确加到对应维度。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="lively")
        result = pm.apply_constraints(dict(sample_vec))
        # lively 的 tone_boost: valence +0.1
        expected_valence = max(-1.0, min(1.0, -0.5 + 0.1))
        assert result["valence"] == pytest.approx(expected_valence, abs=1e-6)

    def test_no_side_effects_on_input(self, minimal_templates_path: str, sample_vec: dict):
        """apply_constraints 不应修改输入字典。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="lively")
        original = dict(sample_vec)
        pm.apply_constraints(sample_vec)
        assert sample_vec == original


# ---- expression params --------------------------------------------------------

class TestExpressionParams:

    def test_lively_lower_threshold(self, minimal_templates_path: str):
        """活泼型的 intensity threshold 应更低（更易表达）。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="lively")
        params = pm.expression_params()
        assert params["intensity_threshold"] == pytest.approx(0.5, abs=1e-6)

    def test_calm_higher_threshold(self, minimal_templates_path: str):
        """冷静型的 intensity threshold 应更高（更克制）。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="calm")
        params = pm.expression_params()
        assert params["intensity_threshold"] == pytest.approx(0.65, abs=1e-6)

    def test_calm_longer_cooldown(self, minimal_templates_path: str):
        """冷静型的冷却时间应更长。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="calm")
        params = pm.expression_params()
        assert params["surface_cooldown_seconds"] == 90
        assert params["deep_cooldown_seconds"] == 240  # 来自内置默认值合并


# ---- override -----------------------------------------------------------------

class TestShouldExpressOverride:

    def test_calm_suppresses_excited(self, minimal_templates_path: str):
        """冷静型应否决高激活情绪标签的表达。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="calm")
        override = pm.should_express_override("excited", 0.7, [])
        assert override is not None
        assert override["rewrite_hint"] == "suppress"

    def test_lively_no_override(self, minimal_templates_path: str):
        """活泼型对 excited 不应干预。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="lively")
        override = pm.should_express_override("excited", 0.7, [])
        assert override is None

    def test_tsundere_negation(self, tmp_path: Path, sample_vec: dict):
        """傲娇型应对深层情绪应用否定式改写。"""
        pm = PersonaManager(active_persona="tsundere")
        override = pm.should_express_override("vulnerable", 0.7, [])
        assert override is not None
        assert override["reason"] == "tsundere_negation"


# ---- style hints --------------------------------------------------------------

class TestStyleHints:

    def test_lively_high_emoji_chance(self, minimal_templates_path: str):
        """活泼型的 emoji_chance 应较高。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="lively")
        hints = pm.style_hints()
        assert hints["emoji_chance"] == pytest.approx(0.6, abs=1e-6)

    def test_calm_low_emoji_chance(self, minimal_templates_path: str):
        """冷静型的 emoji_chance 应较低。"""
        pm = PersonaManager(templates_path=minimal_templates_path, active_persona="calm")
        hints = pm.style_hints()
        assert hints["emoji_chance"] == pytest.approx(0.1, abs=1e-6)

    def test_style_hints_keys(self, minimal_templates_path: str):
        """style_hints 应包含必要键。"""
        pm = PersonaManager(templates_path=minimal_templates_path)
        hints = pm.style_hints()
        assert "punctuation_bias" in hints
        assert "sentence_endings" in hints


# ---- merge defaults -----------------------------------------------------------

class TestMergeDefaults:

    def test_missing_fields_filled_by_builtin(self, tmp_path: Path):
        """外部配置缺少的字段应由内置默认值补齐。"""
        p = tmp_path / "partial.json"
        p.write_text(
            json.dumps(
                {
                    "templates": {
                        "lively": {
                            "name": "活泼型",
                            "thresholds": {"intensity": 0.5},
                            # 缺少 style_modifiers 和 constraints
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        pm = PersonaManager(templates_path=str(p))
        lively = pm.templates["lively"]
        # constraints 应由内置补齐
        assert "constraints" in lively
        assert "style_modifiers" in lively
