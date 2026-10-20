"""Download verified upstream source and RVC base assets; never character weights."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "engine-manifest.json").read_text(encoding="utf-8"))


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def download(url, target, expected_hash):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != expected_hash:
            raise RuntimeError(f"Hash mismatch in existing {target}; inspect/remove it before retrying.")
        return
    partial = target.with_suffix(target.suffix + ".part")
    # curl resumes partial files; a cache buster avoids expired CDN redirects.
    separator = "&" if "?" in url else "?"
    subprocess.run(["curl.exe", "-fL", "--retry", "2", "--connect-timeout", "20",
                    "--max-time", "900", "--speed-limit", "1024", "--speed-time", "45",
                    "--silent", "--show-error", "-C", "-", "-o", str(partial),
                    url + separator + "download=true&nonce=" + str(time.time_ns())], check=True)
    if sha256(partial) != expected_hash:
        raise RuntimeError(f"Downloaded hash mismatch: {partial}; file was not activated.")
    partial.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-only", action="store_true")
    args = parser.parse_args()
    source_root = ROOT / "runtime/source"
    checkout = source_root / ("voice-changer-" + MANIFEST["source_commit"])
    if not args.assets_only:
        archive = ROOT / "runtime/downloads/voice-changer-d8ef157.zip"
        download(MANIFEST["source_url"], archive, MANIFEST["source_sha256"])
        if not checkout.exists():
            with zipfile.ZipFile(archive) as zipped:
                for info in zipped.infolist():
                    dest = (source_root / info.filename).resolve()
                    if not dest.is_relative_to(source_root.resolve()) or ":" in info.filename:
                        raise RuntimeError("Unsafe archive path")
                zipped.extractall(source_root)
    server = checkout / "server"
    if not server.exists():
        raise RuntimeError("Source checkout missing")
    (server / "model_dir").mkdir(exist_ok=True)
    for asset in MANIFEST["assets"]:
        print("Preparing " + asset["file"], flush=True)
        download(asset["url"], server / "pretrain" / asset["file"], asset["sha256"])
    print("Pinned source and RVC base assets ready; no character model installed.")


if __name__ == "__main__":
    main()
