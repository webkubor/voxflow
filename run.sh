#!/usr/bin/env bash
#
# VoxFlow 启动器（macOS / Linux）。Windows 用同目录的 run.ps1。
#
# ## 这个脚本为什么这么薄
#
# 它以前有 70 行：前端产物过期检查、museav 未登录提示、LLM 模型名 export。
# 2026-09-12 全部搬进了 `voice web`（cli/app.py）—— 因为**它们不是「启动脚本
# 的职责」，是「启动这件事本身的职责」**。放在 bash 里，等于 Windows 用户
# 一样都拿不到：改完前端不会自动编译、没连中台没有提示、模型名默认成
# FreeLLMAPI 的 "auto" 去打中台然后报错。
#
# 现在三个平台共用同一份逻辑，这个脚本只剩「找到 venv 里的 voice」。
#
# ## 用法
#
#   ./run.sh          启动 Web UI（默认，http://localhost:8866）
#   ./run.sh dev      开发模式：后端 8866 + Vite 前端 5173（改代码秒级热更新）
#   ./run.sh doctor   自检
#   ./run.sh <任意 voice 子命令>
#
# 开发时打开 http://localhost:5173（不是 8866）—— API 会自动代理到后端。

set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv/bin/voice ] || { echo "✗ 没找到 .venv/bin/voice，先跑 ./install.sh"; exit 1; }

# dev 模式：后端和前端各起一个，前端带热更新
if [ "${1:-}" = "dev" ]; then
  [ -d web/ui/node_modules ] || { echo "  安装前端依赖…"; (cd web/ui && npm install); }
  echo "  后端 → http://localhost:8866"
  echo "  前端 → http://localhost:5173  ← 开发时打开这个"
  echo
  .venv/bin/voice web &
  BACKEND_PID=$!
  trap 'kill $BACKEND_PID 2>/dev/null' EXIT INT TERM
  cd web/ui && exec npm run dev
fi

exec .venv/bin/voice "${@:-web}"
