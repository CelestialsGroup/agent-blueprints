# 生产运行治理

## SLI 与初始 SLO

必须观测 Access 延迟/可用性、Temporal 队列延迟、Invocation 重试/未知结果/对账时长、Event 追加/SSE 延迟、DeerFlow/Sandbox 启动/恢复、Runtime 连接、Artifact/Delivery 和 Gateway 预算/拒绝指标。

初始目标：Agent Access 月可用性 99.9%，已接受 WorkOrder 持久化丢失 0，P95 接受延迟 < 500ms，P95 持久 Event 延迟 < 3s，`outcome_unknown` 24 小时内对账率 99%，Delivery 24 小时最终送达率 99.9%。这些目标必须经容量测试后按部署等级修订。

## 1. 恢复目标

初始基线：

| 数据 | RPO | RTO |
|---|---:|---:|
| Agent PostgreSQL | 5 分钟 | 60 分钟 |
| Temporal Persistence | 5 分钟 | 60 分钟 |
| Artifact Object Storage | 15 分钟 | 120 分钟 |
| Signing/Verification Keys | 0 | 30 分钟 |

## 2. 准入与背压

- Client 请求速率
- Tenant 并发量
- Scenario 并发量
- Capability 队列深度
- Provider 并发量
- Resource Class 容量
- 全局上限

响应：

- 429：调用方限制
- 503 + Retry-After：平台容量不足
- `accepted`/`queued`：在排队 SLO 内

## 3. 公平性

- 每 Tenant 并发量
- 加权队列
- 预留容量
- 突发限制
- 饥饿告警

## 4. Token 与密钥

- Service Token 使用 RFC 9068 Profile 或等价验证
- 生产使用 Audience 限制
- 推荐 Sender-constrained Token
- 所有 JWT 类型互斥验证
- JWKS Endpoint 预注册，拒绝 Token Header 动态 URL
- Signing Key 轮换与撤销

## 5. Temporal

- Worker Deployment + Build ID
- Workflow Type 明确固定版本/自动升级策略
- Continue-as-New
- 加密 Payload Codec
- History 大小告警
- Namespace 保留期限
- 回放测试

## 6. 数据保留

- Event：90 天，按 Event Type Retention Class 覆盖
- Artifact：30 天
- Invocation：180 天
- Usage：365 天
- Audit：365 天
- WorkSession：失效后记录 30 天
- RuntimeRecording：按 Business/Tenant Policy，默认 30 天；Recording Audit 独立保留

敏感内容避免进入日志、Event 和 Temporal History。

## 7. Webhook 与 Connector

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
- Work Sequence 锁竞争
- Temporal 队列延迟/History
- Model Token
- Sandbox/Browser 内存
- Conversion CPU
- Object Storage 吞吐量

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

多节点验收至少覆盖：任意 API/Worker/Provider Pod 删除、跨 Pod SSE 续传、Redis 通知丢失补拉、Provider Controller 故障转移、Sandbox Node 故障、Runtime 重路由、Temporal 回放、Artifact 并发提交和 Migration 回滚。

## 11. Sandbox 容量

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
