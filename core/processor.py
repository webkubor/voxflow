import os
from pydub import AudioSegment
from .utils import sanitize_path_component

class AudioProcessor:
    def __init__(self, base_dir):
        self.temp_dir = os.path.join(base_dir, "assets/temp")

    def extract_voice_seed(self, audio_path, persona_cn, max_sec=10, skip_start_ms=1500):
        os.makedirs(self.temp_dir, exist_ok=True)
        safe_persona = sanitize_path_component(persona_cn, fallback="未命名角色")
        temp_path = os.path.join(self.temp_dir, f"当前参考_{safe_persona}.wav")
        if os.path.exists(temp_path) and os.path.getmtime(temp_path) >= os.path.getmtime(audio_path):
            return temp_path
        audio = AudioSegment.from_file(audio_path)
        if len(audio) > skip_start_ms + 2000:
            audio = audio[skip_start_ms:]
        audio = self._trim_silence(audio, threshold=-50.0)
        if len(audio) > max_sec * 1000:
            audio = audio[:max_sec * 1000]
        audio.export(temp_path, format="wav")
        return temp_path

    def prepare_clone_reference(self, audio_path, ref_text):
        """Keep the entire utterance paired with its transcript; never crop speech."""
        from uuid import uuid4
        if not isinstance(ref_text, str) or not 1 <= len(ref_text.strip()) <= 1000:
            raise ValueError("请填写与参考音频逐字对应的原文（1–1000 字）")
        with open(audio_path, "rb") as source:
            audio = AudioSegment.from_file(source)
        if not 500 <= len(audio) <= 30000:
            raise ValueError("参考音频须为 0.5–30 秒，请上传一段完整短句")
        if audio.rms == 0:
            raise ValueError("参考音频没有可用声音，请重新录制")
        os.makedirs(self.temp_dir, exist_ok=True)
        target = os.path.join(self.temp_dir, f"reference_{uuid4().hex}.wav")
        with open(target, "wb") as dest:
            audio.set_channels(1).set_frame_rate(24000).export(dest, format="wav")
        return target

    def _trim_silence(self, audio, threshold=-50.0, chunk_size=5):
        def detect(sound):
            it = 0
            while it < len(sound) and sound[it:it+chunk_size].dBFS < threshold:
                it += chunk_size
            return it
        s = detect(audio)
        e = detect(audio.reverse())
        return audio[s : (len(audio) - e)] if s + e < len(audio) else audio

    def apply_post_tuning(
        self,
        path,
        is_dialogue=False,
        trim_head_ms=0,
        trim_tail_ms=0,
        enable_fade=True,
    ):
        """统一后处理。

        - trim_head_ms / trim_tail_ms: 额外裁切首尾，单位毫秒
        - enable_fade: 是否应用极短淡入淡出
        """
        try:
            audio = AudioSegment.from_file(path)
            # 对话模式放宽阈值，保全尾音颤动
            thresh = -55.0 if is_dialogue else -50.0
            audio = self._trim_silence(audio, threshold=thresh)
            if trim_head_ms > 0 and len(audio) > trim_head_ms:
                audio = audio[trim_head_ms:]
            if trim_tail_ms > 0 and len(audio) > trim_tail_ms:
                audio = audio[:-trim_tail_ms]
            audio = audio.normalize(headroom=0.1)
            # 极短淡入淡出，防止切断尾音
            if enable_fade:
                audio = audio.fade_in(50).fade_out(50)
            audio.export(path, format="wav")
            return audio
        except: return None

    def apply_design_cleanup(self, path):
        """设计模式专用净化：尽量只保留文案本体，去掉前后杂音/气口。"""
        try:
            audio = AudioSegment.from_file(path)
            # 设计试听更激进：提高阈值以裁掉低能量杂音
            audio = self._trim_silence(audio, threshold=-45.0)
            # 再小幅裁切首尾，减少起音/尾部杂讯
            head_cut = 20 if len(audio) > 200 else 0
            tail_cut = 20 if len(audio) > 200 else 0
            if head_cut:
                audio = audio[head_cut:]
            if tail_cut and len(audio) > tail_cut:
                audio = audio[:-tail_cut]
            audio = audio.normalize(headroom=0.1)
            # 设计模式关闭淡入，避免“前面像垫了一段”
            audio = audio.fade_out(30)
            audio.export(path, format="wav")
            return audio
        except:
            return None

    def merge_scene(self, segments, output_path, gap_ms=600, overlap_ms=200):
        """【高级重构】支持音频重叠（Cross-fade）缝合，营造交织感"""
        print(f"🧵 正在执行【交叠式】场景缝合 (重叠: {overlap_ms}ms)...")
        combined = AudioSegment.empty()
        
        for i, seg in enumerate(segments):
            if i == 0:
                combined = seg
            else:
                # 核心：在前一段的尾声中，淡入下一段
                # 这种“人声未消，呼吸已至”的效果最真实
                combined = combined.append(seg, crossfade=overlap_ms)
                # 如果间隔大于重叠，补一点静音
                if gap_ms > overlap_ms:
                    combined += AudioSegment.silent(duration=gap_ms - overlap_ms)
        
        combined.export(output_path, format="wav")
        # 总轨脱水（温和模式）
        self.apply_post_tuning(output_path, is_dialogue=True)
        print(f"✅ 场景总轨已完成交叠缝合与呼吸保全。")
