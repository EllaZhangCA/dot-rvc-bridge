"""Adapter for w-okada's open-source v1 /info + /update_settings API.

Source contract: d8ef15799470193f7c8176ef471245753a656626.
No claim of VCClient v2 binary compatibility or successful audio playback.
"""

import math
import re
import threading

from .backends import create_backend
from .backends.base import Backend
from .errors import BridgeError

from .config import Config
from .models import inventory


class Engine:
    def __init__(self, config: Config, transport=None, *, backend: Backend | None = None):
        self.config = config
        self.backend = backend or create_backend(config, transport)
        self.lock = threading.RLock()

    def info(self) -> dict:
        data = self.backend.read_state()
        for key in ("modelSlots", "serverAudioInputDevices", "serverAudioOutputDevices"):
            if not isinstance(data.get(key), list) or any(not isinstance(item, dict) for item in data[key]):
                raise BridgeError("incompatible_engine", f"缺少兼容 v1 API 的 {key} 列表。")
        for key in ("serverAudioStated", "enableServerAudio"):
            if type(data.get(key)) is not int or data[key] not in (0, 1):
                raise BridgeError("incompatible_engine", f"缺少兼容 v1 API 的 {key} 状态。")
        if type(data.get("passThrough")) is not bool or type(data.get("modelSlotIndex")) not in (int, str):
            raise BridgeError("incompatible_engine", "无法识别模型选择或旁路状态。")
        return data

    @staticmethod
    def _slot(info: dict, slot_id=None) -> dict:
        wanted = info["modelSlotIndex"] if slot_id is None else slot_id
        for slot in info["modelSlots"]:
            if slot.get("slotIndex") == wanted and slot.get("voiceChangerType") == "RVC" and slot.get("modelFile"):
                return slot
        raise BridgeError("model_missing", "请先在引擎界面导入并选择一个 RVC 模型。")

    @staticmethod
    def _device(info: dict, direction: str):
        device_id = info.get(f"server{direction}DeviceId")
        for device in info[f"serverAudio{direction}Devices"]:
            if device.get("index") == device_id and type(device_id) is int and device_id >= 0:
                return device
        return None

    def blockers(self, info: dict) -> list[str]:
        problems = []
        try:
            self._slot(info)
        except BridgeError:
            problems.append("model_missing: 请在引擎中导入并选择 RVC 模型。")
        if not isinstance(info.get("modelSamplingRate"), (int, float)) or info["modelSamplingRate"] <= 0:
            problems.append("model_not_initialized: 引擎未报告有效的模型采样率。")
        if not isinstance(info.get("pipelineInfo"), dict) or not info["pipelineInfo"].get("inferencer"):
            problems.append("pipeline_not_initialized: 引擎未报告已初始化的 RVC 推理组件。")
        if info["enableServerAudio"] != 1:
            problems.append("server_audio_disabled: 请在引擎中启用 server audio 模式。")
        source = self._device(info, "Input")
        sink = self._device(info, "Output")
        if not source or not re.search(r"\bCABLE(?:-[A-Z])?\s+Output\b", str(source.get("name", "")), re.I):
            problems.append("input_not_cable: 首版要求输入为 VB-CABLE 的 CABLE Output。")
        if not sink or "cable" in str(sink.get("name", "")).lower():
            problems.append("output_not_headphones: 请选定耳机输出，不能接回虚拟线。")
        if source and sink and source.get("index") == sink.get("index"):
            problems.append("audio_loop: 输入与输出不能是同一设备。")
        if info.get("serverMonitorDeviceId") != -1:
            problems.append("monitor_enabled: 请关闭引擎的额外 monitor 输出，避免双重播放。")
        return problems

    def _summary(self, info: dict) -> dict:
        try:
            slot = self._slot(info)
            selected = {"slot": slot["slotIndex"], "name": slot.get("name", ""), "model": slot["modelFile"]}
        except BridgeError:
            selected = None
        blockers = self.blockers(info)
        chunks = info.get("serverReadChunkSize")
        configured_buffer_ms = round(chunks * 128 / 48000 * 1000, 2) if type(chunks) is int and chunks > 0 else None
        return {
            "engine_reachable": True,
            "adapter": self.backend.name,
            "engine_url": self.config.engine_url,
            "configuration_ready": not blockers,
            "blockers": blockers,
            "selected_model": selected,
            "audio_start_requested": info["serverAudioStated"] == 1,
            "configured_mode": "original" if info["passThrough"] else "rvc",
            "pitch_semitones": info.get("tran"),
            "index_ratio": info.get("indexRatio"),
            "input_device": self._device(info, "Input"),
            "output_device": self._device(info, "Output"),
            "audio_flow_verified": False,
            "dot_integration_verified": False,
            "measured_latency_ms": None,
            "configured_input_buffer_ms": configured_buffer_ms,
            "latency_note": "输入缓冲理论时长，不含推理、输出缓冲或 Dot 响应；不是实测延迟。",
            "note": "这是引擎配置回读；音频流、Dot 路由和实际音色仍需试听验证。",
        }

    def status(self) -> dict:
        local = inventory(self.config.models_dir)
        try:
            result = self._summary(self.info())
        except BridgeError as exc:
            result = {
                "engine_reachable": None if exc.code != "engine_unreachable" else False,
                "engine_url": self.config.engine_url,
                "configuration_ready": False,
                "blockers": [str(exc)],
                "audio_start_requested": None,
                "audio_flow_verified": False,
                "dot_integration_verified": False,
                "measured_latency_ms": None,
            }
        result["local_models"] = local
        return result

    def list_models(self) -> dict:
        info = self.info()
        return {"models": [
            {"slot": item.get("slotIndex"), "name": item.get("name", ""),
             "model_file": item["modelFile"], "index_file": item.get("indexFile", ""),
             "selected": item.get("slotIndex") == info["modelSlotIndex"]}
            for item in info["modelSlots"]
            if item.get("voiceChangerType") == "RVC" and item.get("modelFile")
        ]}

    def _update(self, key: str, value) -> dict:
        self.backend.write_setting(key, value)
        info = self.info()
        actual = info.get(key)
        if type(value) is float:
            matches = type(actual) in (int, float) and math.isclose(actual, value, abs_tol=1e-6)
        else:
            matches = type(actual) is type(value) and actual == value
        if not matches:
            raise BridgeError("update_not_confirmed", f"{key} 回读值与请求不同；请检查引擎，勿假定已生效。")
        return self._summary(info)

    def audio_plan(self, input_name: str, output_name: str, host_api: str, chunk_size: int | None = None) -> dict:
        """Read-only device resolution. Does not open streams or change settings."""
        info = self.info()
        if chunk_size is not None and (type(chunk_size) is not int or not 16 <= chunk_size <= 512):
            raise BridgeError("invalid_chunk_size", "输入缓冲块数须为 16–512 的整数；较小值需要实测稳定性。")
        selected = {}
        for direction, name in (("Input", input_name), ("Output", output_name)):
            if not name:
                raise BridgeError("device_not_configured", f"尚未指定 {direction}；请从 devices 清单复制完整设备名称。")
            matches = [d for d in info[f"serverAudio{direction}Devices"]
                       if d.get("name") == name and d.get("hostAPI") == host_api]
            if len(matches) != 1:
                raise BridgeError("device_not_unique", f"{direction}: {name} ({host_api}) 需要唯一匹配，当前为 {len(matches)} 个。若 devices 能看到新设备而引擎看不到，请在暂停后重启本项目引擎刷新设备，再预览。")
            selected[direction] = matches[0]
        settings = {"serverMonitorDeviceId": -1,
                    "serverInputDeviceId": selected["Input"]["index"],
                    "serverOutputDeviceId": selected["Output"]["index"],
                    "serverAudioSampleRate": 48000, "enableServerAudio": 1}
        if chunk_size is not None:
            settings["serverReadChunkSize"] = chunk_size
        trial = {**info, **settings}
        route_errors = [p for p in self.blockers(trial)
                        if not p.startswith(("model_missing:", "model_not_initialized:", "pipeline_not_initialized:"))]
        if route_errors:
            raise BridgeError("invalid_route", "；".join(route_errors))
        return {"settings": settings, "input_device": selected["Input"], "output_device": selected["Output"],
                "changes": {k: {"before": info.get(k), "after": v} for k, v in settings.items() if info.get(k) != v},
                "pause_required": bool(info["serverAudioStated"]),
                "windows_app_output": "将承载 Dot 的应用输出手动设为 CABLE Input；麦克风保持原设备。",
                "note": "只读路由预览，不修改 Windows 或引擎设置，不打开音频设备。"}

    def configure_audio(self, input_name: str, output_name: str, host_api: str, chunk_size: int | None = None) -> dict:
        """Resolve names each time; PortAudio IDs change after device/reboot changes."""
        with self.lock:
            info = self.info()
            if info["serverAudioStated"]:
                raise BridgeError("pause_required", "请先暂停，再配置音频设备。")
            plan = self.audio_plan(input_name, output_name, host_api, chunk_size)
            if plan["pause_required"]:
                raise BridgeError("pause_required", "请先暂停，再配置音频设备。")
            # Sequential readbacks: on any error stop and report partial configuration.
            applied = []
            for key, value in plan["settings"].items():
                try:
                    self._update(key, value)
                except BridgeError as exc:
                    raise BridgeError(exc.code, f"{exc} 已确认设置：{applied}；失败项 {key} 的结果可能未知。停止后续写入，请重新查询；未自动回滚。") from exc
                applied.append(key)
            result = self.status()
            result["note"] = "音频路由配置已回读，保持暂停。Windows 应用输出仍需单独设置。"
            return result

    def select_model(self, slot: int) -> dict:
        if type(slot) is not int or not 0 <= slot < 1000:
            raise BridgeError("invalid_slot", "模型槽位必须是 0–999 的整数。")
        with self.lock:
            info = self.info()
            self._slot(info, slot)
            if info["serverAudioStated"]:
                raise BridgeError("pause_required", "请先暂停引擎音频，再切换模型；切换后需要重新启动。")
            return self._update("modelSlotIndex", slot)

    def set_pitch(self, semitones: int) -> dict:
        if type(semitones) is not int or not -24 <= semitones <= 24:
            raise BridgeError("invalid_pitch", "此插件的音高范围为 -24 至 24 个半音，必须为整数。")
        with self.lock:
            self._slot(self.info())
            return self._update("tran", semitones)

    def set_index_ratio(self, ratio: float) -> dict:
        if type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
            raise BridgeError("invalid_index_ratio", "检索比例必须为 0–1 的有限数值。")
        with self.lock:
            slot = self._slot(self.info())
            if ratio > 0 and not slot.get("indexFile"):
                raise BridgeError("index_missing", "当前角色未配置 .index；检索比例只能设为 0。")
            return self._update("indexRatio", float(ratio))

    def set_bypass(self, enabled: bool) -> dict:
        if type(enabled) is not bool:
            raise BridgeError("invalid_bypass", "旁路开关必须为布尔值。")
        with self.lock:
            info = self.info()
            if not enabled:
                self._slot(info)
            return self._update("passThrough", enabled)

    def start_audio(self) -> dict:
        with self.lock:
            info = self.info()
            problems = self.blockers(info)
            if problems:
                raise BridgeError("not_ready", "；".join(problems))
            return self._update("serverAudioStated", 1)

    def pause_audio(self) -> dict:
        with self.lock:
            self.info()
            result = self._update("serverAudioStated", 0)
            result["note"] = (
                "已回读暂停请求。若 Dot 仍输出到虚拟线，现在将听不到它；"
                "恢复原声请启用旁路后重新启动音频，或在 Windows 将应用输出改回耳机。"
                "此工具不会恢复 Windows 输出设备。"
            )
            return result
