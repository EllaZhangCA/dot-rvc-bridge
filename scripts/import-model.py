"""Import a user-selected RVC v2 f0 checkpoint using the modern CPU validator."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dot_rvc.model_safety import require_restricted_loader
from dot_rvc.model_package import MAX_FILE, checkpoint_metadata
from dot_rvc.portable_profile import readers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    require_restricted_loader(importlib.metadata.version("torch"))
    import torch
    torch.set_num_threads(1)
    if args.model.is_symlink() or not args.model.is_file():
        raise ValueError("Select a regular .pth file")
    with args.model.open("rb") as file:
        data = file.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError("Checkpoint exceeds size limit")
    if checkpoint_metadata(data)["format"] != "pytorch_zip_with_pickle":
        raise ValueError("Expected a modern PyTorch ZIP checkpoint; legacy pickle/tar is unsupported")
    spec = importlib.util.spec_from_file_location("normalize_model", ROOT / "scripts/normalize-rvc-model.py")
    normalize = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(normalize)
    checkpoint = normalize.normalize(torch.load(io.BytesIO(data), map_location="cpu", weights_only=True), torch)
    if checkpoint["version"] != "v2" or checkpoint["f0"] != 1:
        raise ValueError("Easy edition supports RVC v2 with f0=1. v1/no-f0 models are not supported yet.")
    profile = args.root.resolve() / "runtime/profiles" / uuid.uuid4().hex
    (profile / "model_dir/0").mkdir(parents=True)
    for folder in ("upload_dir", "tmp_dir", "logs", "no_static_models"):
        (profile / folder).mkdir()
    bundle = profile / "model_dir/0/voice.rvcd"
    manifest = {"format": "dot-rvc-oneoff-raw-v1", "byteorder": "little", "config": checkpoint["config"],
                "version": "v2", "f0": 1, "sr": checkpoint["sr"], "tensors": []}
    types = {torch.float16: "<f2", torch.float32: "<f4", torch.float64: "<f8"}
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as archive:
        for i, (name, tensor) in enumerate(checkpoint["weight"].items()):
            raw = tensor.numpy().tobytes()
            item = {"name": name, "file": f"{i:04d}.bin", "dtype": types[tensor.dtype],
                    "shape": list(tensor.shape), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            archive.writestr(item["file"], raw)
            manifest["tensors"].append(item)
        archive.writestr("manifest.json", json.dumps(manifest))
    metadata = {"format": "dot-rvc-profile-v1", "name": args.model.stem[:100],
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(), "config": checkpoint["config"],
                "version": "v2", "f0": 1, "tensor_count": len(manifest["tensors"])}
    (profile / "profile.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _, read, _ = readers(profile)
    read(bundle)
    (profile / "stored_setting.json").write_text(json.dumps({"gpu": 0, "f0Detector": "rmvpe"}), encoding="utf-8")
    current = args.root.resolve() / "runtime/easy-current.json"
    temporary = current.with_suffix(".tmp")
    temporary.write_text(json.dumps({"directory": str(profile), "name": metadata["name"]}), encoding="utf-8")
    temporary.replace(current)
    print(json.dumps({"imported": True, "name": metadata["name"], "profile": str(profile), "index_enabled": False}))


if __name__ == "__main__":
    main()
