"""Build the software-only Windows distribution from an explicit asset allowlist."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_source", ROOT / "scripts/package-source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def release_assets(root):
    manifest = json.loads((root / "easy-manifest.json").read_text(encoding="utf-8"))
    assets = [("release-assets/tools/uv.exe", manifest["uv"]["exe_sha256"])]
    assets += [("release-assets/wheels/" + w["file"], w["sha256"]) for w in manifest["wheels"]]
    for name, expected in assets:
        file = root / name
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
            raise ValueError("Missing/unsafe release asset: " + name)
        if digest(file) != expected:
            raise ValueError("Release asset hash mismatch: " + name)
        yield file


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    target = ROOT / "dist" / f"dot-rvc-bridge-{version}-windows-easy.zip"
    target.parent.mkdir(exist_ok=True)
    files = [*source.source_files(ROOT), *release_assets(ROOT)]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            name = file.relative_to(ROOT).as_posix()
            if file.suffix.lower() in {".pth", ".pt", ".index", ".rvcd", ".onnx", ".safetensors"}:
                raise ValueError("Model data must never enter a release: " + name)
            archive.write(file, name)
    manifest = json.loads((ROOT / "easy-manifest.json").read_text(encoding="utf-8"))
    assets = [target, ROOT / "dist" / f"dot-rvc-bridge-{version}-source.zip"]
    assets += [ROOT / "release-assets/wheels" / w["file"] for w in manifest["wheels"]]
    (ROOT / "dist/SHA256SUMS.txt").write_text("".join(f"{digest(p)}  {p.name}\n" for p in assets), encoding="utf-8")
    print(target)
    print(f"{len(files)} allowlisted software files; no character model or runtime directory")


if __name__ == "__main__":
    main()
