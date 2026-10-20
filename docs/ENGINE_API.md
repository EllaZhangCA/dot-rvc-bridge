# 引擎适配依据

本原型使用 w-okada/voice-changer 的开源 v1 服务端协议。源码核对及实际部署日期 2026-10-19，提交 `d8ef15799470193f7c8176ef471245753a656626`。已运行该源码版并验证状态查询、设备设置回读与 GPU 基础推理；角色模型及实时转换待验收。不据此承诺所有下载版兼容。

| 行为 | 已核对的源码契约 |
| --- | --- |
| 查询状态 | `GET /info`，JSON 包含 `status: OK`、`modelSlots`、`modelSlotIndex`、设备列表及配置 |
| 更新设置 | `POST /update_settings`，表单字段 `key` 和 `val`；随后重新 GET 状态确认 |
| 模型选择 | `modelSlotIndex`；只接受查询到的 RVC 槽位 |
| 半音偏移 | `tran` 整数；本插件自行限制为 ±24 |
| 检索比例 | `indexRatio`，本插件限制为 0–1，无索引只允许 0 |
| 原声旁路 | `passThrough`，表单值必须是小写字符串 `true` / `false` |
| 音频启停 | `serverAudioStated` 的 0/1；拼写按上游保留，不能改成 `Started` |
| 模型初始化 | `pipelineInfo` 的推理组件用于预检；不代表首个音频块已生成 |

上游在一些异常情况下可能返回 HTTP 200 和无效内容，所以客户端同时检查 HTTP、JSON、状态字段、API 结构及修改后的回读值。修改超时不自动重试，因为服务端可能已执行。模型切换会重新创建引擎对象，本原型不承诺失败时自动回滚旧模型。

音频启停字段是请求状态。上游音频线程还会检查设备及采样率，失败时可能保留请求值为 1。因此不能根据它推断“正在播放”。插件也没有 Dot 的原生打断事件，不承诺即时清空打断后的尾音。

主要参考文件：

- [REST 路由和表单字段](https://github.com/w-okada/voice-changer/blob/d8ef15799470193f7c8176ef471245753a656626/server/restapi/MMVC_Rest_Fileuploader.py)
- [模型槽位、旁路和设置更新](https://github.com/w-okada/voice-changer/blob/d8ef15799470193f7c8176ef471245753a656626/server/voice_changer/VoiceChangerManager.py)
- [音频设备状态及音频线程](https://github.com/w-okada/voice-changer/blob/d8ef15799470193f7c8176ef471245753a656626/server/voice_changer/Local/ServerDevice.py)
- [RVC 参数](https://github.com/w-okada/voice-changer/blob/d8ef15799470193f7c8176ef471245753a656626/server/voice_changer/RVC/RVCSettings.py)
- [RVC 推理组件状态](https://github.com/w-okada/voice-changer/blob/d8ef15799470193f7c8176ef471245753a656626/server/voice_changer/RVC/RVCr2.py)

修改控制适配器前，应先核对目标引擎实际版本和协议。遇到不兼容版本时返回错误，不尝试猜测其他端点。
