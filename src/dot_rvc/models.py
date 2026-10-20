from pathlib import Path


def inventory(root: Path) -> dict:
    """List local files only; never deserialize checkpoints or infer a pairing."""
    if not root.is_dir():
        return {"directory": str(root), "models": [], "directory_exists": False}
    models = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.suffix.lower() != ".pth" or not path.is_file():
            continue
        candidates = sorted(
            str(p) for p in path.parent.iterdir()
            if p.is_file() and not p.is_symlink() and p.suffix.lower() == ".index"
        )
        size = path.stat().st_size
        models.append({
            "name": path.stem,
            "path": str(path),
            "bytes": size,
            "index_candidates": candidates,
            "compatibility": "not_checked" if size else "empty_file",
            "loaded_into_engine": False,
        })
    return {"directory": str(root), "models": models, "directory_exists": True}
