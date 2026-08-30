#!/usr/bin/env bash
#
# 目录重排迁移 —— 把散落的音频资产按「生命周期」归位。
#
# ## 为什么要重排
#
# 原来的布局是按「文件类型」堆的：61 个音频全平铺在 out/ 下，靠文件名前缀
# [设计]/[克隆] 区分；而音色的**参考音**（克隆的根，删了音色就废）躺在
# assets/temp/ 里 —— 一个叫 temp 的目录。
#
# 问题不是不好看，是**分不清哪些能删**：out/ 里既有随时可以重新生成的试听音，
# 也有发行用的成品；temp/ 听起来像缓存，实际是最不能丢的东西。
#
# ## 新布局按「删了会怎样」分三层
#
#   library/   删了就没了（参考音、音色元数据）→ 要备份
#   out/       删了重跑一遍就有（试听、草稿）  → 可随时清理
#   publish/   平台规定的结构（Audio/歌词/Cover）→ 换平台时只动这一层
#
# ## 安全
#
# **只复制，不删除。** 迁移完跑校验（比 md5），确认新位置的文件和原来逐字节
# 一致之后，旧目录仍然原样留着 —— 由人来决定什么时候清理。
#
# 用法：
#   ./scripts/migrate-layout.sh          # 执行迁移
#   ./scripts/migrate-layout.sh --check  # 只校验，不动文件

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

log() { echo "  $*"; }

# ── 新目录骨架 ──
mk_dirs() {
  mkdir -p library/voices library/presets
  mkdir -p out/clone out/design out/music
  mkdir -p publish
}

# 从 [设计]xxx_20260830_200158.wav 里取日期段（20260830），取不到就用 misc
date_of() {
  local base; base="$(basename "$1")"
  local d; d="$(echo "$base" | grep -oE '[0-9]{8}_[0-9]{6}' | head -1 | cut -d_ -f1)"
  echo "${d:-misc}"
}

migrate() {
  mk_dirs

  # ① 音色的参考音 → library/voices/<音色名>/reference.wav
  #    这是最重要的一步：参考音是克隆的根，从 assets/temp 这种一看就像
  #    缓存的地方搬到 library 下，避免哪天有人清 temp 把音色清没了。
  log "① 音色参考音"
  if [ -d assets/temp ]; then
    for f in assets/temp/当前参考_*.wav; do
      [ -f "$f" ] || continue
      local name; name="$(basename "$f" .wav)"; name="${name#当前参考_}"
      mkdir -p "library/voices/$name"
      cp -n "$f" "library/voices/$name/reference.wav" 2>/dev/null || true
      log "   $name ← $(basename "$f")"
    done
  fi

  # ② out/ 下的产出按「设计 / 克隆」+ 日期归档
  log "② 产出音频按类型和日期归档"
  local n_design=0 n_clone=0 n_other=0
  for f in out/*.wav out/*.mp3 out/*.m4a; do
    [ -f "$f" ] || continue
    local base; base="$(basename "$f")"
    local day; day="$(date_of "$f")"
    case "$base" in
      \[设计\]*) mkdir -p "out/design/$day"; cp -n "$f" "out/design/$day/$base" && n_design=$((n_design+1)) ;;
      \[克隆\]*) mkdir -p "out/clone/$day";  cp -n "$f" "out/clone/$day/$base"  && n_clone=$((n_clone+1)) ;;
      *)         mkdir -p "out/music";       cp -n "$f" "out/music/$base"       && n_other=$((n_other+1)) ;;
    esac
  done
  log "   设计 $n_design 个 / 克隆 $n_clone 个 / 其它 $n_other 个"

  # ③ 发行物料：out/publish/ → publish/
  #    平台要的结构（Audio/歌词/Cover）整体搬，不拆
  log "③ 发行物料"
  if [ -d out/publish ]; then
    cp -Rn out/publish/* publish/ 2>/dev/null || true
    log "   $(ls publish 2>/dev/null | wc -l | tr -d ' ') 个发行批次"
  fi

  # ④ 预设配方
  if [ -d configs/presets ]; then
    cp -Rn configs/presets/* library/presets/ 2>/dev/null || true
    log "④ 预设配方 $(ls library/presets 2>/dev/null | wc -l | tr -d ' ') 个"
  fi
}

# ── 校验：新位置的每个文件都要能在旧位置找到同 md5 的对应物 ──
check() {
  local missing=0 total=0
  while read -r sum path; do
    [ -f "$path" ] || continue
    total=$((total+1))
    # 在新目录里找同 md5 的文件
    if ! find library out publish -type f 2>/dev/null | while read -r nf; do
        [ "$(md5 -q "$nf" 2>/dev/null)" = "$sum" ] && echo found && break
      done | grep -q found; then
      echo "  ✗ 没迁过去: $path"
      missing=$((missing+1))
    fi
  done < /tmp/vox-migrate/before.txt
  echo
  if [ "$missing" = 0 ]; then
    echo "  ✅ 校验通过：$total 个文件都能在新位置找到内容一致的副本"
    echo "     旧目录仍然保留 —— 确认无误后你自己决定什么时候清理"
  else
    echo "  ❌ $missing 个文件没迁过去，先别清理旧目录"
    return 1
  fi
}

case "${1:-}" in
  --check) check ;;
  *) migrate; echo; check ;;
esac
