# 扩展结构

```text
src/dot_rvc/
  cli.py / mcp_server.py   用户入口与 MCP 工具
  engine.py               参数约束、路由检查、修改回读
  backends/base.py         Backend 协议
  backends/w_okada_v1.py   HTTP 端点、表单编码、连接错误
  audio.py                本机设备清单与显式虚拟线信号测试
  config.py               本机 TOML 配置及环境变量覆盖
  models.py               文件清单（不加载权重）
scripts/                  安装、进程管理、基础推理测试、源码打包
runtime/                  可重新安装的运行环境、上游代码、缓存和日志
models/                   用户角色文件
```

## 新引擎

实现 `Backend.read_state()` 与 `write_setting()`，并在 `backends/__init__.py` 注册名称。CLI/MCP 使用相同服务，工具名和用户参数不依赖 HTTP 路径。

目前内部状态契约沿用 v1 字段名，以避免多个未经验证的抽象层。新适配器需转换成这一契约：

| 字段 | 契约 |
| --- | --- |
| modelSlots / modelSlotIndex | 模型槽位列表及选择，RVC 槽位含 modelFile、indexFile、name |
| serverAudioInputDevices / serverAudioOutputDevices | 含 index、name、hostAPI 的设备列表 |
| serverInputDeviceId / serverOutputDeviceId / serverMonitorDeviceId | 当前设备编号；monitor -1 表示关闭 |
| enableServerAudio / serverAudioStated | 整数 0/1；后者为启动请求，不是音频存活证据 |
| passThrough | 布尔值，true 为原声旁路 |
| modelSamplingRate / pipelineInfo.inferencer | 模型初始化预检 |
| tran / indexRatio | 音高与索引比例 |

未来如果引擎不适合槽位模型，先版本化这一内部契约并添加真实契约测试，再改服务层。不要伪造已启动、已测延迟或已完成音频转换。

新增设置必须验证输入、明确停机要求、修改后回读；超时或回读失败不自动重试。异常统一使用 BridgeError，传到 MCP 时转换为工具错误。

## 设备与配置

TOML 保存设备名称与 host API；每次启动重新解析编号，零匹配或多匹配时报错。首版路由明确支持 VB-CABLE，其他虚拟设备应增加路由策略及测试，而不是删除防回录检查。音频线程由上游引擎管理，MCP 不逐帧传输音频。

配置优先级：环境变量 > 本机 TOML > 默认值。支持 DOT_RVC_CONFIG、DOT_RVC_ENGINE_URL、DOT_RVC_MODELS_DIR、DOT_RVC_BACKEND。相对模型目录以 TOML 所在目录解析。

## 运行时升级

更新 engine-manifest.json 的源码提交和资产哈希、重新生成 engine-requirements.lock.txt，验证 CPU 导入、CUDA 基础推理、API 回读及驱动信号。角色音色、连续通话和打断行为必须单独验收。run_engine.py 是本项目的启动包装，不改写上游源码；它跳过样例角色下载、使用空样例目录并关闭自动重载和原生 GUI 启动。

当前启动包装仍固定 v1、18888 端口和 PyTorch HuBERT 路径。配置里的 backend 可扩展控制层，但不会自动下载/启动任意引擎。未来可增加独立生命周期适配器、角色配置和本地界面。
