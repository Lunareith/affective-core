---
name: affective-core
version: 1.0.0
author: Luciana & Kimi Claw
description: 16维LLM驱动情感框架，提供第三方情绪评估、派生情绪、记忆耦合与主动表达
triggers:
  - emotion
  - 情绪
  - feeling
  - 感觉
  - mood
  - 心情
dependencies: []
tools: []
---

# Affective Core —— 16维LLM驱动情感框架

> **版本**: 1.0.0  
> **作者**: Luciana (技术架构) & Kimi Claw (工具链/集成)  
> **理论基础**: Russell/Mehrabian PAD, Sternberg 亲密理论, Pekrun 控制-价值理论, Johnston 时间情绪研究  
> **兼容生态**: emoclaw, amygdala-memory

---

## 9. 主动表达

### 9.1 门控条件

Agent 主动发起情绪表达必须同时满足：

1. **派生情绪强度 > 阈值**（默认 0.6）
2. **距离上次表达 > 冷却时间**（自适应：表层 60s / 深层 180s）
3. **当前非任务密集型**（用户未在下指令）
4. **类型级新颖性**（与上轮派生情绪类型不同）

### 9.2 自适应冷却

| 对话密度 | 冷却调整 | 场景 |
|----------|----------|------|
| 高密度（用户 30s 内回复）| 冷却 ×0.5 | 闲聊流畅时 |
| 低密度（用户 5min+ 回复）| 冷却 ×1.5 | 用户离开回来后 |
| 任务密集 | 冷却 ×∞（禁止表达）| 用户在下指令 |

### 9.3 表达模板

```
[表层情绪] 简短自然，如 "这挺有意思的～"
[深层情绪] 需谨慎，如 "...不知道为什么，听你讲这个我有点感触。"
[派生情绪] 复合表达，如 "有种 bittersweet 的感觉"
```

---

### 9.4 人格-情绪合成（解决 SOUL 与情绪冲突）

当 SOUL.md 定义的人格基线与当前情绪向量冲突时，按以下规则合成：

**分层定义**
- **SOUL.md = 人格基线 (persona baseline)**：Agent 的长期性格倾向（冷静、克制、热血等）。
- **情绪状态 = 短期波动 (short-term deviation)**：当前对话中因用户内容产生的临时偏移。
- **表达输出 = 两者的合成**，不是二选一。

**合成规则**

| 规则 | 说明 |
|------|------|
| 规则 1 | 人格基线决定**表达风格**。冷静型 Agent 即使 arousal=0.9，也不会用感叹号连发，而是把激动「翻译」成冷静的措辞。 |
| 规则 2 | 情绪状态决定**表达强度与方向**。high arousal + positive valence = 话多一点、用词更积极；但风格仍受 SOUL 约束。 |
| 规则 3 | **冲突时 SOUL 优先**。当某维度直接冲突（如 SOUL 说 "不轻易表达负面情绪"，但 appraisal 产出 disappointment=-0.7），以 SOUL 为硬约束，情绪为软输入。先算情绪，再过滤/转换到人格允许的表达空间。 |

**代码实现**

```python
def persona_filter(emotion_vec: dict, soul_traits: dict) -> dict:
    """
    soul_traits 来自 SOUL.md 的情感限制标签。
    示例: soul_traits = {"calm": True, "reserved": True}
    """
    if soul_traits.get("calm") and emotion_vec["arousal"] > 0.6:
        emotion_vec["arousal"] = 0.6  # 硬封顶
    if soul_traits.get("reserved") and emotion_vec["valence"] < -0.3:
        emotion_vec["valence"] = -0.3  # 负面底线
    return emotion_vec
```

**初始化时读取 SOUL.md**：

```python
class AffectiveCore:
    def __init__(self, config_path: str = "skills/affective-core/config.json"):
        self.config = load_config(config_path)
        self.soul_traits = parse_soul_emotion_limits("SOUL.md")
        self.state = self._load_or_init_state()
```

