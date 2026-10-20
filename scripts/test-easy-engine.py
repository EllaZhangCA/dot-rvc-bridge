"""Smoke-test an imported model in a separate engine, without opening audio."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--python", type=Path, default=ROOT / "runtime/engine-venv/Scripts/python.exe")
    args = parser.parse_args()
    import httpx
    import psutil
    from dot_rvc.config import Config
    from dot_rvc.engine import Engine
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log_path = ROOT / "runtime/easy-smoke.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen([str(args.python), "-u", str(ROOT / "scripts/run_easy_engine.py"),
                                    "--port", str(port), "--profile", str(args.profile.resolve())],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5) as client:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(log_path.read_text(encoding="utf-8", errors="replace")[-12000:])
                try:
                    status = client.get("/safe_status").json()
                    break
                except httpx.ConnectError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("Engine did not become ready")
            info = client.get("/info").json()
            profile = json.loads((args.profile / "profile.json").read_text(encoding="utf-8"))
            assert status["profile"] == "easy-rvc-v1", status
            assert status["bundle_sha256"] == profile["sha256"], status
            assert info["modelSlots"][0]["samplingRate"] == profile["config"][-1], info
            assert info["serverAudioStated"] == 0, info
            assert info["pipelineInfo"]["inferencer"], info
            engine = Engine(Config(engine_url=f"http://127.0.0.1:{port}"))
            assert engine.set_pitch(2)["pitch_semitones"] == 2
            engine.set_pitch(0)
            assert client.post("/upload_file").status_code == 403
            print(json.dumps({"pipeline_initialized": True, "profile": status["profile"],
                              "sampling_rate": info["modelSlots"][0]["samplingRate"], "settings_readback": True,
                              "audio_started": False, "port": port}, indent=2))
    finally:
        if process.poll() is None:
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            process.terminate()
            process.wait(timeout=10)
            psutil.wait_procs(children, timeout=5)


if __name__ == "__main__":
    main()
