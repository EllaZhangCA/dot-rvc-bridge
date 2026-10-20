import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_source", ROOT / "scripts/package-source.py")
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


class PackagingTests(unittest.TestCase):
    def test_runtime_models_and_personal_config_never_enter_source_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in packaging.FILES:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.touch()
            for folder in packaging.FOLDERS:
                (root / folder).mkdir(parents=True, exist_ok=True)
            for name in ("runtime/secret.py", "models/character.pth", "dot-rvc.local.toml",
                         "mcp.json", "docs/debug.log", "src/private.pth"):
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("private fixture", encoding="utf-8")
            result = {p.relative_to(root).as_posix() for p in packaging.source_files(root)}
            self.assertEqual(result, set(packaging.FILES))

    def test_missing_required_source_aborts_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "Missing"):
                list(packaging.source_files(Path(directory)))
