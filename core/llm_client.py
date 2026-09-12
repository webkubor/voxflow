"""LLM 客户端 — 任何 OpenAI 兼容后端都能接，实现 AI 文案生成与润色

只依赖 OpenAI SDK 的协议本身，不绑定某一家服务。

## 凭据来源有三档，按顺序取第一个命中的

1. **环境变量** `VOXFLOW_LLM_BASE_URL` + `VOXFLOW_LLM_API_KEY` —— 显式覆盖，
   接自己的网关或别家 LLM 时用。
2. **MUSE AV 应用授权**（`core/museav_auth`）—— 跑过 `voice museav login` 之后
   自动命中，走中台的 OpenAI 标准路径 `/api/chat/completions`。
3. **本地 FreeLLMAPI** —— 需要 Docker 起个容器在 localhost:3001。

第 2 档是 2026-09-11 替掉租户 Key 的那条路。原来中台这条线靠环境变量注入
**voxcraft 租户 Key**，那意味着「应用方持 Key、花应用方的池子」——
对 VoxFlow 是错的：它装在用户自己机器上，该花用户自己的积分、产出归用户自己，
而且租户 Key 一旦发出去只能整把吊销、事后查不出哪次调用是哪个工具发的。
应用授权三件事都解决：一个应用一把、用户能单独撤销、中台记得住是谁调的。

依赖:
    - pip install openai

配置:
    环境变量 VOXFLOW_LLM_BASE_URL (不设则按上面的顺序自动选)
    环境变量 VOXFLOW_LLM_API_KEY  (同上)
    环境变量 VOXFLOW_LLM_MODEL    (默认 auto, 让路由器选模型)
"""

import os
import time
from typing import Optional

_FREELLM_BASE = "http://localhost:3001/v1"
_FREELLM_KEY = "freellmapi-local"
# 中台的 OpenAI 标准路径是 /api/chat/completions，SDK 自己拼 /chat/completions，
# 所以 base_url 给到 /api 为止（见 museav-manager 的 functions/api/chat/completions.js）
_MUSEAV_BASE = "https://manager.museav.top/api"

_env_base = os.environ.get("VOXFLOW_LLM_BASE_URL", "")
_env_key = os.environ.get("VOXFLOW_LLM_API_KEY", "")
# 模型名跟着**后端**走，不能只有一个全局默认：
#   · museav 中台认具体模型名，不认 "auto"（那是 FreeLLMAPI 的路由约定）
#   · 本地 FreeLLMAPI 认 "auto"，让它自己路由
# 此前默认值写死 "auto"，真正对的那个值 export 在 run.sh 里 —— 于是
# **没跑 run.sh 的人（Windows 没有 bash、或直接 `voice web`）会拿 auto 去打
# 中台，AI 文案直接报错**，而错误信息只说模型不存在，看不出是启动方式的差别。
# 配置的默认值不该藏在某个平台的启动脚本里。
_MODEL_BY_SOURCE = {"museav": "deepseek-v4-flash", "museav-cli": "deepseek-v4-flash",
                    "freellm": "auto"}
_env_model = os.environ.get("VOXFLOW_LLM_MODEL", "")


def default_model(source: str = "") -> str:
    """当前该用哪个模型名。显式设了环境变量就一律听它的。"""
    if _env_model:
        return _env_model
    if not source:
        source = resolve_backend()[2]
    return _MODEL_BY_SOURCE.get(source, "auto")


def _museav_cli_creds() -> tuple[str, str]:
    """读 museav CLI 登录后存的凭据。返回 (apiKey, base_url)，没有就 ("", "")。

    baseUrl 存的是站点根（https://manager.museav.top），而 OpenAI 兼容端点在
    /api 下面，所以要补一截 —— 直接拿站点根当 base_url 会 404。
    """
    import json as _json  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    cfg = _Path.home() / ".museav.json"
    if not cfg.is_file():
        return "", ""
    try:
        d = _json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "", ""
    key = d.get("apiKey") or d.get("api_key") or d.get("token") or ""
    base = (d.get("baseUrl") or "").rstrip("/")
    if not key:
        return "", ""
    return key, (f"{base}/api" if base and not base.endswith("/api") else (base or _MUSEAV_BASE))


