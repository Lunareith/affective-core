#!/usr/bin/env python3
"""prompt_injector.py — Prompt注入层：情绪状态 → EMOTION_STATE.md / system prompt"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


class PromptInjector:
    """
    双模式情绪状态注入器：
    - 默认模式：将情绪摘要写入 workspace/EMOTION_STATE.md
    - direct_inject 模式：返回可直接拼接进 system prompt 的文本

    触发条件：任一维度变化量 ≥ threshold（默认 0.1）才重写，避免频繁 IO。
    """

    # 16 维的友好中文名称
    DIM_LABELS: Dict[str, str] = {
        "valence": "愉悦度", "arousal": "激活度", "dominance": "支配感",
        "trust": "信任", "intimacy": "亲密感", "respect": "尊重",
        "forgiveness": "宽恕/怨恨", "curiosity": "好奇心", "confusion": "困惑",
        "certainty": "确定性", "anticipation": "预期", "nostalgia": "怀旧",
        "impatience": "不耐烦", "relief": "释然", "disappointment": "失望",
        "hope": "希望",
    }

    # 阈值维度（变化超过这些值才写入）
    WATCHED_DIMS = [
        "valence", "arousal", "trust", "intimacy", "curiosity",
        "confusion", "certainty", "impatience", "hope",
    ]

    def __init__(
        self,
        config_path: str = "config.json",
        workspace_dir: Optional[str] = None,
        threshold: Optional[float] = None,
        direct_inject: Optional[bool] = None,
        auto_inject_md: Optional[bool] = None,
    ):
        """
        Args:
            config_path: 配置文件路径（用于读取 expression 节）
            workspace_dir: EMOTION_STATE.md 写入目录，默认当前工作目录
            threshold: 重写阈值（任一维度变化量绝对值 ≥ 此值才写）
            direct_inject: 是否启用 direct_inject 模式（返回 system prompt 文本）
            auto_inject_md: 是否自动写入 EMOTION_STATE.md
        """
        self.threshold = 0.1 if threshold is None else threshold
        self.direct_inject = False if direct_inject is None else direct_inject
        self.auto_inject_md = True if auto_inject_md is None else auto_inject_md
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path.cwd()
        self.md_path = self.workspace_dir / "EMOTION_STATE.md"

        # 尝试从 config.json 读取覆盖值（向后兼容：字段不存在用默认值；构造函数显式传入优先）
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            exp = cfg.get("expression", {})
            if threshold is None:
                self.threshold = exp.get("inject_threshold", self.threshold)
            if direct_inject is None:
                self.direct_inject = exp.get("direct_inject", self.direct_inject)
            if auto_inject_md is None:
                self.auto_inject_md = exp.get("auto_inject_md", self.auto_inject_md)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # 记录上次写入的向量，用于比较变化量
        self._last_written_vec: Optional[Dict[str, float]] = None
        self._last_written_time: Optional[str] = None

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def update(
        self,
        vec: Dict[str, float],
        derived_emotions: Optional[List[Dict[str, float]]] = None,
        tone: Optional[str] = None,
    ) -> Optional[str]:
        """
        根据当前情绪状态决定是否重写注入内容。

        返回:
            - direct_inject=True 时：返回 system prompt 段落文本
            - direct_inject=False 时：返回 None（副作用写入 EMOTION_STATE.md）
        """
        # 1. 判断变化量是否超过阈值
        if not self._should_rewrite(vec):
            return None

        # 2. 生成摘要文本
        summary = self._build_summary(vec, derived_emotions or [], tone)

        # 3. 更新 last_written（必须在 return 前执行，否则 threshold 检查失效）
        self._last_written_vec = dict(vec)
        self._last_written_time = datetime.now(timezone.utc).isoformat()

        # 4. 执行注入
        if self.direct_inject:
            return summary

        if self.auto_inject_md:
            self._write_md(summary)

        return None

    def get_md_content(self, vec: Dict[str, float],
                       derived_emotions: Optional[List[Dict[str, float]]] = None,
                       tone: Optional[str] = None) -> str:
        """仅生成摘要文本，不执行任何写入或状态更新。"""
        return self._build_summary(vec, derived_emotions or [], tone)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _should_rewrite(self, vec: Dict[str, float]) -> bool:
        """任一 watched 维度变化 ≥ threshold 则返回 True（含 1e-9 浮点容差）。"""
        if self._last_written_vec is None:
            return True
        for dim in self.WATCHED_DIMS:
            old = self._last_written_vec.get(dim, 0.0)
            new = vec.get(dim, 0.0)
            if abs(new - old) + 1e-9 >= self.threshold:
                return True
        return False

    def _build_summary(
        self,
        vec: Dict[str, float],
        derived_emotions: List[Dict[str, float]],
        tone: Optional[str],
    ) -> str:
        """构建 3-5 句话的自然语言摘要 + 关键数值。"""
        lines: List[str] = []

        # 第一句：总体情绪基调
        valence = vec.get("valence", 0.0)
        arousal = vec.get("arousal", 0.0)
        mood = self._describe_mood(valence, arousal)
        lines.append(f"当前整体情绪基调：{mood}（愉悦度 {valence:+.2f}，激活度 {arousal:+.2f}）。")

        # 第二句：关键维度（变化最大的 watched 维度）
        top_dim, top_val = self._top_watched_dim(vec)
        if top_dim:
            label = self.DIM_LABELS.get(top_dim, top_dim)
            direction = "偏高" if top_val > 0.3 else "偏低" if top_val < -0.3 else "适中"
            lines.append(f"{label} {direction}（{top_val:+.2f}），是当前最显著的情绪信号。")

        # 第三句：派生情绪（如果有强度 > 0.5 的）
        if derived_emotions:
            top_derived = derived_emotions[0]
            if top_derived.get("intensity", 0.0) > 0.5:
                lines.append(
                    f"派生情绪表现为「{top_derived['label']}」"
                    f"（强度 {top_derived['intensity']:.2f}）。"
                )

        # 第四句：社交层简述
        trust = vec.get("trust", 0.0)
        intimacy = vec.get("intimacy", 0.0)
        if trust > 0.3 or intimacy > 0.3:
            lines.append(
                f"社交维度积极：信任 {trust:+.2f}，亲密感 {intimacy:+.2f}。"
            )
        elif trust < -0.3 or intimacy < 0.1:
            lines.append(
                f"社交维度偏冷：信任 {trust:+.2f}，亲密感 {intimacy:+.2f}。"
            )

        # 第五句：建议语气（如果有）
        if tone:
            lines.append(f"建议本轮回复语气：{tone}。")

        # 确保 3-5 句：如果太少，补一句认知维度
        if len(lines) < 3:
            curiosity = vec.get("curiosity", 0.0)
            certainty = vec.get("certainty", 0.0)
            lines.append(
                f"认知状态：好奇心 {curiosity:+.2f}，确定性 {certainty:+.2f}。"
            )

        return " ".join(lines[:5])

    def _describe_mood(self, valence: float, arousal: float) -> str:
        """基于 Russell 环形模型描述情绪基调。"""
        if valence > 0.3:
            if arousal > 0.3:
                return "兴奋/积极"
            return "平静/满足"
        if valence < -0.3:
            if arousal > 0.3:
                return "焦虑/不安"
            return "低落/消沉"
        if arousal > 0.3:
            return "警觉/紧张"
        return "中性/平稳"

    def _top_watched_dim(self, vec: Dict[str, float]) -> tuple:
        """返回变化最大的 watched 维度（基于绝对值）。"""
        best_dim = ""
        best_val = 0.0
        for dim in self.WATCHED_DIMS:
            val = abs(vec.get(dim, 0.0))
            if val > best_val:
                best_val = val
                best_dim = dim
        return best_dim, vec.get(best_dim, 0.0) if best_dim else 0.0

    def _write_md(self, content: str) -> None:
        """原子写入 EMOTION_STATE.md。"""
        self.md_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.md_path.with_suffix(".tmp")
        header = f"<!-- 自动生成：Affective Core 情绪状态快照 | {datetime.now(timezone.utc).isoformat()} -->\n\n"
        tmp.write_text(header + content, encoding="utf-8")
        tmp.replace(self.md_path)
