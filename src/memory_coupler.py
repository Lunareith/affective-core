#!/usr/bin/env python3
"""memory_coupler.py — 记忆耦合：emotion-journal 读写 + 情绪回灌计算"""

import json
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any


class MemoryCoupler:
    """
    管理 emotion-journal 的读写，并根据历史情绪向量计算回灌强度。
    """

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        mem_cfg = cfg.get("memory", {})
        self.journal_path = Path(mem_cfg.get("journal_path", "emotion-journal.jsonl"))
        self.recharge_decay_hours = mem_cfg.get("recharge_time_decay_hours", 48)
        self.lookback_days = mem_cfg.get("recharge_lookback_days", 7)

    def read_journal(self, since: Optional[datetime] = None,
                     topic_fp: Optional[List[str]] = None,
                     limit: int = 100) -> List[Dict[str, Any]]:
        """
        读取 emotion-journal，支持按时间和 topic 过滤。
        """
        if not self.journal_path.exists():
            return []

        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

        results = []
        with open(self.journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry_ts = datetime.fromisoformat(entry.get("ts", ""))
                    if entry_ts >= since:
                        if topic_fp is None or self._topic_match(entry.get("topic_fp", []), topic_fp):
                            results.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue

        return results[-limit:]

    def write_journal(self, vec: Dict[str, float], trigger: str,
                      topic_fp: Optional[List[str]] = None,
                      session_id: str = "default") -> None:
        """写入一条情绪记录到 journal。"""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "vec": dict(vec),
            "trigger": trigger[:200],
            "topic_fp": topic_fp or [],
            "session_id": session_id,
        }
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def compute_recharge(self, current_vec: Dict[str, float],
                         topic_keywords: List[str]) -> Dict[str, float]:
        """
        计算记忆回灌：检索相关历史情绪，按时间衰减后计算回灌强度。
        返回各维度的回灌 delta。
        """
        since = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        records = self.read_journal(since=since, topic_fp=topic_keywords)

        if not records:
            return {dim: 0.0 for dim in current_vec}

        recharge = {dim: 0.0 for dim in current_vec}
        now = datetime.now(timezone.utc)

        for record in records:
            record_ts = datetime.fromisoformat(record.get("ts", ""))
            age_hours = (now - record_ts).total_seconds() / 3600
            decay = 0.5 ** (age_hours / self.recharge_decay_hours)  # 半衰期 decay

            record_vec = record.get("vec", {})
            similarity = self._cosine_similarity(current_vec, record_vec)

            for dim in current_vec:
                val = record_vec.get(dim, 0.0)
                recharge[dim] += val * decay * similarity * 0.1  # 0.1 是耦合强度

        # 钳制回灌量，避免过大影响
        for dim in recharge:
            recharge[dim] = max(-0.1, min(0.1, recharge[dim]))

        return recharge

    # ---- helpers ----------------------------------------------------------------

    @staticmethod
    def _topic_match(entry_fp: List[str], query_fp: List[str]) -> bool:
        if not entry_fp or not query_fp:
            return True  # 没有 topic 时不过滤
        entry_set = set(entry_fp)
        query_set = set(query_fp)
        return len(entry_set & query_set) > 0

    @staticmethod
    def _cosine_similarity(v1: Dict[str, float], v2: Dict[str, float]) -> float:
        dims = set(v1.keys()) & set(v2.keys())
        if not dims:
            return 0.0
        dot = sum(v1[d] * v2[d] for d in dims)
        n1 = math.sqrt(sum(v1[d] ** 2 for d in dims))
        n2 = math.sqrt(sum(v2[d] ** 2 for d in dims))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)

    @staticmethod
    def topic_fingerprint(text: str, hashlen: int = 8) -> List[str]:
        """从文本中提取 topic fingerprint（关键词列表）。"""
        import re
        # 简单实现：提取中文词和英文词
        words = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text.lower())
        # 去重并限制数量
        seen = set()
        result = []
        for w in words:
            if w not in seen and len(result) < hashlen:
                seen.add(w)
                result.append(w)
        return result
