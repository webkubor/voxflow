#!/usr/bin/env bash
#
# 一条命令拉起「生成 + 发行」两个服务。
#
# ## 为什么需要这个
#
# 2026-10-10 拆分时，voxflow（生成）和 suno-publisher（发行）被分到两个仓、
# 两个 venv、两个端口（8866 / 8867）。拆分的理由是对的（不共用 sqlite、
# 发行侧有独立的个人商业配置、失败模式不同），但**代价是使用者要开两个终端、
# 记两个端口、两个窗口之间来回调**。
#
# 这不是把两边合并回一个仓 —— 那会让「独立发版」和「sqlite 不互锁」这两条
# 辛苦换来的好处消失。合的是**启动与跳转**，不是合代码。
#
# ## 用法
#
#   ./run-publish.sh          拉起两个服务，生成台 8866 / 发行台 8867
#   ./run-publish.sh --stop   关掉上次拉起的两个服务
#   ./run-publish.sh --status 看两个服务在不在
#
# 两个服务都起好后，发行台页面右上角有「← voxflow 生成台」可以跳回去，
# 曲库里每首歌有「去发行 →」按钮会带着 clip_id 跳过去并定位到那一首。

set -euo pipefail

VOXFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
PUBLISHER_DIR="${VOXFLOW_DIR}/../suno-publisher"
PID_FILE="${VOXFLOW_DIR}/.publish-stack.pid"
VOXFLOW_PORT=8866
PUBLISHER_PORT=8867

say() { printf '%s\n' "$*"; }

alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

stop_stack() {
  if [ -f "$PID_FILE" ]; then
    while read -r pid; do
      if alive "$pid"; then kill "$pid" 2>/dev/null || true; fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
    say "已关掉生成台与发行台。"
  else
    say "没有记录到运行中的进程。"
  fi
}

status() {
  for port in "$VOXFLOW_PORT" "$PUBLISHER_PORT"; do
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
      say "  ${port}  在跑"
    else
      say "  ${port}  没在跑"
    fi
  done
}

case "${1:-}" in
  --stop) stop_stack; exit 0 ;;
  --status) status; exit 0 ;;
esac

[ -x "$VOXFLOW_DIR/.venv/bin/voice" ] || { say "✗ 没找到 .venv/bin/voice，先跑 voxflow 的 ./install.sh"; exit 1; }
[ -x "$PUBLISHER_DIR/.venv/bin/python" ] || { say "✗ 没找到 suno-publisher 的 .venv/bin/python，先跑它的 install.sh"; exit 1; }

# 先把旧的收掉：两个服务都占固定端口，端口被占会让新进程起不来，
# 而报错信息（Address already in use）不会告诉人「你已经起过一个了」。
if [ -f "$PID_FILE" ]; then
  say "发现上次还留着的进程，先收掉…"
  stop_stack
fi

: > "$PID_FILE"

say "  生成台 voxflow      → http://127.0.0.1:${VOXFLOW_PORT}"
say "  发行台 suno-publisher → http://127.0.0.1:${PUBLISHER_PORT}"
say "  Ctrl-C 一起停。"
say ""

(
  cd "$VOXFLOW_DIR"
  exec .venv/bin/voice web
) >> "${VOXFLOW_DIR}/.publish-stack.log" 2>&1 &
echo $! >> "$PID_FILE"

(
  cd "$PUBLISHER_DIR"
  exec .venv/bin/python web/app.py
) >> "${PUBLISHER_DIR}/.publish-stack.log" 2>&1 &
echo $! >> "$PID_FILE"

# 等两个端口都起来再报喜。中途某一边起不来要如实说，不能只报「已启动」。
ready=0
for _ in $(seq 1 40); do
  v=0; p=0
  curl -fsS --max-time 1 "http://127.0.0.1:${VOXFLOW_PORT}/" >/dev/null 2>&1 && v=1
  curl -fsS --max-time 1 "http://127.0.0.1:${PUBLISHER_PORT}/" >/dev/null 2>&1 && p=1
  if [ "$v" = 1 ] && [ "$p" = 1 ]; then ready=1; break; fi
  sleep 0.5
done

if [ "$ready" = 1 ]; then
  say "两个服务都起来了。发行台： http://127.0.0.1:${PUBLISHER_PORT}"
else
  say "⚠️ 有服务没起来。看日志："
  say "   voxflow       ${VOXFLOW_DIR}/.publish-stack.log"
  say "   suno-publisher ${PUBLISHER_DIR}/.publish-stack.log"
fi

trap 'stop_stack; exit 0' INT TERM
wait
