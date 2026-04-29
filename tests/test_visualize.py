#!/usr/bin/env python3
"""test_visualize.py — 可视化仪表盘单元测试"""

import json
from pathlib import Path

import pytest

from visualize import TerminalRadarChart, HTMLDashboard, DIMENSIONS


@pytest.fixture
def config_path(tmp_path: Path) -> str:
    state_file = tmp_path / "emotion-state.json"
    state_file.write_text(
        json.dumps(
            {
                "vec": {
                    "valence": 0.3, "arousal": 0.5, "dominance": 0.2,
                    "trust": 0.4, "intimacy": 0.2, "respect": 0.1, "forgiveness": 0.0,
                    "curiosity": 0.6, "confusion": 0.1, "certainty": 0.3, "anticipation": 0.2,
                    "nostalgia": 0.1, "impatience": 0.0, "relief": 0.2, "disappointment": -0.1, "hope": 0.4,
                },
                "baseline": {
                    "valence": 0.1, "arousal": 0.3, "dominance": 0.2,
                    "trust": 0.0, "intimacy": 0.0, "respect": 0.0, "forgiveness": 0.0,
                    "curiosity": 0.5, "confusion": 0.0, "certainty": 0.3, "anticipation": 0.2,
                    "nostalgia": 0.0, "impatience": 0.0, "relief": 0.0, "disappointment": 0.0, "hope": 0.1,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    journal_file = tmp_path / "emotion-journal.jsonl"
    journal_file.write_text(
        json.dumps({"ts": "2026-04-29T10:00:00Z", "vec": {"valence": 0.3, "arousal": 0.5}, "trigger": "test"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "visualization": {"html_export_path": str(tmp_path / "dashboard.html")},
                "memory": {
                    "state_path": str(state_file),
                    "journal_path": str(journal_file),
                    "audit_dir": str(tmp_path / "audit"),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(p)


# ---- TerminalRadarChart ------------------------------------------------------

class TestTerminalRadarChart:

    def test_render_returns_string(self):
        vec = {d: 0.3 for d in DIMENSIONS}
        result = TerminalRadarChart().render(vec)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_contains_dimension_names(self):
        vec = {d: 0.2 + (i % 5) * 0.15 for i, d in enumerate(DIMENSIONS)}
        result = TerminalRadarChart().render(vec)
        # 至少部分维度名或短名应出现在输出中
        assert any(d in result or d[:2] in result for d in DIMENSIONS)

    def test_render_contains_title(self):
        vec = {d: 0.3 for d in DIMENSIONS}
        result = TerminalRadarChart().render(vec, title="Test Radar")
        assert "Test Radar" in result

    def test_render_width_matches(self):
        vec = {d: 0.3 for d in DIMENSIONS}
        result = TerminalRadarChart(width=40, height=20).render(vec)
        lines = result.split("\n")
        assert len(lines) == 20
        assert len(lines[0]) == 40

    def test_quick_staticmethod(self):
        vec = {d: 0.3 for d in DIMENSIONS}
        result = TerminalRadarChart.quick(vec)
        assert isinstance(result, str)
        assert "Affective Core Radar" in result

    def test_empty_vec_handled(self):
        result = TerminalRadarChart().render({})
        assert isinstance(result, str)


# ---- HTMLDashboard -----------------------------------------------------------

class TestHTMLDashboard:

    def test_generate_creates_file(self, config_path: str, tmp_path: Path):
        dash = HTMLDashboard(config_path)
        result = dash.generate(str(tmp_path / "out.html"))
        assert Path(result).exists()

    def test_generated_file_contains_html(self, config_path: str, tmp_path: Path):
        dash = HTMLDashboard(config_path)
        path = dash.generate(str(tmp_path / "out.html"))
        content = Path(path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Affective Core Dashboard" in content

    def test_generated_file_contains_radar_canvas(self, config_path: str, tmp_path: Path):
        dash = HTMLDashboard(config_path)
        path = dash.generate(str(tmp_path / "out.html"))
        content = Path(path).read_text(encoding="utf-8")
        assert '<canvas id="radar"' in content

    def test_generated_file_contains_data(self, config_path: str, tmp_path: Path):
        dash = HTMLDashboard(config_path)
        path = dash.generate(str(tmp_path / "out.html"))
        content = Path(path).read_text(encoding="utf-8")
        # 应有维度数据注入
        assert "valence" in content
        assert "arousal" in content

    def test_quick_classmethod(self, config_path: str, tmp_path: Path):
        result = HTMLDashboard.quick(str(tmp_path / "quick.html"), config_path=config_path)
        assert Path(result).exists()

    def test_load_state_empty_when_no_file(self, tmp_path: Path):
        p = tmp_path / "no_state_config.json"
        p.write_text(
            json.dumps(
                {
                    "visualization": {"html_export_path": str(tmp_path / "d.html")},
                    "memory": {
                        "state_path": str(tmp_path / "nonexistent.json"),
                        "journal_path": str(tmp_path / "nonexistent.jsonl"),
                        "audit_dir": str(tmp_path / "nonexistent_audit"),
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        dash = HTMLDashboard(str(p))
        state = dash._load_state()
        assert state == {}

    def test_load_journal_empty_when_no_file(self, config_path: str, tmp_path: Path):
        p = tmp_path / "no_journal_config.json"
        p.write_text(
            json.dumps(
                {
                    "visualization": {"html_export_path": str(tmp_path / "d.html")},
                    "memory": {
                        "state_path": str(tmp_path / "nonexistent.json"),
                        "journal_path": str(tmp_path / "nonexistent.jsonl"),
                        "audit_dir": str(tmp_path / "nonexistent_audit"),
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        dash = HTMLDashboard(str(p))
        journal = dash._load_journal()
        assert journal == []

    def test_html_has_timeline_section(self, config_path: str, tmp_path: Path):
        dash = HTMLDashboard(config_path)
        path = dash.generate(str(tmp_path / "out.html"))
        content = Path(path).read_text(encoding="utf-8")
        assert 'id="timeline"' in content

    def test_html_has_audit_section(self, config_path: str, tmp_path: Path):
        dash = HTMLDashboard(config_path)
        path = dash.generate(str(tmp_path / "out.html"))
        content = Path(path).read_text(encoding="utf-8")
        assert 'id="audit"' in content


# ---- CLI ---------------------------------------------------------------------

class TestCLI:

    def test_main_missing_args(self, capsys):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["visualize"]
            from visualize import main
            rc = main()
            assert rc == 1
        finally:
            sys.argv = old_argv

    def test_main_with_args(self, config_path: str, tmp_path: Path, capsys):
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["visualize", config_path, str(tmp_path / "cli.html")]
            from visualize import main
            rc = main()
            captured = capsys.readouterr()
            assert rc == 0
            assert "HTML Dashboard 已生成" in captured.out
        finally:
            sys.argv = old_argv
