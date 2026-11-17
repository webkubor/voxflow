"""CLI 音色库 / 生成库 / 模板的 agent 契约测试 —— 隔离数据目录，不碰真实音色库。

钉住的是 agent 依赖的东西：--json 时 stdout 是单个 JSON 对象，退出码
0 成功 / 1 错误 / 3 不存在 / 4 冲突；以及与 Web 相同的业务规则。
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = tempfile.TemporaryDirectory(prefix="voxflow-cli-test-")
os.environ["VOXFLOW_HOME"] = ROOT.name
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import soundfile as sf
from typer.testing import CliRunner

from cli.app import app
from core.paths import OUT_DIR

HOME = Path(ROOT.name)


def tone(path, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.sin(np.arange(int(24000 * seconds)) * 2 * np.pi * 220 / 24000) * .1, 24000)


class CliAgentContract(unittest.TestCase):
    runner = CliRunner()

    def cli(self, *args):
        r = self.runner.invoke(app, list(args) + ["--json"])
        return r.exit_code, json.loads(r.stdout.strip().splitlines()[-1])

    def test_voice_lifecycle(self):
        sample = HOME / "me.wav"
        tone(sample, 5)
        code, out = self.cli("voice", "add", "me", str(sample), "--ref-text", "我自己的声音。")
        self.assertEqual((code, out["voice"]["favorite"]), (0, True))
        self.assertEqual(self.cli("voice", "add", "me", str(sample), "--ref-text", "再来")[0], 4)
        self.assertEqual(self.cli("voice", "rename", "me", "新名字")[1]["voice"]["name"], "新名字")
        self.assertEqual(self.cli("voice", "rm", "me")[0], 1)               # 非交互必须 --yes
        code, out = self.cli("voice", "rm", "me", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(self.cli("voice", "show", "me")[0], 3)
        self.assertTrue(sample.is_file())                                   # 用户原始录音保留

    def test_generated_library(self):
        f = OUT_DIR / "[设计]库测试_20261117_120000.wav"
        tone(f)
        f.with_suffix(".json").write_text(json.dumps({"ref_text": "样音原文。"}, ensure_ascii=False))
        code, out = self.cli("library", "list", "--kind", "design", "--unsaved")
        self.assertIn(f.name, [x["filename"] for x in out["files"]])
        self.assertEqual(self.cli("library", "save", f.name, "库测试音色")[0], 0)
        self.assertEqual(self.cli("library", "save", f.name, "另一个")[0], 4)
        self.assertEqual(self.cli("library", "rm", f.name)[0], 1)           # 非交互必须 --yes
        self.assertTrue(f.exists())
        self.assertEqual(self.cli("library", "rm", f.name, "--yes")[0], 0)  # --yes 即确认影响
        self.assertFalse(f.exists())
        self.assertEqual(self.cli("voice", "unfavorite", "库测试音色")[0], 0)

    def test_preset_generated_once(self):
        code, out = self.cli("preset", "list", "--pending")
        self.assertEqual(code, 0)
        target = out["presets"][0]
        self.assertEqual(self.cli("preset", "run", target["name"], "--dry-run")[0], 0)
        (OUT_DIR / "[设计]x.wav").parent.mkdir(parents=True, exist_ok=True)
        from core import voice_library as vlib
        (OUT_DIR / vlib.design_filename(target["display_name"])).write_bytes(b"RIFF")
        code, out = self.cli("preset", "run", target["name"], "--dry-run")
        self.assertEqual((code, out["status"]), (4, 409))
        names = [p["name"] for p in self.cli("preset", "list", "--pending")[1]["presets"]]
        self.assertNotIn(target["name"], names)

    def test_generation_lock_rejects_concurrent_run(self):
        from core import voice_library as vlib
        with vlib.preset_generation_lock("并发模板"):
            with self.assertRaises(vlib.Conflict):
                with vlib.preset_generation_lock("并发模板"):
                    pass


if __name__ == "__main__":
    unittest.main()
