# Desktop guide

Start with the [English quick start](../README.md#quick-start) or [中文快速开始](../README_CN.md#快速开始).

Setup.cmd installs the environment; Start.cmd opens the desktop. Import a standard RVC v2 f0 model, choose a physical WASAPI output, and start. First model loading can take a minute or two. Logs are runtime/desktop.log and runtime/easy-engine.log.

Pitch and original-voice bypass can change during streaming. Importing a model stops this launcher's engine before selecting the new profile. Closing the desktop stops its engine; it does not restore Windows app routing.

If another service owns port 18888, stop it using its own controller. The easy launcher will not take over that service. CLI and MCP can query the easy service after the desktop starts it.

Legacy start-engine.ps1 and start-yukina-engine.ps1 target development-only, locally provisioned profiles. They remain for existing workspaces and are not the public first-run path. Use Start.cmd for the release.
