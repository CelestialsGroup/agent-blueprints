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
- conversation_id
- turn_id
- branch_id
- client_message_id
- scenario_id
- scenario_version 与 scenario_definition_digest
- request_digest
- idempotency_key_digest
- usage=single
- nonce
- capabilities
- limits
- policies
- commercial_authorization（Business 签发的 entitlement/quota/plan/settlement 快照引用）

默认：

```text
max_ttl = 300 seconds
clock_skew = 30 seconds
```

## 请求摘要

使用 RFC 8785 JCS。

不能使用 `json.dumps(sort_keys=True)`、普通 Map 排序或语言默认序列化代替。

摘要覆盖完整 WorkOrder JSON，唯一排除字段：

```text
execution_grant
```

包括：

- source
- work
- delivery
- placement_constraints
- metadata

`work` 中的 Conversation/Turn/Message 绑定和 Experience revision 选择属于摘要覆盖范围，不能在 Grant 签发后替换模板、分支或父消息。

因此 metadata 不得绕过授权改变行为。

输入必须满足 I-JSON/JCS 可互操作要求：

- UTF-8
- 不允许重复 Object Key
- 不允许 NaN/Infinity
- 超出安全整数范围的业务整数使用字符串
- 多语言实现使用 `contracts/testdata/jcs-v1/vectors.json`
- Python、Node 和 Go 必须产生完全相同的 canonical bytes
- 详细规则见 `37_JCS_AND_IJSON_PROFILE.md`

## 原子消费

同一 PostgreSQL 事务：

1. Upsert 并锁定 IdempotencyRecord。
2. 比较 request_digest。
3. 校验 Token Profile、签名、时间、issuer、audience。
4. 校验 authenticated client 与 Grant client。
5. 校验 idempotency digest。
6. 唯一插入 GrantConsumption。
7. 校验 CommercialAuthorizationSnapshot ID/digest、有效期与 quota reservation。
8. 锁定或创建 Conversation 及其 Workspace，追加 Message，并创建 WorkOrder。
9. 写 Workflow Start Outbox 与 Canonical Event。
10. 提交事务。

## 重复请求

- 同一 Client + Idempotency Key + Request Digest：返回原 WorkOrder。
- 同 Key 不同 Digest：409。
- 同 Grant 用于不同请求：409。
- 同 Grant 用于相同已完成幂等请求：返回原 WorkOrder，不重复执行。
