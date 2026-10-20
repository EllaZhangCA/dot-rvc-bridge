# Protected local service

The public first-run path is Setup.cmd → Start.cmd → Import .pth. The engine uses the selected runtime/easy-current.json profile and reports profile=easy-rvc-v1 at GET /safe_status.

The wrapper verifies pinned upstream source files and applies process-local overrides. It does not modify the upstream checkout. Character models load from validated raw tensors with strict network matching. Unknown checkpoint loading, index parsing, uploads, exports and model mutation are disabled. Only two hash-pinned base inference assets use the legacy checkpoint loader.

Allowed endpoints: GET /info, /performance, /safe_status and restricted POST /update_settings. The service exposes no browser UI or WebSocket audio and binds to 127.0.0.1:18888. It is not designed for Internet exposure.

Audio starts paused. Start requires an initialized pipeline, WASAPI CABLE Output input, a non-CABLE WASAPI output, 48 kHz and no extra monitor. Windows app routing remains manual.

Legacy character-specific scripts remain for existing development workspaces. They require local provisioned files and are not the installation path for new users. No character assets are included in the repository or releases.
