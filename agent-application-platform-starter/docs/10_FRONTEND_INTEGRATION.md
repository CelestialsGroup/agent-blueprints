# 前端接入

## 1. 推荐模式

第一阶段使用独立部署的 Agent Workbench。

```text
Business UI
 -> Business Backend
 -> Create/Resume AgentConversation
 -> Create Conversation WorkSession
 -> One-time Exchange
 -> Agent Workbench Cookie Session
```

这样多个业务项目复用同一 Workbench，同时保留自己的 User/会员/订单系统。

## 2. 浏览器认证

默认使用 HttpOnly Secure WorkSession Cookie。

原因：

- 原生 EventSource 不支持自定义 Authorization Header
- WebSocket 不应把长期 Token 放在 Query
- 避免 localStorage Token

详见 `28_BROWSER_SESSION_SECURITY.md`。

## 3. Headless SDK

可信客户端可使用内存 Bearer Token：

- 不落浏览器持久存储
- 使用 Fetch streaming 订阅 SSE
- 明确 Scope
- Token 到期自动关闭

## 4. UI Shell

平台提供：

- Chat
- Plan
- Timeline
- Terminal
- Browser
- Files
- Artifact 查看/编辑
- History
- Export
- Conversation 分支与后续 Turn
- Runtime 录制回放
- 按 Entitlement 过滤的 Experience Catalog

业务应用提供：

- 登录
- 会员
- 商品
- 订单
- 业务导航

## 5. Capability 驱动 UI

正确：

```text
capability("converter.html-to-pptx").available
```

错误：

```text
plugin_id == "html-to-pptx"
```

## 6. 第三方 UI

第一阶段只允许：

- Schema-driven UI
- 平台认证的 `UiExtensionManifest`，固定 Artifact Bundle、Slot、不透明 Origin iframe、CSP 与类型化 postMessage 协议

不允许任意远程 JavaScript。

html-anything、Open Design 和 motion-anything 优先拆分为 Catalog 导入器、Template/Skill、Converter、Renderer/Editor Provider。只有无法用平台 Workbench 表达的富交互部分才使用受隔离的 UI Extension。

## 7. Agent Engineering Workbench

面向用户的 Agent Workbench 与内部 Agent Engineering Workbench 是两个授权面：

- Agent Workbench 服务 Conversation 执行、实时 Runtime、Artifact 和历史回放，权限来自 Business WorkSession 与 Entitlement。
- Agent Engineering Workbench 服务受授权的开发、调试、Trace 导入、Run 对比和评测，权限来自独立的内部角色与对象级 Grant。

工程工作台可以借鉴 LLM Space 的 Run Snapshot、Trace Workbench 和 Rubric 对比体验，但只能消费 CanonicalEvent、RuntimeRecording、ArtifactVersion、RunManifest 和 TechnicalUsage 的只读投影。编辑 Prompt、Tool、Model 或历史消息只修改调试副本；点击重新运行必须创建新的 ConversationBranch、WorkOrder、ExecutionGrant 和 RunManifest。

工程工作台不得：

- 修改或覆盖原始 Run、Event、Recording、Artifact 和 Usage；
- 把导入的 Langfuse/OpenTelemetry/第三方 Trace 直接写成平台事实；
- 在浏览器、本地 JSON 或桌面配置中保存平台长期模型与 Provider 凭据；
- 通过本地 Bash、MCP、模型直连或调试 Transport 绕过 Sandbox 和强制 Gateway；
- 将内部调试权限继承给最终用户 WorkSession。

v0.9 只冻结上述消费与授权边界，不新增 Evaluation/Rubric 稳定领域对象。后续引入持久化评测能力时必须单独完成契约和安全评审。
