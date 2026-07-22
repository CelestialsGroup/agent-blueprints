# Experience Catalog 与 UI Extension

## Catalog 模型

Template、Skill Pack、Design System 和 Editor Profile 都是用户可见的 Experience。可变展示条目指向不可变 Revision；每个 WorkOrder 和 RunManifest 都保存所选 Revision 的摘要。

```text
ExperienceCatalogEntry
 -> 当前不可变 TemplateRevision
 -> 已认证 ProviderRevision
 -> 源/预览 ArtifactVersion
 -> 参数 SchemaReference
```

Catalog 发现结果按 Tenant/Client 绑定、生命周期、Capability 和 Business 签名的商业授权过滤。隐藏或未授权条目不能通过直接提交 ID 进行选择。

Run 准入会重新检查 Scenario 的 `required_tags`、TemplateRevision 的 `required_entitlements`，以及 `CommercialAuthorizationSnapshot` 中的显式 Entitlement 集合；仅靠 Catalog 过滤不能构成授权边界。

Scenario UI 使用签名 UI Schema 和类型化选项源。`/template_id` 等字段查询 Experience Catalog，绝不硬编码 Plugin ID。

## nexu-io 集成 Profile

- html-anything Template/Skill 目录：Catalog 导入器加 Template Provider。
- html-anything 生成：所选 AgentRuntimeProvider 下的 Skill，或 sandbox_cli/MCP Capability；不得依赖 DeerFlow 私有调用路径。
- html-to-pptx/html-video：生成 Artifact Staging 的 Converter Provider。
- Open Design/motion-anything Editor：Artifact Editor/Renderer Provider；嵌入 UI 前优先复用无界面 Capability 和 Catalog Asset。
- 完整桌面应用不得整体挂载到稳定内核中。

每个上游项目都通过源码 Commit/Package 摘要、许可证/来源、Adapter 版本和一致性证据固定。升级时创建新的 Provider 和 Experience Revision；已有 Run 保留旧快照。

## UI Extension 安全

优先使用 Schema 驱动 UI。更丰富的扩展必须提供经过认证的 `UiExtensionManifest`：

- 签名且不可变的 Bundle Artifact；
- 固定 Platform Slot 和 `ui-extension/v1` 消息协议；
- 使用不透明 Origin 的 Sandboxed iframe 和已批准 CSP Profile；
- 对象级 Artifact/Catalog Grant；
- 不得访问 WorkSession Cookie、原始 Token、宿主 DOM 或任意网络。

始终禁止任意远程 JavaScript。
