#!/usr/bin/env python3
"""appraiser.py — LLM 第三方评估器：prompt + jsonschema 校验 + 缓存 + 四级降级"""

import hashlib
import json
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any


class Appraiser:
    """
    调用轻量 LLM 对对话进行第三方情绪评估。
    输出 16 维 delta + reasoning，带 jsonschema 校验与结果缓存。
    四级降级：L1(主模型) → L2(fallback) → L3(应急简化) → L4(跳过)
    """

    # 16 维情绪维度（有序，用于 prompt 和 schema）
    DIMENSIONS = [
        "valence", "arousal", "dominance",
        "trust", "intimacy", "respect", "forgiveness",
        "curiosity", "confusion", "certainty", "anticipation",
        "nostalgia", "impatience", "relief", "disappointment", "hope"
    ]

    # 输出 JSON schema（用于校验 LLM 返回）
    OUTPUT_SCHEMA = {
        "type": "object",
        "required": ["delta", "reasoning"],
        "properties": {
            "delta": {
                "type": "object",
                "properties": {
                    k: {"type": "number", "minimum": -1.0, "maximum": 1.0}
                    for k in DIMENSIONS
                },
                "additionalProperties": False
            },
            "reasoning": {"type": "string", "minLength": 1}
        },
        "additionalProperties": False
    }

    # 简化 schema（L3 降级，仅 valence + arousal）
    EMERGENCY_SCHEMA = {
        "type": "object",
        "required": ["delta", "reasoning"],
        "properties": {
            "delta": {
                "type": "object",
                "properties": {
                    "valence": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                    "arousal": {"type": "number", "minimum": -1.0, "maximum": 1.0}
                },
                "required": ["valence", "arousal"],
                "additionalProperties": False
            },
            "reasoning": {"type": "string", "minLength": 1}
        },
        "additionalProperties": False
    }

    def __init__(self, config_path: str = "skills/affective-core/config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)
        llm_cfg = self.cfg.get("llm", {})
        self.api_base = llm_cfg.get("api_base", "")
        self.api_key = llm_cfg.get("api_key", "")
        self.appraiser_model = llm_cfg.get("appraiser_model", "kimi-k2p5")
        self.fallback_model = llm_cfg.get("fallback_model", "")
        self.emergency_model = llm_cfg.get("emergency_model", "")
        self.timeout = llm_cfg.get("timeout_seconds", 10)
        self.fallback_timeout = llm_cfg.get("fallback_timeout_seconds", 5)
        self.cache_ttl = llm_cfg.get("cache_ttl_seconds", 120)

        # 内存缓存：{hash: {"ts": float, "result": dict}}
        self._cache: Dict[str, Dict[str, Any]] = {}

        # 启动校验
        if not self.api_base:
            print("[AffectiveCore] WARNING: llm.api_base not set. Appraiser will run in L4 (skip) mode.")
        if not self.fallback_model:
            print("[AffectiveCore] WARNING: fallback_model not set. L2 downgrade disabled.")
        if not self.emergency_model:
            print("[AffectiveCore] WARNING: emergency_model not set. L3 downgrade disabled.")

    def _cache_key(self, history: List[dict], state: dict) -> str:
        """基于输入生成缓存 key"""
        dump = json.dumps([history, state], sort_keys=True, ensure_ascii=False)
        return hashlib.md5(dump.encode("utf-8")).hexdigest()

    def _get_cached(self, key: str) -> Optional[dict]:
        """读取缓存，过期返回 None"""
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > self.cache_ttl:
            del self._cache[key]
            return None
        return entry["result"]

    def _set_cached(self, key: str, result: dict) -> None:
        self._cache[key] = {"ts": time.time(), "result": result}

    @staticmethod
    def _build_system_prompt(full: bool = True) -> str:
        dims = Appraiser.DIMENSIONS if full else ["valence", "arousal"]
        dim_desc = {
            "valence": "愉悦度 (-1=极度负面, +1=极度正面)",
            "arousal": "激活度 (-1=极度平静/麻木, +1=极度兴奋/紧张)",
            "dominance": "支配感 (-1=无力/被控制, +1=掌控/主导)",
            "trust": "信任 (-1=极度不信任, +1=极度信任)",
            "intimacy": "亲密感 (-1=极度疏远, +1=极度亲密)",
            "respect": "尊重 (-1=极度轻视, +1=极度敬佩)",
            "forgiveness": "宽恕/怨恨 (-1=强烈怨恨, 0=中性, +1=完全宽恕)",
            "curiosity": "好奇 (0=无, +1=极度好奇)",
            "confusion": "困惑 (0=清晰, +1=极度混乱)",
            "certainty": "确定性 (-1=极度不确定, +1=极度确定)",
            "anticipation": "预期/期待 (-1=消极担忧, +1=积极期待)",
            "nostalgia": "怀旧 (0=无, +1=强烈怀旧)",
            "impatience": "不耐烦 (0=从容, +1=极度急躁)",
            "relief": "释然 (0=无, +1=强烈解脱感)",
            "disappointment": "失望 (-1=强烈失望, 0=无)",
            "hope": "希望 (0=无, +1=强烈希望)"
        }
        lines = ["你是一位情绪评估专家。请根据对话内容，输出当前情绪状态的变化(delta)和推理过程。"]
        lines.append("\n评估维度（仅输出相对于 baseline 的 delta，范围 -1 到 +1）：")
        for d in dims:
            lines.append(f"  {d}: {dim_desc.get(d, d)}")
        lines.append("\n输出格式：严格的 JSON 对象，包含 `delta`（数字字典）和 `reasoning`（字符串说明）。")
        lines.append("不要输出 markdown 代码块，只输出纯 JSON。")
        return "\n".join(lines)

    @staticmethod
    def _build_user_prompt(history: List[dict], current_state: dict, full: bool = True) -> str:
        lines = ["=== 当前情绪状态快照 ==="]
        for k, v in current_state.items():
            if isinstance(v, (int, float)):
                lines.append(f"  {k}: {v:.2f}")
        lines.append("\n=== 对话历史 ===")
        for turn in history[-6:]:  # 最近 6 轮
            role = turn.get("role", "?")
            content = turn.get("content", "")
            lines.append(f"[{role}] {content[:200]}")
        if not full:
            lines.append("\n⚠️ 当前为简化模式，只需评估 valence 和 arousal 两个维度。")
        lines.append("\n请输出 JSON:")
        return "\n".join(lines)

    def _call_llm(self, model: str, messages: List[dict], timeout: int,
                  schema: dict) -> Optional[dict]:
        """
        通过 HTTP POST 调用 LLM API（兼容 OpenAI 风格 chat completions）。
        返回解析后的 dict，或 None 表示失败。
        """
        if not self.api_base:
            return None
        url = self.api_base.rstrip("/") + "/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 512,
            "response_format": {"type": "json_object"}
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                choice = body.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                if not content:
                    return None
                parsed = json.loads(content)
                # jsonschema 校验（可选，未安装时 fallback 到基础类型检查）
                try:
                    import jsonschema
                    jsonschema.validate(instance=parsed, schema=schema)
                except ImportError:
                    # jsonschema 未安装，做基础类型检查
                    if not isinstance(parsed, dict):
                        return None
                    delta = parsed.get("delta", {})
                    if not isinstance(delta, dict):
                        return None
                    for k, v in delta.items():
                        if not isinstance(v, (int, float)):
                            return None
                except jsonschema.ValidationError:
                    return None
                return parsed
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as e:
            print(f"[Appraiser] LLM call failed: {type(e).__name__}: {e}")
            return None

    def appraise(self, conversation_history: List[dict], current_state: dict) -> dict:
        """
        执行四级降级 appraisal。
        返回: {"delta": {...}, "reasoning": str, "level": int, "model": str}
        delta 包含所有 16 维（L3 未覆盖的维度补 0）
        """
        cache_key = self._cache_key(conversation_history, current_state)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return {**cached, "cached": True}

        system_full = self._build_system_prompt(full=True)
        user_full = self._build_user_prompt(conversation_history, current_state, full=True)
        system_emergency = self._build_system_prompt(full=False)
        user_emergency = self._build_user_prompt(conversation_history, current_state, full=False)

        # L1: 主模型完整评估
        result = self._call_llm(
            self.appraiser_model,
            [{"role": "system", "content": system_full},
             {"role": "user", "content": user_full}],
            self.timeout,
            self.OUTPUT_SCHEMA
        )
        if result:
            self._set_cached(cache_key, result)
            return {**result, "level": 1, "model": self.appraiser_model, "cached": False}

        # L2: fallback 模型完整评估
        if self.fallback_model:
            result = self._call_llm(
                self.fallback_model,
                [{"role": "system", "content": system_full},
                 {"role": "user", "content": user_full}],
                self.fallback_timeout,
                self.OUTPUT_SCHEMA
            )
            if result:
                self._set_cached(cache_key, result)
                return {**result, "level": 2, "model": self.fallback_model, "cached": False}

        # L3: emergency 模型简化评估（仅 valence/arousal）
        if self.emergency_model:
            result = self._call_llm(
                self.emergency_model,
                [{"role": "system", "content": system_emergency},
                 {"role": "user", "content": user_emergency}],
                self.fallback_timeout,
                self.EMERGENCY_SCHEMA
            )
            if result:
                # 补全剩余维度为 0
                delta = result.get("delta", {})
                full_delta = {k: delta.get(k, 0.0) for k in self.DIMENSIONS}
                result["delta"] = full_delta
                self._set_cached(cache_key, result)
                return {**result, "level": 3, "model": self.emergency_model, "cached": False}

        # L4: 完全降级，跳过 appraisal
        return {
            "delta": {k: 0.0 for k in self.DIMENSIONS},
            "reasoning": "L4 downgrade: all LLM services unavailable. Using inertia only.",
            "level": 4,
            "model": "none",
            "cached": False
        }