def resolve_backend() -> tuple[str, str, str]:
    """(base_url, api_key, 来源标签)。每次调用都重新解析 —— 授权状态会在运行期变化
    （用户可能刚跑完 login，也可能刚在 MUSE AV 那边撤销了授权）。"""
    if _env_base and _env_key:
        return _env_base, _env_key, "env"
    try:
        from core import museav_auth

        key = museav_auth.load_key()
        if key:
            return _MUSEAV_BASE, key, "museav"
    except Exception:  # noqa: BLE001 - 拿不到就往下走兜底，不该让文案功能整个挂掉
        pass
    # museav CLI 登录后的凭据（~/.museav.json）。
    #
    # **一次登录应该覆盖所有 AI 能力。** 封面出图早就在读这个文件了
    # （core/cover.py 的 _museav_logged_in），文案却另走一套应用授权 ——
    # 于是「我明明登录过 museav」的人，出图能用、文案报未连接，
    # 而界面上两个徽章还长得一模一样，看不出差别在哪。
    #
    # 现在文案也认它：CLI 登录一次，出图和文案一起通。
    cli_key, cli_base = _museav_cli_creds()
    if cli_key:
        return cli_base, cli_key, "museav-cli"
    # 只给了其中一个环境变量时，缺的那半用本地兜底值补齐
    return (_env_base or _FREELLM_BASE), (_env_key or _FREELLM_KEY), "freellm"

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
    """懒加载 OpenAI 客户端。每次都重新 resolve —— 用户可能刚 login 或刚撤销授权"""
    from openai import OpenAI

    base, key, _ = resolve_backend()
    return OpenAI(
        base_url=base,
        api_key=key,
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
            model=default_model(),
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        base, _, source = resolve_backend()
        result = {
            "available": True,
            "base_url": base,
            "source": source,
            "model": default_model(),
            "models": [default_model()],
            "error": "",
        }
        _status_cache.update(at=now, value=result)
        return result
    except Exception as e:
        # 429 是「暂时用太快了」，不是「没配好」。混为一谈的话，
        # 用户看到「未连接」会去翻配置、改 base_url，而其实等一分钟就好了。
        msg = str(e)
        if "429" in msg or "频率超限" in msg:
            base, _, source = resolve_backend()
            return {
                "available": True,
                "throttled": True,
                "base_url": base,
                "source": source,
                "model": default_model(),
                "models": [default_model()],
                "error": "请求太频繁，稍等一下再试",
            }
        base, _, source = resolve_backend()
        # 401 在 museav 这一档有个明确原因：授权被撤销了。直接说清下一步，
        # 别让人对着「Unauthorized」去翻 base_url
        err = str(e)
        if source == "museav" and ("401" in err or "Unauthorized" in err):
            err = "MUSE AV 授权已失效或被撤销，重新跑 `voice museav login`"
        return {
            "available": False,
            "base_url": base,
            "source": source,
            "model": default_model(),
            "models": [],
            "error": err,
        }


def _chat(system: str, user: str, *, action: str, temperature: float = 0.8,
          max_tokens: int = 2048) -> str:
    """
    所有 LLM 调用的唯一出口。

    抽出来的理由不是「少写几行」——是**计量只能埋一个地方**。四个函数各自
    调 create()，就要埋四次，加第五个功能时必然忘记埋第五次，
    然后成本表上会缺一块，而且没有任何报错提示你缺了。

    token 用量取 resp.usage 的真实值，不是估的。走中台时它就是扣积分的依据。
    """
    from core import obs  # 延迟导入，避免 CLI 早期加载时的循环依赖

    client = _get_client()
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=default_model(),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        obs.meter("llm", action, qty=1, credits=0, ok=False,
                  duration_ms=int((time.perf_counter() - t0) * 1000),
                  model=default_model(), error=str(e)[:120])
        raise
    usage = getattr(resp, "usage", None)
    obs.meter("llm", action, qty=1,
              credits=getattr(usage, "total_tokens", 0) or 0,
              duration_ms=int((time.perf_counter() - t0) * 1000),
              model=default_model(),
              prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
              completion_tokens=getattr(usage, "completion_tokens", 0) or 0)
    return resp.choices[0].message.content.strip()


def generate_script(prompt: str, word_count: Optional[int] = None) -> str:
    """根据提示词生成配音文案

    Args:
        prompt: 用户的描述，如 "写一段武侠旁白，讲一个剑客归隐山林的故事"
        word_count: 目标字数 (可选)

    Returns:
        生成的文案文本
    """
    user_msg = prompt
    if word_count:
        user_msg += f"\n\n(目标字数: 约 {word_count} 字)"
    return _chat(_GEN_SYSTEM, user_msg, action="script")


def generate_tags(theme: str) -> str:
    """从一句话主题生成 Suno 能用的风格标签。

    这是小白最不会写的一环 —— AI 认得 `bassoon`（低音管），认不出「搞笑」。
    所以系统提示里把这条钉死：**只出乐器名、流派、音色、BPM，不要情绪词**。
    """
    sys_prompt = """你是 Suno AI 音乐的风格标签专家。根据用户给的主题，输出一行英文风格标签。

严格规则：
1. 只输出标签本身，逗号分隔，不要任何解释、不要引号、不要换行
2. **必须是具体的乐器名、流派、音色描述**（如 ukulele, pizzicato strings, lo-fi）
   **禁止情绪词**（如 funny, sad, epic）—— Suno 认乐器不认情绪
3. 必须包含一个 BPM（60-80 慢 / 100-120 中 / 128-140 快）
4. 中文歌要加 mandarin 或 chinese pop
5. 需要人声就写明音色（如 bright young female vocal）；纯音乐则加 instrumental
6. 总共 6-10 个标签

示例输入：上班摸鱼的搞笑歌，年轻女生唱
示例输出：electropop, hyperpop, bright young female vocal, gen-z, quirky, catchy hook, mandarin, 128 BPM"""
    out = _chat(sys_prompt, theme.strip(), action="tags", temperature=0.7, max_tokens=200)
    return out.strip().strip('"').replace("\n", " ")


def generate_lyrics(prompt: str, style: str = "") -> str:
    """根据创作提示生成带 Suno 段落标记的歌词。"""
    style_hint = f"\n曲风参考：{style}" if style.strip() else ""
    return _chat(_LYRICS_SYSTEM, f"创作主题：{prompt.strip()}{style_hint}",
                 action="lyrics", temperature=0.9, max_tokens=1600)


def polish_script(text: str, style: str = "") -> str:
    """润色文案使其更适合 TTS

    Args:
        text: 原始文案
        style: 风格提示 (可选)，如 "更激昂"、"更平静"、"更口语化"

    Returns:
        润色后的文案
    """
    user_msg = text
    if style:
        user_msg += f"\n\n(风格要求: {style})"
    return _chat(_POLISH_SYSTEM, user_msg, action="polish", temperature=0.6)


_TREND_SYSTEM = """\
你是一个华语流行音乐趋势分析师。给你一份真实的热歌榜（含排名、歌名、艺人、
热度分，score 高的更火，标注 🔥双榜 的歌在网易云和 QQ 都上榜、趋势最可信），
你要提炼「当前听众口味往哪走」，产出可以指导全新创作的风格方向。

必须做：
1. 提炼主线：当前主流曲风（如流行摇滚/国风/抒情芭乐/说唱…）、常见编曲特征
   （鼓点、和声、器乐）、常见情绪基调、常见歌词主题。
2. 产出可直接给 Suno 用的风格标签（英文为主，5-8 个，逗号分隔，可带 BPM）。
3. 给这个方向打「值得做」分（hotness，1-10 整数）：综合热度、市场饱和度、
   可创作空间判断。双榜同火的题材分数更高，但任何方向都不能给 10 ——
   市场没有空档到那个程度。

严格边界（这是不可违反的红线）：
- 只谈风格共性，禁止复述任何单首歌的旋律、歌词、歌名、具体编曲细节。
- 禁止把任何一首歌当作模板或参考对象点名。
- 你的产出必须能让一个没听过这些歌的人据此创作出全新的作品，
  任何一段都不能让人认出对应榜单里哪首具体歌曲。

只输出 JSON，不要 Markdown 代码块，结构：
{"trend": "一句话主线", "tags": "suno 风格标签串", "moods": ["情绪", ...],
 "themes": ["主题", ...], "hotness": 8,
 "hotness_reason": "一句话说为什么值得做这个方向"}
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

    chart = "\n".join(
        f"{s.get('rank', '?'):>3}. {s.get('name', '')} — {s.get('artist', '')}"
        f"  [score={s.get('score', '?')}]"
        f"{' 🔥双榜' if len(s.get('platforms') or []) > 1 else ''}"
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
            data = _parse(_chat(_TREND_SYSTEM, f"热歌榜（前 30）：\n{chart}",
                                action="trending", temperature=0.4, max_tokens=1000))
            if data and data.get("tags"):
                return data
        except Exception:                                # noqa: BLE001
            pass
        time.sleep(1.5 * (attempt + 1))

    return {"trend": "", "tags": "", "moods": [], "themes": []}
