#!/usr/bin/env python3
"""
生成品牌社交横幅（OG 图）—— assets/branding/social-banner.png。

    .venv/bin/python scripts/make_social_banner.py

## 为什么程序化生成而不是 AI 出图

横幅上要写字（品牌名 + 一句定位），AI 生成文字不可控（错字、变形）。
程序化合成文字精确、风格跟主题色一致，改文案改一次脚本重跑即可。

## 视觉

- 1200×630（OG 标准尺寸）
- 深色渐变底（#16161a → #0e0e11），主色 #818cf8 做辉光和装饰声波柱
- 左侧 logo 图标 + 右侧品牌名/定位文案
- 声波柱装饰呼应 logo 的「低-升-顿-推到顶-收」曲线
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND_DIR = Path(__file__).resolve().parent.parent / "assets" / "branding"
OUT = BRAND_DIR / "social-banner.png"

W, H = 1200, 630
PRIMARY = "#818cf8"
PRIMARY_DARK = "#6366f1"
LIGHT = "#a5b4fc"
TEXT_1 = "#ece8e1"
TEXT_2 = "#9a958d"
BG_TOP = "#16161a"
BG_BOTTOM = "#0e0e11"

HELV = "/System/Library/Fonts/Helvetica.ttc"
HEITI = "/System/Library/Fonts/STHeiti Medium.ttc"

# 声波柱曲线（与 logo.svg 注释里的「低-升-顿-推到顶-收」呼应）
WAVE = [0.30, 0.45, 0.62, 0.52, 0.88, 0.70, 0.95, 0.60, 0.40, 0.55, 0.35, 0.22]


def lerp(a: str, b: str, t: float) -> str:
    ca, cb = a.lstrip("#"), b.lstrip("#")
    r = [int(ca[i:i+2], 16) + (int(cb[i:i+2], 16) - int(ca[i:i+2], 16)) * t for i in (0, 2, 4)]
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in r)


def main() -> None:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)

    # ── 背景：对角渐变 + 品牌辉光 ──
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=lerp(BG_TOP, BG_BOTTOM, t))

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(560, 220, -8):
        a = int(26 * (1 - (560 - r) / 340))
        gd.ellipse([80 - r, H/2 - r + 80, 80 + r, H/2 + r + 80], fill=(129, 140, 248, a))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    d = ImageDraw.Draw(img)

    # ── 左侧 logo ──
    logo = Image.open(BRAND_DIR / "logo-icon.png").convert("RGBA").resize((176, 176), Image.LANCZOS)
    img.alpha_composite(logo, (64, (H - 176) // 2))

    # ── 右侧文案 ──
    f_title_latin = ImageFont.truetype(HELV, 84)
    f_title_cn = ImageFont.truetype(HEITI, 84)
    f_sub = ImageFont.truetype(HEITI, 34)
    f_meta = ImageFont.truetype(HELV, 26)

    x0 = 64 + 176 + 56          # 文案左起点
    # VoxFlow（Helvetica 粗体感：用大小写错落 + 主色）
    d.text((x0, 200), "VoxFlow", font=f_title_latin, fill=TEXT_1)
    w = d.textlength("VoxFlow", font=f_title_latin)
    d.text((x0 + w + 24, 200), "声流", font=f_title_cn, fill=PRIMARY)

    # 副标题
    d.text((x0 + 4, 318), "本地中文语音克隆 · 音色设计 · 全网音乐发行",
           font=f_sub, fill=TEXT_2)

    # 底部 meta
    d.text((x0 + 4, 540), "VoxFlow v0.3.0  ·  声流工作台", font=f_meta, fill=TEXT_2)

    # ── 底部声波柱装饰（横贯右侧，呼应 logo 曲线）──
    bar_h = 90
    bar_w = 16
    gap = 10
    x = 320
    y_base = 490
    for i, f in enumerate(WAVE):
        h = max(14, int(bar_h * f))
        d.rounded_rectangle([x, y_base - h, x + bar_w, y_base], radius=5,
                            fill=PRIMARY if i in (4, 6) else LIGHT)
        x += bar_w + gap

    img.convert("RGB").save(OUT, "PNG")
    print(f"✓ {OUT}  ({W}×{H})")


if __name__ == "__main__":
    main()
