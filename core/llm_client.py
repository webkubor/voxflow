"""LLM 客户端 — 任何 OpenAI 兼容后端都能接，实现 AI 文案生成与润色

只依赖 OpenAI SDK 的协议本身，不绑定某一家服务。三个环境变量换后端：

    本地 FreeLLMAPI（默认）  需要 Docker 起一个容器在 localhost:3001
    自己的网关 / 中台        比如 museav：见项目根目录 run.sh

依赖:
    - pip install openai

配置:
    环境变量 VOXFLOW_LLM_BASE_URL (默认 http://localhost:3001/v1)
    环境变量 VOXFLOW_LLM_API_KEY  (默认 freellmapi-local)
    环境变量 VOXFLOW_LLM_MODEL    (默认 auto, 让路由器选模型)
"""

import os
import time
from typing import Optional

_default_base = os.environ.get("VOXFLOW_LLM_BASE_URL", "http://localhost:3001/v1")
_default_key = os.environ.get("VOXFLOW_LLM_API_KEY", "freellmapi-local")
_default_model = os.environ.get("VOXFLOW_LLM_MODEL", "auto")

# ── System Prompts ──────────────────────────────────────────

_GEN_SYSTEM = """\
你是一个专业的中文配音文案创作者。根据用户的描述生成适合语音合成 (TTS) 的中文文案。

规则:
1. 输出纯文本，不包含任何 Markdown 标记 (**、#、-、> 等)
2. 适合口语朗读，句子长度适中，长句拆短句
3. 自然使用逗号和句号制造停顿节奏
4. 中文为主，技术术语可保留英文
5. 不要输出任何解释说明，只输出文案本身
6. 如果用户指定了字数，尽量控制在范围内"""

_POLISH_SYSTEM = """\
你是一个专业的配音文案编辑。优化用户提供的文案，使其更适合语音合成 (TTS)。

优化方向:
1. 调整句子节奏，长句拆成短句
2. 用标点制造自然停顿 (逗号、句号、省略号)
3. 修正口语不通顺的表达
4. 保留原文意思、风格和情感基调
5. 输出纯文本，不包含任何 Markdown 标记
6. 不要输出任何解释说明，只输出优化后的文案"""

_LYRICS_SYSTEM = """\
你是专业的中文流行音乐作词人。根据主题和风格创作适合 Suno 的完整歌词。

规则:
1. 只输出歌词，不要解释、标题或 Markdown 围栏。
2. 使用 [Verse 1]、[Chorus]、[Verse 2]、[Bridge]、[Chorus] 段落标记。
3. 每段 4 到 8 行，句子适合演唱，有可记忆的副歌。
4. 保持中文自然、意象连贯；不要照抄用户提示中的现有歌词。
5. 不要添加曲风说明、和弦、演唱提示或括号旁白。"""


def _get_client():
    """懒加载 OpenAI 客户端"""
    from openai import OpenAI
    return OpenAI(
        base_url=_default_base,
        api_key=_default_key,
        timeout=30,
    )


# 探活结果缓存。改成「真实请求探活」是对的（GET /models 不是兼容协议的必需项，
# 会误报未连接），但它的代价是每次调用都真的打一次 LLM —— 而前端是 30 秒轮询、
# 还可能开着好几个标签页，叠加起来就是每分钟十几次真实请求，把单线程后端堵死。
#
# 连通性这种东西变化很慢，缓存 60 秒完全够用。
_status_cache: dict = {"at": 0.0, "value": None}
_STATUS_TTL = 60.0


