# Agent Workbench 接入

## 部署与交接

第一阶段使用独立部署的 Agent Workbench。多个 Business Application 复用同一 Workbench，但继续拥有自己的登录、会员、订单和业务导航。

```text
Business UI
 -> Business Backend
 -> Create/Resume AgentConversation
 -> Create Conversation WorkSession
 -> One-time Exchange
 -> Agent Workbench Cookie Session
```

## 浏览器认证

浏览器默认使用 HttpOnly Secure WorkSession Cookie：

- 原生 EventSource 无法可靠设置自定义 Authorization Header；
- WebSocket 不在 Query 中携带长期 Token；
- 浏览器不使用 localStorage 保存平台 Token。

可信 Headless SDK 可以使用仅存于内存、Scope 明确且到期自动关闭的 Bearer Token，并通过 Fetch streaming 订阅 SSE。详细规则见 `28_BROWSER_SESSION_SECURITY.md`。

## Workbench 视图与数据来源

| 视图 | 权威来源 | 传输或投影 |
|---|---|---|
| Chat | ConversationMessage、CanonicalEvent | REST + SSE |
| Plan | 标准 Runtime/Canonical Event | Timeline Projection |
| Timeline | CanonicalEvent `work_sequence` | SSE、断点续传 |
| Terminal | RuntimeSession、RuntimeRecording | Runtime Gateway、历史 Chunk |
| Browser | RuntimeSession、RuntimeRecording | Runtime Gateway、受 Capability Gate 控制的录制 |
| Desktop | RuntimeSession、RuntimeRecording | Runtime Gateway、受 Capability Gate 控制的录制 |
| Files | Branch WorkspaceRevision、Artifact、文件增量 Recording | Artifact API、受控 Workspace Projection；分支间不共享可变 Head |
| Artifact | ArtifactVersion、Preview/Edit/Conversion Session | Agent Access API |
| History | Conversation、Branch、Recording Manifest | REST + 回放投影 |
| Tasks | 标准 `runtime.task.*` Event | Task Projection；不暴露 Provider PID/本地队列 |

Workbench 还提供 Approval、Pause/Resume、Cancel、Conversation 分支、Export 和按 Entitlement 过滤的 Experience Catalog。前端不得直接解释 Provider 私有 Thread、Checkpoint、Pod、VM 或 Endpoint。

## 实时与历史路径

```text
实时状态：Platform/Runtime Core Registry -> CanonicalEvent -> SSE -> Chat / Plan / Timeline
实时画面：Sandbox Endpoint -> Runtime Gateway -> Terminal / Browser / Desktop
历史回放：CanonicalEvent + Recording Manifest + ArtifactVersion -> Workbench
```

实时 RuntimeSession 与历史 RuntimeRecording 是独立授权资源。没有存活 Sandbox 时，Workbench 仍应能够消费持久 Event、Artifact 和已完成 Recording。

## Runtime Gateway v1

Terminal、Browser、Desktop、Port Forward 和 File Delta 共用 `runtime-gateway/v1` Envelope：

- 每次连接使用递增 `connection_generation`，旧 Generation 的 Data/Control 一律拒绝；
- 每个 Direction/Channel 使用连续 `frame_sequence`；
- ACK 与 Receive Window 执行背压，Control 通过 `command_id + control_digest` 幂等，ID 相同但摘要不同必须拒绝；
- 重连携带每个订阅 Channel 的 Cursor，窗口过期返回显式 Gap，并转入 RuntimeRecording；
- Recording Checkpoint 同时绑定 Channel `recorded_through_sequence`、Chunk Sequence 和 WorkOrder `work_sequence`；
- Port Forward 只允许短期实时传输，不进入 RuntimeRecording。

Phase 0 只冻结 Terminal Profile。Browser/Desktop 可以复用 Envelope，但录制在 Capture、Consent、Redaction 和容量 Conformance 完成前保持关闭。

Terminal Recording 也只能持久化经过 Emit-time Scrub/Schema Gate 的 Chunk；Workbench 不得访问临时未脱敏缓冲或把部分失败显示为完整回放。

Workbench、Headless SDK 和未来 IDE/ACP 都是 Presentation Adapter；它们消费相同 Conversation、Command、Event、Artifact 和 Usage，不拥有独立 Session 事实。

## Capability 驱动 UI

Scenario 和 Workbench 只按 Capability、Profile、Catalog Revision 和授权结果显示功能。例如，转换入口查询 `converter.html-to-pptx` 是否可用，不比较或硬编码 Plugin ID。

html-anything、Open Design 和 motion-anything 优先拆分为 Catalog Importer、Template/Skill、Converter、Renderer 或 Editor Provider。只有平台原生控件无法表达的富交互才使用 UI Extension。

## UI Extension

第一阶段只允许：

- Schema-driven UI；
- 平台认证的 `UiExtensionManifest`；
- 固定 Artifact Bundle、Slot、CSP Profile 和 `ui-extension/v1` 类型化消息协议；
- 不透明 Origin 的 Sandboxed iframe。

始终禁止任意远程 JavaScript。Extension 不得访问 WorkSession Cookie、原始 Token、宿主 DOM 或任意网络。

## Agent Engineering Workbench

Agent Workbench 与 Agent Engineering Workbench 是两个独立授权面：

| Workbench | 用途 | 权限来源 |
|---|---|---|
| Agent Workbench | Conversation 执行、实时 Runtime、Artifact 和历史回放 | Business WorkSession、ExecutionGrant、Entitlement |
| Agent Engineering Workbench | Trace 导入、Run 对比、调试副本和 Evaluation UX | 内部角色、对象级 Grant |

工程工作台只消费 CanonicalEvent、RuntimeRecording、ArtifactVersion、RunManifest 和 TechnicalUsage 的只读投影。修改 Prompt、Tool、Model 或历史消息只作用于调试副本；重新运行必须创建新的 ConversationBranch、WorkOrder、ExecutionGrant、ProviderResolution 和 RunManifest。

工程工作台不得改写原始运行证据、把第三方 Trace 提升为平台事实，或通过本地 Bash、MCP、模型直连和调试 Transport 绕过 Sandbox 与 Gateway。v0.9 只保留该边界，不新增 Evaluation/Rubric 稳定领域对象。
