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

    # 16 维情绪关键词池（按维度归类，用于 rule 模式的情绪关键词检测）
    DEFAULT_KEYWORDS: Dict[str, List[str]] = {
        "valence": ["开心", "高兴", "难过", "悲伤", "愤怒", "喜欢", "讨厌", "幸福", "痛苦", "失望"],
        "arousal": ["兴奋", "紧张", "激动", "平静", "焦虑", "慌张", "爆发", "冷静", "麻木", "心跳"],
        "dominance": ["控制", "无力", "掌控", "主导", "被动", "服从", "反抗", "压迫", "自由", "束缚"],
        "trust": ["信任", "怀疑", "相信", "背叛", "可靠", "骗子", "诚实", "欺骗", "放心", "戒备"],
        "intimacy": ["亲密", "疏远", "熟悉", "陌生", "靠近", "距离", "贴心", "冷淡", "温暖", "隔阂"],
        "respect": ["尊重", "轻视", "敬佩", "鄙视", "崇拜", "侮辱", "礼貌", "傲慢", "谦逊", "羞辱"],
        "forgiveness": ["怨恨", "原谅", "记仇", "释怀", "报仇", "嫉妒", "仇视", "不满", "宽恕", "和解"],
        "curiosity": ["好奇", "无聊", "想知道", "探索", "疑问", "困惑", "求知欲", "漠不关心", "追问", "调查"],
        "confusion": ["困惑", "迷茫", "混乱", "清楚", "明白", "糊涂", "清晰", "纠结", "矛盾", "模糊"],
        "certainty": ["确定", "不确定", "肯定", "怀疑", "坚信", "动摇", "确信", "犹疑", "明确", "含糊"],
        "anticipation": ["期待", "等待", "盼望", "预感", "展望", "忐忑", "憧憬", "焦急"],
        "nostalgia": ["怀旧", "回忆", "过去", "童年", "从前", "老时光", "记忆", "想念", "旧物", "故乡"],
        "impatience": ["不耐烦", "急躁", "等不及", "催促", "磨蹭", "拖延", "焦急", "从容", "紧迫", "缓慢"],
        "relief": ["释然", "松了口气", "解脱", "放下", "轻松", "如释重负", "宽慰", "安心", "了结", "舒畅"],
        "disappointment": ["失望", "绝望", "希望", "落空", "期望", "破灭", "遗憾", "惋惜", "灰心", "沮丧"],
        "hope": ["希望", "绝望", "乐观", "悲观", "曙光", "前景", "信念", "灰心", "向往", "憧憬"],
    }

    # 任务模式关键词
    TASK_KEYWORDS = ["执行", "运行", "帮我", "查一下", "计算", "生成", "调用"]

    def __init__(self, config_path: str = "skills/affective-core/config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.mode = cfg.get("gate", {}).get("mode", "rule")
        self.rule_threshold = cfg.get("gate", {}).get("rule_threshold", 0.6)
        self.embedding_api_url = cfg.get("gate", {}).get("embedding_api_url", "")
        self.embedding_api_key = cfg.get("gate", {}).get("embedding_api_key", "")
        self.embedding_threshold = cfg.get("gate", {}).get("embedding_threshold", 0.7)

        # 构建扁平关键词集合，用于快速正则检测
        self._keyword_pattern = self._build_keyword_pattern(self.DEFAULT_KEYWORDS)
        self._task_pattern = re.compile("|".join(re.escape(w) for w in self.TASK_KEYWORDS))

    @staticmethod
    def _build_keyword_pattern(keywords: Dict[str, List[str]]) -> re.Pattern:
        flat = set()
        for words in keywords.values():
            flat.update(words)
        # 按长度降序排列，避免短词遮蔽长词
        sorted_words = sorted(flat, key=len, reverse=True)
        escaped = [re.escape(w) for w in sorted_words]
        return re.compile("|".join(escaped))

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        """极简中文分词：按非字母数字中文切割 + 2-gram"""
        import unicodedata
        if not text:
            return set()
        # 保留中文字符、字母、数字
        chars = []
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff" or ch.isalnum():
                chars.append(ch.lower())
            else:
                chars.append(" ")
        raw = "".join(chars)
        tokens = set(raw.split())
        # 中文 2-gram
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
        inter = len(a & b)
        union = len(a | b)
        return inter / union if union else 0.0

    def _check_keywords(self, text: str) -> Tuple[bool, List[str]]:
        """检测文本中是否包含情绪关键词，返回 (是否命中, 命中的关键词列表)"""
        found = set()
        for m in self._keyword_pattern.finditer(text):
            found.add(m.group())
        return (len(found) > 0, sorted(found))

    def _embedding_similarity(self, text_a: str, text_b: str) -> float:
        """
        调用外部 embedding API 计算余弦相似度。
        若不可用则返回 None，由上层 fallback 到 rule 模式。
        """
        if not self.embedding_api_url:
            return None
        try:
            import urllib.request
            import urllib.error
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
        """
        判断是否需要触发 deep appraisal。
        返回统一格式：{"triggered": bool, "reason": str, "similarity_score": float}
        """
        user_message = user_message or ""
        last_message = last_message or ""

        # 任务模式检测
        task_mode = bool(self._task_pattern.search(user_message))

        # 模式 A：embedding
        if self.mode == "embedding":
            sim = self._embedding_similarity(user_message, last_message)
            if sim is not None:
                triggered = sim < self.embedding_threshold
                return {
                    "triggered": triggered,
                    "reason": f"embedding similarity={sim:.3f} < threshold={self.embedding_threshold}" if triggered else f"embedding similarity={sim:.3f} >= threshold={self.embedding_threshold}",
                    "similarity_score": sim,
                    "mode": "embedding"
                }
            # embedding 失败 → 静默 fallback 到 rule

        # 模式 B：rule（默认或 fallback）
        tokens_user = self._tokenize(user_message)
        tokens_last = self._tokenize(last_message)
        jaccard_sim = self._jaccard(tokens_user, tokens_last)

        keyword_hit, keywords = self._check_keywords(user_message)

        # 触发条件：Jaccard 低于阈值，或检测到情绪关键词
        triggered = (jaccard_sim < self.rule_threshold) or keyword_hit

        reasons = []
        if jaccard_sim < self.rule_threshold:
            reasons.append(f"Jaccard={jaccard_sim:.3f} < threshold={self.rule_threshold}")
        if keyword_hit:
            reasons.append(f"keywords hit: {', '.join(keywords)}")

        return {
            "triggered": triggered,
            "reason": "; ".join(reasons) if reasons else (f"Jaccard={jaccard_sim:.3f}, no keyword hit"),
            "similarity_score": jaccard_sim,
            "keyword_hit": keyword_hit,
            "keywords": keywords,
            "mode": "rule",
            "task_mode": task_mode,
        }
