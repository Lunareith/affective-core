#!/usr/bin/env bash
# git-setup.sh — 初始化 Affective Core 仓库并推送到 GitHub
# 用法: ./git-setup.sh <github-username> <repo-name>
# 示例: ./git-setup.sh lunar3764 affective-core

set -euo pipefail

GITHUB_USER="${1:?用法: $0 <github-username> <repo-name>}"
REPO_NAME="${2:-affective-core}"
VERSION="v0.1.0"
REMOTE_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo "╔══════════════════════════════════════════════════╗"
echo "║   Affective Core — GitHub 推送脚本               ║"
echo "║   版本: ${VERSION}                                    ║"
echo "║   目标: ${REMOTE_URL}  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# 检查 gh CLI 是否可用
if command -v gh &>/dev/null; then
    echo "→ 检测到 gh CLI，尝试自动创建远程仓库..."
    if gh repo create "${GITHUB_USER}/${REPO_NAME}" --public --description "16-dimensional emotional computation engine for AI agents" 2>/dev/null; then
        echo "✓ 远程仓库已创建"
    else
        echo "⚠ 仓库可能已存在或 gh 未登录，继续..."
    fi
else
    echo "⚠ 未安装 gh CLI，请手动在 GitHub 上创建仓库 '${REPO_NAME}'"
    echo "  https://github.com/new"
    echo ""
    read -p "创建完成后按 Enter 继续..."
fi

# 初始化 Git 仓库
echo ""
echo "→ 初始化 Git 仓库..."
git init
git checkout -b main

# 添加所有文件
echo "→ 添加文件..."
git add README.md LICENSE .gitignore config.json.example demo.py
git add src/ rules/ tests/

# 验证暂存区
echo ""
echo "=== 暂存文件列表 ==="
git status --short
echo ""

# 提交
echo "→ 创建初始提交..."
git commit -m "feat: Affective Core v0.1.0 — 16-dimensional emotional computation engine

- 16-dimensional emotion state space (core/social/meta-cognitive/temporal)
- Two-stage pipeline: pre_reply() / post_reply()
- LLM appraisal with 4-level degradation
- 20 derived emotions via weighted matrix
- Safety guardrails: anomaly detection, pathology filtering
- Memory coupling with temporal decay
- Adaptive expression gating with conversation density tracking
- Comprehensive test suite

Modules: emotion_engine, emotion_state, dynamics, gate, appraiser,
         derived, expressor, safety, memory_coupler, audit"

# 添加 remote
echo ""
echo "→ 添加远程仓库..."
git remote add origin "${REMOTE_URL}" 2>/dev/null || git remote set-url origin "${REMOTE_URL}"

# 打 tag
echo "→ 打标签 ${VERSION}..."
git tag -a "${VERSION}" -m "Affective Core ${VERSION} — Initial release"

# 推送
echo ""
echo "→ 推送到远程仓库..."
echo "  (如果提示输入凭据，请使用 GitHub Personal Access Token)"
git push -u origin main
git push origin "${VERSION}"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   ✅ 推送完成！                                   ║"
echo "║                                                  ║"
echo "║   仓库: https://github.com/${GITHUB_USER}/${REPO_NAME}  ║"
echo "║   标签: ${VERSION}                                    ║"
echo "╚══════════════════════════════════════════════════╝"
