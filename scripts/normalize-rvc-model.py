"""Opt-in restricted validation in a separately approved, patched PyTorch runtime.

Never use this with the legacy RVC engine Python. No network, microphone, or index
loading. No unsafe pickle fallback. Output is a new canonical tensor checkpoint.
"""

import argparse
from collections import OrderedDict
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dot_rvc.model_package import MAX_FILE, checkpoint_metadata
from dot_rvc.model_safety import check_torch_version, require_restricted_loader


def plain_config(value, depth=0):
    if depth > 4:
        raise ValueError("config 嵌套过深")
    if type(value) is list and 0 < len(value) <= 32:
        return [plain_config(v, depth + 1) for v in value]
    if type(value) is int and 0 <= value <= 100000:
        return value
    if type(value) is float and math.isfinite(value) and -64 <= value <= 64:
        return value
    if type(value) is str and value in {"1", "2"}:
        return value
    raise ValueError("config 包含不支持的类型或范围")


def normalize(cpt, torch):
    if type(cpt) not in (dict, OrderedDict):
        raise ValueError("只接受字典形式的 RVC 推理模型")
    config = cpt.get("config")
    if type(config) is not list or len(config) != 18:
        raise ValueError("当前验证器只支持标准 18 项 config 的 RVC v1/v2")
    config = plain_config(config)
    if config[-1] not in (32000, 40000, 48000):
        raise ValueError("不支持的模型采样率")
    version, f0 = cpt.get("version", "v1"), cpt.get("f0")
    if type(version) is not str or version not in ("v1", "v2") or type(f0) is not int or f0 not in (0, 1):
        raise ValueError("不支持的 RVC 版本或 f0 配置")
    weights = cpt.get("weight")
    if type(weights) not in (dict, OrderedDict) or not 1 <= len(weights) <= 2048:
        raise ValueError("缺少有效 weight 字典；训练检查点不能直接使用")
    result, total = {}, 0
    for name, tensor in weights.items():
        if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_.]{1,200}", name):
            raise ValueError("不支持的权重名称")
        if type(tensor) is not torch.Tensor or tensor.device.type != "cpu" or tensor.layout != torch.strided:
            raise ValueError("只接受普通 CPU 稠密 Tensor，不接受自定义类型")
        if tensor.dtype not in (torch.float16, torch.float32, torch.float64):
            raise ValueError("不支持的权重数据类型")
        if tensor.ndim > 5 or any(d <= 0 or d > 8192 for d in tensor.shape):
            raise ValueError("权重形状超出限制")
        total += tensor.numel()
        if total > 100_000_000 or not bool(torch.isfinite(tensor).all()):
            raise ValueError("权重过大或包含非有限数值")
        result[name] = tensor.detach().contiguous().clone()
    if "emb_g.weight" not in result:
        raise ValueError("缺少 RVC speaker embedding")
    if result["emb_g.weight"].ndim != 2 or result["emb_g.weight"].shape[0] != config[-3]:
        raise ValueError("speaker embedding 与 config 不一致")
    return {"weight": result, "config": config, "version": version,
            "f0": f0, "sr": f"{config[-1] // 1000}k"}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, nargs="?")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check-runtime", action="store_true")
    args = parser.parse_args()
    version = importlib.metadata.version("torch")
    policy = check_torch_version(version)
    if args.check_runtime:
        print(json.dumps(policy, ensure_ascii=False, indent=2))
        return 0 if policy["restricted_loader_version_allowed"] else 2
    require_restricted_loader(version)  # before importing torch or reading the model
    if args.model is None or args.output_dir is None:
        parser.error("需要 model 和 --output-dir；输出目录必须不存在")
    if args.model.is_symlink() or not args.model.is_file() or args.model.stat().st_size > MAX_FILE:
        raise ValueError("请输入大小受限的普通 .pth 文件")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise ValueError("输出目录已存在；不会覆盖")
    with args.model.open("rb") as file:
        data = file.read(MAX_FILE + 1)
    if len(data) > MAX_FILE or checkpoint_metadata(data)["format"] != "pytorch_zip_with_pickle":
        raise ValueError("只接受已静态检查的 PyTorch ZIP，不尝试旧 pickle/tar")
    import io
    import torch
    torch.set_num_threads(1)
    with torch.no_grad():
        original = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
        canonical = normalize(original, torch)
    # A fresh directory preserves the source and any earlier conversion.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    output = args.output_dir / "exusiai.normalized.pth"
    torch.save(canonical, output, pickle_protocol=2)
    report = {"format": "dot-rvc-normalized-v1", "torch_version": version,
              "source_sha256": hashlib.sha256(data).hexdigest(),
              "output_file": output.name, "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
              "version": canonical["version"], "sample_rate": canonical["config"][-1],
              "f0": canonical["f0"], "tensor_count": len(canonical["weight"]),
              "weights_only": True, "index_loaded": False, "inference_verified": False,
              "note": "受限加载和结构校验完成；未运行 RVC、未验证音色或 Dot 通话。输出仅供后续兼容性验证。"}
    (args.output_dir / "normalization.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc), "model_inference_run": False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
