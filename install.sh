#!/bin/bash
set -e

# ════════════════════════════════════════════════════════════
#  VoxFlow 声流 — 安装脚本
#  用法:
#    ./install.sh              交互模式（人类使用）
#    ./install.sh --yes        无交互模式（Agent / CI/CD）
#    ./install.sh --yes --skip-models   跳过模型下载
# ════════════════════════════════════════════════════════════

# ── 参数解析 ──
NON_INTERACTIVE=false
SKIP_MODELS=false
SKIP_VOICE_DESIGN=false

for arg in "$@"; do
  case $arg in
    --yes|-y|--non-interactive)
      NON_INTERACTIVE=true
      shift
      ;;
    --skip-models)
      SKIP_MODELS=true
      shift
      ;;
    --skip-voice-design)
      SKIP_VOICE_DESIGN=true
      shift
      ;;
    --help|-h)
      echo "用法: ./install.sh [--yes] [--skip-models] [--skip-voice-design]"
      echo ""
      echo "选项:"
      echo "  --yes, -y, --non-interactive   无交互模式，跳过所有确认提示（Agent / CI/CD）"
      echo "  --skip-models                  跳过模型下载（仅安装依赖）"
      echo "  --skip-voice-design            跳过 VoiceDesign 模型下载（仅下载 Base）"
      exit 0
      ;;
    *)
      echo "未知参数: $arg（使用 --help 查看帮助）"
      ;;
  esac
done

echo "🎙️  VoxFlow 声流 安装向导 🎙️"
echo "=========================================================================="
if [ "$NON_INTERACTIVE" = true ]; then
  echo "[非交互模式] 跳过所有确认，全自动安装"
  echo ""
fi

# ── 1. 检查 Python ──
if ! command -v python3 &> /dev/null; then
  echo "❌ 未找到 Python3，请先安装 Python 3.10+"
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PY_VERSION"

# ── 2. 检查 FFmpeg ──
if ! command -v ffmpeg &> /dev/null; then
  echo "⚠️  未找到 FFmpeg，处理 MP3 和自动裁剪功能需要它"
  echo "   macOS: brew install ffmpeg"
  if [ "$NON_INTERACTIVE" = false ]; then
    read -p "继续安装？（y/N）" confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
      echo "已取消"
      exit 0
    fi
  fi
else
  echo "✓ FFmpeg 已安装"
fi

# ── 3. 创建虚拟环境 ──
if [ -d ".venv" ]; then
  echo "✓ .venv 已存在，跳过创建"
else
  echo "→ 创建虚拟环境 (.venv)..."
  python3 -m venv .venv
fi

# ── 4. 激活 ──
echo "→ 激活虚拟环境..."
source .venv/bin/activate

# ── 5. 安装依赖 ──
echo "→ 升级 pip 和 setuptools..."
pip install --upgrade pip
pip install "setuptools<70"

echo "→ 安装项目依赖..."
pip install -e .
pip install pydub modelscope

echo "✓ 依赖安装完成"

# ── 6. 下载模型 ──
if [ "$SKIP_MODELS" = true ]; then
  echo ""
  echo "[跳过模型下载] 如需下载模型，请手动运行:"
  echo "  python -m modelscope.cli.cli download --model Qwen/Qwen3-TTS-12Hz-1.7B-Base --local_dir ./models/Base-1.7B"
  echo "  python -m modelscope.cli.cli download --model Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local_dir ./models/VoiceDesign-1.7B"
else
  # Base 模型（克隆合成必需）
  if [ -d "models/Base-1.7B" ] && [ "$(ls -A models/Base-1.7B/ 2>/dev/null)" ]; then
    echo "✓ Base-1.7B 模型已存在，跳过下载"
  else
    echo "→ 下载 Base-1.7B 模型 (~4.2GB)..."
    python -m modelscope.cli.cli download --model Qwen/Qwen3-TTS-12Hz-1.7B-Base --local_dir ./models/Base-1.7B
    echo "✓ Base-1.7B 下载完成"
  fi

  # VoiceDesign 模型（音色设计）
  if [ "$SKIP_VOICE_DESIGN" = false ]; then
    if [ -d "models/VoiceDesign-1.7B" ] && [ "$(ls -A models/VoiceDesign-1.7B/ 2>/dev/null)" ]; then
      echo "✓ VoiceDesign-1.7B 模型已存在，跳过下载"
    else
      if [ "$NON_INTERACTIVE" = true ]; then
        echo "→ 下载 VoiceDesign-1.7B 模型 (~4.2GB)..."
        python -m modelscope.cli.cli download --model Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local_dir ./models/VoiceDesign-1.7B
        echo "✓ VoiceDesign-1.7B 下载完成"
      else
        read -p "是否下载 VoiceDesign 模型？（用于音色设计，~4.2GB）(y/N) " vd_confirm
        if [ "$vd_confirm" = "y" ] || [ "$vd_confirm" = "Y" ]; then
          echo "→ 下载 VoiceDesign-1.7B 模型..."
          python -m modelscope.cli.cli download --model Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local_dir ./models/VoiceDesign-1.7B
          echo "✓ VoiceDesign-1.7B 下载完成"
        else
          echo "[跳过 VoiceDesign] 如需音色设计功能，请后续手动下载"
        fi
      fi
    fi
  else
    echo "[跳过 VoiceDesign 模型]"
  fi
fi

# ── 7. 创建必要目录 ──
mkdir -p assets/temp assets/reference_audio out configs/presets

# ── 8. 运行环境自检 ──
echo ""
echo "→ 运行环境自检..."
python -m cli.app doctor || true

# ── 9. 前端构建 ──
if command -v npm &> /dev/null; then
  echo ""
  echo "→ 检测到 Node.js/npm，开始构建前端 Web UI..."
  cd web/ui
  npm install
  npm run build
  cd ../..
  echo "✓ 前端 UI 构建完成"
else
  echo ""
  echo "⚠️  未检测到 Node.js / npm，跳过前端 UI 构建。"
  echo "   若后续需要修改或重新生成前端，请先安装 Node.js，并在 web/ui 目录下执行 npm install && npm run build"
fi

# ── 完成 ──
echo ""
echo "=========================================================================="
echo "✨ 安装完成！"
echo ""
echo "快速开始:"
echo "  source .venv/bin/activate"
echo "  voice --help          # 查看所有命令"
echo "  voice doctor          # 环境自检"
echo "  voice web             # 启动 Web UI → http://localhost:8866"
echo "=========================================================================="
