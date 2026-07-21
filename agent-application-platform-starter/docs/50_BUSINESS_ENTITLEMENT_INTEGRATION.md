# Business 身份、会员与权益集成

## 边界

参考 Business Application 拥有 User/Login、Organization、Membership、Product、Plan、Order、Payment、Refund、Invoice、商业余额和额度账本。Agent Platform 只拥有技术执行和 Usage 事实。

```text
Membership / Plan
 -> 不可变 EntitlementRevision
 -> 幂等 QuotaReservation
 -> CommercialAuthorizationSnapshot
 -> ExecutionGrant / WorkSession
 -> MeterDefinition + TechnicalUsage + UsageReport
 -> BusinessSettlementEnvelope
 -> 在 Business 中结算 | 释放 | 对账
```

## 准入

在执行 Turn 或向现有 WorkOrder 发送可执行控制输入前，Business 评估会员资格并预留商业额度。它签发 ExecutionGrant，其中包含精确请求 Contract/Digest Profile、有界 PrincipalContextSnapshot 及其 Digest、CommercialAuthorizationSnapshot、已授权 Capability、Policy 和全字段硬限制。Agent Platform 先验证签名、Snapshot、请求摘要以及 Grant 时间窗完全落在两个 Snapshot 有效期内，再随 WorkOrder 保存完整快照，并在 RunManifest 固化 CommercialAuthorizationBinding 的 ID/Digest/`expires_at`；执行热路径绝不查询 Business 会员数据库，但任何 RuntimeAuthorization 都不能越过该到期上限。

Business 需要提前撤销已签发授权时，使用 sender-constrained Service Token 的 `authorization:revoke` Scope 提交不可变 CommercialAuthorizationRevocation。Notice 绑定外部 Tenant、Authorization ID/Digest、闭合原因、生效/签发时间和自身 Digest；Platform 从认证上下文派生 ClientApplication/Tenant，原子保存 Inbox/收据与可恢复 fan-out intent。收据提交后匹配 WorkSession、任何新 Runtime/Child Admission/执行/Gateway 授权立即 fail-closed，Platform Gateway 也拒绝关联旧授权的新副作用；异步 intent 递增/撤销 Session Version 并断开连接，所有仍活动且绑定该精确授权的 WorkOrder 原子进入取消意图，事务快照全部活动 AgentRun，并为每个 RuntimeRun 提高 Fencing、创建必须 Cancel 的独立 SystemSafetyControl。已被外部 Runtime 接纳的调用仍需逐 Run 取消确认和对账，不能宣称瞬时撤销。Platform 不修改 CommercialAuthorizationSnapshot，Business 也不能用撤销入口选择 Runtime Command、恢复执行或改变技术 Usage。

除摘要外，该快照还携带显式授权的 Entitlement ID、Capability 和最大限制。这是本地 Catalog 过滤和准入比较的必要条件；只有摘要而没有受治理值，不能作为可执行授权证据。

WorkSession 携带相同授权身份用于 Catalog 过滤，但每个新的可执行 Turn，以及现有 WorkOrder 的 Append/Interrupt 等可执行控制，都需要新的 Grant。空 Limits 或缺失字段一律拒绝，不能解释为默认值或无限额。

## 结算

Agent Platform 通过已注册的 Settlement Target 和签名 Business Callback 报告不可变 BusinessSettlementEnvelope。Envelope 与 UsageReport 在同一 Reservation 内连续编号并引用紧邻前驱；`settle` 嵌入完整 Final UsageReport，`reconcile` 嵌入完整 Correction UsageReport，`release` 不携带 Usage。Business 因而无需查询 Platform 数据库，即可按自己的价格事实幂等处理：

- 按 Reservation 结算已确认 Usage；
- 释放未使用的 Reservation；
- 对账延迟或更正后的 Usage；
- 应用退款或商业策略。

Platform 无权修改商业余额或推断价格。Business 无权改写 TechnicalUsage 证据。

MeterDefinition 只定义技术单位、聚合方式、测量权威和更正规则，不包含 Price、Currency 或 Plan。Provider 返回 UsageObservation；Platform 校验 Observation/Meter/Evidence/Attempt 后分配 TechnicalUsage identity、归属、幂等键和 `recorded_at`。TechnicalUsage 明确区分 Confirmed、Partial、Estimated 和 Corrected；Final UsageReport 不得把不完整测量伪装为零或已确认。Business 可以拒绝、延迟或对账 Envelope，但只能追加自身结算事实，不能回写 Platform Usage。HTTP 接收成功只证明 Envelope 已持久接纳，不等于商业结算成功。

## 参考应用模块

仓库实现应将 `business-web/business-api` 与 `agent-workbench/agent-api` 分离。参考 Business Application 提供 Login、个人 Organization、Free/Pro Plan、Membership、计费、Entitlement 评估、Reservation/Settlement 和 WorkSession 交接，并且只消费版本化 Agent Platform 契约。
