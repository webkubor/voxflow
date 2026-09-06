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

# harness 的辅助函数是 goto_url + wait_for_load，没有 goto_and_wait
# （那是 ego-browser 的叫法）—— 两套 API 名字很像，容易记混。
ensure_real_tab()                     # noqa: F821 —— harness 预置
goto_url(console)                     # noqa: F821
wait_for_load()                       # noqa: F821
wait(3)                               # noqa: F821
info = page_info()                    # noqa: F821
url = (info or {}).get("url", "")

LOGIN_MARKS = ("/login", "/passport", "/sign", "accounts.", "sso.")
logged_in = bool(url) and not any(m in url.lower() for m in LOGIN_MARKS)

print(json.dumps({
    "ok": True, "platform": platform, "logged_in": logged_in,
    "url": url, "title": (info or {}).get("title", ""),
    "hint": "已登录" if logged_in else "被踢回登录页 —— 在浏览器里登录后重试",
}, ensure_ascii=False))
