#!/bin/bash
set -e

# --- 核心配置 ---
PROJECT_NAME="voxflow"
VERSION=$(grep -m 1 'version =' pyproject.toml | cut -d '"' -f 2)
CHANGELOG_FILE="CHANGELOG.md"

echo "🏔️ Starting Release Process for $PROJECT_NAME v$VERSION..."
echo "=========================================================================="

# 1. 检查 Git 状态
if [[ -n $(git status -s) ]]; then
    echo "❌ Error: Working directory is not clean. Please commit your changes first."
    exit 1
fi

# 2. 提取当前版本的更新日志
echo "📝 Extracting release notes from $CHANGELOG_FILE..."
if [ -f "$CHANGELOG_FILE" ]; then
    # ⚠️ 两个模式都必须锚定行首（^）。
    #
    # 原来写的是 `/## \[$VERSION\]/,/## \[/` —— 没锚定，于是 sed 会在**正文里**
    # 任何含 `## [` 的行提前结束范围。2026-09-14 实际踩到：0.10.0 的正文里有一句
    # 「`release.sh` 正是从 pyproject 取版本号再找 `## [x.y.z]`」，发版说明就在
    # 那里被拦腰截断（228 行 vs 完整 233 行），末尾停在半句话上。
    #
    # 顺带去掉尾部残留的空行和分隔线 —— 上面 sed '$d' 删掉的是下一个版本的
    # 标题行，但标题前那行 `---` 会留下来，挂在发版说明末尾很难看。
    RELEASE_NOTES=$(awk -v v="$VERSION" '
        $0 ~ "^## \\[" v "\\]" { f = 1 }
        f && $0 ~ "^## \\[" && $0 !~ "^## \\[" v "\\]" { exit }
        f { lines[++n] = $0 }
        END {
            while (n > 0 && (lines[n] ~ /^[[:space:]]*$/ || lines[n] ~ /^---[[:space:]]*$/)) n--
            for (i = 1; i <= n; i++) print lines[i]
        }
    ' "$CHANGELOG_FILE")
else
    RELEASE_NOTES="Release version $VERSION of VoxFlow."
fi

# 3. 自动打标 (Tag)
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "⚠️ Warning: Tag v$VERSION already exists. Skipping tagging."
else
    echo "🏷️ Creating Git Tag: v$VERSION..."
    git tag -a "v$VERSION" -m "Release v$VERSION"
    git push origin "v$VERSION"
fi

# 4. 清理并构建
echo "🧹 Cleaning old builds..."
rm -rf dist/ build/ *.egg-info/

echo "📦 Building source and wheel packages..."
# ⚠️ 别用 `python -m build`：mlx-whisper 的 wheel 打包错了 —— 里面套了三层
# `build/lib/build/lib/build/lib/mlx_whisper/...`，装进 venv 后 site-packages
# 里会多出一个杂散的 `build/` **命名空间包**。于是 `import build` 解析到它，
# `python -m build` 报 `No module named build.__main__`（2026-09-14 实际发生过）。
#
# uv build 在隔离的构建环境里跑，不受 venv 的 site-packages 污染影响；
# uv.lock 也说明 uv 本来就是本项目的工具。找不到 uv 才回落到 pip 的 build。
if command -v uv &> /dev/null; then
    uv build
elif [ -f "./.venv/bin/python" ]; then
    ./.venv/bin/python -m build
else
    python3 -m build
fi

# 5. 发布到 GitHub (使用提取的更新日志)
if command -v gh &> /dev/null; then
    echo "🚀 Creating GitHub Release..."
    echo "$RELEASE_NOTES" > temp_notes.md
    gh release create "v$VERSION" dist/* --title "VoxFlow v$VERSION" --notes-file temp_notes.md
    rm temp_notes.md
else
    echo "⚠️ Warning: gh CLI not found. Please manually upload the files in dist/ to GitHub."
fi

# 6. 推群：版本更新
#
# notify.release() 早就写好了，但**从来没有任何地方调用它** —— 于是
# 「这个 app 更新了什么」这一类通知一次都没发出去过。群里只看得到
# 音乐进度，看不到工具本身在往哪走。
#
# 通知失败不能让发版失败：包也打了、tag 也推了，这只是广播。
echo "📣 Pushing release note to Lark..."
.venv/bin/python - "$VERSION" <<'PYEOF' || echo "⚠️ 群通知失败（不影响发版）"
import re, sys
from pathlib import Path
from core import notify

version = sys.argv[1]
text = Path("CHANGELOG.md").read_text(encoding="utf-8")
m = re.search(rf"## \[{re.escape(version)}\][^\n]*\n(.*?)(?=\n## \[|\Z)", text, re.S)
body = (m.group(1) if m else "").strip()
# 只取小标题当要点 —— 整段 changelog 推到群里没人看，标题才是「更新了什么」
points = [ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("### ")]
if not points:
    points = [ln.strip("- ").strip() for ln in body.splitlines() if ln.startswith("- ")][:6]
ok = notify.release(version, "VoxFlow 声流", points[:8],
                    link="https://github.com/webkubor/voxflow/releases/tag/v" + version)
print("  送达" if ok else "  未送达")
PYEOF

echo "=========================================================================="
echo "✨ v$VERSION has been successfully packaged and tagged with changelog! ✨"
