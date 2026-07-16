# 生产运行治理

## 1. 恢复目标

初始基线：

| 数据 | RPO | RTO |
|---|---:|---:|
| Agent PostgreSQL | 5 分钟 | 60 分钟 |
| Temporal Persistence | 5 分钟 | 60 分钟 |
| Artifact Object Storage | 15 分钟 | 120 分钟 |
| Signing/Verification Keys | 0 | 30 分钟 |

## 2. Admission 与 Backpressure

- Client request rate
- Tenant concurrency
- Scenario concurrency
- Capability queue depth
- Provider concurrency
- Resource class capacity
- Global ceiling

响应：

- 429：调用方限制
- 503 + Retry-After：平台容量不足
- accepted/queued：在排队 SLO 内

## 3. Fairness

- per-tenant concurrency
- weighted queue
- reserved capacity
- burst limit
- starvation alert

## 4. Token 与密钥

- Service Token 使用 RFC 9068 Profile 或等价验证
- 生产使用 audience restriction
- 推荐 sender-constrained token
- 所有 JWT 类型互斥验证
- JWKS Endpoint 预注册，拒绝 Token Header 动态 URL
- Signing Key 轮换与撤销

## 5. Temporal

- Worker Deployment + Build ID
- Workflow Type 明确 Pinned/Auto-Upgrade
- Continue-as-New
- Encrypted Payload Codec
- History Size Alert
- Namespace Retention
- Replay Test

## 6. 数据保留

- Event：90 天，按 Event Type Retention Class 覆盖
- Artifact：30 天
- Invocation：180 天
- Usage：365 天
- Audit：365 天
- WorkSession：失效后记录 30 天

敏感内容避免进入日志、Event 和 Temporal History。

## 7. Webhook/Connector

- 注册制 Endpoint
- HTTP Message Signature 或 mTLS
- Replay Window
- Egress Gateway
- DLQ
- SSRF 防护

## 8. 容量

估算：

- WorkOrder QPS/并发
- SSE/Runtime Gateway 连接
- Event 写入率
- Work sequence lock contention
- Temporal queue latency/history
- Model tokens
- Sandbox/Browser memory
- Conversion CPU
- Object Storage throughput

## 9. 降级

- 停止重型任务
- 关闭 Optional Converter
- Provider Draining
- 降低 Preview
- Artifact 只读
- 延迟非关键 Projection
- 明确 503

## 10. 灾难恢复

演练：

- PostgreSQL PITR
- Temporal 恢复
- Object Storage
- Signing Keys
- Cell 故障
- Provider 故障
- Delivery DLQ
- Event Projection 重建

## 11. Sandbox Capacity

Sandbox Admission 需要独立容量模型：

- pending/ready Sandbox
- CPU/Memory/GPU requests
- Runtime Profile capacity
- Node/AZ capacity
- Workspace volume quota
- Browser session count
- Snapshot bandwidth
- Provider provisioning queue

容量不足时：

- 不创建超出硬预算的 Sandbox
- 返回 429（租户限制）或 503 + Retry-After（平台容量）
- 不静默改用更弱隔离级别
- 可按 Policy 选择另一个已通过同等 Conformance 的 ProviderRevision
