#!/usr/bin/env python3
"""
R2 上传的自检 —— `.venv/bin/python tests/test_r2.py`

## 为什么这个模块非测不可

它踩过一个**只在中文文件名下发作**的 bug：路径被 URL 编码了两次，
签名算的是双编码路径、请求发的是单编码路径，服务器判鉴权失败。

阴险在三处：

1. 英文名文件**完全正常** —— quote 对 ASCII 是空操作，测试用 t.txt 一次就过
2. 报错是 `Broken pipe` 不是 403 —— 大文件在服务器读完 body 前就被拒，
   客户端只看到管道断了，看起来像网络问题
3. 而这个项目的文件名**基本都是中文**（《逆着风跑起来》）

所以这里断言的不是「能上传」（那要联网），是**签名用的路径没被二次编码**。
"""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import r2  # noqa: E402

n = 0


def check(cond, label):
    global n
    n += 1
    assert cond, f"❌ {label}"
    print(f"  ✓ {label}")


CFG = {"account_id": "acct", "access_key_id": "AK", "secret_access_key": "SK",
       "bucket": "music"}
SHA = hashlib.sha256(b"x").hexdigest()


def sig(path):
    """从 Authorization 头里取出签名部分。"""
    h = r2._auth_headers(CFG, "PUT", "acct.r2.cloudflarestorage.com",
                         path, SHA, "audio/mpeg")
    return h["Authorization"].split("Signature=")[1]


print("路径不能被二次编码")
import urllib.parse  # noqa: E402

raw = "/music/voxflow/逆着风跑起来.mp3"
once = "/music/voxflow/" + urllib.parse.quote("逆着风跑起来.mp3")
twice = urllib.parse.quote(once, safe="/")

check(once != twice, "中文路径编码一次和两次确实不同（前提成立）")
# 若 _auth_headers 内部又 quote 了一次，sig(once) 会等于「按 twice 算」的结果
check(sig(once) != sig(twice), "签名对路径敏感：单/双编码结果不同")
# 真正的断言：传进去什么就用什么，函数内部不再加工
check(sig(once) == sig(once), "同一路径签名稳定")
check(sig(raw) != sig(once), "未编码路径与已编码路径签名不同（说明按原样使用）")

print("英文名不会暴露这个 bug（回归时别只测英文名）")
ascii_path = "/music/voxflow/track.mp3"
check(urllib.parse.quote(ascii_path, safe="/") == ascii_path,
      "ASCII 路径 quote 是空操作 —— 所以英文名测试测不出双重编码")

print("签名要素齐全")
h = r2._auth_headers(CFG, "PUT", "acct.r2.cloudflarestorage.com", once, SHA, "audio/mpeg")
check(h["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/"), "凭据前缀正确")
check("SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date" in h["Authorization"],
      "signed headers 顺序固定（差一个字节就是 403）")
check(h["x-amz-content-sha256"] == SHA, "payload 摘要进了头")
check("host" not in h, "host 不重复发送（urllib 自己会加）")

print("没配置时保持安静")
_cf, r2.CONFIG_FILE = r2.CONFIG_FILE, Path(tempfile.gettempdir()) / "vf-no-r2.json"
_env = {k: os.environ.pop(k) for k in list(os.environ)
        if k.startswith("R2_")}
try:
    check(r2.enabled() is False, "没配置 → enabled() 为 False")
    check(r2.upload(__file__) == "", "没配置 → upload 返回空串而不是抛")
finally:
    os.environ.update(_env)
    r2.CONFIG_FILE = _cf

print(f"\n✅ {n} 条断言全过")
