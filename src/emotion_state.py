"""
emotion_state.py - 16维情绪状态管理

职责：
- 16维向量读写（持久化到 JSON）
- 轮转备份 .bak1/.bak2/.bak3
- 文件锁（fcntl，Linux only）
- 启动恢复（损坏时从 backup 恢复）
- 基线管理

16 维定义（与 config.json 对齐）：
  joy, sadness, anger, fear, surprise, disgust, trust, anticipation,
  love, guilt, shame, pride, envy, relief, hope, boredom
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DIMENSIONS = [
    "valence", "arousal", "dominance",
    "trust", "intimacy", "respect", "forgiveness",
    "curiosity", "confusion", "certainty", "anticipation",
    "nostalgia", "impatience", "relief", "disappointment", "hope",
]


class EmotionState:
    """管理 16 维情绪状态的持久化、备份与恢复。"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.state_dir = self.config_path.parent / "emotion-state"
        self.state_file = self.state_dir / "current.json"
        self.backup_dir = self.state_dir / "backups"

        # 确保目录存在
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置中的维度定义和基线
        self.dimensions = DEFAULT_DIMENSIONS
        self.baseline: dict[str, float] = self._load_baseline_from_config()
        self.vec: dict[str, float] = {}
        self.last_update: str | None = None
        self.runtime_meta: dict[str, Any] = {}

        # 尝试加载已有状态，否则初始化到 baseline（不自动保存）
        loaded = self.load()
        if loaded is None:
            self.vec = {dim: float(self.baseline.get(dim, 0.0)) for dim in self.dimensions}
            self.last_update = None
            self.runtime_meta = {}

    # ------------------------------------------------------------------
    # 配置读取
    # ------------------------------------------------------------------
    def _load_baseline_from_config(self) -> dict[str, float]:
        """从 config.json 读取 baseline，失败则全部 0.0。"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            baseline = cfg.get("baseline", {})
            return {dim: float(baseline.get(dim, 0.0)) for dim in self.dimensions}
        except Exception:
            return {dim: 0.0 for dim in self.dimensions}

    # ------------------------------------------------------------------
    # 核心 API
    # ------------------------------------------------------------------
    def get_current(self) -> dict:
        """返回当前完整状态（含元数据）。"""
        return {
            "vec": dict(self.vec),
            "baseline": dict(self.baseline),
            "last_update": self.last_update,
            "runtime_meta": dict(self.runtime_meta),
        }

    def reset(self) -> None:
        """重置到基线并保存。"""
        self.vec = {dim: float(self.baseline.get(dim, 0.0)) for dim in self.dimensions}
        self.last_update = datetime.now(timezone.utc).isoformat()
        self.runtime_meta = {"version": "1.0", "resets": self.runtime_meta.get("resets", 0) + 1}
        self.save()

    def update_vec(self, new_vec: dict[str, float]) -> None:
        """由外部模块（如 dynamics）调用，写入新向量并保存。"""
        for dim in self.dimensions:
            val = float(new_vec.get(dim, self.baseline.get(dim, 0.0)))
            # 钳制到 [-1.0, 1.0]
            self.vec[dim] = max(-1.0, min(1.0, val))
        self.last_update = datetime.now(timezone.utc).isoformat()
        self.save()

    # ------------------------------------------------------------------
    # 持久化：原子写入 + 轮转备份 + 文件锁
    # ------------------------------------------------------------------
    def save(self) -> None:
        """原子写入 current.json，并轮转备份。"""
        payload = {
            "vec": self.vec,
            "baseline": self.baseline,
            "last_update": self.last_update,
            "runtime_meta": self.runtime_meta,
        }
        tmp_file = self.state_file.with_suffix(".tmp")

        with open(tmp_file, "w", encoding="utf-8") as f:
            # 文件锁：排他锁，防止并发写入
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # 原子替换
        os.replace(tmp_file, self.state_file)

        # 轮转备份
        self._rotate_backups()

    def load(self) -> dict | None:
        """从 current.json 加载；损坏则从 backup 恢复。"""
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    payload = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (json.JSONDecodeError, OSError):
            # 损坏，尝试从备份恢复
            payload = self._restore_from_backup()
            if payload is None:
                return None

        # 校验维度完整性
        if not self._validate_payload(payload):
            payload = self._restore_from_backup()
            if payload is None:
                return None

        self.vec = {dim: float(payload["vec"].get(dim, 0.0)) for dim in self.dimensions}
        self.baseline = {dim: float(payload.get("baseline", {}).get(dim, 0.0)) for dim in self.dimensions}
        self.last_update = payload.get("last_update")
        self.runtime_meta = payload.get("runtime_meta", {})
        return self.get_current()

    # ------------------------------------------------------------------
    # 备份与恢复
    # ------------------------------------------------------------------
    def _rotate_backups(self) -> None:
        """.bak2 -> .bak3, .bak1 -> .bak2, current -> .bak1"""
        bak1 = self.backup_dir / "state.json.bak1"
        bak2 = self.backup_dir / "state.json.bak2"
        bak3 = self.backup_dir / "state.json.bak3"

        if bak2.exists():
            shutil.move(str(bak2), str(bak3))
        if bak1.exists():
            shutil.move(str(bak1), str(bak2))
        if self.state_file.exists():
            shutil.copy2(str(self.state_file), str(bak1))

    def _restore_from_backup(self) -> dict | None:
        """按 .bak1 -> .bak2 -> .bak3 顺序尝试恢复。"""
        for bak_name in ("state.json.bak1", "state.json.bak2", "state.json.bak3"):
            bak_path = self.backup_dir / bak_name
            if not bak_path.exists():
                continue
            try:
                with open(bak_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if self._validate_payload(payload):
                    # 恢复成功，把备份写回 current
                    shutil.copy2(str(bak_path), str(self.state_file))
                    return payload
            except (json.JSONDecodeError, OSError):
                continue
        return None

    def _validate_payload(self, payload: dict) -> bool:
        """校验 payload 是否包含完整的 16 维向量。"""
        if not isinstance(payload, dict):
            return False
        vec = payload.get("vec")
        if not isinstance(vec, dict):
            return False
        return all(dim in vec for dim in self.dimensions)
