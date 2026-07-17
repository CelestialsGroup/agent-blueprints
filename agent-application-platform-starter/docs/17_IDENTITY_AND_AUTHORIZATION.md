# 身份与授权

## 1. Service Principal 身份

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

`client_app_id` 只从认证上下文产生。

## 2. WorkSession Principal 身份

浏览器默认不直接接收可长期复用 Bearer Token。

流程：

1. Service Principal 创建 WorkSession。
2. 返回一次性 Exchange Token。
3. Browser 在 Workbench Origin Exchange。
4. 设置 HttpOnly Secure Cookie。

Headless SDK 可使用内存 Bearer Profile。

## 3. WorkSession Subject

默认 `subject_mode=owner`，Principal 必须等于 Conversation/WorkOrder 的 Grant Principal。

`subject_mode=delegated` 仅在以下条件允许：

- Service Token 有 `session:delegate`
- WorkOrder collaboration policy 允许
- 记录 delegation reason 和 Audit

## 4. 权限范围

Service 权限：

- work:create
- work:read
- work:cancel
- work:control
- session:create
- session:delegate
- artifact:read
- artifact:write
- provider:admin
- conversation:create
- conversation:read
- catalog:read

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

## 5. 对象授权

每次资源访问必须同时校验：

```text
凭据类型
+ Token Profile
+ Scope
+ 内部 Tenant
+ Conversation 绑定
+ 可选的 work_order 缩窄绑定
+ 对象所有权
+ 商业授权 ID/摘要
+ 当前 Session 版本
+ 可选策略
```

不通过资源 ID 是否存在来泄露跨租户信息。

## 6. Tenant 与数据隔离

- 所有权威记录显式携带内部 `tenant_id`，Repository scope、PostgreSQL RLS、Object Storage prefix、搜索/缓存 filter 和签名下载授权形成纵深防御。
- Secret 不进入 CanonicalEvent、日志或 Temporal History；Temporal 敏感 payload 使用加密 codec，大内容只保存 Artifact reference。
- Audit 默认不保存用户正文；删除按 retention、tombstone 和 crypto erasure policy 执行。
- Callback、Connector、Remote Provider 和 Storage endpoint 必须预注册；网络访问经 DNS/IP/rebinding/redirect policy 与 Egress Gateway 校验。

## 7. JWT 类型隔离

不同 Token 必须使用互斥验证规则、不同 audience 和明确 typ：

- OAuth Access Token：`at+jwt`
- ExecutionGrant：`agent-execution-grant+jwt`
- WorkSession：`agent-work-session+jwt`
- Plugin Invocation：`agent-plugin-invocation+jwt`

未知 typ、alg、iss、aud 或 kid 必须拒绝。
