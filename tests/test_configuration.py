import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dot_rvc.config import Config
from dot_rvc.errors import BridgeError
from test_bridge import EngineFixture


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = EngineFixture(self.root)
        for key in ("serverAudioInputDevices", "serverAudioOutputDevices"):
            for device in self.fixture.state[key]:
                device["hostAPI"] = "Windows WASAPI"

    def test_toml_paths_relative_to_config_and_env_override(self):
        path = self.root / "settings.toml"
        path.write_text('[engine]\nurl="http://localhost:19000"\nmodels_dir="voices"\n[audio]\noutput_device="Headphones"', encoding="utf-8")
        with patch.dict(os.environ, {"DOT_RVC_CONFIG": str(path)}, clear=True):
            config = Config.from_env()
            self.assertEqual(config.models_dir, self.root / "voices")
            self.assertEqual(config.output_device, "Headphones")
            self.assertEqual(config.engine_url, "http://localhost:19000")
            with patch.dict(os.environ, {"DOT_RVC_ENGINE_URL": "http://127.0.0.1:18888"}):
                self.assertEqual(Config.from_env().engine_url, "http://127.0.0.1:18888")

    def configure(self):
        return self.fixture.engine.configure_audio("CABLE Output (VB-Audio Virtual Cable)", "Headphones", "Windows WASAPI")

    def test_resolve_names_with_new_ids_and_keep_paused_without_model(self):
        self.fixture.state["modelSlots"] = []
        self.fixture.state["serverAudioInputDevices"][0]["index"] = 41
        self.fixture.state["serverAudioOutputDevices"][0]["index"] = 42
        result = self.configure()
        self.assertEqual(result["input_device"]["index"], 41)
        self.assertEqual(result["output_device"]["index"], 42)
        self.assertEqual(self.fixture.state["serverAudioSampleRate"], 48000)
        self.assertFalse(result["audio_start_requested"])
        self.assertFalse(result["configuration_ready"])

    def test_ambiguous_device_and_active_audio_do_not_mutate(self):
        self.fixture.state["serverAudioInputDevices"] *= 2
        with self.assertRaisesRegex(BridgeError, "device_not_unique"):
            self.configure()
        self.fixture.state["serverAudioStated"] = 1
        with self.assertRaisesRegex(BridgeError, "pause_required"):
            self.configure()
        self.assertEqual(self.fixture.writes, [])

    def test_device_readback_failure_stops_remaining_writes(self):
        self.fixture.ignore_updates = True
        self.fixture.state["serverMonitorDeviceId"] = 20
        with self.assertRaisesRegex(BridgeError, "update_not_confirmed"):
            self.configure()
        self.assertEqual(len(self.fixture.writes), 1)


if __name__ == "__main__":
    unittest.main()
