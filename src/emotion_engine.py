#!/usr/bin/env python3
"""emotion_engine.py — 核心引擎：pre_reply / post_reply 管线入口"""

import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .derived import DerivedEmotions
from .safety import SafetyGuard
from .gate import KeywordGate
from .appraiser import Appraiser
from .audit import AuditChain
from .prompt_injector import PromptInjector
from .persona_manager import PersonaManager


# 16 维定义（与 config.json 对齐）
DIMENSIONS = [
    "valence", "arousal", "dominance",
    "trust", "intimacy", "respect", "forgiveness",
    "curiosity", "confusion", "certainty", "anticipation",
    "nostalgia", "impatience", "relief", "disappointment", "hope",
]

DEFAULT_BASELINE = {
    "valence": 0.1, "arousal": 0.3, "dominance": 0.2,
    "trust": 0.0, "intimacy": 0.0, "respect": 0.0, "forgiveness": 0.0,
    "curiosity": 0.5, "confusion": 0.0, "certainty": 0.3, "anticipation": 0.2,
    "nostalgia": 0.0, "impatience": 0.0, "relief": 0.0, "disappointment": 0.0,
    "hope": 0.1,
}

CLAMP_RANGES = {
    "valence": [-0.8, 1.0],
    "arousal": [0.0, 1.0],
    "dominance": [-1.0, 1.0],
    "trust": [-1.0, 1.0],
    "intimacy": [0.0, 1.0],
    "respect": [0.0, 1.0],
    "forgiveness": [-0.7, 0.7],
    "curiosity": [0.0, 1.0],
    "confusion": [0.0, 1.0],
    "certainty": [0.0, 1.0],
    "anticipation": [-1.0, 1.0],
    "nostalgia": [0.0, 1.0],
    "impatience": [0.0, 1.0],
    "relief": [0.0, 1.0],
    "disappointment": [-0.8, 0.0],
    "hope": [0.1, 1.0],
}


