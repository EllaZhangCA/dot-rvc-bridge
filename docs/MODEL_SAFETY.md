# Model import

Users find their own RVC character weights on [Hugging Face](https://huggingface.co/models). The project distributes software only. Local checkpoints, indexes, imported raw bundles and profiles never enter Git or release archives.

The easy importer runs in a separate Python 3.13 / PyTorch 2.10 CPU environment. It checks a bounded PyTorch ZIP, calls torch.load with weights_only=True, rejects unsupported structures, and copies ordinary finite CPU tensors into a raw-data archive. It never falls back to unrestricted checkpoint loading. Restricted loading reduces exposure; it is not a sandbox or a guarantee for untrusted files.

Only standard RVC v2 with f0=1 is accepted by the easy edition. The config, tensor names, shapes, sizes, dtypes, per-tensor hashes and whole-bundle hash are validated again by the engine. Model weights must strictly match the inference network. Index parsing is disabled.

Each import creates a new runtime/profiles directory and updates runtime/easy-current.json only after validation. The original selected file is unchanged. Runtime folders and models are excluded from source and easy distributions.

The legacy CUDA environment never deserializes the character .pth. Its checkpoint loader accepts only two fixed, hash-verified HuBERT/RMVPE base assets. Therefore the character data path avoids pickle, while the complete legacy runtime still uses checkpoint deserialization for these fixed dependencies.

For CLI metadata inspection, inspect-model and stage-model do not load tensors or run checkpoint code. They do not replace full model compatibility checks.
