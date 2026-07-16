# Identity 与 Authorization

## 1. Service Principal

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

## 2. WorkSession Principal

浏览器默认不直接接收可长期复用 Bearer Token。

流程：

1. Service Principal 创建 WorkSession。
2. 返回一次性 Exchange Token。
3. Browser 在 Workbench Origin Exchange。
4. 设置 HttpOnly Secure Cookie。

Headless SDK 可使用内存 Bearer Profile。

## 3. WorkSession Subject

默认 `subject_mode=owner`，Principal 必须等于 WorkOrder 的 Grant Principal。

`subject_mode=delegated` 仅在以下条件允许：

- Service Token 有 `session:delegate`
- WorkOrder collaboration policy 允许
- 记录 delegation reason 和 Audit

## 4. Scope

Service：

- work:create
- work:read
- work:cancel
- session:create
- session:delegate
- artifact:read
- artifact:write
- provider:admin

WorkSession：

- work:read
- work:cancel
- event:subscribe
- artifact:read
- artifact:edit
- artifact:export
- work:control
- approval:read
- approval:decide
- runtime:view
- runtime:control

OpenAPI 使用 `x-required-work-session-scopes` 表达 Bearer/Cookie Scheme 无法原生表达的 Scope。

## 5. Object Authorization

每次资源访问必须同时校验：

```text
credential type
+ token profile
+ scope
+ internal tenant
+ work_order binding
+ object ownership
+ current session version
+ optional policy
```

不通过资源 ID 是否存在来泄露跨租户信息。

## 6. JWT 类型隔离

不同 Token 必须使用互斥验证规则、不同 audience 和明确 typ：

- OAuth Access Token：`at+jwt`
- ExecutionGrant：`agent-execution-grant+jwt`
- WorkSession：`agent-work-session+jwt`
- Plugin Invocation：`agent-plugin-invocation+jwt`

未知 typ、alg、iss、aud 或 kid 必须拒绝。
