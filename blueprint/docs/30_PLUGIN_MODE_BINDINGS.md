# Plugin Runtime 模式绑定规范

所有运行模式必须映射到统一 Invocation 语义，但传输细节不同。

## service

- 使用 Plugin Invocation HTTP/gRPC 协议。
- mTLS Workload Identity。
- Invocation Bearer 绑定 Attempt。
- 服务必须支持 Readiness、Liveness、Draining。

## remote_service

- Endpoint 只能由管理员或受信任业务配置注册。
- 禁止 Plugin Manifest 或 WorkOrder 提供任意运行时 URL。
- TLS 证书、DNS、IP 范围和数据驻留策略必须校验。
- 推荐支持状态查询和业务幂等键。

## job

固定文件布局：

```text
/agent/input/invocation.json
/agent/input/artifacts/
/agent/output/result.json
/agent/output/error.json
/agent/output/progress.jsonl
```

环境变量只包含非敏感标识和短期引用。

结果以 Result/Error Manifest 为准；进程退出码仅表示传输状态：

- 0：已写入有效 Result 或 Error Manifest
- 70：Plugin 协议/内部传输失败
- 143：收到终止信号

Kubernetes Job 被删除但外部副作用结果未知时，Invocation 进入 `outcome_unknown`。

## sandbox_cli

- Command 必须来自已签名 Manifest，不接受用户任意可执行路径。
- Input 通过固定 JSON 文件或 Stdin。
- Output 使用同一 Result/Error Manifest。
- SIGTERM 用于取消。
- 工作目录限定在本次 Sandbox Workspace。

## mcp

本节只描述旧 Plugin Bridge 的 MCP 运行模式，不构成平台 MCP Client 或 Server 支持声明。新 MCP Connector 必须按 `56_AGENT_INTEROPERABILITY_PROTOCOLS.md` 固化 Role、Feature、Transport、协议版本、Server identity、Tool Projection、Negotiation Evidence 和专用 Conformance，再映射到 `capability-provider-v1`。

MCP Adapter 负责：

- Capability Request 到 Tool Call 的映射
- Schema 验证
- Progress/Event 映射
- 取消能力声明
- Artifact Staging 封装
- 错误标准化

不支持状态查询或幂等的 MCP Tool 不得声明对应 Capability 特性。

## 过期 Attempt

所有运行模式的结果必须携带：

- invocation_id
- invocation_attempt_id
- fencing_token

平台拒绝旧 Fencing Token 的结果。

## 与 Sandbox Provider 的区别

Sandbox 不作为普通 `service` Plugin 处理完整生命周期。

Sandbox Provider 拥有独立契约，因为它需要：

- 期望状态/观测状态
- Lease
- Exec Operation
- Runtime Session
- Snapshot/Restore
- 资源用量
- Node/Controller 恢复

Plugin 可以在 Sandbox 内执行，但不能替代 Sandbox Registry。
