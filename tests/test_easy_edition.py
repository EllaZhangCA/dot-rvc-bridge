import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from dot_rvc.portable_profile import readers, read_profile
from dot_rvc.safe_model import CONFIG
from dot_rvc import processes
from test_safe_service import fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_easy", ROOT / "scripts/package-easy.py")
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


class EasyEditionTests(unittest.TestCase):
    def test_profile_uses_its_own_model_config_and_rejects_changed_bundle(self):
        config = list(CONFIG)
        config[-1] = 40000
        data = fixture(lambda manifest, raw: manifest.update(config=config, sr="40k"))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = dict(format="dot-rvc-profile-v1", version="v2", f0=1, config=config,
                           tensor_count=457, sha256=hashlib.sha256(data).hexdigest())
            (root / "profile.json").write_text(json.dumps(profile))
            bundle = root / "model.rvcd"
            bundle.write_bytes(data)
            _, read, _ = readers(root)
            self.assertEqual(read(bundle)[0]["sr"], "40k")
            bundle.write_bytes(data + b"changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                read(bundle)

    def test_unsupported_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for version, f0, count in (("v1", 1, 457), ("v2", 0, 457), ("v2", 1, 0)):
                (root / "profile.json").write_text(json.dumps(dict(format="dot-rvc-profile-v1",
                    version=version, f0=f0, config=CONFIG, sha256="0" * 64, tensor_count=count)))
                with self.assertRaises(ValueError):
                    read_profile(root)

    def test_easy_package_only_uses_verified_allowlisted_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "release-assets/tools").mkdir(parents=True)
            (root / "runtime").mkdir()
            (root / "runtime/secret.pth").write_bytes(b"private model")
            (root / "release-assets/tools/uv.exe").write_bytes(b"fixture")
            (root / "release-assets/tools/private.pth").write_bytes(b"private model")
            (root / "easy-manifest.json").write_text(json.dumps(dict(
                uv=dict(exe_sha256=hashlib.sha256(b"fixture").hexdigest()), wheels=[])))
            self.assertEqual([p.name for p in packaging.release_assets(root)], ["uv.exe"])
            (root / "release-assets/tools/uv.exe").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                list(packaging.release_assets(root))

    def test_reused_pid_is_never_terminated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "runtime").mkdir()
            (root / "runtime/easy-process.json").write_text(json.dumps(
                dict(pid=12, started=10, executable="python.exe", script="owned.py")))
            unrelated = Mock()
            unrelated.create_time.return_value = 99
            psutil = Mock()
            psutil.Process.return_value = unrelated
            psutil.NoSuchProcess = ProcessLookupError
            with patch.dict("sys.modules", {"psutil": psutil}):
                with self.assertRaisesRegex(RuntimeError, "unrelated process"):
                    processes.stop(root)
            unrelated.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
