#!/usr/bin/env python3
"""test_safety.py - 安全边界模块契约测试"""

import json
from pathlib import Path

import pytest


try:
    from safety import SafetyGuard
except ImportError:
    from src.safety import SafetyGuard


@pytest.fixture
def config_path(tmp_path: Path) -> str:
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "safety": {
                    "pathology_filter_enabled": True,
                    "pathology_patterns": [
                        "(?i)你.*抑郁",
                        "(?i)你.*焦虑",
                        "(?i)你.*ptsd",
                        "(?i)你.*心理.*病",
                        "(?i)你.*需要.*医生",
                        "(?i)你.*障碍",
                        "(?i)你.*综合征"
                    ],
                    "max_negative_valence": -0.8,
                    "anomaly_window_runs": 3,
                    "anomaly_valence_threshold": -0.5,
                    "anomaly_arousal_threshold": 0.7,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(p)


class TestSafetyMockFallback:

    def test_clamp_respects_boundaries(self, config_path):
        if SafetyGuard is None:
            assert True
            return
        s = SafetyGuard(config_path)
        vec = {"valence": -0.9, "arousal": 1.5}
        result = s.clamp(vec)
        assert result["valence"] >= -0.8
        assert result["arousal"] <= 1.0

    def test_pathology_filter_blocks_diagnosis(self, config_path):
        if SafetyGuard is None:
            assert True
            return
        s = SafetyGuard(config_path)
        text = "你看起来抑郁了，需要看心理医生"
        result = s.filter_pathology(text)
        assert "抑郁" not in result
        assert "心理医生" not in result

    def test_pathology_filter_allows_empathy(self, config_path):
        if SafetyGuard is None:
            assert True
            return
        s = SafetyGuard(config_path)
        text = "听起来你很难过"
        result = s.filter_pathology(text)
        assert "难过" in result  # 共情表达应通过

    def test_anomaly_detection_high_arousal_negative(self, config_path):
        if SafetyGuard is None:
            assert True
            return
        s = SafetyGuard(config_path)
        history = [
            {"valence": -0.6, "arousal": 0.8},
            {"valence": -0.7, "arousal": 0.9},
            {"valence": -0.6, "arousal": 0.85},
        ]
        assert s.check_anomaly(history) is True

    def test_anomaly_detection_normal_range(self, config_path):
        if SafetyGuard is None:
            assert True
            return
        s = SafetyGuard(config_path)
        history = [
            {"valence": 0.2, "arousal": 0.4},
            {"valence": 0.1, "arousal": 0.3},
            {"valence": 0.3, "arousal": 0.5},
        ]
        assert s.check_anomaly(history) is False

    def test_filter_vec_caps_negative(self, config_path):
        if SafetyGuard is None:
            assert True
            return
        s = SafetyGuard(config_path)
        vec = {"valence": -0.95}
        result = s.filter_vec_for_expression(vec)
        assert result["valence"] >= -0.8
