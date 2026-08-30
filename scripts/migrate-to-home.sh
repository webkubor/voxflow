#!/usr/bin/env bash
#
# 把数据从项目目录搬到 ~/.voxflow —— 让资产跨版本继承。
#
# ## 为什么
#
# 代码和数据混在一个目录时，换个目录 clone、git clean 一下，音色和歌就没了。
# 代码是 git clone 随时能拿的，数据录一次生成一次、没了就没了 —— 两者不该同生共死。
#
# ## 怎么搬
#
# 同一磁盘用 mv：**瞬间完成，不占双倍空间**（8.4 GB 的模型用 cp 要复制半天）。
# mv 不是删除 —— 文件还在，只是换了位置。
#
# 目标已存在的目录会跳过并提示，不覆盖、不合并 —— 宁可什么都不做，
# 也不能把两份数据搅在一起。
#
#   ./scripts/migrate-to-home.sh          看会搬什么（不动手）
#   ./scripts/migrate-to-home.sh --go     真的搬

set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="$PWD"
HOME_DIR="${VOXFLOW_HOME:-$HOME/.voxflow}"
GO="${1:-}"

# configs 要单独处理：platforms.json 是代码的一部分，留在项目里；
# 其余（台账、音色库、艺人档案）是数据，搬走。
DATA_DIRS=(assets out publish voice_designs models library)
# 留在项目里的是**代码自带的模板**（git 里有它们）：
#   platforms.json  平台 SOP
#   design/dialogue.json  合成配置模板
#   presets/  内置音色设计预设
#   README.md
# 搬走的是**你的数据**：音色库、作品台账、艺人档案、存的文案、平台账号
CONFIG_KEEP=(platforms.json design.json dialogue.json presets README.md)

echo "项目目录: $PROJECT"
echo "数据目录: $HOME_DIR"
[ "$GO" != "--go" ] && echo "（预演模式，加 --go 才真的搬）"
echo

move() {
  local src="$1" dst="$2"
  [ -e "$src" ] || return 0
  if [ -e "$dst" ]; then
    echo "  ⚠ 跳过 $(basename "$src") —— 目标已存在，不覆盖"
    return 0
  fi
  local size; size=$(du -sh "$src" 2>/dev/null | cut -f1)
  if [ "$GO" = "--go" ]; then
    mkdir -p "$(dirname "$dst")"
    mv "$src" "$dst"
    echo "  ✓ $(basename "$src")  $size"
  else
    echo "  · $(basename "$src")  $size  →  ${dst/#$HOME/\~}"
  fi
}

echo "整目录搬迁："
for d in "${DATA_DIRS[@]}"; do
  # assets/branding 是 logo 源文件，属于代码资源（进 git、跟着版本走），
  # 不能跟着 assets 一起搬 —— 搬走了项目里的 logo 就没了
  if [ "$d" = "assets" ] && [ -d "$PROJECT/assets/branding" ]; then
    if [ "$GO" = "--go" ]; then
      mkdir -p "$HOME_DIR/assets"
      for sub in "$PROJECT/assets"/*; do
        [ -e "$sub" ] || continue
        [ "$(basename "$sub")" = "branding" ] && continue
        move "$sub" "$HOME_DIR/assets/$(basename "$sub")"
      done
    else
      echo "  · assets/（branding 除外）  $(du -sh "$PROJECT/assets" 2>/dev/null | cut -f1)"
    fi
    continue
  fi
  # publish/templates 是代码资源，不能跟着 publish 一起走
  if [ "$d" = "publish" ] && [ -d "$PROJECT/publish/templates" ]; then
    if [ "$GO" = "--go" ]; then
      mkdir -p "$HOME_DIR/publish"
      for sub in "$PROJECT/publish"/*; do
        [ -e "$sub" ] || continue
        [ "$(basename "$sub")" = "templates" ] && continue
        move "$sub" "$HOME_DIR/publish/$(basename "$sub")"
      done
    else
      echo "  · publish/（templates 除外）  $(du -sh "$PROJECT/publish" 2>/dev/null | cut -f1)"
    fi
    continue
  fi
  move "$PROJECT/$d" "$HOME_DIR/$d"
done

echo
echo "configs（platforms.json 留在项目里，它是代码的一部分）："
if [ -d "$PROJECT/configs" ]; then
  for f in "$PROJECT/configs"/*; do
    [ -e "$f" ] || continue
    name=$(basename "$f")
    skip=false
    for k in "${CONFIG_KEEP[@]}"; do [ "$name" = "$k" ] && skip=true; done
    $skip && { echo "  留下 $name"; continue; }
    move "$f" "$HOME_DIR/configs/$name"
  done
fi

echo
if [ "$GO" = "--go" ]; then
  echo "✓ 搬完了。数据在 $HOME_DIR"
  echo "  项目目录现在只剩代码，可以随便 clone、切分支、重装。"
else
  echo "预演结束。确认没问题就跑：./scripts/migrate-to-home.sh --go"
fi
