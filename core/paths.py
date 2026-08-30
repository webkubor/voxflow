"""
路径真源 —— 代码在哪、数据在哪，全项目只在这里定义一次。

## 为什么要把数据挪出项目目录

之前代码和数据混在同一个目录，`BASE_DIR` 一个变量同时当「代码根」和「数据根」。
后果很实在：**换个目录 clone、或者 git clean 一下，音色和歌就没了**。
工具升级、重装、切分支，都在拿资产冒险。

而这两类东西的性质完全相反：

| | 代码 | 数据 |
|---|---|---|
| 来源 | `git clone` 随时能拿 | 录一次、生成一次，没了就没了 |
| 版本 | 应该跟着升级 | 应该跨版本继承 |
| 备份 | git 就是备份 | 需要单独备份（R2） |

所以分开：代码在项目目录，数据在 `~/.voxflow/`（可用 `VOXFLOW_HOME` 覆盖）。
工具怎么升级、装几个副本、clone 到哪，数据都在原地。

模型也放数据目录 —— 8.4 GB，重装工具不该重下一遍。

## 迁移

`scripts/migrate-to-home.sh` 把已有数据搬过去。同磁盘用 mv，瞬间完成，
不占双倍空间。搬完项目目录里只剩代码。
"""

from __future__ import annotations

import os
from pathlib import Path

# 代码根：这个文件在 <项目>/core/paths.py
PROJECT_DIR = Path(__file__).resolve().parent.parent

# 数据根：默认 ~/.voxflow。
# VOXFLOW_HOME 可以覆盖 —— 测试要隔离数据、或者想把数据放到外置盘时用得上。
DATA_DIR = Path(os.environ.get("VOXFLOW_HOME") or (Path.home() / ".voxflow")).expanduser()

# ── 数据（跨版本继承，不进 git）──────────────────────────
CONFIG_DIR = DATA_DIR / "configs"          # 台账、音色库、艺人档案
ASSETS_DIR = DATA_DIR / "assets"           # 参考录音：不可再生
TEMP_DIR = ASSETS_DIR / "temp"             # 当前参考样音
REF_DIR = ASSETS_DIR / "reference_audio"   # 原始录音素材
OUT_DIR = DATA_DIR / "out"                 # 合成产物：可再生
MUSIC_DIR = OUT_DIR / "music"              # Suno 下载的歌
PUBLISH_DIR = DATA_DIR / "publish"         # 发布物料：平台规定的结构
DESIGNS_DIR = DATA_DIR / "voice_designs"   # 音色设计配方
MODELS_DIR = DATA_DIR / "models"           # TTS 模型：8.4 GB，重装不该重下

PERSONAS_FILE = CONFIG_DIR / "personas.json"
SCRIPTS_FILE = CONFIG_DIR / "scripts.json"
LEDGER_FILE = CONFIG_DIR / "pipeline.json"
ARTIST_FILE = CONFIG_DIR / "artist.json"
PUBLISH_ACCOUNTS_FILE = CONFIG_DIR / "publish_accounts.json"
PLATFORM_ACCOUNTS_FILE = CONFIG_DIR / "platform_accounts.json"   # 各平台账号与已发布曲目

# ── 代码自带的资源（跟着版本走，进 git）──────────────────
PLATFORMS_FILE = PROJECT_DIR / "configs" / "platforms.json"   # 平台 SOP
TEMPLATES_DIR = PROJECT_DIR / "publish" / "templates"          # Excel 模板
BRANDING_DIR = PROJECT_DIR / "assets" / "branding"             # logo


def ensure_dirs() -> None:
    """建齐数据目录。每次启动跑一次，成本可忽略。"""
    for d in (CONFIG_DIR, TEMP_DIR, REF_DIR, MUSIC_DIR, PUBLISH_DIR, DESIGNS_DIR, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def needs_migration() -> bool:
    """
    项目目录里还留着老数据吗。

    判据是「有没有真的数据」，不是「目录存不存在」—— 项目里
    configs/platforms.json 是代码的一部分，它在不代表没迁移。
    """
    legacy_ledger = PROJECT_DIR / "configs" / "pipeline.json"
    legacy_personas = PROJECT_DIR / "configs" / "personas.json"
    legacy_music = PROJECT_DIR / "out" / "music"
    return (
        legacy_ledger.exists()
        or legacy_personas.exists()
        or (legacy_music.is_dir() and any(legacy_music.iterdir()))
    )


def find_config(name: str) -> Path:
    """
    找一份配置：**先看你的数据目录，没有再用项目自带的模板**。

    这一层回落是分家之后必须有的。数据搬到 ~/.voxflow 之后，
    像 design.json / dialogue.json / presets 这些「代码自带的模板」
    还留在项目里（它们跟着版本升级走），如果只认数据目录就全读不到了。

    有了回落，两边各司其职：
    - 升级工具 → 模板跟着更新，你没改过的自动吃到新版
    - 你改过的 → 落在 ~/.voxflow/configs，盖住模板，升级不会被冲掉

    这也是「版本升级不影响个人数据、个人数据不进仓库」这句话的实现方式。
    """
    user_copy = CONFIG_DIR / name
    if user_copy.exists():
        return user_copy
    return PROJECT_DIR / "configs" / name


def config_search_dirs() -> list[Path]:
    """配置查找顺序：你的 > 项目自带。目录级查找用它（比如 presets/）。"""
    return [CONFIG_DIR, PROJECT_DIR / "configs"]
