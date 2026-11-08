"""Offline registration contract tests; never touch the user's voice library."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = tempfile.TemporaryDirectory(prefix="voxflow-registration-test-")
os.environ["VOXFLOW_HOME"] = ROOT.name
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from web.app import app, BASE_DIR, PERSONAS_FILE, OUT_DIR
from core.processor import AudioProcessor
from core.utils import upsert_persona_mapping


def wav(seconds=12):
    out = io.BytesIO()
    sr = 24000
    sf.write(out, np.sin(np.arange(int(sr * seconds)) * 2 * np.pi * 220 / sr) * .1, sr, format="WAV")
    return out.getvalue()


class RegistrationTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        ROOT.cleanup()

    def setUp(self):
        self.client = TestClient(app)

    def register(self, key, text="这是参考录音的原文。", content=None):
        data = {"key": key, "name": "同名音色"}
        if text is not None:
            data["ref_text"] = text
        return self.client.post("/api/personas/add", data=data,
                                files={"audio": ("reference.wav", content or wav(), "audio/wav")})

    def test_reference_is_complete_and_transcript_is_persisted(self):
        response = self.register("full")
        self.assertEqual(response.status_code, 200, response.text)
        saved = json.loads(PERSONAS_FILE.read_text())["full"]
        self.assertEqual(saved["ref_text"], "这是参考录音的原文。")
        self.assertAlmostEqual(sf.info(BASE_DIR / saved["ref"]).duration, 12, places=2)
        before = (BASE_DIR / saved["ref"]).read_bytes()
        other = self.register("same_name_other_key")
        self.assertEqual(other.status_code, 200)
        self.assertNotEqual(other.json()["ref"], saved["ref"])
        self.assertEqual((BASE_DIR / saved["ref"]).read_bytes(), before)
        self.assertEqual(self.register("full").status_code, 409)
        self.assertEqual((BASE_DIR / saved["ref"]).read_bytes(), before)

    def test_missing_text_and_invalid_audio_never_register(self):
        self.assertEqual(self.register("missing", None).status_code, 422)
        self.assertEqual(self.register("blank", "   ").status_code, 400)
        self.assertEqual(self.register("broken", content=b"not audio").status_code, 400)
        self.assertEqual(self.register("long", content=wav(31)).status_code, 400)
        data = json.loads(PERSONAS_FILE.read_text()) if PERSONAS_FILE.exists() else {}
        for key in ["missing", "blank", "broken", "long"]:
            self.assertNotIn(key, data)

    def test_delayed_design_commit_preserves_saved_text(self):
        sample = OUT_DIR / "design_test.wav"
        sample.write_bytes(wav())
        sample.with_suffix(".json").write_text(json.dumps({"ref_text": "设计时实际念的短句。"}))
        response = self.client.post("/api/design/commit", json={"filename": sample.name, "voice_name": "设计验收"})
        self.assertEqual(response.status_code, 200, response.text)
        saved = json.loads(PERSONAS_FILE.read_text())[response.json()["persona_key"]]
        self.assertEqual(saved["ref_text"], "设计时实际念的短句。")
        self.assertAlmostEqual(sf.info(BASE_DIR / saved["ref"]).duration, 12, places=2)

    def test_corrupt_mapping_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'configs'
            config.mkdir()
            target = config / 'personas.json'
            target.write_text('{broken')
            with self.assertRaises(json.JSONDecodeError):
                upsert_persona_mapping(root, 'new', 'new', 'ref.wav', '原文')
            self.assertEqual(target.read_text(), '{broken')

    def test_concurrent_registration_keeps_both_voices(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as root:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda key: upsert_persona_mapping(root, key, key, key + '.wav', '原文'), ['a', 'b']))
            self.assertEqual(set(json.loads((Path(root) / 'configs/personas.json').read_text())), {'a', 'b'})

    def test_capability_and_empty_text_guard(self):
        response = self.client.get("/api/personas")
        self.assertTrue(response.json()["capabilities"]["reference_text_registration"])
        with self.assertRaises(ValueError):
            upsert_persona_mapping(str(BASE_DIR), "bad", "bad", "missing.wav", " ")


if __name__ == "__main__":
    unittest.main()
