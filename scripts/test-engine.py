"""Base inference smoke test, without loading a character model or microphone."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "engine-manifest.json").read_text(encoding="utf-8"))
SOURCE = ROOT / "runtime/source" / ("voice-changer-" + MANIFEST["source_commit"]) / "server"
os.chdir(SOURCE)
sys.path.insert(0, str(SOURCE))

import torch
from voice_changer.RVC.embedder.FairseqHubert import FairseqHubert
from voice_changer.RVC.pitchExtractor.RMVPEPitchExtractor import RMVPEPitchExtractor

embedder = FairseqHubert().loadModel("pretrain/hubert_base.pt", torch.device("cuda:0"), False)
audio = torch.sin(torch.arange(16000, device="cuda:0") * (2 * torch.pi * 220 / 16000)) * 0.02
with torch.inference_mode():
    features = embedder.extractFeatures(audio.unsqueeze(0))
pitch = RMVPEPitchExtractor("pretrain/rmvpe.pt", 0)
with torch.inference_mode():
    f0 = pitch.rmvpe.infer_from_audio_t(audio, thred=0.03)
torch.cuda.synchronize()
assert features.shape[-1] == 256 and len(f0) > 0
report = {"cuda": torch.cuda.is_available(), "gpu": torch.cuda.get_device_name(0),
          "torch": torch.__version__, "hubert_feature_shape": list(features.shape),
          "pitch_frames": len(f0), "character_conversion_verified": False}
(ROOT / "runtime/base-inference-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
