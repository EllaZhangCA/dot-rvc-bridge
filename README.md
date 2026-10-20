# Dot RVC Bridge

**Give Dot a different voice with your own RVC model, locally on Windows.**

English · [简体中文](README_CN.md) · [Download Windows Easy Edition](https://github.com/EllaZhangCA/dot-rvc-bridge/releases/tag/v0.3.1)

A desktop controller, installer, and optional MCP server for routing Dot's playback through a local RVC engine. Includes model import, playback selection, pitch control, original-voice bypass, and start/pause.

This independent community project converts audio played on your PC; it is not an official OpenAI plugin or a native Dot voice API. The first release targets **Windows x64 with an NVIDIA GPU**. Local use was reported successful on an RTX 3090.

## Quick start

1. Download **dot-rvc-bridge-0.3.1-windows-easy.zip** from [Releases](https://github.com/EllaZhangCA/dot-rvc-bridge/releases/tag/v0.3.1). Extract to a permanent, writable folder. Choose this asset, not GitHub's automatic “Source code” ZIP.
2. Double-click **Setup.cmd**. It installs private Python environments, CUDA-enabled PyTorch, the pinned engine, and base inference assets. The first install needs internet access, several GB of downloads, and about 15 GB of free disk space. No manual Python, Node.js, or C++ compiler installation is needed.
3. If VB-CABLE is missing, setup opens its signed installer. Accept the Windows administrator prompt for **BUREL VINCENT**, click **Install Driver**, and restart if requested. Keep your usual microphone and speakers as Windows defaults.
4. Double-click **Start.cmd**. Click **Import .pth**, select your model, choose playback headphones/speakers, then click **Start**.
5. In **Windows Settings → System → Sound → Volume mixer**, set the app hosting Dot to output to **CABLE Input (VB-Audio Virtual Cable)**. Keep Dot's microphone set to your normal microphone. Start a conversation and listen.

If the app is absent from the mixer, play audio in it first. App-level routing can include its other sounds. The launcher does not change Windows defaults or per-app routing.

```text
Dot app → CABLE Input → CABLE Output → RVC → headphones / speakers
Your microphone ─────────────────────────→ Dot
```

**Restore normal sound:** enable **Original voice** while the engine runs, or change the app's Windows output back to your headphones/speakers. Pausing or closing the engine silences audio still routed to the cable.

## Support and limits

| v0.3.1 supports | Details |
| --- | --- |
| RVC inference checkpoints | Standard **v2, f0=1**, 18-item configuration, 32/40/48 kHz |
| Pitch extraction | RMVPE; NVIDIA GPU 0 |
| Pitch control | −24 to +24 semitones |
| Audio | Windows WASAPI; 48 kHz cable/output route |
| Model selection | One active profile; import another model to switch |

Find and download your own RVC character `.pth` on [Hugging Face](https://huggingface.co/models). This project does not choose, host, bundle, or automatically download character weights. **No local character weights, indexes, converted model bundles, recordings, or personal settings are included.** Models undergo structural and size checks; not every checkpoint is compatible. Raw bundles are limited to 100 MB. RVC v1, no-f0 models, training checkpoints, `.index` retrieval, CPU-only use, and other operating systems are outside this release's supported path. The desktop uses speaker 0 for multi-speaker models.

RVC changes timbre; source rhythm, expression, and pronunciation still matter. Use models and demo audio you have permission to use and share.

## The easy ZIP

Includes the bilingual controller, source, official **uv 0.13.2**, prebuilt **fairseq 0.12.2** and ANTLR wheels, manifests, and license notices. This is an **online installer**. Engine source, PyTorch, base assets, and VB-CABLE are downloaded during setup.

Runtime files stay in `.venv/` and `runtime/`. Moving the folder after installation can break environment paths; install again in a new folder instead. There is no automatic updater.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Download failed | Retry Setup.cmd with access to GitHub, PyPI, PyTorch, and Hugging Face. Hash mismatches stop installation. |
| No CABLE devices | Complete driver installation, restart if requested, and relaunch. |
| Port 18888 occupied | Stop the other RVC instance first; the launcher will not terminate an unrelated process. |
| No voice after Start | Check app output, CABLE installation, playback selection, and `runtime/easy-engine.log`. |
| Device changed/unplugged | Pause, stop the engine, refresh devices, choose the output, and start again. |
| Import rejected | Use a standard RVC v2 inference .pth with pitch guidance; see `runtime/desktop.log`. |
| Double playback | Disable Windows “Listen to this device” on the cable and check other monitoring paths. |

The default buffer is 64 × 128 samples at 48 kHz: about 171 ms **of input buffering**, not measured total latency. See [validation scope](docs/VALIDATION.md).

## Optional MCP controls

Setup writes a machine-local `mcp.json`. Use its stdio entry with a compatible **local** MCP host after the desktop loads the engine. A cloud host's localhost is not your PC; direct Dot-to-MCP control has not been verified for this release.

Tools: `get_voice_status`, `list_local_models`, `list_voice_models`, `select_voice_model`, `set_voice_pitch`, `set_voice_index_ratio`, `start_voice_audio`, `pause_voice_audio`, and `set_voice_bypass`. Configure devices through the desktop or CLI first. The protected service has one active slot and keeps index ratio at zero.

## Development

```powershell
uv run --no-project --python 3.13.5 scripts/bootstrap.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/package-source.py
```

Source installation fetches pinned wheels from this repository's release. Desktop, CLI, and MCP share `Engine`; adapters implement `read_state()` and `write_setting()`. Model import and the legacy CUDA engine use separate environments joined by a validated raw tensor format.

See [architecture](docs/DESIGN.md), [extensions](docs/EXTENDING.md), [model handling](docs/MODEL_SAFETY.md), and [release builds](docs/RELEASING.md).

Original bridge code is [MIT licensed](LICENSE). [Third-party components](THIRD_PARTY.md), model assets, and VB-CABLE retain their own terms. Thanks to [w-okada/voice-changer](https://github.com/w-okada/voice-changer), [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI), and the underlying model and library authors.