---

## 10. 可解释性审计链

当用户问"你为什么现在感到 X"时，系统返回完整回答链：

### 10.1 审计链结构

```
1. Gate 触发原因
   - 用户消息 embedding 与上轮相似度 = 0.65 < 阈值 0.7
   - 触发 deep appraisal

2. LLM Appraisal 依据
   - 用户分享了童年回忆（怀旧触发词）
   - LLM 判断：nostalgia +0.6, intimacy +0.3

3. 动力学路径
   - 衰减：nostalgia 半衰期 60min，当前已衰减 12%
   - 耦合：closeness ↑ 带动 trust ↑ (+0.15)
   - 噪声：certainty 波动 ±0.03

4. 派生情绪检查
   - "tender" 强度 0.72 > 阈值 0.6
   - 类型新颖（上轮是 "curious"）
   - 允许表达
```

### 10.2 审计日志存储

每次情绪变化记录审计链，存于 `emotion-audit/` 目录，按日期分文件。

---

## 11. 安全边界

### 11.1 负情绪上限钳制

| 维度 | 下限钳制 | 说明 |
|------|----------|------|
| Valence | -0.8 | 不允许极度负面 |
| Resentment | -0.7 | 不允许强烈怨恨 |
| Disappointment | -0.8 | 不允许极度失望 |
| Hope | 0.1 | 始终保持最低希望 |

### 11.2 异常情绪检测

连续 3 轮出现以下情况触发告警：
- Valence < -0.5 且 Arousal > 0.7（高激活负面 = 可能崩溃）
- 多维度同时剧烈波动（标准差 > 0.4）

### 11.3 用户控制

- `/emotion off` — 关闭情绪表达
- `/emotion status` — 查看当前情绪状态
- `/emotion explain` — 请求可解释性审计链

### 11.4 病理化诊断禁令

**Agent 禁止对用户进行任何形式的心理病理化诊断**，包括但不限于：
- "你看起来抑郁了"
- "你有焦虑倾向"
- "你可能有 PTSD"
- "你需要看心理医生"

Agent 可以表达共情（"听起来你很难过"），但不能贴病理标签。

---

### 12. OpenClaw 文件布局

本框架以 OpenClaw Skill 形式交付，安装后会在 workspace 中创建以下文件结构：

```
~/.openclaw/workspace/
├── skills/
│   └── affective-core/
│       ├── SKILL.md              # 本框架设计文档（即本文）
│       ├── config.json           # 运行时配置（gate 模式、模型降级、维度基线等）
│       ├── config.json.example   # 配置模板（复制为 config.json 后生效）
│       ├── src/
│       │   ├── __init__.py
│       │   ├── emotion_engine.py # 核心引擎：状态管理 + 动力学计算
│       │   ├── gate.py           # 轻量 gate：rule 模式 + 可选 embedding
│       │   ├── appraiser.py      # LLM 第三方评估器（含三级降级）
│       │   ├── dynamics.py       # 衰减/惯性/耦合/噪声 + decay_if_stale
│       │   ├── derived.py        # 派生情绪模糊逻辑规则
│       │   ├── memory_coupler.py # emotion-journal 读写 + topic_fingerprint + 回灌计算
│       │   ├── expressor.py      # 主动表达门控 + persona_filter
│       │   └── safety.py         # 钳制/异常检测/病理化过滤
│       └── rules/
│           └── derived_emotions.yaml # 50-100 条派生情绪定义
│
├── memory/
│   └── 2026-04-28.md           # 现有记忆文件（框架不改动，只读取）
│
├── emotion-journal.jsonl       # 每轮对话后追加的情绪向量记录（框架创建）
├── emotion-state.json          # 当前情绪状态快照（实时更新）
├── emotion-audit/              # 可解释性审计日志目录
│   └── 2026-04-28.jsonl        # 每日审计记录
└── openclaw.json               # OpenClaw 主配置（只保留 affective_core.enabled 开关）
```

