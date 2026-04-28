#!/usr/bin/env python3
"""test_gate.py - Gate 模块契约测试"""

import json
from pathlib import Path

import pytest


try:
    from gate import KeywordGate
except ImportError:
    from src.gate import KeywordGate


@pytest.fixture
def config_path(tmp_path: Path) -> str:
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "gate": {
                    "mode": "rule",
                    "keyword_gate": {
                        "similarity_threshold": 0.7,
                        "emotion_keywords": {
                            "positive_shift": ["开心", "谢谢", "喜欢", "太好了"],
                            "negative_shift": ["失望", "生气", "难过", "讨厌"],
                            "intimacy_signal": ["秘密", "小时候", "家人", "只告诉你"],
                            "task_mode": ["执行", "运行", "查询", "设置"],
                        },
                        "max_keywords": 20,
                        "use_jaccard": True,
                        "use_regex": True,
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(p)


class TestGateMockFallback:

    def test_rule_gate_triggers_on_keywords(self, config_path):
        if KeywordGate is None:
            assert True
            return
        g = KeywordGate(config_path)
        result = g.should_trigger("我今天很开心", "")
        assert result["triggered"] is True
        assert result["reason"] == "keyword_match"

    def test_rule_gate_does_not_trigger_on_neutral(self, config_path):
        if KeywordGate is None:
            assert True
            return
        g = KeywordGate(config_path)
        result = g.should_trigger("今天星期几", "")
        assert result["triggered"] is False

    def test_rule_gate_task_mode_detected(self, config_path):
        if KeywordGate is None:
            assert True
            return
        g = KeywordGate(config_path)
        result = g.should_trigger("执行这个任务", "")
        assert result.get("task_mode") is True
