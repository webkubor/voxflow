#!/usr/bin/env python3
"""
飞书通知的自检 —— `.venv/bin/python tests/test_notify.py`

## 为什么要测这个

通知是**旁路**，它坏了不会有人喊 —— 生成照常成功，只是群里没消息、
台账少一行，等到有人问「那首歌怎么没进表」才发现，中间漏掉的补不回来。

所以这里守的是三件会**静默出错**的事：

1. 卡片结构不对 → 飞书直接拒收，业务侧看不出区别
2. `HTTP 200` 被当成送达 → 最阴的一个，见下
3. 账户切错公司 → 消息发到别家群里去了

网络那半截不在这里测（真发一次验证过：卡片进群 + 台账进行）。

## 不用 pytest

跟 test_obs.py 一致：项目没有测试依赖，裸 assert + 直接跑就够。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import notify  # noqa: E402

n = 0


def check(cond, label):
    global n
    n += 1
    assert cond, f"❌ {label}"
    print(f"  ✓ {label}")


print("卡片结构")
c = notify._card("标题", "green", {"曲名": "十年人间", "专辑": "", "平台": "汽水"})
check(c["msg_type"] == "interactive", "msg_type 是 interactive")
check(c["card"]["header"]["template"] == "green", "颜色跟 level 走")
md = c["card"]["elements"][0]["text"]["content"]
check("**曲名**：十年人间" in md and "**平台**：汽水" in md, "字段渲染成 lark_md")
# 空值不剔掉的话，生成阶段的卡片会挂一串「专辑：」「上架时间：」
check("专辑" not in md, "空值字段被剔掉")

c = notify._card("t", "blue", {"a": "1"}, [
    {"text": "看台账", "url": "https://x"},
    {"text": "没链接", "url": ""},
])
acts = c["card"]["elements"][1]["actions"]
check(len(acts) == 1 and acts[0]["url"] == "https://x", "没 url 的按钮被剔掉")

# 内容全空时 lark_md 为空串，飞书会整条拒收，所以要占位
check(notify._card("t", "blue", {"a": "", "b": ""})
      ["card"]["elements"][0]["text"]["content"] == "—", "全空时给占位符")

print("HTTP 200 ≠ 送达")


class FakeResp:
    """机器人被移出群 / 关键词不匹配时，飞书返回的正是 200 + code!=0。"""
    def read(self): return b'{"code":19024,"msg":"Key Words Not Found"}'
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeOpener:
    def open(self, *a, **k): return FakeResp()


# 打桩的是 `net.opener` 而不是 `urllib.request.urlopen` —— 证书与代理这两个坑
# 收在 core/net.py 之后，_post 就是从那里拿 opener 的。
_orig = notify.net.opener
notify.net.opener = lambda *a, **k: FakeOpener()
try:
    ok, err = notify._post("https://x", {})
finally:
    notify.net.opener = _orig
check(ok is False and "19024" in err, "200 但 code 非 0 → 判为失败")

print("多公司账户切换")
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "notify.json"
    f.write_text(json.dumps({"active": "a", "accounts": {
        "a": {"company": "甲"}, "b": {"company": "乙"}}}), encoding="utf-8")
    _cf, notify.CONFIG_FILE = notify.CONFIG_FILE, f
    _env = os.environ.pop("VOXFLOW_NOTIFY_ACCOUNT", None)
    try:
        check(notify.account()["company"] == "甲", "默认跟 active")
        check(notify.account("b")["company"] == "乙", "显式指定优先于 active")
        os.environ["VOXFLOW_NOTIFY_ACCOUNT"] = "b"
        check(notify.account()["company"] == "乙", "环境变量能临时换一家")
        check(notify.account("a")["company"] == "甲", "显式仍然压过环境变量")
        check(notify.account("查无此人") == {}, "账户不存在返回空")
    finally:
        os.environ.pop("VOXFLOW_NOTIFY_ACCOUNT", None)
        if _env: os.environ["VOXFLOW_NOTIFY_ACCOUNT"] = _env
        notify.CONFIG_FILE = _cf

print("没配置时保持安静")
_cf, notify.CONFIG_FILE = notify.CONFIG_FILE, Path(tempfile.gettempdir()) / "vf-no-such.json"
try:
    check(notify.notify("t", {"a": "1"}) is False, "没配置 → 返回 False 而不是抛")
    check(notify.ledger_add({"曲名": "x"}) == "", "没配置 → 台账写入返回空串")
finally:
    notify.CONFIG_FILE = _cf

print(f"\n✅ {n} 条断言全过")
