# ExecutionGrant 安全规范

## 格式

使用 JWS 紧凑序列化。

头部：

```json
{
  "alg": "EdDSA",
  "kid": "business-a-2026-01",
  "typ": "agent-execution-grant+jwt"
}
```

算法白名单：

- EdDSA
- ES256

禁止：

- none
- 对称共享密钥算法
- 动态接受 Token Header 中的 jku、x5u、jwk
- 未识别 crit

JWKS 或公钥只能来自管理员预注册的 ClientApplication 配置。

## Claim

必须包含：

- jti
- iss
- aud
- sub
- iat
- nbf
- exp
- client_app_id
- external_tenant_id
- external_principal_id
- principal_context（有界、不可变 PrincipalContextSnapshot）
- principal_context_digest
- conversation_id
- branch_id
- request_contract_id
- request_digest_profile=`rfc8785-request-excluding-execution-grant-v1`
- request_digest
- idempotency_key_digest
- usage=single
- nonce
- capabilities
- limits
- policies
- commercial_authorization（Business 签发的 entitlement/quota/plan/settlement 快照引用）

Turn Grant 额外且只能包含 `turn_id + client_message_id + scenario_id/version/definition_digest`。Control Grant 额外且只能包含 `work_order_id + control_request_id`，不得复制原 Turn/Message/Scenario Claim。`principal_context_digest` 必须匹配内嵌 Snapshot，Snapshot 的 Tenant/Principal/ClientApplication 必须匹配顶层 Claim。

默认：

```text
max_ttl = 300 seconds
clock_skew = 30 seconds
```

## 请求摘要

使用 RFC 8785 JCS。

不能使用 `json.dumps(sort_keys=True)`、普通 Map 排序或语言默认序列化代替。

`request_contract_id` 必须是实际提交的 `work-order-request:v1`、`conversation-turn-request:v1` 或 `work-order-control-request:v1`。摘要覆盖该精确请求 JSON，唯一排除字段：

```text
execution_grant
```

WorkOrderRequest 包括 `source`、`work`、`delivery`、`placement_constraints` 和 `metadata`；ConversationTurnRequest 包括 Message、Branch、Scenario、Experience、Delivery 和 Metadata；WorkOrderControlRequest 包括 WorkOrder/Conversation/Branch、Action、Active Work CAS、Append/Interrupt 专用 Message Head CAS、客户端 Control Input 和 Metadata。不能先把三种请求映射成含混的内部对象再计算摘要。

WorkOrderRequest 包括：

- source
- work
- delivery
- placement_constraints
- metadata

请求中的 Conversation/Turn/ClientMessage 绑定和 Experience Revision 选择属于摘要覆盖范围，不能在 Grant 签发后替换模板、分支、父消息或请求类型。ConversationTurn 的 `turn_id` 从已验证 Grant 创建，内部 `input_message_id` 由平台原子分配。

因此 metadata 不得绕过授权改变行为。

Limits 使用全字段 EffectiveExecutionLimits；空对象、字段缺失或未知 Profile 均 fail-closed。Control Grant 不得复用原 Turn Grant；客户端只提供 `client_control_input_id + content`，平台在 Grant 验证成功的同一事务内分配内部 `input_id + input_message_id`。

输入必须满足 I-JSON/JCS 可互操作要求：

- UTF-8
- 不允许重复 Object Key
- 不允许 NaN/Infinity
- 超出安全整数范围的业务整数使用字符串
- 多语言实现使用 Contract 资源 `contracts/testdata/jcs-v1/vectors.json`
- Python、Node 和 Go 必须产生完全相同的 canonical bytes
- 详细规则见 `37_JCS_AND_IJSON_PROFILE.md`

## 原子消费

同一 PostgreSQL 事务：

1. Upsert 并锁定 IdempotencyRecord。
2. 比较 request_digest。
3. 校验 `request_contract_id`、Digest Profile、Token Profile、签名、时间、issuer、audience。
4. 校验 authenticated client 与 Grant client。
5. 校验 idempotency digest。
6. 唯一插入 GrantConsumption。
7. 校验 CommercialAuthorizationSnapshot ID/digest、有效期与 quota reservation。
8. 校验 Grant 的 `iat..exp` 完整落在 PrincipalContextSnapshot 与 CommercialAuthorizationSnapshot 有效期内。
9. 锁定或创建 Conversation 及其 Workspace，追加 Message，并创建 WorkOrder。
10. 写 Workflow Start Outbox 与 Canonical Event。
11. 提交事务。

## 重复请求

- 同一 Client + Idempotency Key + Request Digest：返回原 WorkOrder。
- 同 Key 不同 Digest：409。
- 同 Grant 用于不同请求：409。
- 同 Grant 用于相同已完成幂等请求：返回原 WorkOrder，不重复执行。