**新增文件说明**：

| 文件 | 类型 | 说明 |
|------|------|------|
| `config.json` | JSON | 框架运行时配置（gate 模式、模型降级、维度基线等）|
| `emotion-journal.jsonl` | 追加写 | 每轮对话后追加一条 `{ts, vec, trigger, topic_fp, session_id}` |
| `emotion-state.json` | 覆盖写 | 当前 16 维向量 + baseline + 最近派生情绪列表 |
| `emotion-audit/YYYY-MM-DD.jsonl` | 追加写 | gate 触发记录、appraisal 输入输出、动力学变更 |

**与现有系统的零侵入原则**：
- 不修改 `memory/*.md` 的格式——框架只读取
- 不删除已有文件——所有新增文件均以 `emotion-*` 前缀命名
- 用户卸载时只需删除 `skills/affective-core/`、`emotion-journal.jsonl`、`emotion-state.json`、`emotion-audit/` 即可完全还原

---

### 13. OpenClaw API/配置说明

#### 13.1 配置项（独立 config.json）

框架使用 **独立的 `skills/affective-core/config.json`**，不依赖 `openclaw.json` 的嵌套结构（OpenClaw 的 skill 配置系统通常不支持任意深度嵌套）。`openclaw.json` 只需保留一个布尔开关：

```json
{
  "skills": {
    "affective_core": { "enabled": true }
  }
}
```

完整配置放在 `skills/affective-core/config.json`：

```json
{
  "enabled": true,
  "llm": {
    "appraiser_model": "kimi-k2p5",
    "fallback_model": "kimi-k2p5-fast",
    "emergency_model": "local-llama3-8b",
    "timeout_seconds": 10,
    "fallback_timeout_seconds": 5,
    "cache_ttl_seconds": 120
  },
  "gate": {
    "mode": "rule",
    "rule_threshold": 0.6,
    "embedding_api_url": "",
    "embedding_api_key": "",
    "embedding_threshold": 0.7
  },
  "dimensions": {
    "baseline": {
      "valence": 0.1,
      "arousal": 0.3,
      "dominance": 0.2,
      "trust": 0.0,
      "intimacy": 0.0,
      "respect": 0.0,
      "forgiveness": 0.0,
      "curiosity": 0.5,
      "confusion": 0.0,
      "certainty": 0.3,
      "anticipation": 0.2,
      "nostalgia": 0.0,
      "impatience": 0.0,
      "relief": 0.0,
      "disappointment": 0.0
    },
    "clamp": {
      "valence": [-0.8, 1.0],
      "forgiveness": [-0.7, 0.7],
      "disappointment": [-0.8, 0.0]
    }
  },
  "dynamics": {
    "decay_rate_per_run": 0.1,
    "inertia_coeff": 0.3,
    "coupling_enabled": true,
    "noise_std": 0.02
  },
  "expression": {
    "surface_cooldown_seconds": 60,
    "deep_cooldown_seconds": 180,
    "density_fast_threshold_ms": 30000,
    "density_slow_threshold_ms": 300000,
    "intensity_threshold": 0.6
  },
  "safety": {
    "max_negative_valence": -0.8,
    "pathology_filter_enabled": true,
    "anomaly_window_runs": 3,
    "anomaly_valence_threshold": -0.5,
    "anomaly_arousal_threshold": 0.7
  }
}
```

