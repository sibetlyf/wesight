#!/bin/bash
# 启动 Orchestrator API 服务器的脚本

set -e

# 项目根目录
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)

# 清理旧的测试目录
echo "清理旧的测试目录..."
rm -rf "$PROJECT_ROOT/.cache/userspace"

# 创建测试目录结构
echo "创建测试目录结构..."
mkdir -p "$PROJECT_ROOT/.cache/userspace/sessions"

# 生成会话ID
SESSION_ID=$(uuidgen)
SESSION_DIR="$PROJECT_ROOT/.cache/userspace/sessions/$SESSION_ID"
mkdir -p "$SESSION_DIR/runs"
mkdir -p "$SESSION_DIR/skills"
mkdir -p "$SESSION_DIR/tools"
mkdir -p "$SESSION_DIR/subagents"
mkdir -p "$SESSION_DIR/todo"

# 设置环境变量
echo "设置环境变量..."
export USERSPACE="$PROJECT_ROOT/.cache/userspace"
export SESSIONSPACE="$PROJECT_ROOT/.cache/userspace/sessions"
export WORKSPACE="$SESSION_DIR"
export RUNSPACE="$SESSION_DIR/runs"
export USER_ID="test_user"
export RECORD_ID=$(uuidgen)
export AUTHORIZATION="${AUTHORIZATION:-TEST_AUTHORIZATION}"
export TESTING="1"
export AGNO_DEBUG="true"

# 加载测试配置并设置 ORCHESTRATOR_CONFIG
echo "加载测试配置..."
CONFIG_JSON=$(python3 -c "
import yaml
import json
with open('$PROJECT_ROOT/tests/test_config.yaml', 'r') as f:
    config = yaml.safe_load(f)
print(json.dumps(config))
")
export ORCHESTRATOR_CONFIG="$CONFIG_JSON"

# 打印环境信息
echo ""
printf '=%.0s' {1..60}
echo ""
echo "本地测试环境设置完成"
printf '=%.0s' {1..60}
echo ""
echo "用户空间: $USERSPACE"
echo "会话空间: $SESSIONSPACE"
echo "工作空间: $WORKSPACE"
echo "运行空间: $RUNSPACE"
echo "会话ID: $SESSION_ID"
echo "用户ID: $USER_ID"
echo "记录ID: $RECORD_ID"
printf '=%.0s' {1..60}
echo ""
echo ""

# 启动 API 服务器
echo "启动 API 服务器..."
echo "API 文档: http://localhost:8000/docs"
echo "健康检查: http://localhost:8000/health"
echo "按 Ctrl+C 停止服务器"
echo ""

# 进入 src 目录并启动服务器
cd "$PROJECT_ROOT/src" && uv run python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
