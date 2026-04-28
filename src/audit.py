#!/usr/bin/env python3
"""audit.py — 可解释性审计链：生成、存储、查询"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional


class AuditChain:
    """
    记录每一轮情绪变化的完整审计链，支持按日期分文件存储和按情绪标签查询。
    """

    def __init__(self, config_path: str = "skills/affective-core/config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.audit_dir = cfg.get("memory", {}).get("audit_dir", "emotion-audit")
        os.makedirs(self.audit_dir, exist_ok=True)

        # 内存中保留最近 100 条，用于快速查询
        self._recent: List[dict] = []
        self._max_recent = 100

    def _today_file(self) -> str:
        date_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
        return os.path.join(self.audit_dir, f"{date_str}.jsonl")

    def log(self, event_type: str, data: dict) -> None:
        """
        写入一条审计记录。
        event_type: gate | appraisal | dynamics | derived | expressor | safety | coupling
        data: 任意结构化字典
        """
        entry = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(),
            "event_type": event_type,
            "data": data
        }
        # 追加到日文件
        filepath = self._today_file()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # 维护内存 recent
        self._recent.append(entry)
        if len(self._recent) > self._max_recent:
            self._recent.pop(0)

    def get_explainability(self, emotion_label: Optional[str] = None) -> dict:
        """
        返回最近一轮的完整审计链，或按 emotion_label 过滤。
        如果没有 emotion_label，返回最近一轮的所有审计记录。
        """
        # 从文件中读取今天的记录
        filepath = self._today_file()
        if not os.path.exists(filepath):
            return {"round": None, "chain": []}

        all_entries = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    all_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not all_entries:
            return {"round": None, "chain": []}

        # 按时间分轮：简单的做法是把连续的记录分成"轮"
        # 这里简化处理：返回最近 N 条，或按 emotion_label 过滤
        if emotion_label:
            filtered = [
                e for e in all_entries
                if emotion_label.lower() in json.dumps(e.get("data", {}), ensure_ascii=False).lower()
            ]
            return {
                "round": None,
                "emotion_label": emotion_label,
                "chain": filtered[-20:]
            }

        # 返回最近一轮（最近 20 条）
        return {
            "round": "latest",
            "chain": all_entries[-20:]
        }

    def get_chain_for_timestamp(self, ts_iso: str) -> List[dict]:
        """获取某个时间戳附近的审计链"""
        filepath = self._today_file()
        if not os.path.exists(filepath):
            return []
        results = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # 允许 60 秒内的模糊匹配
                    entry_ts = entry.get("ts", "")
                    if entry_ts and abs(self._parse_ts(entry_ts) - self._parse_ts(ts_iso)) <= 60:
                        results.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue
        return results

    @staticmethod
    def _parse_ts(ts_iso: str) -> float:
        """解析 ISO 格式时间戳为 Unix 时间"""
        # 处理带时区的格式，如 2026-04-28T16:30:00+08:00
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
