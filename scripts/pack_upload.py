#!/usr/bin/env python3
"""
把一首歌的上传物料归到一个文件夹，人能直接拖进平台。

    .venv/bin/python scripts/pack_upload.py [歌名...]
    不带参数 = 所有备料齐了的曲目

## 为什么需要它

音频在 `out/music/`，封面在 `library/covers/museav/` 且**文件名是哈希**
（`d5217f476aa6_1440.jpg`）—— 人要手动上传时，根本找不到哪张图配哪首歌。
自动填表能跑通的时候无所谓，跑不通就得手工，那时候这个目录就是救命的。

产出：`~/.voxflow/out/待上传/<发行歌名>/` 下面放
  歌名.mp3 / 歌名_封面.jpg / 上传信息.txt
一个文件夹拖完，不用在两个目录之间找。
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import pipeline  # noqa: E402
from core.paths import ARTIST_FILE, DATA_DIR, OUT_DIR  # noqa: E402

DEST_ROOT = OUT_DIR / "待上传"


def pack(track: dict) -> Path | None:
    name = track.get("release_title") or track.get("title") or track["id"][:8]
    audio = DATA_DIR / (track.get("audio_file") or "")
    if not audio.is_file():
        print(f"  ✗ {name}：没有音频文件")
        return None
    d = DEST_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio, d / f"{name}{audio.suffix}")

    cover = Path(track.get("cover_file") or "")
    if cover.is_file():
        shutil.copy2(cover, d / f"{name}_封面{cover.suffix}")

    try:
        artist = json.loads(ARTIST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        artist = {}
    roles = artist.get("roles") or {}
    dur = int(track.get("duration") or 0)
    info = (track.get("platforms") or {}).get("qishui") or {}
    lines = [
        f"歌曲标题：{name}",
        f"时长：{dur // 60}:{dur % 60:02d}",
        f"表演者 / 词作者 / 曲作者 / 制作人：{roles.get('performer') or artist.get('stage_name','')}",
        f"专辑名称：{info.get('album') or track.get('album_desc','')}",
        f"专辑歌手：{roles.get('album_artist') or artist.get('stage_name','')}",
        f"是否是纯音乐：{'是' if (track.get('lyrics') or '').strip().lower() in ('', '[instrumental]') else '否'}",
        f"歌词：{track.get('lyrics') or '[Instrumental]'}",
        "AI 创作声明：是（使用的AI工具：Suno）",
        "音乐类型：原创",
        "",
        "── 第二步 · 授权作品 ──",
        # 真实姓名不能用艺名。版权登记和收益结算按法律姓名走，
        # 填成艺名会在结算时对不上人。
        f"词作者真实姓名：{artist.get('real_name','')}",
        f"曲作者真实姓名：{artist.get('real_name','')}",
        "授权比例：100%",
    ]
    (d / "上传信息.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ {name} → {d}")
    return d


def main() -> int:
    want = set(sys.argv[1:])
    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    n = 0
    for t in pipeline.list_tracks():
        name = t.get("release_title") or t.get("title") or ""
        if want and name not in want:
            continue
        if not want:
            r = pipeline.readiness(t["id"], "qishui")
            if not r.get("ok"):
                continue
        if pack(t):
            n += 1
    print(f"\n打包 {n} 首 → {DEST_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
