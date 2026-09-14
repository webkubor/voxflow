class DesignMode:
    """【模块 2：音色设计】 2026-09-14 迁 Apple MLX

    MLX 的 generate_voice_design(text, instruct, language, ...) 跟原 PyTorch
    的 generate_voice_design(text, language, instruct) 参数顺序略不同，
    但功能等价：纯文本凭空捏一个音色 + 情绪指令。
    """
    def __init__(self, engine, processor=None):
        # 兼容旧签名（processor 没人用了，但调用方可能还在传），保留参数
        self.engine = engine

    def run(self, text, lang, instruct):
        print(f"🎨 模式：音色设计 | 指令集：{instruct}")
        # MLX 设计路径：参数顺序 (text, instruct, language)，不是 (text, language, instruct)
        results = list(self.engine.wrapped_model.generate_voice_design(
            text=text,
            instruct=instruct,
            language="chinese",
        ))
        sr = self.engine.sample_rate
        wavs = [r.audio for r in results]
        return wavs, sr
