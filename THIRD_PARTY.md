# Third-party components

The root MIT license covers original bridge code only. Other code, drivers, assets and character models retain their own terms.

## Included in the easy ZIP

| Component | Version / provenance | Notices |
| --- | --- | --- |
| uv | Official [0.13.2 Windows release](https://github.com/astral-sh/uv/releases/tag/0.13.2) | [MIT](third_party/uv/LICENSE-MIT.txt) / [Apache-2.0](third_party/uv/LICENSE-APACHE.txt) |
| fairseq | [Meta fairseq](https://github.com/facebookresearch/fairseq), 0.12.2, locally built CPython 3.10 Windows wheel | MIT; copyright and license retained inside the wheel |
| ANTLR Python runtime | [ANTLR 4.8](https://github.com/antlr/antlr4/tree/4.8), pure-Python wheel | [BSD notice](third_party/antlr4/LICENSE.txt), also inside the wheel |

Digests are recorded in easy-manifest.json. No character model, driver, or installed runtime environment is included.

## Downloaded during setup

| Component | Provenance |
| --- | --- |
| w-okada voice-changer | [Pinned source](https://github.com/w-okada/voice-changer/tree/d8ef15799470193f7c8176ef471245753a656626), [LICENSE](https://github.com/w-okada/voice-changer/blob/d8ef15799470193f7c8176ef471245753a656626/LICENSE), [additional notices](https://github.com/w-okada/voice-changer/blob/d8ef15799470193f7c8176ef471245753a656626/LICENSE-NOTICE) |
| Python | uv-managed CPython distributions, with bundled notices |
| VB-CABLE Pack45 | [Official site](https://vb-audio.com/Cable/), [licensing](https://vb-audio.com/Services/licensing.htm); donationware |
| PyTorch / torchaudio | Official [CUDA](https://download.pytorch.org/whl/cu118) / [CPU](https://download.pytorch.org/whl/cpu) wheels |
| HuBERT / RMVPE | Exact URLs, revisions, sizes and hashes in engine-manifest.json; independent model terms |
| Other dependencies | engine-requirements.lock.txt and pyproject.toml; each retains its own license |

Downloaded source and packages retain their upstream license files. Base assets are shared inference components, not authorization to distribute a character voice or related media. Users supply their own character weights.
