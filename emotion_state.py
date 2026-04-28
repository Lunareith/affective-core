"""emotion_state.py - 16维情绪状态管理"""

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
    """16维情绪状态管理：读写、轮转备份、文件锁、损坏恢复"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 状态文件路径
        state_dir = self.config_path.parent / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = state_dir / "emotion_state.json"
        self.backup_dir = state_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # 基线（从 config 读取，默认值兜底）
        self.baseline = self.config.get("baseline", {})
        for dim in DEFAULT_DIMENSIONS:
            if dim not in self.baseline:
                self.baseline[dim] = 0.0

        # 状态（延迟加载，不立即创建文件）
        self._vec: dict[str, float] | None = None
        self._last_update: str | None = None

    # ---- 内部加载 ---------------------------------------------------------

    def _load(self) -> None:
        """从磁盘加载状态，损坏时从备份恢复，全部损坏时重置到基线。"""
        # 尝试主文件
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                self._vec = payload.get("vec", {})
                self._last_update = payload.get("last_update")
                for dim in DEFAULT_DIMENSIONS:
                    if dim not in self._vec:
                        self._vec[dim] = self.baseline.get(dim, 0.0)
                return
            except Exception:
                pass  # 主文件损坏，继续尝试备份

        # 尝试备份文件（.bak3 → .bak2 → .bak1）
        for i in range(3, 0, -1):
            bak = self.backup_dir / f"state.json.bak{i}"
            if bak.exists():
                try:
                    with open(bak, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    self._vec = payload.get("vec", {})
                    self._last_update = payload.get("last_update")
                    for dim in DEFAULT_DIMENSIONS:
                        if dim not in self._vec:
                            self._vec[dim] = self.baseline.get(dim, 0.0)
                    # 恢复成功，写回主文件
                    self._save()
                    return
                except Exception:
                    pass

        # 全部损坏，重置到基线
        self.reset()

    # ---- 公共接口 ----------------------------------------------------------

    def get_current(self) -> dict[str, Any]:
        """返回当前状态（延迟加载）"""
        if self._vec is None:
            self._load()
        return {
            "vec": dict(self._vec) if self._vec else dict(self.baseline),
            "baseline": dict(self.baseline),
            "last_update": self._last_update,
            "state_file": str(self.state_file),
            "backup_dir": str(self.backup_dir),
        }

    def update_vec(self, vec: dict[str, float]) -> None:
        """更新向量并保存，带钳制和备份。"""
        if self._vec is None:
            self._load()

        for dim in DEFAULT_DIMENSIONS:
            val = vec.get(dim, self._vec.get(dim, self.baseline.get(dim, 0.0)))
            # 钳制到 [-1, 1]
            self._vec[dim] = max(-1.0, min(1.0, float(val)))

        self._last_update = datetime.now(timezone.utc).isoformat()
        self._save()

    def reset(self) -> None:
        """重置到基线。"""
        self._vec = {dim: float(self.baseline.get(dim, 0.0)) for dim in DEFAULT_DIMENSIONS}
        self._last_update = datetime.now(timezone.utc).isoformat()
        self._save()

    # ---- 保存与备份 --------------------------------------------------------

    def _save(self) -> None:
        """原子写入 + 轮转备份。"""
        payload = {
            "vec": self._vec,
            "baseline": self.baseline,
            "last_update": self._last_update,
        }

        # 轮转备份：.bak2 → .bak3, .bak1 → .bak2, current → .bak1
        for i in range(3, 1, -1):
            src = self.backup_dir / f"state.json.bak{i-1}"
            dst = self.backup_dir / f"state.json.bak{i}"
            if src.exists():
                shutil.copy2(str(src), str(dst))

        if self.state_file.exists():
            shutil.copy2(str(self.state_file), str(self.backup_dir / "state.json.bak1"))

        # 原子写入
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(self.state_file)
