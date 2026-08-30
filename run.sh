#!/usr/bin/env bash
#
# VoxFlow 启动器 —— 把 AI 文案助手接到自己的中台，不依赖第三方 LLM 服务。
#
# ## 为什么要这个脚本
#
# AI 文案助手（生成/润色配音文案）原本依赖 FreeLLMAPI：一个要用 Docker 起在
# localhost:3001 的第三方容器。多一个常驻服务、多一份要维护的东西，而这台机器
# 本来就有自己的 LLM 通道（museav 中台，key 只在中台一份、用量按租户记账）。
#
# core/llm_client.py 用的是标准 OpenAI SDK，三个环境变量就能换后端，
# 所以一行 Python 都不用改 —— 换的是配置，不是代码。
#
# ## 密钥为什么不写进 .env
#
# 写进 .env 就是明文落盘。这里用 `cs kyvault run` 把密钥**注入子进程环境**：
# 不落盘、不进 shell history、不出现在 ps 的 argv 里。
# 密钥本体在 secret://museav/voxcraft-tenant-key，要吊销去中台后台停这个租户即可。
#
# ## 用法
#
#   ./run.sh          启动 Web UI（默认，http://localhost:8866）
#   ./run.sh doctor   自检（会显示 AI 助手连没连上）
#   ./run.sh <任意 voice 子命令>
#
# 不想用中台、想回到本地 FreeLLMAPI：把下面三个 export 注释掉即可，
# llm_client.py 的默认值就是 localhost:3001。

set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv/bin/voice ] || { echo "✗ 没找到 .venv/bin/voice，先跑 ./install.sh"; exit 1; }

# 模型名跟着中台的口径走。中台 GET /api/chat 会下发当前模型，
# 换模型时改这里一处 —— 不要写 auto，那是 FreeLLMAPI 的路由约定，中台不认。
export VOXFLOW_LLM_BASE_URL="https://manager.museav.top/api"
export VOXFLOW_LLM_MODEL="deepseek-v4-flash"

# `cs` 在交互式 shell 里是个函数（见 .zshrc），脚本里调不到 —— 必须走真实二进制。
# CORTEXOS_ROOT 由 .zshrc 导出；非交互场景（launchd、后台进程）拿不到，所以给默认值。
CS_BIN="${CORTEXOS_ROOT:-$HOME/dev/gitlab/webkubor/CortexOS}/bin/cs"
[ -x "$CS_BIN" ] || { echo "✗ 找不到 cs（$CS_BIN）—— 密钥注入依赖它"; exit 1; }

exec "$CS_BIN" kyvault run --env VOXFLOW_LLM_API_KEY=secret://museav/voxcraft-tenant-key \
  -- .venv/bin/voice "${@:-web}"
