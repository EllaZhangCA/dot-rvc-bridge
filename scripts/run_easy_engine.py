"""Run the easy edition's selected data-only model on loopback."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18888)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "engine-manifest.json").read_text(encoding="utf-8"))
    source = ROOT / "runtime/source" / ("voice-changer-" + manifest["source_commit"]) / "server"
    profile = args.profile or Path(json.loads((ROOT / "runtime/easy-current.json").read_text(encoding="utf-8"))["directory"])
    from dot_rvc.portable_profile import readers
    metadata, reader, loader = readers(profile)
    os.chdir(source)
    sys.path.insert(0, str(source))
    from safe_engine_runtime import install
    from dot_rvc.safe_api import SafeAPI
    status = install(ROOT, source, profile_path=profile, reader=reader, tensor_loader=loader,
                     model_name=metadata["name"], filename="voice.rvcd", sample_rate=metadata["config"][-1],
                     bundle_hash=metadata["sha256"], profile_name="easy-rvc-v1")
    from const import getSampleJsonAndModelIds
    for url in getSampleJsonAndModelIds("production")[0]:
        catalog = source / Path(urlsplit(url).path).name
        if not catalog.exists():
            catalog.write_text('{"RVC": []}', encoding="utf-8")
    sys.argv = ["MMVCServerSIO.py", "--host", "127.0.0.1", "-p", str(args.port),
                "--https", "false", "--content_vec_500_onnx_on", "false", "--model_dir", str(profile / "model_dir")]
    import MMVCServerSIO
    import uvicorn
    MMVCServerSIO.voiceChangerManager.update_settings("modelSlotIndex", 0)
    assert MMVCServerSIO.voiceChangerManager.serverDevice.settings.serverAudioStated == 0
    uvicorn.run(SafeAPI(MMVCServerSIO.app_fastapi, status), host="127.0.0.1", port=args.port,
                log_level="info", access_log=False)


if __name__ == "__main__":
    main()
