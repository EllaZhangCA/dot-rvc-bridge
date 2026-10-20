"""Data-only Exusiai model reader. Never imports pickle or calls torch.load.

The digest is a reviewed artifact identity, not a signature or arbitrary-model
approval. A different character requires separate restricted validation.
"""
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile

BUNDLE_SHA256 = "7659e492e3aae334d32e0a39743dbfbed3d63cabb76cc44bd6b06c3a3de3c02a"
CONFIG = [1025, 32, 192, 192, 768, 2, 6, 3, 0, "1", [3, 7, 11],
          [[1, 3, 5], [1, 3, 5], [1, 3, 5]], [12, 10, 2, 2], 512,
          [24, 20, 4, 4], 109, 256, 48000]
MAX_BUNDLE = 100_000_000


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON constant")


def read_bundle(path, expected_sha256=BUNDLE_SHA256, *, config=CONFIG, sr="48k", count=457):
    """Hash the exact bounded bytes subsequently parsed; no extraction to disk."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular data bundle")
    with path.open("rb") as file:
        data = file.read(MAX_BUNDLE + 1)
    if len(data) > MAX_BUNDLE or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Unapproved or changed data bundle")
    return decode_bundle(data, config=config, sr=sr, count=count)


def decode_bundle(data, *, config=CONFIG, sr="48k", count=457):
    """Validate the plain schema; production callers must verify the digest first."""
    if len(data) > MAX_BUNDLE:
        raise ValueError("Oversized data bundle")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if type(count) is not int or not 1 <= count <= 2048:
            raise ValueError("Invalid tensor count")
        if len(infos) != count + 1 or len({i.filename for i in infos}) != len(infos):
            raise ValueError("Unexpected or duplicate archive members")
        for item in infos:
            if item.compress_type != zipfile.ZIP_STORED or item.flag_bits & 1:
                raise ValueError("Only uncompressed unencrypted data is supported")
            if item.file_size > 50_000_000 or item.file_size != item.compress_size:
                raise ValueError("Oversized or inconsistent member")
        if archive.getinfo("manifest.json").file_size > 500_000:
            raise ValueError("Oversized manifest")
        manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=_object,
                              parse_constant=_constant)
        if set(manifest) != {"format", "byteorder", "config", "version", "f0", "sr", "tensors"}:
            raise ValueError("Unexpected manifest fields")
        if (manifest["format"] != "dot-rvc-oneoff-raw-v1" or manifest["byteorder"] != "little"
                or manifest["version"] != "v2" or type(manifest["f0"]) is not int
                or manifest["f0"] != 1 or manifest["sr"] != sr
                or manifest["config"] != config):
            raise ValueError("Unsupported RVC configuration")
        tensors = manifest["tensors"]
        if type(tensors) is not list or len(tensors) != count:
            raise ValueError("Unexpected tensor count")
        weights = {}
        for i, item in enumerate(tensors):
            if type(item) is not dict or set(item) != {"name", "file", "dtype", "shape", "bytes", "sha256"}:
                raise ValueError("Unexpected tensor metadata")
            name, shape, dtype = item["name"], item["shape"], item["dtype"]
            if (type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_.]{1,200}", name)
                    or name in weights or item["file"] != f"{i:04d}.bin"):
                raise ValueError("Invalid tensor identity")
            if dtype not in ("<f2", "<f4", "<f8") or type(shape) is not list or len(shape) > 5:
                raise ValueError("Invalid tensor type")
            if any(type(n) is not int or not 0 < n <= 8192 for n in shape):
                raise ValueError("Invalid tensor shape")
            size = math.prod(shape) * int(dtype[-1])
            if type(item["bytes"]) is not int or size != item["bytes"] or size > 50_000_000:
                raise ValueError("Invalid tensor size")
            member = archive.getinfo(item["file"])
            if member.file_size != size:
                raise ValueError("Tensor size mismatch")
            raw = archive.read(item["file"])
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError("Tensor digest mismatch")
            weights[name] = (dtype, shape, raw)
        if set(archive.namelist()) != {"manifest.json", *(f"{i:04d}.bin" for i in range(count))}:
            raise ValueError("Unexpected archive member")
        if "emb_g.weight" not in weights or weights["emb_g.weight"][1] != [config[-3], config[-2]]:
            raise ValueError("Invalid speaker embedding")
    return manifest, weights


def load_tensors(path, expected_sha256=BUNDLE_SHA256, *, config=CONFIG, sr="48k", count=457):
    manifest, raw_weights = read_bundle(path, expected_sha256, config=config, sr=sr, count=count)
    import numpy as np
    import torch
    weights = {}
    for name, (dtype, shape, raw) in raw_weights.items():
        array = np.frombuffer(raw, dtype=dtype).copy().reshape(shape)
        if not np.isfinite(array).all():
            raise ValueError("Non-finite tensor")
        weights[name] = torch.from_numpy(array)
    return {"weight": weights, "config": manifest["config"], "version": "v2", "f0": 1, "sr": sr}
