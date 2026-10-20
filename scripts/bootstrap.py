"""Windows easy installer. No system Python, Node.js, C++ tools or policy edits."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-cable", action="store_true")
    args = parser.parse_args()
    easy = json.loads((ROOT / "easy-manifest.json").read_text(encoding="utf-8"))
    engine = json.loads((ROOT / "engine-manifest.json").read_text(encoding="utf-8"))
    uv = ROOT / "release-assets/tools/uv.exe"
    if not uv.is_file():
        uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Use the Windows easy ZIP or install uv first.")
    os.environ.setdefault("UV_CACHE_DIR", str(ROOT / "runtime/uv-cache"))
    os.environ.setdefault("UV_PYTHON_INSTALL_DIR", str(ROOT / "runtime/python"))
    os.environ["UV_LINK_MODE"] = "copy"
    def run(*command):
        subprocess.run([str(x) for x in command], check=True, cwd=ROOT)
    def venv(folder, version):
        python = ROOT / folder / "Scripts/python.exe"
        if not python.exists():
            run(uv, "venv", "--python", version, ROOT / folder)
        return python
    print("[1/6] Installing local Python runtimes...", flush=True)
    run(uv, "python", "install", easy["python_control"], engine["python"])
    bridge = venv(".venv", easy["python_control"])
    run(uv, "pip", "install", "--python", bridge, "-e", str(ROOT) + "[audio]")
    print("[2/6] Preparing verified source and base assets...", flush=True)
    run(bridge, ROOT / "scripts/prepare-engine.py")
    source = ROOT / "runtime/source" / ("voice-changer-" + engine["source_commit"])
    (source / "client/demo/dist").mkdir(parents=True, exist_ok=True)
    print("[3/6] Installing CUDA engine (several GB on first run)...", flush=True)
    python = venv("runtime/engine-venv", engine["python"])
    wheels = ROOT / "release-assets/wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("prepare_engine", ROOT / "scripts/prepare-engine.py")
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    for wheel in easy["wheels"]:
        url = f'https://github.com/{easy["repository"]}/releases/download/{easy["release_tag"]}/{wheel["file"]}'
        prepare.download(url, wheels / wheel["file"], wheel["sha256"])
    run(uv, "pip", "install", "--python", python, "torch==" + engine["torch"],
        "torchaudio==" + engine["torchaudio"], "--index-url", "https://download.pytorch.org/whl/cu118")
    run(uv, "pip", "install", "--python", python, "-r", ROOT / "engine-requirements.lock.txt",
        "--find-links", wheels, "--only-binary", ":all:")
    print("[4/6] Installing separate model importer...", flush=True)
    validator = venv("runtime/model-check-venv", easy["python_control"])
    run(uv, "pip", "install", "--python", validator, "torch==" + easy["torch_validator"],
        "--index-url", "https://download.pytorch.org/whl/cpu")
    run(uv, "pip", "install", "--python", validator, "numpy==" + easy["numpy_validator"])
    print("[5/6] Checking virtual cable...", flush=True)
    result = subprocess.run([str(bridge), "-m", "dot_rvc.cli", "devices"], capture_output=True, encoding="utf-8", check=True)
    has_cable = any(d["name"] == "CABLE Output (VB-Audio Virtual Cable)" for d in json.loads(result.stdout)["devices"])
    if not has_cable and not args.skip_cable:
        print("VB-CABLE is needed. Its installer requires your Windows administrator confirmation.", flush=True)
        archive = ROOT / "runtime/downloads/VBCABLE_Driver_Pack45.zip"
        prepare.download("https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip", archive,
                         "b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb")
        import zipfile
        cable = ROOT / "runtime/vb-cable"
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(cable)
        installer = cable / "VBCABLE_Setup_x64.exe"
        path = str(installer).replace("'", "''")
        # Directly invoke the signed installer; no script execution policy changes.
        command = f"$s=Get-AuthenticodeSignature -LiteralPath '{path}'; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'BUREL VINCENT'){{throw 'Invalid driver signature'}}; Start-Process -FilePath '{path}' -Verb RunAs -WindowStyle Normal -Wait"
        run("powershell.exe", "-NoProfile", "-Command", command)
    print("[6/6] Writing local configuration...", flush=True)
    config = ROOT / "dot-rvc.local.toml"
    if not config.exists():
        shutil.copyfile(ROOT / "config.example.toml", config)
    mcp = {"mcpServers": {"dot-rvc-bridge": {"type": "stdio", "command": str(bridge),
           "args": ["-m", "dot_rvc.mcp_server"], "env": {"DOT_RVC_CONFIG": str(config), "PYTHONUTF8": "1"}}}}
    (ROOT / "mcp.json").write_text(json.dumps(mcp, indent=2), encoding="utf-8")
    run(uv, "pip", "check", "--python", python)
    run(bridge, "-c", "import tkinter, sounddevice, psutil; print('Desktop dependencies OK')")
    print("Setup complete. Double-click Start.cmd, import your .pth, and choose your output device.", flush=True)
    print("After driver installation, keep your normal microphone selected in Windows. Reboot if requested.")


if __name__ == "__main__":
    main()
