# 生产运行治理

## SLI 与初始 SLO

必须观测 Access 延迟/可用性、Temporal 队列延迟、Invocation 重试/未知结果/对账时长、Event 追加/SSE 延迟、各 AgentRuntimeProvider/SandboxProvider 启动与恢复、Runtime 连接、Artifact/Delivery 和 Gateway 预算/拒绝指标。指标必须携带 ProviderInstance/ProviderRevision 维度，支持跨框架比较。

初始目标：Agent Access 月可用性 99.9%，P95 接受延迟 < 500ms，P95 持久 Event 延迟 < 3s，`outcome_unknown` 24 小时内对账率 99%，Delivery 24 小时最终送达率 99.9%。只有在 WorkOrder、GrantConsumption、Workflow Start Outbox 和接受事件所在 PostgreSQL 写入采用跨故障域同步复制，并有提交确认、故障切换与恢复演练证据的部署等级，才可承诺“已返回 accepted 的 WorkOrder RPO=0”；异步副本/PITR 的基线不得宣称零丢失。

## 恢复目标

初始基线：

| 数据 | RPO | RTO |
|---|---:|---:|
| Agent PostgreSQL 通用状态/PITR 基线 | 5 分钟 | 60 分钟 |
| 已确认 accepted 的 WorkOrder 事务（仅同步复制等级） | 0 | 60 分钟 |
| Temporal Persistence | 5 分钟 | 60 分钟 |
| Artifact Object Storage | 15 分钟 | 120 分钟 |
| Signing/Verification Keys | 0 | 30 分钟 |

## 准入与背压

- Client 请求速率
- Tenant 并发量
- Scenario 并发量
- Capability 队列深度
- Provider 并发量
- WorkOrder AgentRun 总数、深度与并发量
- Resource Class 容量
- 全局上限

响应：

- 429：调用方限制
- 503 + Retry-After：平台容量不足
- `accepted`/`queued`：在排队 SLO 内

## 公平性

- 每 Tenant 并发量
- 加权队列
- 预留容量
- 突发限制
- 饥饿告警

## Token 与密钥

- Service Token 使用 RFC 9068 Profile 或等价验证
- 生产使用 Audience 限制
- 推荐 Sender-constrained Token
- 所有 JWT 类型互斥验证
- JWKS Endpoint 预注册，拒绝 Token Header 动态 URL
- Signing Key 轮换与撤销

## Temporal

- Worker Deployment + Build ID
- Workflow Type 明确固定版本/自动升级策略
- Continue-as-New
- 加密 Payload Codec
- History 大小告警
- Namespace 保留期限
- 回放测试

## 数据保留

- Event：90 天，按 Event Type Retention Class 覆盖
- Artifact：30 天
- Invocation：180 天
- Usage：365 天
- Audit：365 天
- WorkSession：失效后记录 30 天
- RuntimeRecording：按 Business/Tenant Policy，默认 30 天；Recording Audit 独立保留

敏感内容避免进入日志、Event 和 Temporal History。

## Telemetry Privacy

生产 Telemetry 使用闭合 Attribute Registry，默认不导出 Prompt、代码、完整路径、Tool 参数、Shell Command、Token 或错误正文。内容字段必须单独 Policy Gate，并同时经过：

1. Emit-time Secret/Home Path Scrub 与长度限制；
2. Export-time Schema/Gate Validator；
3. 违反闭合 Schema 或发现未脱敏 Secret 时丢弃整条 Record，不能 fail-open 导出。

TechnicalUsage、CanonicalEvent、RuntimeRecording 和第三方 Trace 与 OTEL 指标是不同证据层；Telemetry 丢失不得改变执行终态或结算事实。

RuntimeRecording 使用同样的 Fail-closed 原则，但不属于 Telemetry：未脱敏实时 Frame 只能驻留在有界内存，Scrub/Schema Gate 通过后才能持久化为 Chunk ArtifactVersion。Redaction 失败必须产生可见的 Recording Failure，不得保存原始字节后异步补救。

## Webhook 与 Connector

- 注册制 Endpoint
- HTTP Message Signature 或 mTLS
- Replay Window
- Egress Gateway
- DLQ
- SSRF 防护

## 容量

估算：

- WorkOrder QPS/并发
- Child Spawn Admission QPS、AgentRun 深度/扇出、共享预算锁竞争与孤儿 Run 数
- SSE/Runtime Gateway 连接
- Event 写入率
- Work Sequence 锁竞争
- Temporal 队列延迟/History
- Model Token
- Sandbox/Browser 内存
- Conversion CPU
- Object Storage 吞吐量

## 降级

- 停止重型任务
- 关闭 Optional Converter
- Provider Draining
- 降低 Preview
- Artifact 只读
- 延迟非关键 Projection
- 明确 503

## 灾难恢复

演练：

- PostgreSQL PITR
- Temporal 恢复
- Object Storage
- Signing Keys
- Cell 故障
- Provider 故障
- Delivery DLQ
- Event Projection 重建

多节点验收至少覆盖：任意 API/Worker/Provider Pod 删除、跨 Pod SSE 续传、Redis 通知丢失补拉、Provider Controller 故障转移、Sandbox Node 故障、Runtime 重路由、Temporal 回放、Artifact 并发提交和 Migration 回滚。

`RPO=0` 的验收必须证明同步副本 quorum、故障域隔离、主库确认后副本可见、自动/人工故障切换、PITR 与 Temporal/Outbox 重放不会重复消费 Grant 或丢失已接受 WorkOrder。仅配置参数、备份成功或 Gate 通过不构成该生产证据。

## Sandbox 容量

Sandbox Admission 需要独立容量模型：

- `pending`/`ready` Sandbox
- CPU/Memory/GPU Request
- Runtime Profile 容量
- Node/AZ 容量
- Workspace Volume 额度
- Browser Session 数量
- Snapshot 带宽
- Provider Provisioning 队列

容量不足时：

- 不创建超出硬预算的 Sandbox
- 返回 429（租户限制）或 503 + Retry-After（平台容量）
- 不静默改用更弱隔离级别
- 可按 Policy 选择另一个已通过同等 Conformance 的 ProviderRevision
