#!/usr/bin/env python3
"""gate.py — 轻量 Gate：Jaccard + 关键词检测，可选 embedding 增强"""

import json
import re
from typing import Dict, List, Set, Tuple


class KeywordGate:
    """
    判断本轮用户消息是否需要触发 deep appraisal。
    默认 rule 模式：Jaccard 相似度 + 情绪关键词正则。
    可选 embedding 模式：外部 API 余弦相似度（fallback 到 rule）。
    """

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        gate_cfg = cfg.get("gate", {})
        self.mode = gate_cfg.get("mode", "rule")
        self.rule_threshold = gate_cfg.get("keyword_gate", {}).get("similarity_threshold", 0.7)
        self.embedding_api_url = gate_cfg.get("embedding_gate", {}).get("api_url", "")
        self.embedding_api_key = gate_cfg.get("embedding_gate", {}).get("api_key", "")
        self.embedding_threshold = gate_cfg.get("embedding_gate", {}).get("similarity_threshold", 0.7)

        # Read keywords from config if available
        kw_cfg = gate_cfg.get("keyword_gate", {})
        self.emotion_keywords = kw_cfg.get("emotion_keywords", {})
        self._keyword_pattern = self._build_keyword_pattern(self.emotion_keywords)

    @staticmethod
    def _build_keyword_pattern(keywords: Dict[str, List[str]]) -> re.Pattern:
        flat = set()
        for words in keywords.values():
            flat.update(words)
        if not flat:
            return re.compile("^$")  # Never match
        sorted_words = sorted(flat, key=len, reverse=True)
        escaped = [re.escape(w) for w in sorted_words]
        return re.compile("|".join(escaped))

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        if not text:
            return set()
        chars = []
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff" or ch.isalnum():
                chars.append(ch.lower())
            else:
                chars.append(" ")
        raw = "".join(chars)
        tokens = set(raw.split())
        bigrams = set()
        for i in range(len(raw) - 1):
            a, b = raw[i], raw[i + 1]
            if "\u4e00" <= a <= "\u9fff" and "\u4e00" <= b <= "\u9fff":
                bigrams.add(a + b)
        tokens.update(bigrams)
        return tokens

    @staticmethod
    def _jaccard(a: Set[str], b: Set[str]) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _check_keywords(self, text: str) -> Tuple[bool, List[str], bool]:
        """Returns: (keyword_hit, keywords_found, is_task_mode)"""
        found = set()
        for m in self._keyword_pattern.finditer(text):
            found.add(m.group())

        # Check task_mode keywords separately
        task_keywords = self.emotion_keywords.get("task_mode", [])
        is_task = any(kw in text for kw in task_keywords)

        return (len(found) > 0, sorted(found), is_task)

    def _embedding_similarity(self, text_a: str, text_b: str) -> float:
        if not self.embedding_api_url:
            return None
        try:
            import urllib.request
            payload = json.dumps({
                "model": "text-embedding-3-small",
                "input": [text_a, text_b]
            }).encode("utf-8")
            req = urllib.request.Request(
                self.embedding_api_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.embedding_api_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                emb = data["data"]
                if len(emb) < 2:
                    return None
                v1 = emb[0]["embedding"]
                v2 = emb[1]["embedding"]
                return self._cosine(v1, v2)
        except Exception:
            return None

    @staticmethod
    def _cosine(v1: List[float], v2: List[float]) -> float:
        import math
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(a * a for a in v2))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)

    def should_trigger(self, user_message: str, last_message: str = "") -> dict:
        user_message = user_message or ""
        last_message = last_message or ""

        if self.mode == "embedding":
            sim = self._embedding_similarity(user_message, last_message)
            if sim is not None:
                triggered = sim < self.embedding_threshold
                return {
                    "triggered": triggered,
                    "reason": f"embedding similarity={sim:.3f} {'<' if triggered else '>='} threshold={self.embedding_threshold}",
                    "similarity_score": sim,
                    "mode": "embedding",
                    "task_mode": False,
                }

        tokens_user = self._tokenize(user_message)
        tokens_last = self._tokenize(last_message)
        jaccard_sim = self._jaccard(tokens_user, tokens_last)
        keyword_hit, keywords, is_task = self._check_keywords(user_message)
        triggered = keyword_hit  # Only keyword triggers, not Jaccard for neutral text

        if keyword_hit:
            return {
                "triggered": True,
                "reason": "keyword_match",
                "similarity_score": jaccard_sim,
                "keyword_hit": True,
                "keywords": keywords,
                "mode": "rule",
                "task_mode": is_task,
            }

        return {
            "triggered": False,
            "reason": f"Jaccard={jaccard_sim:.3f}, no keyword hit",
            "similarity_score": jaccard_sim,
            "keyword_hit": False,
            "keywords": [],
            "mode": "rule",
            "task_mode": is_task,
        }
