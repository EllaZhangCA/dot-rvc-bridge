"""Build a source-only archive from an explicit allowlist, not the working tree."""
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "README_CN.md", "AGENTS.md", "agent.md", "Setup.cmd", "Start.cmd", "easy-manifest.json", "LICENSE", "THIRD_PARTY.md", "pyproject.toml", "plugin.json",
         "config.example.toml", "engine-manifest.json", "engine-requirements.in",
         "engine-requirements.lock.txt", ".gitignore", ".gitattributes", "models/README.md"]
FOLDERS = {"src": {".py"}, "tests": {".py"}, "scripts": {".py", ".ps1"},
           "docs": {".md"}, "third_party": {".txt", ".md"}, ".github/workflows": {".yml"}}


def source_files(root):
    for name in FILES:
        file = root / name
        if file.is_symlink() or not file.is_file():
            raise RuntimeError(f"Missing or symlinked source file: {name}")
        yield file
    for folder, suffixes in FOLDERS.items():
        for file in sorted((root / folder).rglob("*")):
            if file.suffix in suffixes and file.is_file():
                if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
                    raise RuntimeError(f"Source file escapes project: {file}")
                yield file


def main():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    target = ROOT / "dist" / f"dot-rvc-bridge-{version}-source.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in source_files(ROOT):
            archive.write(file, file.relative_to(ROOT).as_posix())
    print(target)


if __name__ == "__main__":
    main()
