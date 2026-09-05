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
    # 提取当前版本号到下一个版本号之间的内容
    RELEASE_NOTES=$(sed -n "/## \[$VERSION\]/,/## \[/p" "$CHANGELOG_FILE" | sed '$d')
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
if [ -f "./.venv/bin/python" ]; then
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

echo "=========================================================================="
echo "✨ v$VERSION has been successfully packaged and tagged with changelog! ✨"
