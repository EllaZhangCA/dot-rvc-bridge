# User-supplied character models

Find and download your own RVC character weights on [Hugging Face](https://huggingface.co/models). This repository and its releases contain software only; no local character checkpoint, index, or converted model bundle is published.

Use Start.cmd → Import .pth to select a standard RVC v2 inference checkpoint with f0=1. The original file can live anywhere you choose. The importer creates a validated local profile under runtime/, which is excluded from Git and releases.

The CLI can list files placed in models/, but listing or staging a file does not import it. Index retrieval is disabled in v0.3.1. See the [README](../README.md) and [model handling](../docs/MODEL_SAFETY.md).
