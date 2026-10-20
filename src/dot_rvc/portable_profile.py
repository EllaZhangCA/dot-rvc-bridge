"""Per-user model profiles for the Windows easy installer."""
import json
from pathlib import Path
import re

from .safe_model import read_bundle, load_tensors


def read_profile(directory):
    directory = Path(directory).resolve()
    data = json.loads((directory / "profile.json").read_text(encoding="utf-8"))
    config = data["config"]
    if (data.get("format") != "dot-rvc-profile-v1" or data.get("version") != "v2"
            or data.get("f0") != 1 or not isinstance(config, list) or len(config) != 18
            or config[-1] not in (32000, 40000, 48000)
            or type(config[-3]) is not int or not 1 <= config[-3] <= 8192
            or config[-2] != 256 or type(data.get("tensor_count")) is not int
            or not 1 <= data["tensor_count"] <= 2048
            or not re.fullmatch(r"[a-f0-9]{64}", str(data.get("sha256", "")))):
        raise ValueError("Unsupported profile: expected standard RVC v2 with pitch guidance")
    return data


def readers(directory):
    profile = read_profile(directory)
    options = dict(config=profile["config"], sr=f'{profile["config"][-1] // 1000}k', count=profile["tensor_count"])
    def read(path):
        return read_bundle(path, profile["sha256"], **options)
    def load(path):
        return load_tensors(path, profile["sha256"], **options)
    return profile, read, load
