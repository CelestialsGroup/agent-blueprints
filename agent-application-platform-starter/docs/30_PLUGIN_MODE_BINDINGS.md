# Plugin Runtime Mode 绑定规范

所有 Mode 必须映射到统一 Invocation 语义，但传输细节不同。

## 1. service

- 使用 Plugin Invocation HTTP/gRPC 协议。
- mTLS Workload Identity。
- Invocation Bearer 绑定 Attempt。
- 服务必须支持 readiness、liveness、draining。

## 2. remote_service

- Endpoint 只能由管理员或受信任业务配置注册。
- 禁止 Plugin Manifest 或 WorkOrder 提供任意运行时 URL。
- TLS 证书、DNS、IP 范围和数据驻留策略必须校验。
- 推荐支持 Status Query 和业务幂等键。

## 3. job

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
- 70：Plugin Protocol/Internal transport failure
- 143：收到终止信号

Kubernetes Job 被删除但外部副作用结果未知时，Invocation 进入 `outcome_unknown`。

## 4. sandbox_cli

- Command 必须来自已签名 Manifest，不接受用户任意可执行路径。
- Input 通过固定 JSON 文件或 stdin。
- Output 使用同一 Result/Error Manifest。
- SIGTERM 用于取消。
- 工作目录限定在本次 Sandbox Workspace。

## 5. mcp

MCP Adapter 负责：

- Capability Request 到 Tool Call 映射
- Schema 验证
- Progress/Event 映射
- Cancellation 能力声明
- Artifact Staging 封装
- 错误标准化

不支持状态查询或幂等的 MCP Tool 不得声明对应 Capability 特性。

## 6. Stale Attempt

所有 Mode 的结果必须携带：

- invocation_id
- invocation_attempt_id
- fencing_token

平台拒绝旧 Fencing Token 的结果。

## 7. 与 Sandbox Provider 的区别

Sandbox 不作为普通 `service` Plugin 处理完整生命周期。

Sandbox Provider 拥有独立 Contract，因为它需要：

- Desired/Observed State
- Lease
- Exec Operation
- Runtime Session
- Snapshot/Restore
- Resource Usage
- Node/Controller Recovery

Plugin 可以在 Sandbox 内执行，但不能替代 Sandbox Registry。
