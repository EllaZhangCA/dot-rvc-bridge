import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from dot_rvc.config import Config
from dot_rvc.engine import BridgeError, Engine
from dot_rvc.mcp_server import create_server
from dot_rvc.models import inventory


def engine_state():
    # Shaped from the documented source contract, not a claim of live RVC output.
    return {
        "status": "OK", "modelSlotIndex": 0, "passThrough": False,
        "serverAudioStated": 0, "enableServerAudio": 1,
        "serverInputDeviceId": 10, "serverOutputDeviceId": 20, "serverMonitorDeviceId": -1,
        "modelSamplingRate": 48000, "tran": 0, "indexRatio": 0.0,
        "pipelineInfo": {"inferencer": {"type": "test-only"}},
        "modelSlots": [
            {"slotIndex": 0, "voiceChangerType": "RVC", "name": "fixture", "modelFile": "fixture.pth", "indexFile": "fixture.index"},
            {"slotIndex": 1, "voiceChangerType": "RVC", "name": "second", "modelFile": "second.pth", "indexFile": ""},
            {"slotIndex": 2, "voiceChangerType": None, "modelFile": ""},
        ],
        "serverAudioInputDevices": [{"index": 10, "name": "CABLE Output (VB-Audio Virtual Cable)", "maxInputChannels": 2}],
        "serverAudioOutputDevices": [{"index": 20, "name": "Headphones", "maxOutputChannels": 2}],
    }


