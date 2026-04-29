#!/usr/bin/env python3
"""test_prompt_injector.py — Prompt注入层单元测试"""

import json
from pathlib import Path

import pytest

from prompt_injector import PromptInjector


# ---- fixtures -----------------------------------------------------------------

@pytest.fixture
def config_path(tmp_path: Path) -> str:
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "expression": {
                    "inject_threshold": 0.1,
                    "auto_inject_md": True,
                    "direct_inject": False,
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
        "valence": 0.5, "arousal": 0.3, "dominance": 0.2,
        "trust": 0.4, "intimacy": 0.3, "respect": 0.2, "forgiveness": 0.0,
        "curiosity": 0.6, "confusion": 0.1, "certainty": 0.4, "anticipation": 0.2,
        "nostalgia": 0.1, "impatience": 0.2, "relief": 0.3, "disappointment": 0.0, "hope": 0.5,
    }


# ---- init / config -----------------------------------------------------------

class TestPromptInjectorInit:

    def test_default_values_without_config(self, tmp_path: Path, sample_vec: dict):
        """无 config.json 时应使用硬编码默认值。"""
        injector = PromptInjector(workspace_dir=str(tmp_path))
        assert injector.threshold == 0.1
        assert injector.auto_inject_md is True
        assert injector.direct_inject is False

    def test_reads_config_override(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """config.json 中的 expression 节应覆盖默认值。"""
        injector = PromptInjector(config_path=config_path, workspace_dir=str(tmp_path))
        assert injector.threshold == 0.1
        assert injector.auto_inject_md is True
        assert injector.direct_inject is False

    def test_direct_inject_mode(self, config_path: str, sample_vec: dict):
        """direct_inject=True 时应返回文本而非写入文件。"""
        injector = PromptInjector(
            config_path=config_path, direct_inject=True, auto_inject_md=False
        )
        result = injector.update(sample_vec)
        assert isinstance(result, str)
        assert len(result) > 0


# ---- threshold / rewrite -------------------------------------------------------

class TestThresholdRewrite:

    def test_first_call_always_writes(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """首次调用无 last_written_vec，应始终触发写入。"""
        injector = PromptInjector(config_path=config_path, workspace_dir=str(tmp_path))
        injector.update(sample_vec)
        assert (tmp_path / "EMOTION_STATE.md").exists()

    def test_no_rewrite_when_change_below_threshold(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """变化量低于 threshold 时不应重写。"""
        injector = PromptInjector(config_path=config_path, workspace_dir=str(tmp_path), threshold=0.2)
        injector.update(sample_vec)
        mtime_before = (tmp_path / "EMOTION_STATE.md").stat().st_mtime

        # 只改变 0.05，低于 threshold 0.2
        vec2 = dict(sample_vec)
        vec2["valence"] = 0.55
        injector.update(vec2)
        mtime_after = (tmp_path / "EMOTION_STATE.md").stat().st_mtime

        assert mtime_before == mtime_after

    def test_rewrite_when_change_at_threshold(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """变化量等于 threshold 时应重写。"""
        injector = PromptInjector(config_path=config_path, workspace_dir=str(tmp_path), threshold=0.1)
        injector.update(sample_vec)
        content_before = (tmp_path / "EMOTION_STATE.md").read_text(encoding="utf-8")

        vec2 = dict(sample_vec)
        vec2["valence"] = 0.6  # 变化 0.1，等于 threshold
        injector.update(vec2)
        content_after = (tmp_path / "EMOTION_STATE.md").read_text(encoding="utf-8")

        assert content_after != content_before


# ---- summary content -----------------------------------------------------------

class TestSummaryContent:

    def test_summary_length_3_to_5_sentences(self, config_path: str, sample_vec: dict):
        """摘要应为 3-5 句话。"""
        injector = PromptInjector(config_path=config_path)
        text = injector.get_md_content(sample_vec)
        sentences = [s.strip() for s in text.split("。") if s.strip()]
        assert 3 <= len(sentences) <= 5

    def test_summary_contains_key_dimensions(self, config_path: str, sample_vec: dict):
        """摘要应包含关键维度数值。"""
        injector = PromptInjector(config_path=config_path)
        text = injector.get_md_content(sample_vec)
        assert "愉悦度" in text or "valence" in text
        assert "0." in text  # 至少有一个小数数值

    def test_summary_includes_derived_emotion(self, config_path: str, sample_vec: dict):
        """当有高强度派生情绪时应包含。"""
        injector = PromptInjector(config_path=config_path)
        derived = [{"label": "curious", "intensity": 0.8}]
        text = injector.get_md_content(sample_vec, derived_emotions=derived)
        assert "curious" in text or "好奇" in text

    def test_summary_includes_tone(self, config_path: str, sample_vec: dict):
        """tone 参数存在时应包含建议语气。"""
        injector = PromptInjector(config_path=config_path)
        text = injector.get_md_content(sample_vec, tone="warm")
        assert "warm" in text or "语气" in text


# ---- watched dims --------------------------------------------------------------

class TestWatchedDimensions:

    def test_only_watched_dims_trigger_rewrite(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """非 watched 维度的大变化不应触发重写。"""
        injector = PromptInjector(
            config_path=config_path, workspace_dir=str(tmp_path), threshold=0.1
        )
        injector.update(sample_vec)
        mtime_before = (tmp_path / "EMOTION_STATE.md").stat().st_mtime

        # nostalgia 不是 watched dim
        vec2 = dict(sample_vec)
        vec2["nostalgia"] = 0.9  # 大变化，但不在 watched 列表
        injector.update(vec2)
        mtime_after = (tmp_path / "EMOTION_STATE.md").stat().st_mtime

        # nostalgia 不是 watched，不应触发重写
        assert mtime_before == mtime_after


# ---- md file format ------------------------------------------------------------

class TestMdFileFormat:

    def test_md_has_header_comment(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """EMOTION_STATE.md 应有自动生成注释头。"""
        injector = PromptInjector(config_path=config_path, workspace_dir=str(tmp_path))
        injector.update(sample_vec)
        md = (tmp_path / "EMOTION_STATE.md").read_text(encoding="utf-8")
        assert md.startswith("<!-- 自动生成")

    def test_md_no_residual_tmp(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """原子写入后不应残留 .tmp 文件。"""
        injector = PromptInjector(config_path=config_path, workspace_dir=str(tmp_path))
        injector.update(sample_vec)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


# ---- direct inject -----------------------------------------------------------

class TestDirectInject:

    def test_direct_inject_returns_string(self, config_path: str, sample_vec: dict):
        """direct_inject 模式应返回字符串。"""
        injector = PromptInjector(
            config_path=config_path, direct_inject=True, auto_inject_md=False
        )
        result = injector.update(sample_vec)
        assert isinstance(result, str)
        assert "愉悦度" in result or "valence" in result

    def test_direct_inject_no_md_side_effect(self, config_path: str, tmp_path: Path, sample_vec: dict):
        """direct_inject 时不应写入 EMOTION_STATE.md。"""
        injector = PromptInjector(
            config_path=config_path,
            workspace_dir=str(tmp_path),
            direct_inject=True,
            auto_inject_md=False,
        )
        injector.update(sample_vec)
        assert not (tmp_path / "EMOTION_STATE.md").exists()

    def test_direct_inject_respects_threshold(self, config_path: str, sample_vec: dict):
        """direct_inject 也应遵守 threshold。"""
        injector = PromptInjector(
            config_path=config_path, direct_inject=True, threshold=0.2
        )
        result1 = injector.update(sample_vec)
        assert result1 is not None  # 首次应触发

        vec2 = dict(sample_vec)
        vec2["valence"] = 0.55  # 变化 0.05 < 0.2
        result2 = injector.update(vec2)
        assert result2 is None  # 不应触发