class AffectiveCore:
    """
    Affective Core 核心引擎。
    提供 pre_reply（回复前）和 post_reply（回复后）两个阶段的调用入口。
    """

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        # 状态文件路径
        mem_cfg = self.cfg.get("memory", {})
        self.state_file = Path(mem_cfg.get("state_path", "emotion-state.json"))
        self.journal_path = Path(mem_cfg.get("journal_path", "emotion-journal.jsonl"))

        # 初始化子模块
        self.gate = KeywordGate(str(self.config_path))
        self.appraiser = Appraiser(str(self.config_path))
        self.audit = AuditChain(str(self.config_path))
        self.derived = DerivedEmotions(str(Path(self.config_path).parent / "rules" / "derived_emotions.yaml"))
        self.safety = SafetyGuard(str(self.config_path))
        self.prompt_injector = PromptInjector(str(self.config_path))
        self.persona = PersonaManager(
            templates_path=str(Path(self.config_path).parent / "persona_templates.json"),
            active_persona=self.cfg.get("persona", {}).get("active", "calm"),
        )

        # 状态
        self.vec: Dict[str, float] = {}
        self.baseline: Dict[str, float] = dict(DEFAULT_BASELINE)
        self.last_update: Optional[datetime] = None
        self.runtime_meta: Dict[str, Any] = {}
        self.last_expressions: List[str] = []
        self.last_gate_result: Optional[Dict[str, Any]] = None
        self._conversation_timestamps: List[float] = []

        # 加载或初始化
        self._load_or_init()

    # ------------------------------------------------------------------
    # 状态持久化
    # ------------------------------------------------------------------
    def _load_or_init(self) -> None:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                self.vec = {dim: float(payload["vec"].get(dim, self.baseline[dim])) for dim in DIMENSIONS}
                self.baseline = {dim: float(payload.get("baseline", {}).get(dim, DEFAULT_BASELINE[dim])) for dim in DIMENSIONS}
                self.last_update = datetime.fromisoformat(payload["last_update"]) if payload.get("last_update") else None
                self.runtime_meta = payload.get("runtime_meta", {})
                self.last_expressions = payload.get("last_expressions", [])
                return
            except Exception:
                pass
        self.reset()

    def _save(self) -> None:
        payload = {
            "vec": self.vec,
            "baseline": self.baseline,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "runtime_meta": self.runtime_meta,
            "last_expressions": self.last_expressions[-10:],
        }
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(self.state_file)

    def reset(self) -> None:
        self.vec = {dim: float(self.baseline.get(dim, DEFAULT_BASELINE[dim])) for dim in DIMENSIONS}
        self.last_update = datetime.now(timezone.utc)
        self.runtime_meta = {"version": "1.0", "resets": self.runtime_meta.get("resets", 0) + 1}
        self.last_expressions = []
        self.last_gate_result = None
        self._conversation_timestamps = []
        self._save()

    # ------------------------------------------------------------------
    # pre_reply: 回复前阶段
    # ------------------------------------------------------------------
    def pre_reply(self, user_message: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        在 Agent 生成回复前调用。
        1. decay_if_stale — 离线衰减补偿
        2. gate — 检测是否需要情绪影响
        3. 返回当前情绪状态（供 Agent 融入回复风格）
        """
        now = datetime.now(timezone.utc)

        # 1. 离线衰减补偿
        self._decay_if_stale(now)

        # 2. Gate 检测（保存结果供 post_reply 使用）
        gate_result = self.gate.should_trigger(user_message, history[-1]["content"] if history else "")
        self.last_gate_result = gate_result
        if gate_result["triggered"]:
            self.audit.log("gate", gate_result)

        # 3. 计算派生情绪（供 Agent 参考）
        derived = self._compute_derived()

        # 4. persona_filter 应用人格约束（替换硬编码，使用 PersonaManager）
        filtered_vec = self.persona.apply_constraints(dict(self.vec))

        # 5. 决定当前回复的建议语气
        tone = self._suggest_tone(filtered_vec, derived)

        # 6. Prompt 注入（情绪变化超阈值才写入 EMOTION_STATE.md）
        inject_result = self.prompt_injector.update(
            filtered_vec, derived_emotions=derived, tone=tone
        )

        return {
            "emotion_vec": filtered_vec,
            "derived_emotions": derived[:3],
            "suggested_tone": tone,
            "gate_triggered": gate_result["triggered"],
            "system_prompt_inject": inject_result,
        }

    # ------------------------------------------------------------------
    # post_reply: 回复后阶段
    # ------------------------------------------------------------------
    def post_reply(self, user_message: str, agent_reply: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        在 Agent 生成回复后调用。
        1. appraisal — LLM 第三方评估（gate 触发时）
        2. dynamics — 衰减/惯性/耦合/噪声/钳制
        3. safety — 异常检测 + 病理化过滤
        4. derived — 计算派生情绪
        5. expressor — 计划下一轮是否主动表达
        6. audit — 记录审计链
        7. journal — 写入 emotion-journal
        """
        now = datetime.now(timezone.utc)

        # 更新对话密度追踪
        self._update_conversation_density()

        # 1. LLM 第三方评估（仅在 gate 触发时调用，节省 token）
        if self.last_gate_result and self.last_gate_result.get("triggered"):
            appraisal_result = self.appraiser.appraise(history, dict(self.vec))
            delta = appraisal_result.get("delta", {k: 0.0 for k in DIMENSIONS})
            self.audit.log("appraisal", appraisal_result)
        else:
            delta = {k: 0.0 for k in DIMENSIONS}
            appraisal_result = {"delta": delta, "reasoning": "Gate not triggered, skipping appraisal", "level": 0}
            self.audit.log("appraisal", appraisal_result)

        # 2. 动力学更新
        new_vec = self._dynamics_update(delta)
        self.vec = new_vec
        self.audit.log("dynamics", {"delta": delta, "new_vec": new_vec})

        # 3. 安全检查（S2 修复）
        # 3.1 异常检测
        recent_history = self._get_recent_vec_history()
        if self.safety.check_anomaly(recent_history):
            self.vec["arousal"] = max(0.0, self.vec["arousal"] * 0.5)
            self.audit.log("safety", {"event": "anomaly_detected", "action": "arousal_halved"})

        # 3.2 病理化过滤（对 agent_reply）
        filtered_reply = self.safety.filter_pathology(agent_reply)
        if filtered_reply != agent_reply:
            self.audit.log("safety", {"event": "pathology_filtered", "original": agent_reply, "filtered": filtered_reply})

        # 3.3 表达前向量过滤
        safe_vec = self.safety.filter_vec_for_expression(dict(self.vec))

        # 3.4 人格约束应用（v1.1.0：替换硬编码 _persona_filter）
        safe_vec = self.persona.apply_constraints(safe_vec)

        # 4. 派生情绪（使用 derived.py 模块，M3 修复）
        derived = self.derived.compute(safe_vec)
        self.audit.log("derived", {"derived": derived[:5]})

        # 5. 主动表达计划（传入对话密度 + 人格参数，v1.1.0）
        density = self._get_conversation_density()
        express_plan = self._expressor_plan(derived, safe_vec, density)

        # 5.1 人格最终否决/改写权（v1.1.0）
        if express_plan["should_express"]:
            override = self.persona.should_express_override(
                express_plan["emotion_label"],
                express_plan.get("intensity", 0.0),
                self.last_expressions,
            )
            if override and override.get("rewrite_hint") == "suppress":
                express_plan = {"should_express": False, "emotion_label": None, "reason": override["reason"]}

        if express_plan["should_express"]:
            self.last_expressions.append(express_plan["emotion_label"])
            self.last_expressions = self.last_expressions[-10:]
        self.audit.log("expressor", express_plan)

        # 6. 保存状态
        self.last_update = now
        self._save()

        # 7. 写入 journal
        self._write_journal(user_message, delta)

        return {
            "emotion_vec": dict(self.vec),
            "expressed": express_plan["should_express"],
            "expression": express_plan.get("emotion_label"),
            "appraisal_level": appraisal_result.get("level", 0),
            "filtered_reply": filtered_reply if filtered_reply != agent_reply else None,
        }

    # ------------------------------------------------------------------
    # 动力学更新
    # ------------------------------------------------------------------
    def _dynamics_update(self, delta: Dict[str, float]) -> Dict[str, float]:
        """delta → 衰减 → 耦合(快照) → 惯性 → 噪声 → 钳制"""
        dyn_cfg = self.cfg.get("dynamics", {})
        decay_rate = dyn_cfg.get("decay_rate_per_run", 0.1)
        inertia = dyn_cfg.get("inertia_coeff", 0.3)
        noise_std = dyn_cfg.get("noise_std", 0.02)
        coupling_on = dyn_cfg.get("coupling_enabled", True)

        new_vec = {}

        # 1. 应用 delta
        for dim in DIMENSIONS:
            new_vec[dim] = self.vec.get(dim, 0.0) + delta.get(dim, 0.0)

        # 2. 衰减向 baseline
        for dim in DIMENSIONS:
            base = self.baseline.get(dim, DEFAULT_BASELINE[dim])
            new_vec[dim] = new_vec[dim] + (base - new_vec[dim]) * decay_rate

        # 3. 耦合（快照计算避免顺序副作用）
        if coupling_on:
            new_vec = self._apply_coupling(new_vec)

        # 4. 惯性平滑
        for dim in DIMENSIONS:
            old = self.vec.get(dim, 0.0)
            new_vec[dim] = new_vec[dim] * (1 - inertia) + old * inertia

        # 5. 噪声
        for dim in DIMENSIONS:
            new_vec[dim] += random.gauss(0, noise_std)

        # 6. 钳制
        for dim in DIMENSIONS:
            lo, hi = CLAMP_RANGES.get(dim, [-1.0, 1.0])
            new_vec[dim] = max(lo, min(hi, new_vec[dim]))

        return new_vec

    # 耦合矩阵（快照计算）
    COUPLING = {
        "trust": {"intimacy": 0.25, "respect": 0.0, "forgiveness": 0.0},
        "intimacy": {"respect": 0.15, "trust": 0.0},
        "disappointment": {"trust": -0.30, "hope": -0.15},
        "curiosity": {"anticipation": 0.20},
        "confusion": {"certainty": -0.25},
        "relief": {"valence": 0.35},
        "forgiveness": {"trust": 0.20},
    }

    def _apply_coupling(self, vec: Dict[str, float]) -> Dict[str, float]:
        snapshot = {k: v for k, v in vec.items()}
        deltas = {dim: 0.0 for dim in DIMENSIONS}
        for src, targets in self.COUPLING.items():
            if src not in snapshot:
                continue
            for tgt, coeff in targets.items():
                deltas[tgt] += snapshot[src] * coeff
        for dim in DIMENSIONS:
            vec[dim] += max(-0.1, min(0.1, deltas[dim]))
        return vec

    # ------------------------------------------------------------------
    # decay_if_stale
    # ------------------------------------------------------------------
    def _decay_if_stale(self, now: datetime) -> None:
        if self.last_update is None:
            return
        delta_minutes = (now - self.last_update).total_seconds() / 60
        threshold = self.cfg.get("dynamics", {}).get("stale_threshold_minutes", 30)
        if delta_minutes < threshold:
            return

        # 离线期间的批量衰减
        decay_rate = self.cfg.get("dynamics", {}).get("decay_rate_per_run", 0.1)
        for dim in DIMENSIONS:
            base = self.baseline.get(dim, DEFAULT_BASELINE[dim])
            self.vec[dim] = self.vec[dim] + (base - self.vec[dim]) * decay_rate * (delta_minutes / 5)
            lo, hi = CLAMP_RANGES.get(dim, [-1.0, 1.0])
            self.vec[dim] = max(lo, min(hi, self.vec[dim]))

        self.audit.log("dynamics", {"event": "decay_if_stale", "minutes": delta_minutes})

    # ------------------------------------------------------------------
    # 派生情绪（已迁移到 derived.py，emotion_engine 直接调用）
    # ------------------------------------------------------------------
    def _compute_derived(self) -> List[Dict[str, Any]]:
        """计算派生情绪强度，返回排序后的列表。"""
        return self.derived.compute(dict(self.vec))

    # ------------------------------------------------------------------
    # expressor 门控（传入对话密度，L1 修复）
    # ------------------------------------------------------------------
    def _expressor_plan(self, derived: List[Dict[str, Any]], vec: Dict[str, float],
                        density: str = "normal") -> Dict[str, Any]:
        # v1.1.0：优先使用人格模板的表达参数
        persona_params = self.persona.expression_params()
        exp_cfg = self.cfg.get("expression", {})
        intensity_threshold = persona_params.get("intensity_threshold", exp_cfg.get("intensity_threshold", 0.6))
        surface_cd = persona_params.get("surface_cooldown_seconds", exp_cfg.get("surface_cooldown_seconds", 60))
        deep_cd = persona_params.get("deep_cooldown_seconds", exp_cfg.get("deep_cooldown_seconds", 180))
        novelty_on = exp_cfg.get("novelty_check_enabled", True)

        # 获取上次表达时间
        last_ts = self.runtime_meta.get("last_expression_ts", 0)
        now_ts = datetime.now(timezone.utc).timestamp()

        # 深层/表层分类（简单规则）
        deep_labels = {"vulnerable", "grateful", "bittersweet", "guilty", "lonely", "overwhelmed"}

        for emo in derived:
            if emo["intensity"] < intensity_threshold:
                continue

            # 类型新颖性
            if novelty_on and emo["label"] in self.last_expressions[-3:]:
                continue

            # 冷却（根据对话密度自适应）
            is_deep = emo["label"] in deep_labels
            cooldown = deep_cd if is_deep else surface_cd

            # L1 修复：对话密度自适应
            if density == "fast":
                cooldown = int(cooldown * 0.6)  # 高密度对话，冷却缩短
            elif density == "slow":
                cooldown = int(cooldown * 1.5)  # 低密度对话，冷却延长

            if now_ts - last_ts < cooldown:
                continue

            # 通过
            self.runtime_meta["last_expression_ts"] = now_ts
            return {"should_express": True, "emotion_label": emo["label"], "intensity": emo["intensity"], "density": density}

        return {"should_express": False, "emotion_label": None}

    def _suggest_tone(self, vec: Dict[str, float], derived: List[Dict[str, Any]]) -> str:
        """根据情绪状态建议回复语气。"""
        valence = vec.get("valence", 0.0)
        arousal = vec.get("arousal", 0.0)

        if valence > 0.3 and arousal > 0.5:
            return "excited"
        if valence > 0.3 and arousal < 0.4:
            return "warm"
        if valence < -0.2 and arousal > 0.5:
            return "concerned"
        if valence < -0.2 and arousal < 0.4:
            return "calm_supportive"
        return "neutral"

    # ------------------------------------------------------------------
    # 对话密度追踪（L1 修复）
    # ------------------------------------------------------------------
    def _update_conversation_density(self) -> None:
        """维护 5 分钟窗口内的消息时间戳。"""
        now = time.time()
        window = 300  # 5 分钟
        self._conversation_timestamps.append(now)
        # 清理过期时间戳
        self._conversation_timestamps = [ts for ts in self._conversation_timestamps if now - ts < window]

    def _get_conversation_density(self) -> str:
        """返回对话密度: fast | normal | slow"""
        count = len(self._conversation_timestamps)
        if count >= 8:
            return "fast"
        elif count <= 2:
            return "slow"
        return "normal"

    def _get_recent_vec_history(self) -> List[Dict[str, float]]:
        """获取最近的情绪向量历史（用于异常检测）。"""
        # 从 journal 文件读取最近的记录
        history = []
        if not self.journal_path.exists():
            return history
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    vec = entry.get("vec", {})
                    if vec:
                        history.append(vec)
        except Exception:
            pass
        # 返回最近 5 条 + 当前
        return history[-5:] + [dict(self.vec)]
    def _write_journal(self, trigger: str, delta: Dict[str, float]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "vec": dict(self.vec),
            "delta": delta,
            "trigger": trigger[:100],
        }
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # explainability
    # ------------------------------------------------------------------
    def get_explainability(self, emotion_label: Optional[str] = None) -> Dict[str, Any]:
        return self.audit.get_explainability(emotion_label)

    def get_current_emotion(self) -> Dict[str, Any]:
        return {
            "vec": dict(self.vec),
            "baseline": dict(self.baseline),
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }
