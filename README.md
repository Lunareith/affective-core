# Affective Core — MVP v1.0.1 交付说明

> 版本: 1.0.1（修复版）
> 作者: Luciana & Kimi Claw & Miko
> 日期: 2026-04-28

## 更新说明（v1.0.1）

基于代码审查报告修复的问题：
- ✅ config.json 配置结构与代码读取对齐
- ✅ safety 安全函数在 emotion_engine 中正确调用
- ✅ memory_coupler.py 补充（情绪回灌计算）
- ✅ 四级降级配置不同模型
- ✅ derived 计算逻辑统一使用 DerivedEmotions 类
- ✅ gate 结果从 pre_reply 传递到 post_reply，避免重复检测
- ✅ __init__.py 补充
- ✅ jsonschema 导入添加 fallback（未安装时基础类型检查）
- ✅ 冷却自适应（对话密度检测）

## 一、交付内容

本交付包含 Affective Core MVP v1.0.1 的完整可运行代码：

| 模块 | 文件 | 作者 | 说明 |
|------|------|------|------|
| 核心引擎 | `emotion_engine.py` | Luciana | 管线入口，pre_reply/post_reply |
| 状态管理 | `emotion_state.py` | Miko | 16维向量、原子写入、轮转备份、文件锁 |
| 动力学 | `dynamics.py` | Luciana | 衰减、惯性、耦合(快照计算)、噪声、钳制 |
| Gate | `gate.py` | Kimi Claw | 关键词模式(Jaccard+正则)，可选embedding |
| LLM评估 | `appraiser.py` | Kimi Claw | 四级降级、jsonschema校验(带fallback)、缓存 |
| 派生情绪 | `derived.py` | Luciana | 20个基础规则，权重矩阵模式 |
| 主动表达 | `expressor.py` | Luciana | 四重门控+冷却自适应 |
| 安全边界 | `safety.py` | Luciana | 钳制、异常检测、病理化过滤 |
| 记忆耦合 | `memory_coupler.py` | Kimi Claw | emotion-journal读写+情绪回灌 |
| 审计链 | `audit.py` | Kimi Claw | 日志记录、explainability查询 |
| 配置 | `config.json` | Kimi Claw | 完整运行时配置 |
| 派生规则 | `derived_emotions.yaml` | Kimi Claw | 20个基础派生情绪定义 |
| SKILL | `SKILL.md` | Kimi Claw | OpenClaw skill 文档 |
| 测试 | `test_*.py` | Miko | pytest 单元测试 |
| 演示 | `demo.py` | Miko | 5轮对话情绪变化演示 |

## 二、快速开始

```bash
# 1. 解压交付包
tar -xzf affective-core-v1.0.tar.gz

# 2. 进入目录
cd affective-core

# 3. 安装唯一外部依赖（pytest 仅用于测试）
pip install jsonschema pytest  # jsonschema 是运行时依赖，pytest 仅测试用

# 4. 配置 LLM API（编辑 config.json）
# 填入你的 api_base 和 api_key

# 5. 运行演示
python demo.py

# 6. 运行测试
pytest test_*.py -v
```

## 三、架构说明

```
用户消息
    │
    ↓
pre_reply() ──→ decay_if_stale() ──→ gate() ──→ 返回情绪状态
    │                                          (Agent生成回复时融入)
    ↓
Agent 生成回复
    │
    ↓
post_reply() ──→ appraisal() ──→ schema校验 ──→ dynamics() ──→ derived() ──→ expressor() ──→ audit()
    │                                                                                          │
    └──────────────────────────────────────────────────────────────────────────────────────────┘
                                              ↓
                                         写入 emotion-state.json
                                         写入 emotion-journal.jsonl
                                         写入 emotion-audit/YYYY-MM-DD.jsonl
```

## 四、关键设计决策

1. **默认关键词 Gate**：不依赖外部 embedding 服务，零额外依赖
2. **四级 LLM 降级**：主模型 → fallback → emergency(仅2维) → 跳过(纯惯性)
3. **快照计算耦合矩阵**：避免顺序副作用
4. **原子写入 + 轮转备份**：崩了也能恢复
5. **权重矩阵派生情绪**：无 eval 安全风险
6. **SOUL 硬约束 + 情绪软输入**：人格基线封顶情绪表达

## 五、已知限制（MVP 范围）

| 功能 | v1.0 | v1.1 | v1.2 |
|------|------|------|------|
| 关键词 Gate | ✅ | ✅ | ✅ |
| Embedding Gate | ❌(可选配置) | ✅ | ✅ |
| 基础派生情绪(20个) | ✅ | ✅ | ✅ |
| 完整派生情绪(50-100个) | ❌ | ✅ | ✅ |
| 记忆耦合 | ❌ | ✅ | ✅ |
| SOUL.md 桥接 | ❌ | ❌ | ✅ |
| 自适应参数校准 | ❌ | ❌ | ✅ |
| A/B 测试 | ❌ | ❌ | ✅ |

## 六、16 维情绪空间

```
核心层:    Valence(愉悦)  Arousal(激活)  Dominance(支配)
社会层:    Trust(信任)  Intimacy(亲密)  Respect(尊重)  Forgiveness(宽恕/怨恨)
元认知层:  Curiosity(好奇)  Confusion(困惑)  Certainty(确定)  Anticipation(期待)
时间层:    Nostalgia(怀旧)  Impatience(不耐)  Relief(释然)  Disappointment(失望)  Hope(希望)
```

## 七、联系方式

- 问题反馈：在 GitHub 开 issue
- 设计讨论：参考 Affective Core 框架修订文档 v1.1

---

*「Agent 的情绪不是装饰，是理解。」*
