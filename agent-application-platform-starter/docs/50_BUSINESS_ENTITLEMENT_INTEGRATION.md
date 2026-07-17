# Business 身份、会员与权益集成

## 边界

参考 Business Application 拥有 User/Login、Organization、Membership、Product、Plan、Order、Payment、Refund、Invoice、商业余额和额度账本。Agent Platform 只拥有技术执行和 Usage 事实。

```text
Membership / Plan
 -> 不可变 EntitlementRevision
 -> 幂等 QuotaReservation
 -> CommercialAuthorizationSnapshot
 -> ExecutionGrant / WorkSession
 -> Agent TechnicalUsage
 -> 在 Business 中结算 | 释放 | 对账
```

## 准入

在执行 Turn 前，Business 评估会员资格并预留商业额度。它签发 ExecutionGrant，其中包含 CommercialAuthorizationSnapshot 摘要、已授权 Capability、Policy 和硬限制。Agent Platform 验证签名，并随 WorkOrder/RunManifest 保存快照；执行热路径绝不查询 Business 会员数据库。

除摘要外，该快照还携带显式授权的 Entitlement ID、Capability 和最大限制。这是本地 Catalog 过滤和准入比较的必要条件；只有摘要而没有受治理值，不能作为可执行授权证据。

WorkSession 携带相同授权身份用于 Catalog 过滤，但每个新的可执行 Turn 都需要新的 Grant 和 Reservation。

## 结算

Agent Platform 通过已注册的 Delivery/Usage Target 报告不可变 TechnicalUsage 和 WorkOrder 终态结果。Business 以幂等方式：

- 按 Reservation 结算已确认 Usage；
- 释放未使用的 Reservation；
- 对账延迟或更正后的 Usage；
- 应用退款或商业策略。

Platform 无权修改商业余额或推断价格。Business 无权改写 TechnicalUsage 证据。

## 参考应用模块

仓库实现应将 `business-web/business-api` 与 `agent-workbench/agent-api` 分离。参考 Business Application 提供 Login、个人 Organization、Free/Pro Plan、Membership、计费、Entitlement 评估、Reservation/Settlement 和 WorkSession 交接，并且只消费版本化 Agent Platform 契约。
