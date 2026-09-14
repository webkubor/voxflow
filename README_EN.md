# VoxFlow

A local-first Chinese TTS workstation for creators, AI, and agents. It combines voice cloning, text-guided voice design, multi-speaker dialogue synthesis, Suno music workflows, and release-material packaging in one workspace.

<p align="center">
  <img src="assets/branding/logo-icon.png" width="160" alt="VoxFlow logo"/>
</p>

<p align="center">
  <img src="assets/branding/social-banner.png" width="100%" alt="VoxFlow — AI Voice and Music Workflow"/>
</p>

## Quick start

```bash
git clone https://github.com/webkubor/voxflow.git
cd voxflow
chmod +x install.sh && ./install.sh
source .venv/bin/activate
voice --help
```

The installer creates `.venv`, installs the Python dependencies, downloads the Base model, and optionally downloads VoiceDesign.

## Requirements

| Requirement | Notes |
| :--- | :--- |
| Platform | **macOS on Apple Silicon is required.** The TTS engine runs on Apple MLX; there is no CPU fallback — the PyTorch path was removed on 2026-09-14. `voice doctor` reports FAIL (not WARN) on anything else. |
| Python | 3.10+ (developed on 3.14.7). |
| Disk | About 2.9 GB for Base-1.7B-8bit, plus about 2.9 GB for VoiceDesign-1.7B-8bit (MLX 8-bit weights, ~5.8 GB total). |
| FFmpeg | Recommended for MP3 reference audio and automatic trimming. Install on macOS with `brew install ffmpeg`. |
| Node.js / npm | Needed only to modify or rebuild the Vue UI: `cd web/ui && npm install && npm run build`. |

For a manual Python setup, or when `voice doctor` reports missing packages:

```bash
pip install -e .
pip install pydub "huggingface_hub[cli]"

# mlx-audio needs --no-deps: it declares transformers>=5.14 while this project
# pins transformers==4.57.3. Resolving normally would either upgrade transformers
# (which breaks the CLI) or silently downgrade mlx-audio to an incompatible 0.2.x.
pip install --no-deps "mlx-audio==0.5.3"
pip install miniaudio scipy sounddevice tqdm
```

## TTS backend: Apple MLX 8-bit

Since 2026-09-14 the engine runs Qwen3-TTS via **Apple MLX** instead of PyTorch(MPS),
using the 8-bit quantised weights from `mlx-community`.

| Metric | PyTorch + MPS | Apple MLX 8-bit |
| :--- | :---: | :---: |
| Model size (Base + VoiceDesign) | 8.4 GB | **5.8 GB** (−31%) |
| Single inference | 9.32 s | **5.29 s** (1.76× faster) |
| Output duration (same text/voice) | 4.64 s | 4.56 s |
| Peak memory | — | 6.97 GB (measured) |
| Load time | 14.44 s | 6.55 s cold / 5.74 s warm |

The speed-up is not because MLX is intrinsically faster. The PyTorch build relied on
`PYTORCH_ENABLE_MPS_FALLBACK=1`, which **silently falls back to CPU** for unsupported
operators — wasting unified memory with no visible signal. MLX has no fallback: either
everything runs on the Metal GPU or it errors. Eliminating that class of silent
degradation was the point of the migration.

Speaker fidelity is **unchanged**: x-vector cosine similarity against the reference is
0.9934 on MLX vs 0.9931 on PyTorch, a 0.0006 gap that equals the seed-to-seed noise
floor. Migration is neutral here — do not treat it as a compensating win.

Two limitations to know:

1. **No dynamic emotion instruction on the clone path.** MLX's Base model has no
   `instruct` entry point at source level. PyTorch's `instruct_ids` genuinely worked
   (verified by a controlled experiment), so this is a net loss, not a no-op. Write
   emotion into the text itself, or use voice design (VoiceDesign supports instructions).
2. **`ref_text` is required.** The transcript of the reference audio must be set in
   `personas.json`; leaving it empty produces truncated, garbled output.

Full decision record, change list and rollback steps: [docs/MLX_MIGRATION.md](docs/MLX_MIGRATION.md).

## Main commands

```bash
voice voice list
voice clone <persona> "Hello from VoxFlow"
voice design <voice_name> "This is a short modeling sentence" --tone "warm, clean, intimate"
voice dialogue configs/dialogue.json
voice doctor
voice web
```

## Current capabilities

| Capability | Status | Entry point |
| :--- | :---: | :--- |
| Voice cloning | Available | `voice clone` or the Clone tab. `--tone` / `--emotion` do **not** apply on this path (see limitations above) — the CLI says so explicitly instead of failing silently. |
| Voice design | Available | `voice design` or the Design tab. Supports instructions natively. |
| Multi-speaker dialogue | Available | `voice dialogue <config.json>` or the Dialogue tab |
| Web UI | Available | `voice web` → `http://localhost:8866` |
| Presets and task history | Available | `voice preset` and `voice job` |
| AI script generation / polishing | Optional | Any OpenAI-compatible backend via `VOXFLOW_LLM_*` environment variables |

## Optional AI writing backend

Script generation and polishing use an OpenAI-compatible API. The default is a local FreeLLMAPI endpoint, but any compatible gateway can be selected without code changes:

```bash
export VOXFLOW_LLM_BASE_URL="https://your-gateway.example/v1"
export VOXFLOW_LLM_MODEL="your-model"
```

Inject `VOXFLOW_LLM_API_KEY` through the runtime environment or a secret manager; never write it to a config file or the repository.

Without an LLM backend, the core TTS workflows continue to work normally.

## Next direction

- Make TTS providers configurable: local Qwen3-TTS by default, cloud providers as an option.
- Add high-resolution cover generation and platform-specific release SOPs.
- Verify third-party music distribution services before building further upload automation.

## License

[Apache-2.0](LICENSE)
