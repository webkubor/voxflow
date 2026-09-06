"""
探一个平台的登录态。

    VF_PLATFORM=qishui browser-harness < scripts/check_login.py

## 为什么要用 harness 而不是服务端请求

登录态是**浏览器里的 cookie**，voxflow 这个进程看不到。服务端拿不到就
只能猜「大概登录了吧」—— 而猜错的代价是：人按着「✅ 可以发布」去跑填表，
跑到一半才发现登录过期，前面填的全白费。

harness 附着的是用户日常那个浏览器，登录态直接可用，探一次几秒钟。

## 判断依据

打开平台控制台，看是不是被踢回登录页。**不看页面上有没有「登录」两个字**
—— 已登录的页面上也可能有「登录设备管理」之类的字样，那样会误判。
看的是最终 URL：跳到 /login、/passport、/sign 就是没登录。
"""
import json
import os
import sys
from pathlib import Path

BASE = Path(os.environ.get("VF_BASE") or Path.cwd()).resolve()
sys.path.insert(0, str(BASE))

from core import pipeline as P  # noqa: E402

platform = os.environ.get("VF_PLATFORM", "qishui")
spec = P.PLATFORMS.get(platform) or {}
console = spec.get("console") or ""
if not console:
    print(json.dumps({"ok": False, "error": f"{platform} 没有配置控制台地址"}, ensure_ascii=False))
    raise SystemExit(1)

# ⚠️ 不要用 wait_for_load()：平台后台是重页面（大量异步请求），
# 它会一直等到网络空闲，实测直接超时。而判断登录只需要看**最终 URL**，
# 页面渲染完没完根本不影响。所以只 goto + 短等，然后读 page_info。
ensure_real_tab()                     # noqa: F821 —— harness 预置
info = page_info()                    # noqa: F821
# 已经在目标站上就不折腾了 —— 重新导航会打断用户正在填的表
host = console.split("//")[-1].split("/")[0]
if host not in (info or {}).get("url", ""):
    # ⚠️ 导航 + 长等会撑爆 harness 的 socket 超时（平台后台是重页面）。
    # 拆开：先发导航（不等它加载完），短等，再读 URL。
    # 判断登录只看**最终 URL**，页面渲染完没完不影响结论。
    goto_url(console)                 # noqa: F821
    wait(2)                           # noqa: F821
    info = page_info()                # noqa: F821
    # 还在跳转中就再等一轮 —— SSO 会连跳两次
    if host not in (info or {}).get("url", ""):
        wait(3)                       # noqa: F821
        info = page_info()            # noqa: F821
url = (info or {}).get("url", "")

LOGIN_MARKS = ("/login", "/passport", "/sign", "accounts.", "sso.")
logged_in = bool(url) and not any(m in url.lower() for m in LOGIN_MARKS)

print(json.dumps({
    "ok": True, "platform": platform, "logged_in": logged_in,
    "url": url, "title": (info or {}).get("title", ""),
    "hint": "已登录" if logged_in else "被踢回登录页 —— 在浏览器里登录后重试",
}, ensure_ascii=False))
