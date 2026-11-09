#!/usr/bin/env bash
#
# 构建 VoxFlow 原生 macOS App（MyGo），并安装到 ~/Applications。
#
# ## 为什么需要这个脚本
#
# App 启动后要找到项目里的 run.sh，才能拉起本地 Python 后端。从访达双击
# 打开时没有工作目录、没有环境变量，所以项目路径必须**烧进二进制**：
#
#     MYGO_LDFLAGS="-X main.buildProjectDir=<路径>"
#
# MyGo 把 MYGO_LDFLAGS 追加在它自己的 -X 之后，所以这个注入不会被覆盖。
#
# ## 用法
#
#     desktop/build.sh          构建并安装
#     desktop/build.sh --dev    构建开发版（带调试器）
#
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP="$PROJECT/desktop"
# App 名字取自 mygo.json 的 name（"VoxFlow 声流"），不是脚本里另写一份 ——
# 两处不一致会让「构建成功但装不上」。
APP_NAME="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["name"])' "$DESKTOP/mygo.json").app"
DEST="$HOME/Applications/$APP_NAME"

# Go 工具链交给 Go 自己选（auto）：go.mod 要求 1.27.3（MyGo 依赖它），
# 本机装的是 1.27.2 时，Go 会自动切到 1.27.3 —— 本地缓存里有就直接用，
# 没有就自动下载。在脚本里硬钉 GOTOOLCHAIN=go1.27.3 反而更脆：
# 一旦设了 GOTOOLCHAIN，Go 就不再自动兜底，工具链缺失时直接失败。
export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"
export PATH="$PATH:$(go env GOPATH)/bin"

command -v mygo >/dev/null || { echo "✗ 找不到 mygo，先装：go install github.com/egoist/mygo/cmd/mygo@latest"; exit 1; }

# ── 1. 前端产物 ──────────────────────────────────────────
# MyGo 嵌入的是 web/static（前端 base 是 /static/），所以每次构建都要把
# 最新产物同步过去。同步是「删掉旧的再拷贝」而不是增量拷贝：前端删掉一个
# 文件后，旧的残留物会让页面去加载一个已经不存在的 chunk。
echo "▸ 同步前端产物"
rm -rf "$DESKTOP/web"
mkdir -p "$DESKTOP/web"
cp -R "$PROJECT/web/static" "$DESKTOP/web/static"

# ── 2. 构建 ─────────────────────────────────────────────
# 项目路径用 main. 前缀注入，不是模块全路径。
#
# main 包的变量在符号表里是 main.buildProjectDir，Go 的 -X 对它只认
# "main.变量名"；写成模块全路径 github.com/webkubor/voxflow/desktop.
# buildProjectDir 编译不报错，但**静默不生效** —— 构建照过，装出来的 App
# 却找不到项目，双击打开只剩一个空窗口。
echo "▸ 构建 App"
export MYGO_LDFLAGS="-X main.buildProjectDir=$PROJECT"
cd "$DESKTOP"
mygo build -skip-dmg "$@"

BUILT="$DESKTOP/build/darwin-arm64/$APP_NAME"
test -d "$BUILT/Contents/MacOS" || { echo "✗ 构建产物不对：$BUILT"; exit 1; }

# ── 3. 安装 ─────────────────────────────────────────────
echo "▸ 安装到 $DEST"
mkdir -p "$HOME/Applications"
# 原子替换：先装到临时目录，再整个换掉。中途失败不会留下半个 App。
STAGING="$(mktemp -d)/$APP_NAME"
ditto "$BUILT" "$STAGING"
if [ -d "$DEST" ]; then
  rm -rf "${DEST:?}"
fi
mv "$STAGING" "$DEST"

echo "✓ 已安装：$DEST"
echo "  双击打开即可。想放程序坞：在访达里拖过去。"
echo
echo "  注意：App 需要能找到项目目录才能启动本地音频服务。"
echo "  当前烧录路径：$PROJECT"
echo "  换机器或移动项目后，重跑 desktop/build.sh 重新烧录。"
