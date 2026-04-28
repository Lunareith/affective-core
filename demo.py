"""
demo.py - 模拟 5 轮对话，展示情绪状态变化

运行方式：
    python demo.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from emotion_state import EmotionState


# 16 维定义
DIMS = [
    "valence", "arousal", "dominance",
    "trust", "intimacy", "respect", "forgiveness",
    "curiosity", "confusion", "certainty", "anticipation",
    "nostalgia", "impatience", "relief", "disappointment", "hope",
]


def mock_dynamics_update(state: EmotionState, user_msg: str, agent_reply: str) -> None:
    """
    模拟 dynamics 更新：根据对话内容简单调整情绪向量。
    实际项目中由 dynamics.py 的 Dynamics.update() 替代。
    """
    cur = state.get_current()
    vec = cur["vec"]

    # 简单的关键词映射（演示用）
    keyword_map = {
        "开心": {"valence": 0.3, "arousal": 0.1},
        "难过": {"valence": -0.4, "hope": -0.2},
        "生气": {"valence": -0.3, "arousal": 0.3, "forgiveness": -0.2},
        "害怕": {"dominance": -0.3, "trust": -0.1, "arousal": 0.3},
        "谢谢": {"valence": 0.3, "trust": 0.2},
        "喜欢": {"valence": 0.3, "intimacy": 0.2},
        "讨厌": {"valence": -0.4, "arousal": 0.2},
        "无聊": {"impatience": 0.3, "anticipation": -0.2},
    }

    delta = {dim: 0.0 for dim in vec}
    text = (user_msg + " " + agent_reply).lower()
    for kw, changes in keyword_map.items():
        if kw in text:
            for dim, val in changes.items():
                if dim in delta:
                    delta[dim] += val

    # 衰减模拟
    for dim in vec:
        vec[dim] *= 0.9  # 10% 衰减
        vec[dim] += delta.get(dim, 0.0)
        # 钳制到 [-1, 1]
        vec[dim] = max(-1.0, min(1.0, vec[dim]))

    state.update_vec(vec)


def print_state(state: EmotionState, round_num: int, label: str) -> None:
    cur = state.get_current()
    vec = cur["vec"]
    print(f"\n{'='*60}")
    print(f"Round {round_num} — {label}")
    print(f"{'='*60}")
    # 按强度排序，只显示非零的
    nonzero = sorted(
        ((dim, val) for dim, val in vec.items() if abs(val) > 0.01),
        key=lambda x: abs(x[1]),
        reverse=True,
    )
    if nonzero:
        for dim, val in nonzero:
            bar = "█" * int(abs(val) * 20)
            print(f"  {dim:12s}: {val:+.3f} {bar}")
    else:
        print("  (全部接近基线)")
    print(f"  last_update: {cur['last_update']}")


def main() -> None:
    # 准备临时配置
    demo_dir = Path(__file__).parent / "demo_state"
    demo_dir.mkdir(exist_ok=True)
    config_path = demo_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "baseline": {
                    "valence": 0.1, "arousal": 0.3, "dominance": 0.2,
                    "trust": 0.0, "intimacy": 0.0, "respect": 0.0, "forgiveness": 0.0,
                    "curiosity": 0.5, "confusion": 0.0, "certainty": 0.3, "anticipation": 0.2,
                    "nostalgia": 0.0, "impatience": 0.0, "relief": 0.0,
                    "disappointment": 0.0, "hope": 0.1,
                },
                "dynamics": {"decay_rate": 0.05},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = EmotionState(str(config_path))
    state.reset()

    # 5 轮对话
    conversations = [
        ("用户: 你好呀，今天天气真不错！", "Agent: 是啊，阳光明媚，心情都变好了～"),
        ("用户: 我有点难过，工作不太顺利", "Agent: 抱抱你，困难总会过去的，要对自己有信心"),
        ("用户: 谢谢你，感觉好多了", "Agent: 能帮到你我也很开心！"),
        ("用户: 但是那个同事真的很讨厌", "Agent: 遇到讨厌的人确实让人生气，不过别让他影响你太久"),
        ("用户: 哈哈你说得对，我要去喝杯咖啡开心一下", "Agent: 好主意！享受你的咖啡时光 ☕"),
    ]

    print("\n" + "=" * 60)
    print("Affective Core MVP v1.0 — 5 轮对话情绪演示")
    print("=" * 60)

    for i, (user_msg, agent_reply) in enumerate(conversations, 1):
        # 模拟 pre_reply：衰减 + 返回当前状态
        print_state(state, i, f"pre_reply | {user_msg[:30]}...")

        # 模拟 post_reply：dynamics 更新
        mock_dynamics_update(state, user_msg, agent_reply)
        print_state(state, i, f"post_reply | {agent_reply[:30]}...")

        time.sleep(0.1)  # 让 last_update 有时间差

    # 最终总结
    print("\n" + "=" * 60)
    print("最终情绪状态快照")
    print("=" * 60)
    final = state.get_current()
    for dim in sorted(final["vec"].keys()):
        val = final["vec"][dim]
        marker = "*" if abs(val) > 0.3 else " "
        print(f"  {marker} {dim:12s}: {val:+.3f}")

    print(f"\n状态文件: {state.state_file}")
    print(f"备份目录: {state.backup_dir}")


if __name__ == "__main__":
    main()
