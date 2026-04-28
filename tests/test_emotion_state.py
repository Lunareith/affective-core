#!/usr/bin/env python3
"""test_emotion_state.py - 状态管理单元测试"""

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from emotion_state import EmotionState


# ---- fixtures -----------------------------------------------------------------

@pytest.fixture
def tmp_state(tmp_path: Path) -> EmotionState:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "baseline": {
                    "valence": 0.1, "arousal": 0.3, "dominance": 0.2,
                    "trust": 0.0, "intimacy": 0.0, "respect": 0.0, "forgiveness": 0.0,
                    "curiosity": 0.5, "confusion": 0.0, "certainty": 0.3, "anticipation": 0.2,
                    "nostalgia": 0.0, "impatience": 0.0, "relief": 0.0,
                    "disappointment": 0.0, "hope": 0.1,
                },
                "dynamics": {"decay_rate": 0.05},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return EmotionState(str(config_path))


# ---- init / reset ------------------------------------------------------------

def test_init_creates_empty_state(tmp_state: EmotionState) -> None:
    s = tmp_state
    assert s.state_file.exists() is False
    assert s.backup_dir.exists() is False


def test_reset_creates_state_file(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    assert s.state_file.exists()
    assert s.backup_dir.exists()


def test_reset_creates_all_dimensions(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    cur = s.get_current()
    expected = [
        "valence", "arousal", "dominance",
        "trust", "intimacy", "respect", "forgiveness",
        "curiosity", "confusion", "certainty", "anticipation",
        "nostalgia", "impatience", "relief", "disappointment", "hope",
    ]
    for dim in expected:
        assert dim in cur["vec"], f"维度 {dim} 缺失"


# ---- persistence --------------------------------------------------------------

def test_save_and_load_roundtrip(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    s.update_vec({"valence": 0.5, "trust": 0.3})
    s2 = EmotionState(str(s.config_path))
    assert s2.get_current()["vec"]["valence"] == pytest.approx(0.5, abs=1e-6)
    assert s2.get_current()["vec"]["trust"] == pytest.approx(0.3, abs=1e-6)


def test_load_from_backup_on_corruption(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    s.update_vec({"valence": 0.8})
    # 损坏主文件
    s.state_file.write_text("NOT JSON", encoding="utf-8")
    s2 = EmotionState(str(s.config_path))
    assert s2.get_current()["vec"]["valence"] == pytest.approx(0.8, abs=1e-6)


def test_load_from_baseline_on_total_corruption(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    s.update_vec({"valence": 0.8})
    # 损坏所有备份
    s.state_file.write_text("NOT JSON", encoding="utf-8")
    for i in range(1, 4):
        bak = s.backup_dir / f"state.json.bak{i}"
        if bak.exists():
            bak.write_text("NOT JSON", encoding="utf-8")
    s2 = EmotionState(str(s.config_path))
    assert s2.get_current()["vec"]["valence"] == pytest.approx(0.1, abs=1e-6)  # 基线


# ---- backup -------------------------------------------------------------------

def test_backup_rotation(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    for i in range(5):
        s.update_vec({"valence": i / 10.0})
    # 最多 3 个备份
    backups = sorted(s.backup_dir.glob("state.json.bak*"))
    assert len(backups) == 3


# ---- update -------------------------------------------------------------------

def test_update_applies_delta(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    s.update_vec({"valence": 0.5, "trust": 0.3})
    assert s.get_current()["vec"]["valence"] == pytest.approx(0.5, abs=1e-6)
    assert s.get_current()["vec"]["trust"] == pytest.approx(0.3, abs=1e-6)


def test_update_clamps_to_range(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    s.update_vec({"valence": 999.0})
    assert s.get_current()["vec"]["valence"] <= 1.0


def test_update_nonexistent_dimension_ignored(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    s.update_vec({"nonexistent": 0.9})
    assert "nonexistent" not in s.get_current()["vec"]


# ---- timestamp ----------------------------------------------------------------

def test_timestamp_updated_on_save(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    before = datetime.now(timezone.utc)
    time.sleep(0.01)
    s.update_vec({"valence": 0.2})
    after = datetime.now(timezone.utc)
    ts = s.get_current()["last_update"]
    assert before <= ts <= after


# ---- idempotency --------------------------------------------------------------

def test_idempotent_updates(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    s.update_vec({"valence": 0.5})
    val1 = s.get_current()["vec"]["valence"]
    s.update_vec({"valence": 0.5})
    val2 = s.get_current()["vec"]["valence"]
    assert val2 == pytest.approx(0.5, abs=1e-6)  # idempotent


# ---- atomic write --------------------------------------------------------------

def test_atomic_write_no_partial_files(tmp_state: EmotionState) -> None:
    s = tmp_state
    s.reset()
    tmp_files = list(s.state_file.parent.glob("*.tmp"))
    assert len(tmp_files) == 0  # 原子写入后不应残留 .tmp
