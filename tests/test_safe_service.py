import asyncio
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from dot_rvc.safe_api import SafeAPI, validate_setting
from dot_rvc.safe_model import CONFIG, decode_bundle, read_bundle


def fixture(mutate=None, compressed=False):
    manifest = dict(format="dot-rvc-oneoff-raw-v1", byteorder="little", config=CONFIG,
                    version="v2", f0=1, sr="48k", tensors=[])
    raws = {}
    for i in range(457):
        shape = [109, 256] if i == 0 else [1]
        raw = bytes(109 * 256 * 2 if i == 0 else 2)
        name = "emb_g.weight" if i == 0 else f"layer.{i}"
        member = f"{i:04d}.bin"
        manifest["tensors"].append(dict(name=name, file=member, dtype="<f2", shape=shape,
            bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        raws[member] = raw
    if mutate:
        mutate(manifest, raws)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED) as archive:
        for name, data in raws.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest))
    return stream.getvalue()


class DataBundleTests(unittest.TestCase):
    def test_reviewed_bytes_read_without_deserialization(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.rvcd"
            path.write_bytes(data)
            manifest, weights = read_bundle(path, hashlib.sha256(data).hexdigest())
            self.assertEqual(manifest["version"], "v2")
            self.assertEqual(len(weights), 457)

    def test_digest_mismatch_stops_before_zip_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.pth"
            path.write_bytes(b"not a ZIP; must never be interpreted")
            with self.assertRaisesRegex(ValueError, "Unapproved"):
                read_bundle(path)

    def test_tensor_hash_tampering(self):
        data = fixture(lambda m, r: r.update({"0001.bin": b"xx"}))
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            decode_bundle(data)

    def test_unexpected_pickle_member(self):
        data = fixture(lambda m, r: r.update({"data.pkl": b"ignored"}))
        with self.assertRaisesRegex(ValueError, "archive members"):
            decode_bundle(data)

    def test_no_compressed_archive(self):
        with self.assertRaisesRegex(ValueError, "uncompressed"):
            decode_bundle(fixture(compressed=True))

    def test_tensor_path_rejected(self):
        data = fixture(lambda m, r: m["tensors"][1].update(file="../anything"))
        with self.assertRaisesRegex(ValueError, "identity"):
            decode_bundle(data)

    def test_tensor_duplicate_name_rejected(self):
        data = fixture(lambda m, r: m["tensors"][1].update(name="emb_g.weight"))
        with self.assertRaisesRegex(ValueError, "identity"):
            decode_bundle(data)

    def test_tensor_shape_size_rejected(self):
        for change in ({"shape": [8193]}, {"shape": [False]}, {"bytes": 99}, {"dtype": "object"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                decode_bundle(fixture(lambda m, r: m["tensors"][1].update(change)))

    def test_other_config_rejected(self):
        with self.assertRaisesRegex(ValueError, "configuration"):
            decode_bundle(fixture(lambda m, r: m.update(config=[1] * 18)))


class SafeAPITests(unittest.TestCase):
    def request(self, method="GET", path="/info", body=b"", headers=None, scope_type="http"):
        self.forwarded = []
        async def app(scope, receive, send):
            self.forwarded.append(scope["path"])
            if scope["method"] == "POST":
                self.forwarded.append((await receive())["body"])
            await send({"type": "http.response.start", "status": 200})
        api = SafeAPI(app, {"profile": "test"})
        scope = dict(type=scope_type, method=method, path=path, headers=headers or [])
        async def run():
            messages = []
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            async def send(message):
                messages.append(message)
            await api(scope, receive, send)
            return messages
        return asyncio.run(run())

    def form(self, body):
        return self.request("POST", "/update_settings", body,
                            [(b"content-type", b"application/x-www-form-urlencoded")])

    def test_read_only_info_passes(self):
        self.assertEqual(self.request()[0]["status"], 200)
        self.assertEqual(self.forwarded, ["/info"])

    def test_profile_receipt_is_local(self):
        self.assertEqual(self.request(path="/safe_status")[0]["status"], 200)
        self.assertEqual(self.forwarded, [])

    def test_settings_forward_exact_body(self):
        body = b"key=serverAudioStated&val=0"
        self.assertEqual(self.form(body)[0]["status"], 200)
        self.assertEqual(self.forwarded, ["/update_settings", body])

    def test_model_ingress_and_export_routes_blocked(self):
        for path in ("/load_model", "/upload_file", "/concat_uploaded_file", "/merge_model",
                     "/update_model_info", "/upload_model_assets", "/update_model_default",
                     "/onnx", "/test", "/socket.io/"):
            for method in ("POST", "GET"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(method, path)[0]["status"], 403)
                    self.assertEqual(self.forwarded, [])

    def test_duplicate_or_unknown_settings_rejected(self):
        for body in (b"key=modelFile&val=evil.pth", b"key=modelSlotIndex&val=1000",
                     b"key=indexRatio&val=1", b"key=f0Detector&val=rmvpe_onnx",
                     b"key=gpu&val=0&val=-1", b"key=passThrough&val=True"):
            with self.subTest(body=body):
                self.assertEqual(self.form(body)[0]["status"], 400)
                self.assertEqual(self.forwarded, [])

    def test_cross_origin_rejected(self):
        self.assertEqual(self.request(headers=[(b"origin", b"https://example.invalid")])[0]["status"], 403)

    def test_websocket_rejected(self):
        self.assertEqual(self.request(scope_type="websocket")[0]["type"], "websocket.close")

    def test_wrong_content_type_and_oversize(self):
        self.assertEqual(self.request("POST", "/update_settings")[0]["status"], 415)
        self.assertEqual(self.form(b"x" * 1025)[0]["status"], 413)

    def test_settings_finite_and_bounded(self):
        for key, value in (("serverOutputAudioGain", "nan"), ("dstId", "109"),
                           ("tran", "25"), ("serverMonitorDeviceId", "0"),
                           ("serverReadChunkSize", "0")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_setting(key, value)


if __name__ == "__main__":
    unittest.main()
