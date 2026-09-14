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
# huggingface_hub[cli] 提供 `hf` 命令 —— 下模型用它。
# 2026-09-14 迁 MLX 前用的是 modelscope（下 PyTorch 原生权重），现在不用了。
pip install pydub "huggingface_hub[cli]"

# ── 推理引擎 mlx-audio（要绕开依赖声明，原因见下）──
#
# mlx-audio 0.5.3 声明 transformers>=5.14.0，而本项目锁 transformers==4.57.3
# （随仓库自带的 qwen_tts 参考实现需要）。不绕过的话 pip 只有两条路：
#   ① 把 transformers 顶到 5.x —— 实测 CLI 直接死在
#      ImportError: cannot import name 'hf_api' from 'transformers.utils'
#   ② 静默降级到 mlx-audio 0.2.9 —— 那版没有 load_model / generate(ref_text=)，
#      装完能 import、一合成才炸，是最难查的那种
# 实测 0.5.3 在 transformers 4.57.3 上跑得通（端到端合成 + 全部入口 import 通过），
# 所以这里显式绕过声明，把真正需要的运行时依赖单独装上。
#
# ⚠️ 这是**已知的依赖冲突**，不是干净解法。等上游放宽约束、或本项目升级
# transformers 之后，应改回普通的 pip install。见 docs/MLX_MIGRATION.md。
pip install --no-deps "mlx-audio==0.5.3"
pip install miniaudio scipy sounddevice tqdm

echo "✓ 依赖安装完成"

# ── 6. 下载模型 ──
#
# ⚠️ 下的是 **MLX 8-bit 权重**（mlx-community），不是 Qwen 原生的 PyTorch 权重。
# 2026-09-14 起运行时只加载 models-mlx/，PyTorch 那套（~/.voxflow/models/，8.4 GB）
# 不再被任何代码读取 —— 这里一度还在下它，新用户会拿到一份完全用不上的 8.4 GB，
# 而界面照样报「模型未就绪」。迁移时漏改的就是这一段。
#
# 真源是 core/paths.py 的 MODELS_MLX_DIR。之前这里写死 ./models/，而运行时去
# ~/.voxflow/models-mlx 找 —— 新用户老老实实跑完 install.sh、下了 4 GB，
# 打开界面还是「模型未就绪」，而且完全看不出为什么。这是数据从项目目录
# 搬到 ~/.voxflow 那次改造漏改的地方（paths.py 里详细写了为什么要搬）。
#
# 直接问 Python 要路径，不在这里重新拼一遍 —— 拼第二遍就会有第二次对不上。
VOXFLOW_MODELS_DIR=$(.venv/bin/python -c "from core.paths import MODELS_MLX_DIR; print(MODELS_MLX_DIR)")
mkdir -p "$VOXFLOW_MODELS_DIR"
echo "→ 模型目录: $VOXFLOW_MODELS_DIR"

# 老版本可能把模型下在项目目录里，搬过去而不是重下 —— 2.9 GB 重下一遍
# 是最没必要的等待。同磁盘 mv 是瞬间完成的。
for _m in Base-1.7B-8bit VoiceDesign-1.7B-8bit; do
  if [ -d "models-mlx/$_m" ] && [ -n "$(ls -A "models-mlx/$_m" 2>/dev/null)" ] \
     && [ ! -d "$VOXFLOW_MODELS_DIR/$_m" ]; then
    echo "→ 发现项目目录里的旧模型 $_m，搬到数据目录（不重下）..."
    mv "models-mlx/$_m" "$VOXFLOW_MODELS_DIR/$_m"
    echo "✓ $_m 已搬到 $VOXFLOW_MODELS_DIR/$_m"
  fi
done

# hf 来自 huggingface_hub[cli]，上面刚装过。找不到就说人话 ——
# 等到「模型下载失败」才让用户猜原因，是最没必要的一步。
if ! command -v hf > /dev/null 2>&1; then
  echo "⚠️ 找不到 hf 命令（huggingface_hub[cli] 没装上？）"
  echo "   已跳过模型下载；装好后手动跑下面两条命令即可。"
  SKIP_MODELS=true
fi

_BASE_REPO=mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit
_VD_REPO=mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit

if [ "$SKIP_MODELS" = true ]; then
  echo ""
  echo "[跳过模型下载] 如需下载模型，请手动运行:"
  echo "  hf download $_BASE_REPO --local-dir $VOXFLOW_MODELS_DIR/Base-1.7B-8bit"
  echo "  hf download $_VD_REPO --local-dir $VOXFLOW_MODELS_DIR/VoiceDesign-1.7B-8bit"
else
  # Base 模型（克隆合成必需）
  if [ -d "$VOXFLOW_MODELS_DIR/Base-1.7B-8bit" ] && [ "$(ls -A "$VOXFLOW_MODELS_DIR/Base-1.7B-8bit/" 2>/dev/null)" ]; then
    echo "✓ Base-1.7B-8bit 模型已存在，跳过下载"
  else
    echo "→ 下载 Base-1.7B-8bit 模型 (~2.9GB)..."
    hf download "$_BASE_REPO" --local-dir "$VOXFLOW_MODELS_DIR/Base-1.7B-8bit"
    echo "✓ Base-1.7B-8bit 下载完成"
  fi

  # VoiceDesign 模型（音色设计）
  if [ "$SKIP_VOICE_DESIGN" = false ]; then
    if [ -d "$VOXFLOW_MODELS_DIR/VoiceDesign-1.7B-8bit" ] && [ "$(ls -A "$VOXFLOW_MODELS_DIR/VoiceDesign-1.7B-8bit/" 2>/dev/null)" ]; then
      echo "✓ VoiceDesign-1.7B-8bit 模型已存在，跳过下载"
    else
      if [ "$NON_INTERACTIVE" = true ]; then
        echo "→ 下载 VoiceDesign-1.7B-8bit 模型 (~2.9GB)..."
        hf download "$_VD_REPO" --local-dir "$VOXFLOW_MODELS_DIR/VoiceDesign-1.7B-8bit"
        echo "✓ VoiceDesign-1.7B-8bit 下载完成"
      else
        read -p "是否下载 VoiceDesign 模型？（用于音色设计，~2.9GB）(y/N) " vd_confirm
        if [ "$vd_confirm" = "y" ] || [ "$vd_confirm" = "Y" ]; then
          echo "→ 下载 VoiceDesign-1.7B-8bit 模型..."
          hf download "$_VD_REPO" --local-dir "$VOXFLOW_MODELS_DIR/VoiceDesign-1.7B-8bit"
          echo "✓ VoiceDesign-1.7B-8bit 下载完成"
        else
          echo "[跳过 VoiceDesign] 如需音色设计功能，请后续手动下载"
        fi
      fi
    fi
  else
    echo "[跳过 VoiceDesign 模型]"
  fi

  # 迁移前那套 PyTorch 模型（~/.voxflow/models/，8.4 GB）已经没有代码读它，
  # 只留着当回滚用。这里**只提示、不删** —— 删用户的文件得他自己决定。
  _LEGACY_DIR="$(dirname "$VOXFLOW_MODELS_DIR")/models"
  if [ -d "$_LEGACY_DIR" ]; then
    echo ""
    echo "提示：检测到迁移前的 PyTorch 模型（$_LEGACY_DIR，约 8.4 GB）。"
    echo "      现在没有功能读它；确认 MLX 版稳定后可以自行删除腾空间。"
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
