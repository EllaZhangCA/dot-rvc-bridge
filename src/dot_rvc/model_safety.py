"""Runtime policy checks only; this module never imports torch or reads weights."""

import re
from pathlib import Path

from .errors import BridgeError

MIN_TORCH = (2, 10, 0)
ADVISORIES = [
    "https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6",
    "https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p",
]


def check_torch_version(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\+[A-Za-z0-9.]+)?", version)
    supported = bool(match and tuple(map(int, match.groups())) >= MIN_TORCH)
    return {"torch_version": version, "restricted_loader_version_allowed": supported,
            "minimum_version_for_known_advisories": "2.10.0", "advisories": ADVISORIES,
            "note": "版本门槛只覆盖列出的已知漏洞；仍须 weights_only=True、格式/结构限制，不得回退到普通 pickle。"}


def require_restricted_loader(version):
    if not check_torch_version(version)["restricted_loader_version_allowed"]:
        raise BridgeError("unsafe_torch_runtime", "当前 PyTorch 不符合已知漏洞修复门槛；停止加载未知 .pth。请先批准独立验证环境。")


def inspect_runtime(project_root):
    site = Path(project_root) / "runtime/engine-venv/Lib/site-packages"
    versions = sorted(p.name[len("torch-"):-len(".dist-info")]
                      for p in site.glob("torch-*.dist-info") if p.is_dir())
    result = check_torch_version(versions[0]) if len(versions) == 1 else {
        "torch_version": None, "restricted_loader_version_allowed": False,
        "note": "无法唯一确定项目引擎的 PyTorch 版本；未导入任何包。", "advisories": ADVISORIES}
    result["engine_import_approved"] = False
    result["note"] += " 此检查不导入模型，也不授权上游普通 torch.load。"
    return result
