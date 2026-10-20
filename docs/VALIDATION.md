# Validation scope — v0.3.0

Windows / NVIDIA RTX 3090, 2026-10-19.

The user reported successful local use of the Dot/RVC audio route before publication. This is a listening report on one machine, not a latency benchmark or a cross-device guarantee.

Release checks cover:

- Control-layer unit tests, MCP stdio handshake, setting readbacks, route checks, checkpoint validation, and package exclusions.
- A new Python 3.10 environment installed using wheels only, including the bundled fairseq build. No compiler was used for this consumer installation.
- Restricted import of two local RVC v2 models (40/48 kHz) into fresh data-only profiles. Their weights are not published.
- A separate loopback engine smoke test: pipeline initialization and setting readback, with audio paused.
- Desktop startup and packaging checks. Logs and local reports are excluded from releases.

Earlier development checks exercised CPU/CUDA synthetic RVC inference and the VB-CABLE signal path.

Not established: installation on a completely fresh Windows PC, broad GPU/model compatibility, measured total audio latency, long-session reliability, or direct Dot invocation of optional MCP controls. CI runs control tests and source packaging without GPU hardware or character models.

The API returns audio_flow_verified=false and measured_latency_ms=null when it has only configuration readbacks. The user's listening report is not treated as a permanent automated health assertion.
