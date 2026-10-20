"""Offline real-engine integration check. No server, audio devices or base loads."""
import argparse
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "runtime/source/voice-changer-d8ef15799470193f7c8176ef471245753a656626/server")
    parser.add_argument("--report", type=Path, default=ROOT / "runtime/safe-service-offline.json")
    args = parser.parse_args()
    source = args.source.resolve()
    os.chdir(source)
    sys.path.insert(0, str(source))
    import torch
    import sounddevice as sd
    import faiss
    attempts = []
    def prohibited(*args, **kwargs):
        attempts.append("prohibited_loader_or_audio")
        raise RuntimeError("Offline test forbids checkpoint deserialization, index parsing and audio streams")
    # Underlying legacy loader is a sentinel. A character fallback cannot pass.
    torch.load = prohibited
    torch.serialization.load = prohibited
    faiss.read_index = prohibited
    for name in ("InputStream", "OutputStream", "Stream", "RawInputStream", "RawOutputStream", "RawStream", "play", "rec", "playrec"):
        setattr(sd, name, prohibited)
    from safe_engine_runtime import install
    status = install(ROOT, source)
    from const import EnumInferenceTypes
    from voice_changer.RVC.inferencer.InferencerManager import InferencerManager
    from voice_changer.RVC.inferencer.RVCInferencerv2 import RVCInferencerv2
    from voice_changer.VoiceChangerManager import VoiceChangerManager
    import voice_changer.ModelSlotManager as slot_manager
    import voice_changer.RVC.pipeline.PipelineGenerator as pipeline
    bundle = ROOT / "runtime/safe-service/model_dir/0/exusiai.rvcd"
    directory = bundle.parent.parent
    slots = slot_manager.loadAllSlotInfo(str(directory))
    assert len(slots) == 1 and slots[0].slotIndex == 0 and slots[0].indexFile == ""
    rejected = 0
    def reject(call):
        nonlocal rejected
        try:
            call()
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("Disabled operation unexpectedly succeeded")
    reject(lambda: torch.load(ROOT / "models/exusiai/Exusiai_arknights_301.pth"))
    reject(lambda: torch.serialization.load(ROOT / "models/exusiai-normalized/exusiai.normalized.pth"))
    reject(lambda: torch.load(io.BytesIO(b"never inspect this")))
    reject(lambda: InferencerManager.getInferencer(EnumInferenceTypes.pyTorchRVC, str(bundle), -1))
    reject(lambda: RVCInferencerv2().loadModel(str(bundle.with_suffix(".pth")), -1))
    reject(lambda: pipeline._loadIndex(str(bundle.parent / "unverified.index")))
    assert pipeline._loadIndex(str(bundle.parent)) is None
    for name in ("loadModel", "merge_models", "export2onnx", "update_model_info", "update_model_default", "upload_model_assets"):
        reject(lambda name=name: getattr(VoiceChangerManager, name)(None, None))
    mic = SimpleNamespace(name="Microphone (Shure MV88+)", hostAPI="Windows WASAPI")
    headphones = SimpleNamespace(name="Headphones (Shure MV88+)", hostAPI="Windows WASAPI")
    device = SimpleNamespace(settings=SimpleNamespace(serverAudioStated=0, serverInputDeviceId=1,
        serverOutputDeviceId=2, serverMonitorDeviceId=-1, serverAudioSampleRate=48000, enableServerAudio=1),
        getServerInputAudioDevice=lambda _: mic, getServerOutputAudioDevice=lambda _: headphones)
    manager = SimpleNamespace(serverDevice=device, voiceChangerModel=SimpleNamespace(pipeline=object()))
    reject(lambda: VoiceChangerManager.update_settings(manager, "serverAudioStated", 1))
    device.settings.serverAudioStated = 1
    reject(lambda: VoiceChangerManager.update_settings(manager, "modelSlotIndex", 0))
    torch.set_num_threads(2)
    results = []
    for gpu in ([-1, 0] if torch.cuda.is_available() else [-1]):
        inferencer = InferencerManager.getInferencer(EnumInferenceTypes.pyTorchRVCv2, str(bundle), gpu, "v2")
        parameter = next(inferencer.model.parameters())
        device, dtype = parameter.device, parameter.dtype
        with torch.no_grad():
            output = inferencer.infer(torch.zeros((1, 20, 768), device=device, dtype=dtype),
                torch.tensor([20], device=device), torch.full((1, 20), 100, device=device, dtype=torch.long),
                torch.full((1, 20), 220.0, device=device, dtype=dtype),
                torch.tensor([0], device=device), None)
        assert tuple(output.shape) == (9600,) and bool(torch.isfinite(output).all())
        results.append(dict(device=str(device), dtype=str(dtype), output_shape=list(output.shape), finite=True))
    # Exercise the real upstream FastAPI form endpoint directly in memory.
    from fastapi import FastAPI
    from restapi.MMVC_Rest_Fileuploader import MMVC_Rest_Fileuploader
    from dot_rvc.safe_api import SafeAPI
    class FakeManager:
        def __init__(self):
            self.writes = []
        def get_info(self):
            return {"status": "OK", "serverAudioStated": 0}
        def update_settings(self, key, val):
            self.writes.append((key, val))
            return self.get_info()
    fake = FakeManager()
    app = FastAPI()
    app.include_router(MMVC_Rest_Fileuploader(fake).router)
    async def api_check():
        safe_app = SafeAPI(app, status)
        async def request(method, path, data=None):
            body = urlencode(data or {}).encode("ascii")
            headers = [(b"content-type", b"application/x-www-form-urlencoded"),
                       (b"content-length", str(len(body)).encode("ascii"))]
            scope = dict(type="http", asgi={"version": "3.0"}, http_version="1.1",
                method=method, path=path, raw_path=path.encode("ascii"), query_string=b"",
                root_path="", scheme="http", headers=headers, client=("127.0.0.1", 1),
                server=("127.0.0.1", 18888))
            messages = []
            delivered = False
            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}
            async def send(message):
                messages.append(message)
            await safe_app(scope, receive, send)
            code = next(m["status"] for m in messages if m["type"] == "http.response.start")
            content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
            return code, json.loads(content)
        assert (await request("GET", "/info"))[1]["status"] == "OK"
        code, content = await request("POST", "/update_settings", {"key": "serverAudioStated", "val": "0"})
        assert code == 200 and content["status"] == "OK"
        assert (await request("POST", "/load_model"))[0] == 403
        assert (await request("GET", "/onnx"))[0] == 403
        assert (await request("POST", "/update_settings", {"key": "modelSlotIndex", "val": "1000"}))[0] == 400
    asyncio.run(api_check())
    assert fake.writes == [("serverAudioStated", 0)]
    assert not attempts and not status["base_checkpoint_loads"]
    assert "MMVCServerSIO" not in sys.modules
    report = dict(passed=True, data_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        rejected_direct_operations=rejected, real_inferencer_results=results,
        upstream_http_form_contract=True, tested_with_in_memory_asgi=True,
        role_pickle_fallback_calls=len(attempts), base_checkpoint_loads=[],
        microphone=False, playback=False, service_started=False, source_modified=False,
        full_audio_pipeline_tested=False, dot_integration_verified=False)
    with args.report.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    main()