class EngineFixture:
    def __init__(self, root):
        self.state = engine_state()
        self.requests = []
        self.ignore_updates = False
        self.fail_updates = False
        self.timeout_updates = False
        self.engine = Engine(Config(models_dir=root), httpx.MockTransport(self.handle))

    def handle(self, request):
        self.requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/update_settings"
            if self.fail_updates:
                return httpx.Response(200, json={"status": "ERROR"})
            if self.timeout_updates:
                raise httpx.ReadTimeout("test timeout", request=request)
            fields = parse_qs(request.content.decode())
            key, value = fields["key"][0], fields["val"][0]
            if not self.ignore_updates:
                if key == "passThrough":
                    assert value in {"true", "false"}
                    self.state[key] = value == "true"
                elif key == "indexRatio":
                    self.state[key] = float(value)
                else:
                    self.state[key] = int(value)
        else:
            assert request.method == "GET" and request.url.path == "/info"
        return httpx.Response(200, json=copy.deepcopy(self.state))

    @property
    def writes(self):
        return [r for r in self.requests if r.method == "POST"]


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = EngineFixture(self.root)
        self.engine = self.fixture.engine

    def test_status_is_read_only_and_never_claims_audio_verified(self):
        self.fixture.state["serverAudioStated"] = 1
        result = self.engine.status()
        self.assertTrue(result["configuration_ready"])
        self.assertTrue(result["audio_start_requested"])
        self.assertFalse(result["audio_flow_verified"])
        self.assertFalse(result["dot_integration_verified"])
        self.assertIsNone(result["measured_latency_ms"])
        self.assertEqual(self.fixture.writes, [])

    def test_missing_model_prevents_start(self):
        self.fixture.state["modelSlots"] = []
        with self.assertRaisesRegex(BridgeError, "model_missing"):
            self.engine.start_audio()
        self.assertEqual(self.fixture.writes, [])

    def test_failed_pipeline_prevents_start(self):
        self.fixture.state["pipelineInfo"] = "None"
        with self.assertRaisesRegex(BridgeError, "pipeline_not_initialized"):
            self.engine.start_audio()
        self.assertEqual(self.fixture.writes, [])

    def test_bad_routes_cannot_start(self):
        for field, value in (("serverMonitorDeviceId", 20), ("serverOutputDeviceId", 99), ("enableServerAudio", 0)):
            with self.subTest(field=field):
                self.fixture.state = engine_state()
                self.fixture.state[field] = value
                with self.assertRaisesRegex(BridgeError, "not_ready"):
                    self.engine.start_audio()
        self.fixture.state = engine_state()
        self.fixture.state["serverAudioInputDevices"][0]["name"] = "User microphone"
        with self.assertRaisesRegex(BridgeError, "input_not_cable"):
            self.engine.start_audio()
        self.fixture.state = engine_state()
        self.fixture.state["serverAudioOutputDevices"][0]["name"] = "CABLE Input (VB-Audio Virtual Cable)"
        with self.assertRaisesRegex(BridgeError, "output_not_headphones"):
            self.engine.start_audio()
        self.assertEqual(self.fixture.writes, [])

    def test_model_selection_requires_pause_and_existing_model(self):
        self.fixture.state["serverAudioStated"] = 1
        with self.assertRaisesRegex(BridgeError, "pause_required"):
            self.engine.select_model(1)
        self.fixture.state["serverAudioStated"] = 0
        with self.assertRaisesRegex(BridgeError, "model_missing"):
            self.engine.select_model(2)
        self.assertEqual(self.fixture.writes, [])
        self.assertEqual(self.engine.select_model(1)["selected_model"]["slot"], 1)

    def test_pitch_is_absolute_and_read_back(self):
        self.assertEqual(self.engine.set_pitch(-3)["pitch_semitones"], -3)
        self.assertEqual(self.engine.set_pitch(-3)["pitch_semitones"], -3)
        self.assertEqual(self.fixture.requests[-1].method, "GET")

    def test_invalid_parameters_never_touch_engine(self):
        for value in (True, 1.5, -25, 25):
            with self.subTest(pitch=value), self.assertRaises(BridgeError):
                self.engine.set_pitch(value)
        for value in (-1, 1.1, math.nan, math.inf, True):
            with self.subTest(ratio=value), self.assertRaises(BridgeError):
                self.engine.set_index_ratio(value)
        with self.assertRaises(BridgeError):
            self.engine.set_bypass("false")
        with self.assertRaises(BridgeError):
            self.engine.select_model(1000)
        self.assertEqual(self.fixture.requests, [])

    def test_no_index_rejects_nonzero_ratio(self):
        self.fixture.state["modelSlots"][0]["indexFile"] = ""
        with self.assertRaisesRegex(BridgeError, "index_missing"):
            self.engine.set_index_ratio(0.5)
        self.assertEqual(self.fixture.writes, [])
        self.assertEqual(self.engine.set_index_ratio(0)["index_ratio"], 0.0)

    def test_bypass_does_not_pause_or_change_devices(self):
        self.fixture.state["serverAudioStated"] = 1
        self.assertEqual(self.engine.set_bypass(True)["configured_mode"], "original")
        self.assertEqual(self.engine.set_bypass(False)["configured_mode"], "rvc")
        self.assertEqual(self.fixture.state["serverAudioStated"], 1)
        self.assertEqual(self.fixture.state["serverInputDeviceId"], 10)

    def test_start_and_pause_are_requests_not_audio_proof(self):
        result = self.engine.start_audio()
        self.assertTrue(result["audio_start_requested"])
        self.assertFalse(result["audio_flow_verified"])
        paused = self.engine.pause_audio()
        self.assertFalse(paused["audio_start_requested"])
        self.assertIn("Windows", paused["note"])

    def test_http_200_is_not_enough_to_claim_mutation_success(self):
        self.fixture.ignore_updates = True
        with self.assertRaisesRegex(BridgeError, "update_not_confirmed"):
            self.engine.set_pitch(3)

    def test_engine_rejection_and_timeout_are_not_retried(self):
        self.fixture.fail_updates = True
        with self.assertRaisesRegex(BridgeError, "engine_rejected"):
            self.engine.set_pitch(3)
        self.fixture.fail_updates = False
        self.fixture.timeout_updates = True
        with self.assertRaisesRegex(BridgeError, "engine_timeout"):
            self.engine.set_pitch(3)
        self.assertEqual(len(self.fixture.writes), 2)

    def test_offline_status_is_actionable(self):
        def offline(request):
            raise httpx.ConnectError("test offline", request=request)
        engine = Engine(Config(models_dir=self.root), httpx.MockTransport(offline))
        result = engine.status()
        self.assertFalse(result["engine_reachable"])
        self.assertFalse(result["configuration_ready"])
        self.assertIn("engine_unreachable", result["blockers"][0])

    def test_unknown_schema_rejected_without_writes(self):
        self.fixture.state.pop("serverAudioStated")
        with self.assertRaisesRegex(BridgeError, "incompatible_engine"):
            self.engine.set_pitch(1)
        self.assertEqual(self.fixture.writes, [])

    def test_html_and_redirects_are_not_followed(self):
        requests = []
        def redirect(request):
            requests.append(request)
            return httpx.Response(302, headers={"Location": "https://example.com"})
        engine = Engine(Config(models_dir=self.root), httpx.MockTransport(redirect))
        with self.assertRaisesRegex(BridgeError, "engine_http_error"):
            engine.info()
        self.assertEqual(len(requests), 1)
        engine = Engine(Config(models_dir=self.root), httpx.MockTransport(lambda _: httpx.Response(200, text="<html>Not an API</html>")))
        with self.assertRaisesRegex(BridgeError, "incompatible_engine"):
            engine.info()

    def test_model_scan_does_not_load_or_pair_checkpoints(self):
        folder = self.root / "角色"
        folder.mkdir()
        (folder / "voice.pth").write_bytes(b"not a real checkpoint")
        (folder / "other.index").write_bytes(b"not an index")
        (folder / "empty.PTH").touch()
        models = inventory(self.root)["models"]
        self.assertEqual(len(models), 2)
        self.assertEqual({m["compatibility"] for m in models}, {"empty_file", "not_checked"})
        self.assertTrue(all(not m["loaded_into_engine"] for m in models))
        self.assertEqual(len(models[0]["index_candidates"]), 1)

    def test_remote_and_ambiguous_urls_rejected(self):
        for url in ("http://example.com", "http://127.0.0.1.evil", "http://u:p@localhost", "http://localhost/api", "http://localhost:bad", "file:///tmp/api"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Config(engine_url=url)
        self.assertEqual(Config(engine_url="http://[::1]:18888/").engine_url, "http://[::1]:18888")

    def test_cli_utf8_with_non_ascii_model_path(self):
        (self.root / "角色.pth").touch()
        env = {**os.environ, "DOT_RVC_MODELS_DIR": str(self.root), "PYTHONIOENCODING": "cp1252"}
        result = subprocess.run([sys.executable, "-m", "dot_rvc.cli", "models"], capture_output=True, env=env, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.decode("utf-8"))["models"][0]["name"], "角色")


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_contract_and_errors_through_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = EngineFixture(Path(directory))
            async with Client(create_server(fixture.engine)) as client:
                listing = await client.list_tools()
                self.assertEqual(len(listing.tools), 9)
                result = await client.call_tool("get_voice_status", {})
                self.assertFalse(result.is_error)
                self.assertFalse(result.structured_content["audio_flow_verified"])
                changed = await client.call_tool("set_voice_pitch", {"semitones": -2})
                self.assertFalse(changed.is_error)
                self.assertEqual(fixture.state["tran"], -2)
                writes = len(fixture.writes)
                invalid = await client.call_tool("set_voice_pitch", {"semitones": True})
                self.assertTrue(invalid.is_error)
                bad_ratio = await client.call_tool("set_voice_index_ratio", {"ratio": True})
                self.assertTrue(bad_ratio.is_error)
                self.assertEqual(len(fixture.writes), writes)
                missing = await client.call_tool("select_voice_model", {"slot": 999})
                self.assertTrue(missing.is_error)
                self.assertIn("model_missing", str(missing.content))

    async def test_real_stdio_process_starts_and_lists_empty_models(self):
        with tempfile.TemporaryDirectory() as directory:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "dot_rvc.mcp_server"],
                env={**os.environ, "DOT_RVC_MODELS_DIR": directory, "PYTHONUTF8": "1"},
            )
            async with Client(params, read_timeout_seconds=15) as client:
                self.assertEqual(len((await client.list_tools()).tools), 9)
                result = await client.call_tool("list_local_models", {})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["models"], [])


if __name__ == "__main__":
    unittest.main()
