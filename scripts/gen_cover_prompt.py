#!/usr/bin/env python3
"""
gen_cover_prompt.py — 按模板生成音乐封面提示词

从 templates/music-cover-prompt.md 读模板，按歌曲信息填占位符，
输出可直接喂给 museav gen 的完整 prompt。

绝不自动执行 museav gen —— 那是花钱操作，必须用户手动确认。

用法:
  # 直接传参
  ./scripts/gen_cover_prompt.py \
    --title 心脏跳动 --subtitle HEARTBEAT \
    --mood 治愈 --scene "城市天台" --time "傍晚蓝调时刻"

  # 用预设（覆盖同类信息）
  ./scripts/gen_cover_prompt.py --preset 治愈系傍晚 \
    --title 心脏跳动 --subtitle HEARTBEAT

  # 从 JSON 读（批量出图方便）
  ./scripts/gen_cover_prompt.py --json songs.json

  # 输出到文件
  ./scripts/gen_cover_prompt.py --preset 热血系正午 \
    --title 破晓 --subtitle DAWN --out prompts/破晓.txt

  # 顺便显示 museav gen 命令（不执行）
  ./scripts/gen_cover_prompt.py --preset 治愈系傍晚 \
    --title 心脏跳动 --show-museav-cmd
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "templates" / "music-cover-prompt.md"


# 场景预设 —— 跟模板里的「常用配置预设」一一对应
PRESETS: dict[str, dict] = {
    "治愈系傍晚": {
        "scene": "城市天台",
        "time_desc": "傍晚蓝调时刻",
        "light_type": "夕阳侧逆光",
        "light_dir": "画面右上方 30°",
        "color_palette": "蓝白为主 + 极少量暖粉橙点缀",
        "decoration": "画面左下到右下细线手绘波动曲线，象征音乐让心跳被感知",
        "style_reference": "滨田英明 家庭日记 / 上田义彦 静谧人像",
        "character": "年轻东亚女性（约 22-25 岁）",
        "clothing": "干净奶油白棉质 T 恤",
        "accessory": "白色头戴式耳机",
        "pose": "闭眼，长发被晚风自然吹向画面右侧",
        "expression": "嘴角微微上扬，像在微笑哼歌",
        "mood_state": "听歌入迷",
        "angle": "平视略仰拍 5°",
        "framing": "中景（腰部以上）",
        "light_effect": "发丝边缘金色轮廓光 + 皮肤通透保留肌理",
        "environment_detail": "天空中漂浮少量云被夕阳染成淡粉、奶橘色；远处建筑虚化为散景光斑",
        "title_font": "白色思源宋体 Bold",
        "subtitle_font": "白色 Helvetica Neue Light",
        "keywords_en": (
            "Japanese editorial photography, cinematic summer dusk, "
            "airy blue sky, soft golden hour, natural wind, candid portrait, "
            "white headphones, Kodak Portra 400, dreamy lens flare, "
            "35mm f/2 shallow depth of field, minimalist album artwork, "
            "youthful, emotional, clean composition"
        ),
    },
    "热血系正午": {
        "scene": "城市天台",
        "time_desc": "正午烈日",
        "light_type": "顶光强对比",
        "light_dir": "正上方",
        "color_palette": "高饱和红黄 + 黑色硬阴影",
        "decoration": "无装饰，纯人物 + 光影",
        "style_reference": "森山大道 街头摄影",
        "character": "年轻东亚男性（约 20-24 岁）",
        "clothing": "黑色宽松运动背心",
        "accessory": "无线入耳式耳机",
        "pose": "侧身站立，单手插兜，下巴微扬",
        "expression": "坚毅直视远方，嘴角微抿",
        "mood_state": "蓄势待发",
        "angle": "仰拍 10°",
        "framing": "全身",
        "light_effect": "硬阴影 + 高光区对比，皮肤强反差",
        "environment_detail": "天台边缘城市天际线，远处建筑清晰可见，热浪扭曲",
        "title_font": "白色思源黑体 Heavy",
        "subtitle_font": "白色 Impact",
        "keywords_en": (
            "urban street photography, harsh midday sun, "
            "high contrast black and yellow, athletic stance, "
            "tank top, sweaty skin, city skyline, "
            "Daido Moriyama style, bold typography, "
            "cinematic gritty, motivational"
        ),
    },
    "伤感深夜": {
        "scene": "深夜便利店门口",
        "time_desc": "深夜雨后 1 点",
        "light_type": "便利店霓虹散光",
        "light_dir": "画面左侧 60°",
        "color_palette": "冷蓝主调 + 远处暖色霓虹散景",
        "decoration": "无装饰，单人独处",
        "style_reference": "上田义彦 静谧人像 / 是枝裕和 电影剧照",
        "character": "年轻东亚女性（约 24 岁）",
        "clothing": "洗旧的灰色连帽卫衣",
        "accessory": "有线入耳式耳机",
        "pose": "坐在便利店门口台阶，单手托腮",
        "expression": "眼神放空，不聚焦",
        "mood_state": "独处沉思",
        "angle": "平视",
        "framing": "中景（膝盖以上）",
        "light_effect": "冷色皮肤保留纹理，霓虹在衣服上反射",
        "environment_detail": "便利店玻璃门透出冷白光，地面有雨后反光，远处街灯散景",
        "title_font": "白色思源宋体 Regular",
        "subtitle_font": "白色 Helvetica Neue Thin",
        "keywords_en": (
            "late night convenience store, neon ambient light, "
            "rainy night, lonely portrait, hoodie, earbuds, "
            "contemplative mood, Ueda Yoshihiko style, "
            "Koreeda film still, melancholic, quiet, "
            "cool blue with warm neon bokeh"
        ),
    },
    "抖音热门卡点": {
        "scene": "深夜 club",
        "time_desc": "午夜 12 点 club 高峰",
        "light_type": "频闪彩色光",
        "light_dir": "多向（频闪变化）",
        "color_palette": "黑底 + 霓虹粉/紫/青高频闪烁",
        "decoration": "音乐节拍点的频闪光斑 + 烟雾",
        "style_reference": "Tim Walker 时尚摄影 / Hypebeast 杂志封面",
        "character": "年轻东亚女性（约 20 岁）",
        "clothing": "反光银色短款上衣",
        "accessory": "镭射透明耳机",
        "pose": "动态瞬间，甩头长发飞扬",
        "expression": "闭眼，张嘴跟随节拍",
        "mood_state": "完全沉浸",
        "angle": "略仰拍 8°",
        "framing": "特写（胸部以上）",
        "light_effect": "霓虹粉紫在脸上流动，皮肤湿润反光",
        "environment_detail": "背景虚化的 club 灯墙，烟雾弥漫，低频震动感",
        "title_font": "白色 Montserrat Black",
        "subtitle_font": "白色 Impact",
        "keywords_en": (
            "nightclub photography, strobe light, "
            "neon pink purple cyan, dancing moment, "
            "hair flying, silver reflective clothing, "
            "Tim Walker style, Hypebeast aesthetic, "
            "festival energy, sweaty skin, motion blur"
        ),
    },
}


def load_template() -> tuple[str, str]:
    """读模板文件，返回 (正文模板, 用法说明)。"""
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    # 拆出正文部分（## 模板正文 到 ## 占位符说明 之间）
    if "## 模板正文" not in text:
        return text, ""
    body = text.split("## 模板正文", 1)[1]
    if "## 占位符说明" in body:
        body = body.split("## 占位符说明", 1)[0]
    # 去掉 markdown 代码块包裹
    body = body.strip()
    if body.startswith("```"):
        lines = body.split("\n")
        body = "\n".join(lines[1:-1]) if lines[-1].strip().startswith("```") else body
    return body.strip(), text


def fill_template(body: str, fields: dict) -> str:
    """替换模板里的 {占位符}，缺字段标 TODO。"""
    import re
    out_lines = []
    for line in body.split("\n"):
        # 处理一行可能含多个 {x}
        def replace(match):
            key = match.group(1)
            value = fields.get(key)
            if value:
                return str(value)
            return f"[TODO: 填 {key}]"
        out_lines.append(re.sub(r"\{(\w+)\}", replace, line))
    return "\n".join(out_lines)


def build_fields(args: argparse.Namespace) -> dict:
    """合并命令行参数 + preset 默认值。"""
    # preset 提供所有 24 个字段默认值
    fields: dict = {}
    if args.preset:
        if args.preset not in PRESETS:
            print(f"❌ 未知 preset: {args.preset}", file=sys.stderr)
            print(f"   可用: {', '.join(PRESETS.keys())}", file=sys.stderr)
            sys.exit(1)
        fields.update(PRESETS[args.preset])

    # 命令行覆盖（必填的先校验）
    if not args.title:
        print("❌ 缺 --title", file=sys.stderr)
        sys.exit(1)
    if not args.subtitle:
        # 英文标题自动从中文转大写拼音（极简 fallback）
        # 实际项目里建议手动指定，AI 转写会出错
        args.subtitle = args.title.upper()

    fields["title"] = args.title
    fields["subtitle"] = args.subtitle
    fields["platform"] = args.platform or "汽水音乐"
    if args.mood: fields["mood_state"] = args.mood
    if args.scene: fields["scene"] = args.scene
    if args.time: fields["time_desc"] = args.time

    # JSON 输入可以覆盖任意字段
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            override = json.load(f)
        fields.update(override)

    return fields


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按模板生成音乐封面提示词（不自动跑 museav gen）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--title", required=True, help="主标题中文")
    parser.add_argument("--subtitle", help="副标题英文（大写）")
    parser.add_argument("--platform", help="上架平台（默认汽水音乐）")
    parser.add_argument("--mood", help="情绪状态（覆盖 preset）")
    parser.add_argument("--scene", help="场景（覆盖 preset）")
    parser.add_argument("--time", help="时间（覆盖 preset）")
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        help="场景预设（治愈系傍晚 / 热血系正午 / 伤感深夜 / 抖音热门卡点）",
    )
    parser.add_argument("--json", help="从 JSON 文件读完整字段覆盖")
    parser.add_argument("--out", help="输出到文件，不指定则打印到 stdout")
    parser.add_argument(
        "--show-museav-cmd",
        action="store_true",
        help="打印 museav gen 命令（不执行），方便复制粘贴",
    )
    args = parser.parse_args()

    if not TEMPLATE_PATH.exists():
        print(f"❌ 模板不存在: {TEMPLATE_PATH}", file=sys.stderr)
        return 1

    body, full_doc = load_template()
    fields = build_fields(args)
    prompt = fill_template(body, fields)

    output = f"═══════ 封面提示词 · {args.title} ═══════\n\n{prompt}\n"

    if args.show_museav_cmd:
        output += (
            "\n═══════ museav gen 命令（不自动执行） ═══════\n"
            f"museav gen --prompt @- --size 3000x3000 --ratio 1:1\n"
            "\n  ↑ 把上面 prompt 复制粘贴，或：\n"
            f"  cat prompts/{args.title}.txt | museav gen --prompt @- --size 3000x3000\n"
            "\n⚠️  museav gen 花钱 —— 确认后再跑\n"
        )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"✅ 已写入 {out_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
