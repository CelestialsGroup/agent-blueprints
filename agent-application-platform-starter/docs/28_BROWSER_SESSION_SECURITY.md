# 浏览器 WorkSession 安全

## 1. 默认模式

Standalone Agent Workbench 使用：

```text
Business Backend
 -> 创建 WorkSession
 -> 返回一次性 Exchange Token
 -> Browser 在 Workbench Origin 完成 Exchange
 -> Server 设置 HttpOnly Secure Cookie
```

不把长期 Bearer Token 放入：

- URL Query
- localStorage
- sessionStorage
- 浏览器日志
- iframe 属性

## 2. Cookie

默认 Cookie：

```text
__Host-agent_session
Secure
HttpOnly
Path=/
```

SameSite 由部署模式决定：

- 顶级导航 Workbench：`Lax` 或 `Strict`
- 跨站嵌入：需要经过安全评审，不默认支持第三方 Cookie

## 3. SSE

原生 EventSource 无法可靠设置自定义 Authorization Header。

浏览器 SSE 默认使用同源 HttpOnly Cookie。

Headless SDK 可以使用内存中的 WorkSession Bearer，并通过 Fetch streaming 实现事件流。

## 4. WebSocket

WebSocket 不得在 Query String 中携带长期 Token。

使用：

- WorkSession Cookie，或
- 一次性 Runtime Session Exchange，或
- 受控 WebSocket Subprotocol Token

Runtime Token 必须短期、单次或连接绑定。

## 5. CSRF

Cookie 认证的写操作要求：

- SameSite Cookie
- Origin/Referer 校验
- X-CSRF-Token
- 禁止简单跨域请求
- 严格 CORS Allowlist

## 6. Token 类型隔离

不同 JWT 使用不同：

- typ
- audience
- validation profile
- Key namespace

包括：

- OAuth Access Token：`at+jwt`
- ExecutionGrant：`agent-execution-grant+jwt`
- WorkSession：`agent-work-session+jwt`
- Plugin Invocation：`agent-plugin-invocation+jwt`

## 7. 撤销

WorkSession 保存 session_version 和 revoked_at。

权限变更、用户退出、商业授权失效或安全事件可以立即撤销 Conversation WorkSession；仅当 Session 被缩窄到该 WorkOrder 时，WorkOrder 终止才要求撤销。

长连接必须在 Token 到期或 Session 撤销时关闭。
