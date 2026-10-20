"""Bounded archive inspection/staging. Never unpickle or load a model/index."""

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import pickletools
import re
import shutil
import stat
import tempfile
import zipfile

from .errors import BridgeError

MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_METADATA = 4 * 1024 * 1024
DISCLAIMER = "仅完成静态检查；未加载权重或索引，不证明安全、兼容或音色正确。"


def _fail(message):
    raise BridgeError("model_package_rejected", message)


def _members(archive, *, max_count=32):
    entries = archive.infolist()
    if len(entries) > max_count:
        _fail("压缩包条目过多。")
    seen, files, total = set(), [], 0
    for item in entries:
        name = item.orig_filename
        path = PurePosixPath(name)
        if (not name or name != item.filename or "\\" in name or path.is_absolute() or
                any(p in {".", ".."} or ":" in p or p.endswith((" ", ".")) or
                    re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?", p)
                    for p in name.rstrip("/").split("/"))):
            _fail("压缩包包含不安全路径。")
        folded = name.rstrip("/").casefold()
        if folded in seen:
            _fail("压缩包包含重复或大小写冲突路径。")
        seen.add(folded)
        mode = item.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            _fail("不接受符号链接或特殊文件。")
        if item.flag_bits & 1:
            _fail("不接受加密压缩包。")
        if item.is_dir():
            continue
        total += item.file_size
        if not 0 < item.file_size <= MAX_FILE or total > MAX_TOTAL:
            _fail("文件为空或超过大小限制。")
        if item.file_size / max(item.compress_size, 1) > 1000:
            _fail("压缩比超过限制。")
        files.append(item)
    return files


def checkpoint_metadata(data):
    """Parse pickle opcodes as data only. GLOBAL names are reported, never imported."""
    stream = io.BytesIO(data)
    if not zipfile.is_zipfile(stream):
        return {"format": "legacy_or_unknown", "load_verified": False,
                "note": "不是可静态检查的 PyTorch ZIP；未尝试 pickle/torch.load。"}
    with zipfile.ZipFile(stream) as archive:
        entries = _members(archive, max_count=8192)
        candidates = [e for e in entries if e.filename.endswith("/data.pkl") or e.filename == "data.pkl"]
        if len(candidates) != 1 or candidates[0].file_size > MAX_METADATA:
            _fail("PyTorch ZIP 缺少唯一且大小受限的 data.pkl。")
        metadata = archive.read(candidates[0])
        globals_found, strings, count, stopped = set(), set(), 0, False
        dynamic_globals = False
        try:
            for opcode, argument, _ in pickletools.genops(metadata):
                count += 1
                if count > 200000:
                    _fail("pickle 元数据指令过多。")
                if opcode.name == "GLOBAL":
                    globals_found.add(str(argument)[:200])
                elif opcode.name == "STACK_GLOBAL":
                    dynamic_globals = True
                elif opcode.name in {"BINUNICODE", "SHORT_BINUNICODE", "UNICODE"}:
                    if argument in {"weight", "config", "f0", "version", "sr", "v1", "v2", "32k", "40k", "48k"}:
                        strings.add(argument)
                elif opcode.name == "STOP":
                    stopped = True
        except (ValueError, UnicodeError) as exc:
            raise BridgeError("invalid_checkpoint_metadata", "无法静态解析 pickle 元数据。") from exc
        if not stopped:
            _fail("pickle 元数据不完整。")
        return {"format": "pytorch_zip_with_pickle", "archive_entries": len(entries),
                "pickle_globals": sorted(globals_found), "dynamic_globals": dynamic_globals,
                "rvc_markers_observed": sorted(strings), "load_verified": False,
                "note": "标记是字符串线索，不代表已验证 RVC 结构；静态扫描不能证明 pickle 安全。"}


def _read_package(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TOTAL:
        _fail("请选择大小受限的普通 ZIP 文件。")
    # One bounded snapshot: report and extracted bytes describe exactly the same archive.
    with path.open("rb") as source:
        blob = source.read(MAX_TOTAL + 1)
    if len(blob) > MAX_TOTAL:
        _fail("压缩包超过大小限制。")
    report = {"archive_name": path.name, "archive_sha256": hashlib.sha256(blob).hexdigest(),
              "files": [], "model_loaded": False, "index_loaded": False,
              "engine_imported": False, "note": DISCLAIMER}
    payloads = {}
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            entries = _members(archive)
            suffixes = [PurePosixPath(e.filename).suffix.lower() for e in entries]
            if suffixes.count(".pth") != 1 or suffixes.count(".index") > 1 or any(s not in {".pth", ".index"} for s in suffixes):
                _fail("当前流程只接受一个 .pth 和至多一个 .index，不执行或提取其他文件。")
            for item in entries:
                data = archive.read(item)
                name = PurePosixPath(item.filename).name
                if name.casefold() in {n.casefold() for n in payloads}:
                    _fail("提取后的文件名冲突。")
                payloads[name] = data
                record = {"source_name": item.filename, "name": name, "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()}
                if name.lower().endswith(".pth"):
                    record["checkpoint"] = checkpoint_metadata(data)
                else:
                    record["format"] = "unverified_index_binary"
                    record["header_hex"] = data[:16].hex()
                report["files"].append(record)
    except BridgeError:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise BridgeError("invalid_model_archive", "ZIP 格式、校验或压缩方式无效。") from exc
    return report, payloads


def inspect_package(path):
    return _read_package(path)[0]


def stage_package(path, models_dir, profile):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", profile):
        _fail("角色目录名须为 1–48 位小写字母、数字、下划线或连字符。")
    if re.fullmatch(r"(con|prn|aux|nul|com[0-9]|lpt[0-9])", profile):
        _fail("角色目录名不能是 Windows 保留名称。")
    report, payloads = _read_package(path)
    root = Path(models_dir)
    if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
        _fail("模型根目录不能是链接。")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    target = root / profile
    if target.exists() or target.is_symlink():
        _fail("角色目录已存在；不会覆盖已有模型或报告，请选择新目录名。")
    temporary = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    try:
        for name, data in payloads.items():
            (temporary / name).write_bytes(data)
        report["profile"] = profile
        report["directory"] = str(target)
        (temporary / "inspection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.rename(target)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return report
