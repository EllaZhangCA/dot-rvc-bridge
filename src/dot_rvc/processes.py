"""Manage only an engine process launched by this checkout."""
import json
from pathlib import Path
import socket
import subprocess


def launch(root):
    import psutil
    root = Path(root).resolve()
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 18888)) == 0:
            raise RuntimeError("Port 18888 is already in use. Stop that engine before using this launcher.")
    python = root / "runtime/engine-venv/Scripts/python.exe"
    script = root / "scripts/run_easy_engine.py"
    with (root / "runtime/easy-engine.log").open("wb") as log:
        proc = subprocess.Popen([str(python), "-u", str(script)], cwd=root, stdout=log,
                                stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    record = {"pid": proc.pid, "started": psutil.Process(proc.pid).create_time(),
              "executable": str(python), "script": str(script)}
    (root / "runtime/easy-process.json").write_text(json.dumps(record), encoding="utf-8")
    return proc


def stop(root):
    import psutil
    root = Path(root).resolve()
    file = root / "runtime/easy-process.json"
    if not file.exists():
        return
    record = json.loads(file.read_text(encoding="utf-8"))
    try:
        process = psutil.Process(record["pid"])
        if (abs(process.create_time() - record["started"]) > 0.1
                or Path(process.exe()).resolve() != Path(record["executable"]).resolve()
                or record["script"] not in process.cmdline()):
            raise RuntimeError("Engine PID identity changed; refusing to stop an unrelated process.")
        children = process.children(recursive=True)
        for child in children:
            if child.name().lower() == "python.exe" and record["script"] in child.cmdline():
                child.terminate()
        process.terminate()
        psutil.wait_procs([process, *children], timeout=5)
    except psutil.NoSuchProcess:
        return
