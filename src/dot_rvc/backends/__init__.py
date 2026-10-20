"""Engine-specific transport adapters. See docs/EXTENDING.md for the contract."""

from .w_okada_v1 import WOkadaV1


def create_backend(config, transport=None):
    if config.backend == "w-okada-v1":
        return WOkadaV1(config.engine_url, transport)
    raise ValueError(f"Unsupported engine backend: {config.backend}")
