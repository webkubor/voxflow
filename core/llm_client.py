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


def _get_client():
    """懒加载 OpenAI 客户端"""
    from openai import OpenAI
    return OpenAI(
        base_url=_default_base,
        api_key=_default_key,
        timeout=30,
    )


def check_status() -> dict:
    """检测 LLM 后端是否可用（用一次真实的最小请求，不是 GET /models）

    返回:
        {"available": bool, "base_url": str, "model": str, "error": str}
    """
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
        return {
            "available": True,
            "base_url": _default_base,
            "model": _default_model,
            "models": [_default_model],
            "error": "",
        }
    except Exception as e:
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
