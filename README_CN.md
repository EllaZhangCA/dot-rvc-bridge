# Dot RVC Bridge

**用自己的 RVC 模型，在 Windows 本地改变 Dot 的声线。**

[English](README.md) · 简体中文 · [下载 Windows 懒人版](https://github.com/EllaZhangCA/dot-rvc-bridge/releases/tag/v0.3.1)

包含桌面控制器、安装器及可选 MCP 服务，支持模型导入、播放设备选择、音高调节、原声旁路和开始/暂停。已在 RTX 3090 的本机使用中获得成功反馈。

这是独立社区项目，并非 OpenAI 官方插件。它通过本机音频后处理改变播放出来的声音，不修改 Dot 原生声线，也不会自动改变手机端的声音。首版面向 **Windows x64 + NVIDIA 显卡**。

## 快速开始

1. 从 [Releases](https://github.com/EllaZhangCA/dot-rvc-bridge/releases/tag/v0.3.1) 下载 **dot-rvc-bridge-0.3.1-windows-easy.zip**，解压到固定、可写的目录。请选择这个附件，不要下载 GitHub 自动生成的 Source code ZIP。
2. 双击 **Setup.cmd**。自动安装独立 Python 环境、CUDA 版 PyTorch、固定版本引擎和基础模型。首次需联网下载数 GB，请预留约 15 GB 磁盘空间。无需自行安装 Python、Node.js 或 C++ 编译工具。
3. 若缺少 VB-CABLE，会打开官方签名安装器。在 Windows 管理员提示中确认发布者为 **BUREL VINCENT**，点击“是”，再在安装器点击 **Install Driver**。如提示重启，请重启电脑。Windows 默认麦克风和播放设备保持平常使用的设备。
4. 双击 **Start.cmd**，点击 **导入模型 / Import .pth**，选择自己的权重；选择变声后播放到的耳机或音箱，点击 **开始变声 / Start**。
5. 打开 **Windows 设置 → 系统 → 声音 → 音量合成器**，将承载 Dot 的应用输出改为 **CABLE Input (VB-Audio Virtual Cable)**。Dot 的麦克风继续使用原设备，然后开始对话试听。

如果合成器没有显示应用，先让它播放声音。应用级路由可能同时处理该应用的其他声音。启动器不会自动修改 Windows 默认设备或应用路由。

```text
Dot 应用 → CABLE Input → CABLE Output → RVC → 耳机 / 音箱
你的麦克风 ─────────────────────────────→ Dot
```

**恢复正常声音：**引擎运行时勾选“原声”，或者在 Windows 中把应用输出改回耳机/音箱。暂停或关闭引擎后，仍送入虚拟线的声音将无法听到。

## 支持范围

| v0.3.1 支持 | 说明 |
| --- | --- |
| RVC 推理权重 | 标准 **v2、f0=1**，18 项配置，32/40/48 kHz |
| 音高提取 | RMVPE，使用 NVIDIA GPU 0 |
| 音高调节 | −24 至 +24 个半音 |
| 音频设备 | Windows WASAPI，虚拟线与输出使用 48 kHz |
| 模型切换 | 一个当前配置，重新导入即可更换 |

请自行前往 [Hugging Face](https://huggingface.co/models) 寻找并下载 RVC 角色 `.pth`。项目不代选、不托管、不附带、不自动下载角色权重。**发布内容不包含本机角色权重、索引、转换后的模型包、录音或个人配置。**导入检查结构和大小，不保证兼容所有权重；纯数据模型包上限为 100 MB。首版暂不支持 RVC v1、无 f0 模型、训练检查点、`.index` 检索、纯 CPU 使用及其他操作系统。桌面界面使用多说话人模型的 speaker 0。

RVC 主要改变音色，语速、语气、情绪和发音仍受到原声影响。模型及演示素材的使用和分享应遵循其提供方的授权范围。

## 懒人包包含什么

中英双语控制器、源码、官方 **uv 0.13.2**、预编译 **fairseq 0.12.2** 与 ANTLR 运行库、版本清单和第三方许可证。

这是**联网安装包**，引擎源码、PyTorch、基础模型和 VB-CABLE 在安装时下载。环境保存在 `.venv/` 和 `runtime/`；安装后请勿直接移动目录，换位置时应重新安装。当前不自动升级。

## 常见问题

| 现象 | 处理方法 |
| --- | --- |
| 下载失败 | 确认能访问 GitHub、PyPI、PyTorch 和 Hugging Face，重跑 Setup.cmd。哈希不符时安装停止。 |
| 找不到 CABLE 设备 | 完成驱动安装，按要求重启，再打开控制器。 |
| 18888 端口被占用 | 先关闭其他引擎实例；启动器不会强制结束无关进程。 |
| 开始后无声 | 检查应用输出、虚拟线、播放设备及 `runtime/easy-engine.log`。 |
| 更换或拔插设备 | 暂停并关闭引擎，刷新设备，重新选输出后启动。 |
| 导入失败 | 使用带音高引导的标准 RVC v2 推理 .pth，查看 `runtime/desktop.log`。 |
| 原声与变声同时出现 | 关闭虚拟线的“侦听此设备”，排查其他监听输出。 |

默认输入缓冲为 64 × 128 个采样点，48 kHz 下约 171 ms。这只是**输入缓冲时长，不是实测总延迟**。详见[验证范围](docs/VALIDATION.md)。

## 可选 MCP 控制

安装后生成本机专用 `mcp.json`，可接入兼容 MCP 的本地应用。先用桌面控制器加载引擎。云端服务的 localhost 不等于这台电脑，当前尚未验收 Dot 直接调用本地 MCP 的完整流程。

工具支持查状态、列出/选择模型、调音高、切原声及启停。设备先通过桌面或 CLI 配置。当前只有一个活动模型槽位，索引比例固定为 0。工具名见 [English README](README.md#optional-mcp-controls)。

## 开发与扩展

```powershell
uv run --no-project --python 3.13.5 scripts/bootstrap.py
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/package-source.py
```

源码安装会从本仓库 Release 下载固定版本的 wheel。桌面、CLI 与 MCP 共用控制层；引擎适配、模型导入、设备路由及运行环境分离，便于后续扩展。见[架构](docs/DESIGN.md)、[扩展说明](docs/EXTENDING.md)、[模型处理](docs/MODEL_SAFETY.md)和[发布构建](docs/RELEASING.md)。

原创代码采用 [MIT 许可证](LICENSE)。[第三方依赖](THIRD_PARTY.md)、基础模型及 VB-CABLE 保留各自条款。感谢 [w-okada/voice-changer](https://github.com/w-okada/voice-changer)、[RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 及相关开源项目。
