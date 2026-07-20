# 身份与授权

## Service Principal 身份

业务后端使用 OAuth2 Client Credentials。

生产 Access Token 应采用 RFC 9068 JWT Profile 或等价可验证 Profile：

- typ=`at+jwt`
- iss
- aud
- exp
- iat
- jti
- client_id
- scope

生产推荐 Sender-Constrained Token：

- mTLS Certificate Bound Token，或
- DPoP

Service Access Token 的接受 Profile 是闭合的：最长 300 秒、Issuer 预注册、Audience 只能是 Agent Access、`sub/client_id` 匹配已认证工作负载、Scope 按 Client allowlist 解析，未知 Claim 拒绝。`token_profile_signature_and_type_isolation` 与 `service_token_sender_constraint_and_replay` 必须在 Phase 0 身份集成测试中覆盖签名、`typ/alg/kid`、时钟偏差、Sender Constraint、`jti` 重放和 Mutation 幂等。

`client_app_id` 只从认证上下文产生。

## WorkSession Principal 身份

浏览器默认不直接接收可长期复用 Bearer Token。

流程：

1. Service Principal 创建 WorkSession。
2. 返回一次性 Exchange Token。
3. Browser 在 Workbench Origin Exchange。
4. 设置 HttpOnly Secure Cookie。

Headless SDK 可使用内存 Bearer Profile。

## WorkSession Subject

默认 `subject_mode=owner`，Principal 必须等于 Conversation/WorkOrder 的 Grant Principal。

`subject_mode=delegated` 仅在以下条件允许：

- Service Token 有 `session:delegate`
- WorkOrder collaboration policy 允许
- 记录 delegation reason 和 Audit

## 权限范围

Service 权限：

- work:create
- work:read
- work:cancel
- work:control
- authorization:revoke
- session:create
- session:delegate
- artifact:read
- artifact:write
- provider:admin
- conversation:create
- conversation:read
- catalog:read

`commercial_authorization_revocation_ingest`：`authorization:revoke` 只授予预注册且 sender-constrained 的 Business workload。Agent Access 从认证上下文派生 ClientApplication，以请求中的 `external_tenant_id` 解析 Platform Tenant，并要求 Path ID、已存 CommercialAuthorization ID/Digest 和 Revocation Notice 完全一致；`revocation_id + revocation_digest` 重放幂等，摘要冲突、跨 Client/Tenant、未来生效时间或超过允许 Clock Skew 的未来签发时间均拒绝。收据是 WorkSession 鉴权的同步 deny 索引，并以可恢复 intent 驱动 Session Version 撤销/断连和活动 WorkOrder SystemSafetyControl；浏览器 WorkSession 永远不能获得该 Scope。

WorkSession 权限：

- work:read
- work:cancel
- event:subscribe
- artifact:read
- artifact:edit
- artifact:export
- work:control
- conversation:read
- conversation:write
- catalog:read
- approval:read
- approval:decide
- runtime:view
- runtime:control
- recording:read

OpenAPI 使用 `x-required-work-session-scopes` 表达 Bearer/Cookie Scheme 无法原生表达的 Scope。

## 对象授权

每次资源访问必须同时校验：

```text
凭据类型
+ Token Profile
+ Scope
+ 内部 Tenant
+ ClientApplication 与 PrincipalContextSnapshot Digest
+ Conversation 绑定
+ 可选的 work_order 缩窄绑定
+ 对象所有权
+ 商业授权 ID/摘要/到期上限
+ 当前 Session 版本
+ 可选策略
```

不通过资源 ID 是否存在来泄露跨租户信息。

## Tenant 与数据隔离

- 所有权威记录显式携带内部 `tenant_id`，Repository scope、PostgreSQL RLS、Object Storage prefix、搜索/缓存 filter 和签名下载授权形成纵深防御。
- Secret 不进入 CanonicalEvent、日志或 Temporal History；Temporal 敏感 payload 使用加密 codec，大内容只保存 Artifact reference。
- Audit 默认不保存用户正文；删除按 retention、tombstone 和 crypto erasure policy 执行。
- Callback、Connector、Remote Provider 和 Storage endpoint 必须预注册；网络访问经 DNS/IP/rebinding/redirect policy 与 Egress Gateway 校验。
- ProviderResolution、IdempotencyRecord、CapabilityInvocation 和 Event Inbox 都显式 Tenant-qualified；`client_app_id` 只能来自认证上下文，不能信任请求体覆盖。
- PrincipalContextSnapshot 只包含有界角色、组和策略属性，使用 `rfc8785-principal-context-excluding-digest-v1`；凭据、Secret、Token、Email 和可变展示资料不得进入 Snapshot。ExecutionGrant 内嵌 Snapshot，Provider 只接收其摘要绑定。

## JWT 类型隔离

不同 Token 必须使用互斥验证规则、不同 audience 和明确 typ：

- OAuth Access Token：`at+jwt`
- ExecutionGrant：`agent-execution-grant+jwt`
- WorkSession：`agent-work-session+jwt`
- Plugin Invocation：`agent-plugin-invocation+jwt`
- Capability Invocation：`agent-capability-invocation+jwt`
- Artifact Gateway Operation：`agent-artifact-operation+jwt`
- Egress Invocation：`agent-egress-invocation+jwt`
- Agent Runtime Invocation：`agent-runtime-invocation+jwt`
- Sandbox Operation：`agent-sandbox-operation+jwt`

新 Provider 使用 Capability Invocation Profile；Artifact/Egress 使用独立操作 Profile；Plugin Profile 只用于兼容 Adapter。未知 typ、alg、iss、aud 或 kid 必须拒绝，Capability audience 必须来自 admitted ProviderResolution，Gateway audience 必须来自 RunManifest Port Binding。

九类 Profile 分别由 `service-access-token-jws-header`、`execution-grant-jws-header`、`work-session-jws-header`、`plugin-invocation-jws-header`、`capability-invocation-jws-header`、`artifact-gateway-jws-header`、`egress-invocation-jws-header`、`agent-runtime-invocation-jws-header` 和 `sandbox-operation-jws-header` 执行。验证器必须先按预期用途选择唯一 Profile，再同时验证闭合 Header 与 Claims；不得根据不受信任的 `typ` 动态选择验证器，也不得接受缺失 `kid`、未知 Algorithm 或额外 Header 参数。

所有 Runtime、Sandbox、Capability、Artifact、Egress 和兼容 Plugin 操作 Token 还必须用 `sub` 绑定当前 mTLS/Workload Identity；验证 Audience 不能替代验证 Caller Subject，另一合法工作负载取得 Token 时也必须拒绝。Sandbox Capability 发现是先于 Operation 的控制面协商，只允许已准入控制面 mTLS 身份，不接受也不要求伪造 Sandbox Operation Token。

执行 Token 的时间窗是双向包含关系：`nbf` 不早于所绑定 RuntimeAuthorization、PolicyDecision 或 Artifact Grant 生效，`exp` 不晚于对应执行期限。Runtime/Capability/Plugin 的 `safety_control` 只保留取消与对账权，不重新激活已经过期的执行或 Artifact 权限。