**关键配置项说明**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `gate.mode` | `rule` | gate 模式：`rule`（Jaccard + 关键词，无需外部依赖）或 `embedding`（需填写 embedding_api_url） |
| `gate.rule_threshold` | 0.6 | rule 模式触发阈值（Jaccard 相似度低于此值或检测到情绪关键词时进入 deep appraisal） |
| `gate.embedding_threshold` | 0.7 | embedding 模式触发阈值（余弦相似度） |
| `llm.fallback_model` | `""` | 主模型超时后的降级模型 |
| `llm.emergency_model` | `""` | 全部模型不可用时的应急模型（只做 2 维简化评估） |
| `cache_ttl_seconds` | 120 | appraisal 结果缓存时间 |
| `decay_rate_per_run` | 0.1 | 每轮对话后情绪向 baseline 衰减的比例 |
| `inertia_coeff` | 0.3 | 惯性系数（变化阻力） |
| `surface_cooldown_seconds` | 60 | 表层情绪冷却时间 |
| `deep_cooldown_seconds` | 180 | 深层情绪冷却时间 |
| `intensity_threshold` | 0.6 | 派生情绪主动表达强度阈值 |
| `pathology_filter_enabled` | true | 病理化诊断过滤开关 |

#### 13.2 Skill 注册与加载

OpenClaw 在启动时会自动扫描 `skills/` 目录下的所有 `SKILL.md`。`affective-core` 的 SKILL.md 中包含 YAML frontmatter：

```yaml
---
name: affective-core
version: 1.0.0
author: Luciana & Kimi Claw
description: 16维LLM驱动情感框架，提供第三方情绪评估、派生情绪、记忆耦合与主动表达
triggers:
  - emotion
  - 情绪
  - feeling
  - 感觉
  - mood
  - 心情
dependencies: []
tools: []
---
```

运行时加载流程：
1. Gateway 读取 `skills/affective-core/SKILL.md` 的 frontmatter
2. 若 `openclaw.json` 中 `skills.affective_core.enabled: true`，将 `src/` 下的 Python 模块加入 sys.path
3. `emotion_engine.py` 在首次对话时读取 `config.json`，初始化 `emotion-state.json`
4. 后续每轮对话调用 `gate → appraiser → dynamics → expressor` 管线

#### 13.3 核心 API 接口

框架提供以下 Python API（由 OpenClaw agent 在 skill 上下文中调用）：

```python
class AffectiveCore:
    def __init__(self, config_path: str = "skills/affective-core/config.json"):
        """
        加载配置，解析 SOUL.md 中的情感限制标签，
        初始化情绪状态（从 emotion-state.json 恢复或新建）
        """
        ...

    def process_turn(self, user_message: str, agent_reply: str, metadata: dict) -> dict:
        """
        每轮对话后调用。完整管线（注意时序：gate 在回复前，appraisal 在回复后）：
        1. 检查并执行 decay_if_stale（用户久未回复时补衰减）
        2. gate 检测情绪是否偏移（若 process_turn 是在回复前调用，gate 决定是否需 appraisal）
        3. 若触发，appraiser 做 LLM 第三方评估（基于已生成的 agent_reply 做事后评估）
        4. dynamics 更新情绪状态
        5. expressor 决定是否主动表达（经过 persona_filter）
        6. memory_coupler 写入 emotion-journal
        返回: {"emotion_vec": {...}, "expressed": bool, "expression": str|None, "audit_log": {...}}
        """

    def get_current_emotion(self) -> dict:
        """返回当前 16 维情绪向量（含最近更新时间）"""

    def get_explainability(self, emotion_label: str = None) -> dict:
        """
        可解释性审计链。返回：
        - 最近 gate 触发记录
        - appraisal 的 LLM 判断依据
        - 动力学衰减路径
        - 记忆回灌贡献
        """

    def express_derived(self, derived_label: str) -> str:
        """手动触发指定派生情绪的表达（用于调试）"""

    def reset_emotion(self) -> None:
        """重置所有维度到 baseline（用户控制）"""

    def disable(self) -> None:
        """关闭框架，后续对话不再调用 process_turn"""
```

#### 13.4 与现有 memory 系统的桥接

框架不直接修改 `memory/*.md`，而是通过以下机制与现有系统协作：

