import io
import json
from pathlib import Path
import pickle
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from dot_rvc.errors import BridgeError
from dot_rvc.model_package import inspect_package, stage_package
from dot_rvc.model_safety import check_torch_version, inspect_runtime, require_restricted_loader


def checkpoint(metadata=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("voice/data.pkl", metadata or pickle.dumps({"weight": {}, "config": [], "version": "v2", "sr": "48k"}, protocol=2))
        archive.writestr("voice/data/0", b"\0\0")
    return data.getvalue()


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "voice.zip"

    def package(self, entries=None):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.archive, "w") as archive:
                for name, data in entries or [("voice.pth", checkpoint()), ("voice.index", b"unverified")]:
                    if isinstance(name, str) and "\\" in name:
                        item = zipfile.ZipInfo("placeholder")
                        item.filename = name  # bypass Windows writer's slash normalization
                        name = item
                    archive.writestr(name, data)
        return self.archive

    def test_inspection_does_not_execute_pickle_or_import_torch(self):
        # The payload names a callable but is only disassembled as data.
        payload = b"cos\nsystem\n(S'echo MUST_NOT_EXECUTE'\ntR."
        path = self.package([("voice.pth", checkpoint(payload))])
        with patch("pickle.loads", side_effect=AssertionError("must not unpickle")), patch("pickle.load", side_effect=AssertionError("must not unpickle")):
            result = inspect_package(path)
        self.assertEqual(result["files"][0]["checkpoint"]["pickle_globals"], ["os system"])
        self.assertFalse(result["model_loaded"])
        self.assertFalse(result["engine_imported"])
        self.assertFalse((self.root / "models").exists())

    def test_stage_retains_exact_bytes_and_hashes_but_never_imports(self):
        path = self.package()
        result = stage_package(path, self.root / "models", "exusiai")
        target = self.root / "models/exusiai"
        report = json.loads((target / "inspection.json").read_text(encoding="utf-8"))
        self.assertEqual(report, result)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual((target / "voice.pth").read_bytes(), archive.read("voice.pth"))
        self.assertEqual(len(result["archive_sha256"]), 64)
        self.assertFalse(result["index_loaded"])
        with self.assertRaisesRegex(BridgeError, "已存在"):
            stage_package(path, self.root / "models", "exusiai")
        self.assertEqual((target / "voice.index").read_bytes(), b"unverified")

    def test_paths_duplicates_scripts_and_multiple_models_are_rejected(self):
        cases = [
            [("../voice.pth", b"x")], [("/voice.pth", b"x")],
            [("C:/voice.pth", b"x")], [("dir\\voice.pth", b"x")],
            [("NUL.pth", b"x")], [("bad./voice.pth", b"x")],
            [("voice.pth", b"x"), ("run.py", b"raise Exception")],
            [("voice.pth", b"x"), ("VOICE.PTH", b"x")],
            [("voice.pth", b"x"), ("second.pth", b"x")],
            [("voice.index", b"x")], [("voice.pth", b"")],
        ]
        for entries in cases:
            with self.subTest(entries=[x[0] for x in entries]), self.assertRaises(BridgeError):
                stage_package(self.package(entries), self.root / "models", "blocked")
        self.assertFalse((self.root / "models/blocked").exists())

    def test_symlink_member_rejected(self):
        item = zipfile.ZipInfo("voice.pth")
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(BridgeError, "符号链接"):
            inspect_package(self.package([(item, b"target")]))

    def test_bounded_inputs_and_corrupt_zip_rejected(self):
        path = self.package()
        with patch("dot_rvc.model_package.MAX_FILE", 8), self.assertRaises(BridgeError):
            inspect_package(path)
        path.write_bytes(b"not zip")
        with self.assertRaisesRegex(BridgeError, "invalid_model_archive"):
            inspect_package(path)

    def test_legacy_checkpoint_never_falls_back_to_unpickle(self):
        result = inspect_package(self.package([("voice.pth", b"legacy binary")]))
        self.assertEqual(result["files"][0]["checkpoint"]["format"], "legacy_or_unknown")
        self.assertFalse(result["model_loaded"])

    def test_bad_profile_cannot_escape_models_root(self):
        path = self.package()
        for name in ("../elsewhere", "C:\\elsewhere", "con", "lpt1", "", "A"):
            with self.subTest(name=name), self.assertRaises(BridgeError):
                stage_package(path, self.root / "models", name)

    def test_nested_pickle_path_is_validated_without_extraction(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("../data.pkl", b"N.")
        with self.assertRaises(BridgeError):
            inspect_package(self.package([("voice.pth", data.getvalue())]))


class RuntimePolicyTests(unittest.TestCase):
    def test_old_and_unrecognized_versions_fail_closed(self):
        for version in ("2.0.1+cu118", "2.6.0", "2.9.1", "2.10.0rc1", "unknown"):
            with self.subTest(version=version), self.assertRaisesRegex(BridgeError, "unsafe_torch_runtime"):
                require_restricted_loader(version)
        self.assertTrue(check_torch_version("2.10.0+cpu")["restricted_loader_version_allowed"])

    def test_runtime_check_uses_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime/engine-venv/Lib/site-packages/torch-2.0.1+cu118.dist-info").mkdir(parents=True)
            result = inspect_runtime(root)
            self.assertEqual(result["torch_version"], "2.0.1+cu118")
            self.assertFalse(result["restricted_loader_version_allowed"])
            self.assertFalse(result["engine_import_approved"])
