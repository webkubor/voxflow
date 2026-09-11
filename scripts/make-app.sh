#!/usr/bin/env bash
#
# 生成 ~/Applications/VoxFlow.app —— 双击启动本地服务并开一个无地址栏的窗口。
#
# 不是 Tauri/Electron。macOS 的 .app 就是个带 Info.plist 的目录，里面这个
# shell 脚本干三件事：后端没跑就拉起来、等它就绪、用 Chrome --app 开窗。
# 打包壳省不掉 ~/.voxflow 那 8.4G 模型和 1.4G venv，所以不值得为它引一套
# Rust 工具链；这 60 行给的是同一个东西：一个能双击的图标。
#
# 幂等，改完重跑即可覆盖。
set -euo pipefail
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/VoxFlow.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# 图标：1024 的母图切成标准 iconset，iconutil 打包成 icns
ICONSET="$(mktemp -d)/VoxFlow.iconset"
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$PROJECT/assets/branding/logo-icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$PROJECT/assets/branding/logo-icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/VoxFlow.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>VoxFlow</string>
  <key>CFBundleDisplayName</key><string>VoxFlow 声流</string>
  <key>CFBundleIdentifier</key><string>com.webkubor.voxflow</string>
  <key>CFBundleExecutable</key><string>VoxFlow</string>
  <key>CFBundleIconFile</key><string>VoxFlow</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/VoxFlow" <<LAUNCHER
#!/usr/bin/env bash
PROJECT="$PROJECT"
LAUNCHER
cat >> "$APP/Contents/MacOS/VoxFlow" <<'LAUNCHER'
URL="http://localhost:8866"
LOG="$HOME/.voxflow/webui.log"

# 后端没在跑就拉起来。已在跑就直接开窗 —— 重启一个加载了模型的进程有代价，
# 幂等不等于可以随便重跑。
if ! curl -sf -m 2 "$URL/api/health" >/dev/null 2>&1; then
  osascript -e 'display notification "正在启动，首次加载模型约需半分钟…" with title "VoxFlow 声流"' &
  mkdir -p "$HOME/.voxflow"
  nohup "$PROJECT/run.sh" >>"$LOG" 2>&1 &
  # ponytail: 固定等 120s；模型加载再慢就改这个数，不值得为它做进度回调
  for _ in $(seq 120); do
    curl -sf -m 2 "$URL/api/health" >/dev/null 2>&1 && break
    sleep 1
  done
  if ! curl -sf -m 2 "$URL/api/health" >/dev/null 2>&1; then
    osascript -e "display alert \"VoxFlow 启动失败\" message \"看日志：$LOG\""
    exit 1
  fi
fi

# --app = 独立窗口、无地址栏无标签页。没装 Chrome 就退回默认浏览器。
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] && exec "$CHROME" --app="$URL" || exec open "$URL"
LAUNCHER

chmod +x "$APP/Contents/MacOS/VoxFlow"
touch "$APP"   # 让 Finder 重读图标
echo "✓ $APP"
echo "  双击即用。想放程序坞：在 Finder 里拖过去。"