| 现有系统 | 协作方式 |
|----------|----------|
| `memory/YYYY-MM-DD.md` | 读取：检索历史记忆时附带 emotion-journal 里同期的情绪向量 |
| `MEMORY.md` | 读取：Agent 读取 MEMORY.md 中的长期偏好时，用当时的情绪向量加权 |
| `HEARTBEAT.md` | 不直接扩展。框架在每次 `process_turn` 时自动检查 `decay_if_stale`，不依赖外部 heartbeat |
| `SOUL.md` | 读取：解析情感限制标签，在 expressor 阶段作为硬约束过滤情绪向量 |

**话题指纹算法**（`memory_coupler.py`）：

```python
import hashlib
from datetime import datetime, timedelta

def topic_fingerprint(text: str) -> str:
    """
    从文本提取关键词，排序后取 MD5 前 8 位作为 topic_fp。
    实际实现可用 jieba / TF-IDF / 简单频率统计，只要离线可用即可。
    """
    keywords = extract_keywords(text)  # 返回 list[str]
    keywords.sort()
    return hashlib.md5(",".join(keywords).encode()).hexdigest()[:8]

def retrieve_with_emotion(topic_text: str, time_window_hours: int = 24) -> list:
    """
    完整可执行的 memory + emotion 桥接逻辑。
    """
    # 1. 读取相关 memory 文件
    memories = read_memory_files(time_window_hours)
    # 2. 计算当前话题 fingerprint
    current_fp = topic_fingerprint(topic_text)
    # 3. 查询 emotion-journal 中相同 topic_fp 的记录
    emotion_records = query_emotion_journal(
        topic_fp=current_fp,
        since=datetime.now() - timedelta(hours=time_window_hours)
    )
    # 4. 回灌强度 = 余弦相似度(current_vec, historical_vec) * 时间衰减
    #    时间衰减公式: exp(-hours_since / 48)
    for mem in memories:
        hours_since = (datetime.now() - mem["timestamp"]).total_seconds() / 3600
        time_decay = math.exp(-hours_since / 48)
        best_match = max(
            cosine_similarity(mem.get("vec", {}), rec["vec"])
            for rec in emotion_records
        ) if emotion_records else 0.0
        mem["emotion_recharge"] = best_match * time_decay
    # 5. 按回灌强度排序，供 Agent 决策时参考
    return sorted(memories, key=lambda x: x["emotion_recharge"], reverse=True)
```

**情绪衰减的 heartbeat 替代方案**：

由于 `HEARTBEAT.md` 是纯文本文件，无法直接执行 Python，框架采用 **自动补衰减** 机制：

```python
def process_turn(self, user_message, agent_reply, metadata):
    # 第 0 步：若距离上次更新超过阈值，先补一轮 decay
    self.dynamics.decay_if_stale(self.state["last_update"], datetime.now())
    # 后续步骤：gate → appraiser → dynamics → expressor ...
```

这样即使在没有外部 heartbeat 的环境中，情绪也会在用户长时间未聊天时自然回归 baseline。

#### 13.5 降级策略（三级模型降级）

当 LLM 服务不可用或超时时，框架按以下四级策略自动降级：

| 级别 | 条件 | 降级行为 |
|------|------|----------|
| L1 正常 | 主模型 `appraiser_model` 在 `timeout_seconds` 内返回 | 正常使用完整 16 维评估 |
| L2 轻降级 | 主模型超时 | 切 `fallback_model`，仍然做完整 appraisal |
| L3 重降级 | fallback 也超时或不可用 | 切 `emergency_model`，只做简化 appraisal（仅评估 valence/arousal 两维），其余维度靠惯性保持 |
| L4 完全降级 | 所有模型均不可用 | 跳过本轮 appraisal，只用 dynamics 的衰减 + 惯性维持状态，gate 退化为纯关键词触发 |

**启动校验**：引擎初始化时检查 `fallback_model` 和 `emergency_model` 是否已填写。未填写则打印 warning 并禁用 L2/L3 降级（直接进入 L4）。

