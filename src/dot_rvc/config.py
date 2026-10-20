from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    engine_url: str = "http://127.0.0.1:18888"
    models_dir: Path = Path(__file__).resolve().parents[2] / "models"
    backend: str = "w-okada-v1"
    input_device: str = "CABLE Output (VB-Audio Virtual Cable)"
    output_device: str = ""
    host_api: str = "Windows WASAPI"

    def __post_init__(self):
        url = urlsplit(self.engine_url)
        try:
            port = url.port
        except ValueError as exc:
            raise ValueError("引擎端口无效。") from exc
        if (
            url.scheme not in {"http", "https"}
            or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username is not None
            or url.password is not None
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
            or port == 0
        ):
            raise ValueError("首版只连接本机 loopback 引擎地址，不接受路径、凭据或远程地址。")
        object.__setattr__(self, "engine_url", self.engine_url.rstrip("/"))
        object.__setattr__(self, "models_dir", Path(self.models_dir).expanduser().resolve())

    @classmethod
    def from_env(cls):
        defaults = cls()
        config_path = Path(os.environ.get("DOT_RVC_CONFIG", str(Path(__file__).resolve().parents[2] / "dot-rvc.local.toml")))
        data = {}
        if config_path.exists():
            with config_path.open("rb") as file:
                data = tomllib.load(file)
        engine, audio = data.get("engine", {}), data.get("audio", {})
        model_path = Path(os.environ.get("DOT_RVC_MODELS_DIR", engine.get("models_dir", str(defaults.models_dir))))
        if not model_path.is_absolute():
            model_path = config_path.parent / model_path
        return cls(
            engine_url=os.environ.get("DOT_RVC_ENGINE_URL", engine.get("url", defaults.engine_url)),
            models_dir=model_path,
            backend=os.environ.get("DOT_RVC_BACKEND", engine.get("backend", defaults.backend)),
            input_device=audio.get("input_device", defaults.input_device),
            output_device=audio.get("output_device", defaults.output_device),
            host_api=audio.get("host_api", defaults.host_api),
        )
