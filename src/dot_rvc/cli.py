import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .engine import BridgeError, Engine
from .models import inventory
from .audio import devices, test_cable
from .model_package import inspect_package, stage_package
from .model_safety import inspect_runtime


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Dot RVC 本地控制原型；不会直接替换 Dot 内置语音。")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "models", "engine-models", "start", "pause", "devices", "test-cable", "model-safety"):
        commands.add_parser(name)
    commands.add_parser("inspect-model").add_argument("archive", type=Path)
    stage = commands.add_parser("stage-model", help="只安全解压数据并记录哈希；不加载或导入引擎")
    stage.add_argument("archive", type=Path)
    stage.add_argument("--name", required=True)
    for name in ("audio-plan", "configure-audio"):
        audio_parser = commands.add_parser(name)
        audio_parser.add_argument("--input", dest="input_device")
        audio_parser.add_argument("--output", dest="output_device")
        audio_parser.add_argument("--host-api")
        audio_parser.add_argument("--chunk-size", type=int, help="可选输入缓冲块数；不会持久写入 TOML")
    commands.add_parser("select").add_argument("slot", type=int)
    commands.add_parser("pitch").add_argument("semitones", type=int)
    commands.add_parser("index").add_argument("ratio", type=float)
    commands.add_parser("bypass").add_argument("mode", choices=["on", "off"])
    args = parser.parse_args()
    try:
        config = Config.from_env()
        engine = Engine(config)
        def audio_args():
            return (args.input_device or config.input_device, args.output_device or config.output_device,
                    args.host_api or config.host_api, args.chunk_size)
        actions = {
            "status": engine.status,
            "models": lambda: inventory(config.models_dir),
            "engine-models": engine.list_models,
            "select": lambda: engine.select_model(args.slot),
            "pitch": lambda: engine.set_pitch(args.semitones),
            "index": lambda: engine.set_index_ratio(args.ratio),
            "bypass": lambda: engine.set_bypass(args.mode == "on"),
            "start": engine.start_audio,
            "pause": engine.pause_audio,
            "devices": devices,
            "test-cable": test_cable,
            "audio-plan": lambda: engine.audio_plan(*audio_args()),
            "configure-audio": lambda: engine.configure_audio(*audio_args()),
            "inspect-model": lambda: inspect_package(args.archive),
            "stage-model": lambda: stage_package(args.archive, config.models_dir, args.name),
            "model-safety": lambda: inspect_runtime(Path(__file__).resolve().parents[2]),
        }
        result = actions[args.command]()
    except (BridgeError, ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
