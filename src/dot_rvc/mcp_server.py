from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import StrictBool, StrictFloat, StrictInt
from typing import Any

from .config import Config
from .engine import BridgeError, Engine
from .models import inventory
from . import __version__


def create_server(engine: Engine | None = None) -> MCPServer:
    bridge = engine or Engine(Config.from_env())
    server = MCPServer(
        "dot-rvc-bridge", version=__version__,
        instructions=(
            "Controls a local w-okada v1-compatible engine. Check get_voice_status first. "
            "This does not intercept Dot voice or install audio routing. "
            "Configuration readback is not proof of live audio; never report successful "
            "Dot voice conversion from these tools alone. Import weights in the desktop controller. "
            "Pause before model selection. For original voice use bypass; pausing can silence "
            "the virtual cable. Cloud localhost is not the user's PC."
        ),
    )
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    def invoke(action, *args):
        try:
            return action(*args)
        except (BridgeError, OSError) as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(annotations=read, structured_output=True)
    def get_voice_status() -> dict[str, Any]:
        """检查本机 RVC 引擎、模型、音频配置及阻塞原因；不启动录音，不证明实际通话音频已接通。"""
        return invoke(bridge.status)

    @server.tool(annotations=read, structured_output=True)
    def list_local_models() -> dict[str, Any]:
        """列出配置目录里的 .pth 和候选 .index 路径；不反序列化权重，不自动导入或判断兼容性。"""
        return invoke(inventory, bridge.config.models_dir)

    @server.tool(annotations=read, structured_output=True)
    def list_voice_models() -> dict[str, Any]:
        """列出已导入兼容引擎的 RVC 模型槽位。请用返回的槽位选择角色。"""
        return invoke(bridge.list_models)

    @server.tool(annotations=write, structured_output=True)
    def select_voice_model(slot: StrictInt) -> dict[str, Any]:
        """在引擎音频暂停时选择已导入的 RVC 模型；回读选择状态，不启动音频或保证预热成功。"""
        return invoke(bridge.select_model, slot)

    @server.tool(annotations=write, structured_output=True)
    def set_voice_pitch(semitones: StrictInt) -> dict[str, Any]:
        """将当前 RVC 角色的音高偏移设置为 -24 至 24 个半音；是绝对设置，不是累加。"""
        return invoke(bridge.set_pitch, semitones)

    @server.tool(annotations=write, structured_output=True)
    def set_voice_index_ratio(ratio: StrictFloat) -> dict[str, Any]:
        """将当前角色检索比例设为 0–1；没有索引文件时只允许 0。"""
        return invoke(bridge.set_index_ratio, ratio)

    @server.tool(annotations=write, structured_output=True)
    def set_voice_bypass(enabled: StrictBool) -> dict[str, Any]:
        """开启原声旁路或关闭旁路使用 RVC；保留引擎启停状态，不改变 Windows 音频路由。"""
        return invoke(bridge.set_bypass, enabled)

    @server.tool(annotations=write, structured_output=True)
    def start_voice_audio() -> dict[str, Any]:
        """请求引擎读取已配置的 CABLE Output 并播放到已配置输出。需要模型及完整路由配置；结果仅确认配置。"""
        return invoke(bridge.start_audio)

    @server.tool(annotations=write, structured_output=True)
    def pause_voice_audio() -> dict[str, Any]:
        """请求暂停引擎音频，会使仍路由到虚拟线的 Dot 无声。恢复原声请使用旁路并启动，或手动改回耳机输出。"""
        return invoke(bridge.pause_audio)

    return server


def main():
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
