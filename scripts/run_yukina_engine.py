"""Run the pinned engine with the provisioned data-only Minato Yukina profile.

This wrapper does not alter upstream files. Source checkout and dependencies are
installed by install-engine.ps1. Model/sample downloads are a separate step.
"""
import os
from pathlib import Path
import sys
import json
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/source/voice-changer-d8ef15799470193f7c8176ef471245753a656626/server"


def main():
    profile = ROOT / "runtime/safe-service-yukina"
    if not (profile / "provisioning.json").is_file():
        raise RuntimeError("Run scripts/prepare-yukina-service.py before starting this profile.")
    os.chdir(SOURCE)
    sys.path.insert(0, str(SOURCE))
    sys.path.insert(0, str(ROOT / "src"))
    from safe_engine_runtime_yukina import install
    from dot_rvc.safe_api import SafeAPI
    safety = install(ROOT, SOURCE)
    # Upstream /info expects sample catalogs even with no character installed.
    # Keep an empty local catalog instead of downloading advertised sample voices.
    from const import getSampleJsonAndModelIds
    sample_urls, _ = getSampleJsonAndModelIds("production")
    for url in sample_urls:
        catalog = SOURCE / Path(urlsplit(url).path).name
        if not catalog.exists():
            catalog.write_text(json.dumps({"RVC": []}), encoding="utf-8")
    # The upstream parser runs on import. Keep it separate from this wrapper.
    sys.argv = ["MMVCServerSIO.py", "--host", "127.0.0.1", "-p", "18888",
                "--https", "false", "--content_vec_500_onnx_on", "false",
                "--model_dir", str(profile / "model_dir")]
    import MMVCServerSIO
    import uvicorn
    if MMVCServerSIO.voiceChangerManager.serverDevice.settings.serverAudioStated != 0:
        raise RuntimeError("Safe profile must start paused")
    uvicorn.run(SafeAPI(MMVCServerSIO.app_fastapi, safety), host="127.0.0.1", port=18888,
                log_level="info", access_log=False)


if __name__ == "__main__":
    main()
