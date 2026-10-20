"""Provision a NEW local data-only slot, without starting or contacting a service."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dot_rvc.safe_model import BUNDLE_SHA256, read_bundle


def prepare(root=ROOT):
    root = Path(root).resolve()
    source = root / "runtime/exusiai-model-validation/tensors.zip"
    read_bundle(source)
    # Verify the same bytes used for the copy, not a previous filesystem read.
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != BUNDLE_SHA256:
        raise ValueError("Validated data changed")
    profile = root / "runtime/safe-service"
    if profile.exists() or profile.is_symlink():
        raise ValueError("Profile already exists; refusing to overwrite it")
    (profile / "model_dir/0").mkdir(parents=True)
    for name in ("upload_dir", "tmp_dir", "logs", "no_static_models"):
        (profile / name).mkdir()
    bundle = profile / "model_dir/0/exusiai.rvcd"
    with bundle.open("xb") as file:
        file.write(data)
    read_bundle(bundle)
    (profile / "stored_setting.json").write_text(
        json.dumps({"f0Detector": "rmvpe", "gpu": 0}, indent=2), encoding="utf-8")
    report = {"profile": "exusiai-data-only-v1", "bundle_sha256": BUNDLE_SHA256,
              "slot": 0, "model_selected": False, "service_started": False,
              "audio_started": False, "index_included": False,
              "original_model_dir_modified": False}
    (profile / "provisioning.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
