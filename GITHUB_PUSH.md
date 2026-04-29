# Affective Core — GitHub 推送指南

## 前置条件

1. **GitHub 账号**
2. **Personal Access Token (PAT)**：
   - 进入 GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - 生成新 token，勾选 `repo` 权限
   - 复制 token（只显示一次）

## 方式一：使用自动脚本

```bash
cd affective-core
chmod +x git-setup.sh
./git-setup.sh <你的GitHub用户名> affective-core
```

提示输入密码时，粘贴你的 Personal Access Token。

## 方式二：手动推送

### Step 1: 创建远程仓库

在 GitHub 上创建新仓库：
- URL: https://github.com/new
- 仓库名: `affective-core`
- 描述: `16-dimensional emotional computation engine for AI agents`
- 设为 Public
- **不要**勾选 "Add a README file"（本地已有）

### Step 2: 初始化本地仓库

```bash
cd affective-core

# 初始化
git init
git checkout -b main

# 添加所有文件
git add README.md LICENSE .gitignore config.json.example demo.py
git add src/ rules/ tests/

# 确认文件列表
git status

# 提交
git commit -m "feat: Affective Core v0.1.0 — 16-dimensional emotional computation engine"
```

### Step 3: 关联远程仓库并推送

```bash
# 添加 remote（替换 YOUR_USERNAME）
git remote add origin https://github.com/YOUR_USERNAME/affective-core.git

# 推送
git push -u origin main
```

### Step 4: 打标签

```bash
# 创建 annotated tag
git tag -a v0.1.0 -m "Affective Core v0.1.0 — Initial release"

# 推送标签
git push origin v0.1.0
```

### Step 5: 验证

访问 `https://github.com/YOUR_USERNAME/affective-core` 确认：
- [x] README 正常显示
- [x] 目录结构正确（src/ rules/ tests/）
- [x] Tags 页面有 v0.1.0
- [x] LICENSE 文件存在

## 仓库结构

```
affective-core/
├── README.md              # 项目文档
├── LICENSE                # MIT 许可证
├── .gitignore             # Git 忽略规则
├── config.json.example    # 配置模板
├── demo.py                # 演示脚本
├── git-setup.sh           # 自动推送脚本
├── GITHUB_PUSH.md         # 本文档
├── src/
│   ├── __init__.py
│   ├── emotion_engine.py  # 核心引擎（pre_reply/post_reply）
│   ├── emotion_state.py   # 状态管理（原子写入+备份+锁）
│   ├── dynamics.py        # 动力学（衰减/惯性/耦合/噪声）
│   ├── gate.py            # Gate 触发检测
│   ├── appraiser.py       # LLM 评估（4级降级）
│   ├── derived.py         # 派生情绪（权重矩阵）
│   ├── expressor.py       # 表达门控（冷却+密度）
│   ├── safety.py          # 安全边界
│   ├── memory_coupler.py  # 记忆耦合
│   └── audit.py           # 审计链
├── rules/
│   └── derived_emotions.yaml  # 派生情绪规则
└── tests/
    ├── conftest.py
    ├── test_emotion_state.py
    ├── test_dynamics.py
    ├── test_gate.py
    └── test_safety.py
```

## 常见问题

### Q: push 时提示 403？
A: Token 权限不足。确保 token 有 `repo` scope。

### Q: push 时提示 "Repository not found"？
A: 远程仓库名拼写不对，或仓库还没创建。

### Q: 想用 SSH 而不是 HTTPS？
A: 将 remote URL 改为 `git@github.com:YOUR_USERNAME/affective-core.git`

---

*准备就绪，一键推送。*
