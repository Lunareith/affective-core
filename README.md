# Affective Core

> A 16-dimensional emotional computation engine for AI agents.
> Version: v0.1.0

## Overview

Affective Core is a lightweight, modular emotional computation framework designed for AI agents. It provides a 16-dimensional emotional state space, real-time emotional dynamics, LLM-based appraisal, derived emotion computation, and safe expression gating.

### Key Features

- **16-Dimensional Emotion Space**: Core, social, meta-cognitive, and temporal dimensions
- **Two-Stage Pipeline**: `pre_reply()` before agent response, `post_reply()` after
- **LLM Appraisal with 4-Level Degradation**: Graceful fallback from primary to emergency models
- **Derived Emotions**: 20+ composite emotions via weighted matrix computation
- **Safety Guardrails**: Anomaly detection, pathology filtering, vector clamping
- **Memory Coupling**: Emotion journal with temporal decay and recharge computation
- **Adaptive Expression**: Conversation-density-aware cooldown management

## Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/affective-core.git
cd affective-core

# Install dependencies
pip install pyyaml pytest  # pytest only for testing

# Configure LLM API (edit config.json)
# Set your api_base and api_key

# Run the demo
python demo.py

# Run tests
pytest tests/ -v
```

## Architecture

```
User Message
    │
    ↓
pre_reply() ──→ decay_if_stale() ──→ gate() ──→ Returns emotional state
    │                                          (Agent incorporates into reply)
    ↓
Agent generates reply
    │
    ↓
post_reply() ──→ appraisal() ──→ dynamics() ──→ safety() ──→ derived()
    │                                                          │
    │                                                          ↓
    │                                                    expressor_plan()
    │                                                          │
    └──────────────────────────────────────────────────────────┘
                          ↓
                    Save state
                    Write journal
                    Write audit log
```

### Modules

| Module | File | Purpose |
|--------|------|---------|
| Core Engine | `src/emotion_engine.py` | Pipeline orchestration: pre_reply / post_reply |
| State Manager | `src/emotion_state.py` | 16D vector, atomic writes, rotation backups, file locks |
| Dynamics | `src/dynamics.py` | Decay, inertia, coupling, noise, clamping |
| Gate | `src/gate.py` | Keyword/Jaccard trigger detection, optional embedding |
| Appraiser | `src/appraiser.py` | LLM evaluation with 4-level degradation |
| Derived | `src/derived.py` | Composite emotion computation via weight matrices |
| Expressor | `src/expressor.py` | 4-gate expression planning with adaptive cooldown |
| Safety | `src/safety.py` | Anomaly detection, pathology filtering, vector clamping |
| Memory | `src/memory_coupler.py` | Journal I/O and emotional recharge computation |
| Audit | `src/audit.py` | Explainability chain, per-day log files |

## Configuration

Copy `config.json.example` to `config.json` and customize:

```json
{
  "enabled": true,
  "llm": {
    "api_base": "https://api.example.com",
    "api_key": "your-api-key",
    "appraiser_model": "kimi-k2p5",
    "fallback_model": "qwen-turbo",
    "emergency_model": "kimi-for-coding",
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
    "baseline": { ... },
    "clamp": { ... }
  },
  "dynamics": {
    "decay_rate_per_run": 0.1,
    "inertia_coeff": 0.3,
    "coupling_enabled": true,
    "noise_std": 0.02,
    "stale_threshold_minutes": 30
  },
  "expression": {
    "surface_cooldown_seconds": 60,
    "deep_cooldown_seconds": 180,
    "intensity_threshold": 0.6,
    "novelty_check_enabled": true
  },
  "safety": {
    "max_negative_valence": -0.8,
    "pathology_filter_enabled": true,
    "anomaly_window_runs": 3,
    "anomaly_valence_threshold": -0.5,
    "anomaly_arousal_threshold": 0.7
  },
  "memory": {
    "journal_path": "emotion-journal.jsonl",
    "state_path": "emotion-state.json",
    "audit_dir": "emotion-audit",
    "recharge_time_decay_hours": 48,
    "recharge_lookback_days": 7
  }
}
```

### 16 Dimensions

```
Core Layer:      Valence(愉悦)  Arousal(激活)  Dominance(支配)
Social Layer:    Trust(信任)  Intimacy(亲密)  Respect(尊重)  Forgiveness(宽恕)
Meta-cognitive:  Curiosity(好奇)  Confusion(困惑)  Certainty(确定)  Anticipation(期待)
Temporal Layer:  Nostalgia(怀旧)  Impatience(不耐)  Relief(释然)  Disappointment(失望)  Hope(希望)
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_emotion_state.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Test Files

| File | Coverage |
|------|----------|
| `tests/test_emotion_state.py` | State persistence, backup, atomic writes |
| `tests/test_dynamics.py` | Decay, coupling, inertia, clamping |
| `tests/test_gate.py` | Rule/embedding trigger detection |
| `tests/test_safety.py` | Anomaly detection, pathology filtering |

## License

MIT License — see [LICENSE](LICENSE) file.

---

*"Agent emotion is not decoration, it's understanding."*
