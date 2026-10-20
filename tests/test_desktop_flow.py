from pathlib import Path
import tempfile
import unittest

from dot_rvc.errors import BridgeError
from test_bridge import EngineFixture


class DesktopFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = EngineFixture(Path(self.temp.name))
        self.engine = self.fixture.engine
        for direction in ("Input", "Output"):
            for device in self.fixture.state[f"serverAudio{direction}Devices"]:
                device["hostAPI"] = "Windows WASAPI"

    def args(self):
        return ("CABLE Output (VB-Audio Virtual Cable)", "Headphones", "Windows WASAPI")

    def test_preview_can_run_while_active_and_never_writes(self):
        self.fixture.state["serverAudioStated"] = 1
        result = self.engine.audio_plan(*self.args(), 64)
        self.assertTrue(result["pause_required"])
        self.assertEqual(result["settings"]["serverReadChunkSize"], 64)
        self.assertEqual(self.fixture.writes, [])

    def test_missing_or_wrong_output_is_actionable_without_writes(self):
        with self.assertRaisesRegex(BridgeError, "device_not_configured"):
            self.engine.audio_plan(self.args()[0], "", self.args()[2])
        with self.assertRaisesRegex(BridgeError, "device_not_unique"):
            self.engine.audio_plan(self.args()[0], "wrong device", self.args()[2])
        self.assertEqual(self.fixture.writes, [])

    def test_chunk_validation_and_config_readback(self):
        for value in (True, 0, 15, 513, 1.5):
            with self.subTest(value=value), self.assertRaisesRegex(BridgeError, "invalid_chunk_size"):
                self.engine.audio_plan(*self.args(), value)
        result = self.engine.configure_audio(*self.args(), 64)
        self.assertEqual(self.fixture.state["serverReadChunkSize"], 64)
        self.assertAlmostEqual(result["configured_input_buffer_ms"], 170.67)
        self.assertIsNone(result["measured_latency_ms"])
        self.assertFalse(result["audio_start_requested"])
        self.assertFalse(result["dot_integration_verified"])

    def test_unknown_buffer_does_not_invent_latency(self):
        result = self.engine.status()
        self.assertIsNone(result["configured_input_buffer_ms"])
        self.fixture.state["serverReadChunkSize"] = 256
        self.assertAlmostEqual(self.engine.status()["configured_input_buffer_ms"], 682.67)

    def test_partial_failure_reports_applied_keys_and_stops(self):
        original = self.fixture.handle
        count = 0
        def handle(request):
            nonlocal count
            if request.method == "POST":
                count += 1
                if count == 3:
                    self.fixture.ignore_updates = True
                    self.fixture.state["serverOutputDeviceId"] = 99
            return original(request)
        import httpx
        self.engine.backend.transport = httpx.MockTransport(handle)
        with self.assertRaisesRegex(BridgeError, "已确认设置.*serverMonitorDeviceId.*未自动回滚"):
            self.engine.configure_audio(*self.args(), 64)
        self.assertEqual(len(self.fixture.writes), 3)