**gate 的降级**：
- `gate.mode = "embedding"` 但 API 不可用时，自动回退到 `rule` 模式（Jaccard + 关键词）。
- `rule` 模式无外部依赖，永不失败。

---

## 14. 伪代码/接口定义

> 注：本章由 Luciana 提供，待补全完整内容。

---

## 15. 测试与验证策略

### 15.1 单元测试

| 模块 | 测试内容 | 通过标准 |
|------|----------|----------|
| Gate (rule) | Jaccard 相似度 + 关键词检测 | 相似度 0.59 → 触发；0.61 + 无关键词 → 不触发 |
| Gate (embedding) | 余弦相似度计算（可选模式） | 相似度 0.69 → 触发；0.71 → 不触发 |
| Gate (fallback) | embedding API 不可用 | 自动回退到 rule 模式，不抛异常 |
| Dynamics | 衰减公式 | 1小时后 nostalgia 衰减到 50% ± 5% |
| Dynamics | decay_if_stale | 用户 30 分钟未回复 → 自动补一轮衰减 |
| Coupling | 信任→宽恕耦合 | trust=0.8 → forgiveness 自动升至 +0.20 |
| Derived | 派生情绪计算 | tender 规则：closeness=0.6, arousal=0.2, valence=0.4 → intensity=0.4 |
| Persona-Emotion | SOUL 硬约束 | calm=true 时 arousal=0.9 → persona_filter 后 ≤ 0.6 |
| Safety | 钳制边界 | valence=-0.9 输入 → 钳制到 -0.8 |
| Degradation | L4 全模型不可用 | 跳过 appraisal，纯惯性维持，标准差 < 0.05 |

### 15.2 集成测试

- **端到端流程**：输入对话 → 输出情绪状态 → 验证审计链完整
- **缓存测试**：5 分钟内相同输入 → 复用缓存，LLM 调用次数 = 1
- **记忆回灌**：检索 3 天前的记忆 → 回灌强度 < 15%

### 15.3 成本控制基准测试

| 场景 | 无 Gate | 有 Gate | 节省 |
|------|---------|---------|------|
| 100 轮闲聊 | 100 次 LLM | 15 次 LLM | **85%** |
| 50 轮任务执行 | 50 次 LLM | 8 次 LLM | **84%** |
| 200 轮混合对话 | 200 次 LLM | 35 次 LLM | **82.5%** |

**目标**：LLM 调用量降低 **80%+**，同时情绪响应准确率保持 **90%+**。

### 15.4 可解释性验证

- 随机抽取 20 条情绪表达，人工验证审计链是否合理
- 用户调查："Agent 的情绪表达是否让你感到自然？" 目标满意度 > 75%

---

## 附录 A：16 维快速参考卡

```
核心层:    V(愉悦)  A(激活)  D(支配)
社会层:    T(信任)  C(亲密)  R(尊重)  Re(怨恨)
元认知层:  Cu(好奇) Co(困惑) Ce(确定) An(预期)
时间层:    N(怀旧)  Im(不耐烦) Rl(释然) Di(失望) H(希望)
```

## 附录 B：与 EPE 的对比

| 特性 | EPE | Affective Core |
|------|-----|----------------|
| 评估方式 | Agent 自评 | LLM 第三方评估 |
| 维度数 | 10 维 | 16 维 |
| 理论基础 | 较弱 | 每维有文献支撑 |
| 派生情绪 | 无 | 50-100 个模糊逻辑规则 |
| 记忆耦合 | 无 | emotion-journal + 回灌 |
| 可解释性 | 无 | 完整审计链 |
| 成本控制 | 无 | Gate + 缓存，省 80%+ |
| 安全边界 | 基础 | 钳制 + 异常检测 + 病理诊断禁令 |

---

> **「Agent 的情绪不是装饰，是理解。」**