def check_status(force: bool = False) -> dict:
    """检测 LLM 后端是否可用（用一次真实的最小请求，不是 GET /models）

    返回:
        {"available": bool, "base_url": str, "model": str, "error": str}
    """
    import time
    now = time.time()
    if not force and _status_cache["value"] and (now - _status_cache["at"] < _STATUS_TTL):
        return _status_cache["value"]

    try:
        client = _get_client()
        # 用一次**极小的真实请求**探活，而不是 client.models.list()。
        #
        # models.list() 打的是 GET /models —— 那是 OpenAI 官方 API 的端点，
        # 不是 OpenAI 兼容协议的必需项。很多自建/代理网关（比如接了 museav 中台
        # 之后）只实现 /chat/completions，探活就会误报「未连接」，而实际生成
        # 完全正常。用生成本身探活，探的才是真正要用的那条路。
        #
        # max_tokens=1 让开销可以忽略：一次探活约 10 token。
        client.chat.completions.create(
            model=_default_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        result = {
            "available": True,
            "base_url": _default_base,
            "model": _default_model,
            "models": [_default_model],
            "error": "",
        }
        _status_cache.update(at=now, value=result)
        return result
    except Exception as e:
        # 429 是「暂时用太快了」，不是「没配好」。混为一谈的话，
        # 用户看到「未连接」会去翻配置、改 base_url，而其实等一分钟就好了。
        msg = str(e)
        if "429" in msg or "频率超限" in msg:
            return {
                "available": True,
                "throttled": True,
                "base_url": _default_base,
                "model": _default_model,
                "models": [_default_model],
                "error": "请求太频繁，稍等一下再试",
            }
        return {
            "available": False,
            "base_url": _default_base,
            "model": _default_model,
            "models": [],
            "error": str(e),
        }


def generate_script(prompt: str, word_count: Optional[int] = None) -> str:
    """根据提示词生成配音文案

    Args:
        prompt: 用户的描述，如 "写一段武侠旁白，讲一个剑客归隐山林的故事"
        word_count: 目标字数 (可选)

    Returns:
        生成的文案文本
    """
    client = _get_client()

    user_msg = prompt
    if word_count:
        user_msg += f"\n\n(目标字数: 约 {word_count} 字)"

    resp = client.chat.completions.create(
        model=_default_model,
        messages=[
            {"role": "system", "content": _GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.8,
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


def generate_lyrics(prompt: str, style: str = "") -> str:
    """根据创作提示生成带 Suno 段落标记的歌词。"""
    client = _get_client()
    style_hint = f"\n曲风参考：{style}" if style.strip() else ""
    resp = client.chat.completions.create(
        model=_default_model,
        messages=[
            {"role": "system", "content": _LYRICS_SYSTEM},
            {"role": "user", "content": f"创作主题：{prompt.strip()}{style_hint}"},
        ],
        temperature=0.9,
        max_tokens=1600,
    )
    return resp.choices[0].message.content.strip()


def polish_script(text: str, style: str = "") -> str:
    """润色文案使其更适合 TTS

    Args:
        text: 原始文案
        style: 风格提示 (可选)，如 "更激昂"、"更平静"、"更口语化"

    Returns:
        润色后的文案
    """
    client = _get_client()

    user_msg = text
    if style:
        user_msg += f"\n\n(风格要求: {style})"

    resp = client.chat.completions.create(
        model=_default_model,
        messages=[
            {"role": "system", "content": _POLISH_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.6,
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


_TREND_SYSTEM = """\
你是一个华语流行音乐趋势分析师。给你一份真实的热歌榜（含排名、歌名、艺人），
你要提炼「当前听众口味往哪走」，产出可以指导全新创作的风格方向。

必须做：
1. 提炼主线：当前主流曲风（如流行摇滚/国风/抒情芭乐/说唱…）、常见编曲特征
   （鼓点、和声、器乐）、常见情绪基调、常见歌词主题。
2. 产出可直接给 Suno 用的风格标签（英文为主，5-8 个，逗号分隔，可带 BPM）。

严格边界（这是不可违反的红线）：
- 只谈风格共性，禁止复述任何单首歌的旋律、歌词、歌名、具体编曲细节。
- 禁止把任何一首歌当作模板或参考对象点名。
- 你的产出必须能让一个没听过这些歌的人据此创作出全新的作品，
  任何一段都不能让人认出对应榜单里哪首具体歌曲。

只输出 JSON，不要 Markdown 代码块，结构：
{"trend": "一句话主线", "tags": "suno 风格标签串", "moods": ["情绪", ...], "themes": ["主题", ...]}
"""


def analyze_trending(songs: list[dict]) -> dict:
    """分析热歌榜，提炼可创作的热点风格方向。

    Args:
        songs: 榜单歌曲 [{rank, name, artist}, ...]

    Returns:
        {"trend": str, "tags": str, "moods": list, "themes": list}

    反抄袭边界在 _TREND_SYSTEM 里写死：只提炼风格共性，不输出任何
    能定位到具体歌曲的内容。LLM 偶发输出裹 Markdown 或带废话，解析
    失败重试 2 次，仍然不行才返回空（调用方不要缓存空结果）。
    """
    import json as _json
    import re as _re

    client = _get_client()
    chart = "\n".join(
        f"{s.get('rank', '?'):>3}. {s.get('name', '')} — {s.get('artist', '')}"
        for s in songs[:30]
    )

    def _parse(raw: str) -> dict | None:
        raw = raw.strip()
        # 剥掉 ```json ... ``` 包裹
        m = _re.search(r"```(?:json)?\s*(.*?)\s*```", raw, _re.S)
        if m:
            raw = m.group(1)
        # 直接从文本里抓第一个 {...} 对象（模型可能前后带一句废话）
        m = _re.search(r"\{.*\}", raw, _re.S)
        if not m:
            return None
        try:
            data = _json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except _json.JSONDecodeError:
            return None

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=_default_model,
                messages=[
                    {"role": "system", "content": _TREND_SYSTEM},
                    {"role": "user", "content": f"热歌榜（前 30）：\n{chart}"},
                ],
                temperature=0.4,
                max_tokens=600,
            )
            data = _parse(resp.choices[0].message.content.strip())
            if data and data.get("tags"):
                return data
        except Exception:                                # noqa: BLE001
            pass
        time.sleep(1.5 * (attempt + 1))

    return {"trend": "", "tags": "", "moods": [], "themes": []}
