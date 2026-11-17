#!/usr/bin/env python3
"""
设计预设「已生成样音」探测的自检 —— `.venv/bin/python tests/test_preset_audio.py`

## 为什么值得测

`_find_preset_audio_file` 原来把搜索目录写死成 `out/design/20260830` 和
`20260828` 两个日期。这种写法**当天写当天好用，第三天就悄悄失效** —— 不报错、
不抛异常，只是所有预设的 `has_generated` 全变 False，前端看上去就是「一个样音
都没生成过」。这类静默失效人工根本抽不出来，只能靠断言钉住。

这里钉的就是那一条：**新日期目录下的样音必须能被找到**。
"""
import sys, tempfile, unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run():
    import web.app as app

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # 造三个日期目录，其中 29991231 是「未来的新日期」——写死日期的老版本必然漏掉它
        for day, name in (("20260828", "旧音_A"), ("20260830", "旧音_B"), ("29991231", "新音_C")):
            d = root / "out" / "design" / day
            d.mkdir(parents=True)
            (d / f"[设计]{name}_{day}_120000.wav").write_bytes(b"RIFF")
        (root / "assets" / "temp").mkdir(parents=True)

        with mock.patch.object(app, "DATA_DIR", root):
            got_new = app._find_preset_audio_file("新音_C")
            assert got_new is not None, "新日期目录下的样音没找到 —— 搜索目录又被写死了？"
            assert "29991231" in str(got_new), f"找错了文件：{got_new}"

            got_old = app._find_preset_audio_file("旧音_A")
            assert got_old is not None and "旧音_A" in got_old.name, f"旧样音丢了：{got_old}"

            assert app._find_preset_audio_file("查无此音") is None, "不存在的预设应该返回 None"
            assert app._find_preset_audio_file("新音_D") is None, "相似名称的音色不应被误认为已生成"
            assert app._find_preset_audio_file("新音") is None, "短前缀不应误匹配长名称模板"

            # 清洗非法字符后仍能找到生成文件；不同原名的清洗碰撞不能互相误判。
            import hashlib
            import re
            raw_name = "带 空格·名称"
            safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", raw_name)
            name_id = hashlib.sha256(raw_name.encode("utf-8")).hexdigest()[:8]
            exact = root / "out" / "design" / "29991231" / f"[设计]{safe}_{name_id}_29991231_120000.wav"
            exact.write_bytes(b"RIFF")
            assert app._find_preset_audio_file(raw_name) == exact
            assert app._find_preset_audio_file("带_空格_名称") is None

            # 同名多份时取 mtime 最新的那个
            newer = root / "out" / "design" / "29991231" / "[设计]新音_C_29991231_235959.wav"
            newer.write_bytes(b"RIFF")
            import os, time
            os.utime(newer, (time.time() + 10, time.time() + 10))
            assert app._find_preset_audio_file("新音_C") == newer, "同名多份没取最新的"

    print("✅ 预设样音探测：新日期目录、旧目录、空结果、取最新 —— 四项全过")


if __name__ == "__main__":
    run()
