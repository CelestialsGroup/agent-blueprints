# 从这里开始

Agent Application Platform v0.9.0 是产品边界候选版本。它定义 Manus-like Agent 平台的领域边界、公共契约和实施约束，但尚未冻结，也不代表产品已经实现或具备生产可靠性。

## 当前成熟度

| 层级 | 当前状态 | 说明 |
|---|---|---|
| 架构设计 | 候选完成 | 核心所有权、Provider 模型、Conversation、Sandbox、Recording 和 Business 交接已有设计 |
| 契约验证 | 本地通过 | Schema、OpenAPI、状态机、正反向夹具、跨语言 JCS 和语义 Gate 已通过本地验证 |
| 产品实现 | 未完成 | 当前仓库主要包含文档、契约和验证工具，没有真实 Agent Platform 纵向链路 |
| 生产证明 | 未开始 | 故障注入、容量、安全隔离、Temporal Replay 和备份恢复仍缺运行证据 |

“契约验证通过”只表示候选契约内部可接纳，不等于实现完成，更不等于生产就绪。

## 阅读顺序

1. `AGENTS.md`：实施规则、所有权和禁止项。
2. `docs/00_ARCHITECTURE_BASELINE.md`：系统分层和当前架构摘要。
3. `docs/DECISIONS.md`：当前有效的关键决策。
4. `docs/README.md`：详细规范索引和事实源层级。
5. `tasks/PHASE0.md`：唯一 Phase 0 实现与验收路线。
6. `prompts/CODEX_PHASE0_BOOTSTRAP.md`：实现代理入口。

Schema、OpenAPI、状态机、数据库不变量和验证 Gate 高于叙述性文档。发生冲突时，应先修复低层事实源，再同步说明文档。当前 0A 契约闭合具备进入实现的候选条件；GitHub CI、仓库准入和冻结基线在后续阶段独立处理。

## 已确定的边界

- Business Application 拥有 User、Organization、Membership、Product、Order、Payment、Entitlement 和商业额度。
- Agent Platform 拥有 Conversation、WorkOrder、Workflow、Event、Artifact、Technical Usage、Provider、Sandbox、RuntimeRecording 和 Experience Catalog。
- Agent Runtime 和 Sandbox 只能通过带解析证据的 Provider Port/Resolution 接入，框架或基础设施私有模型不得进入稳定内核。
- ExecutionGrant 精确绑定请求 Contract/Digest Profile；Conversation Branch Create/Fork 命令精确绑定来源 Message Cut、WorkspaceRevision Head 与 CAS。
- 新 Turn 与现有 WorkOrder 控制使用不同请求；Message、Workspace 和 Active Work 使用独立 CAS 版本。
- 用户控制仍需要新的 Business ExecutionGrant；Business 授权撤销通过 sender-constrained 的不可变 Revocation Notice 进入 Platform。授权到期、撤销、Deadline/预算触发或紧急停机时，唯一 Platform Safety Controller 以不可变 `SystemSafetyControl` 仅执行 Pause/Cancel。该路径不能恢复执行、追加输入、批准、Checkpoint 或产生新副作用。
- RunManifest 精确绑定已消费 ExecutionGrant 的请求 Contract/Profile/Digest，并固化实际有界输入、ContextPackage、ArtifactAccessRequirement、初始预算/策略/权限上限、商业授权 ID/Digest/到期上限和四类 Gateway Binding；Runtime Start 携带本 Attempt 可等价/缩权续期的短期 RuntimeAuthorization/ArtifactGrant，任何跨 Tenant/WorkOrder、越过商业期限、Grant 早发/晚到期、缺失或扩权都 fail-closed。
- 通用 Capability Provider 拥有独立 Port/Token，不以 Plugin 或 `plugin_id` 作为公共前提；请求携带完整执行授权值并绑定 ProviderResolution/Instance/Audience，Invoke/Status/Cancel/Event 使用正式 Contract/Profile/Digest、不可跨操作重放且可在原授权窗口内续期的短期 Token。
- Model/Tool 复用 Capability Port；Artifact/Egress 使用独立可执行 Gateway Port。Artifact 写入由 ArtifactStagingGrant 与更短期 Gateway Token 共同授权，Provider 永远不能 Finalize ArtifactVersion。
- Preview/Edit/Conversion 使用统一 ArtifactOperation ExecutionScope。客户端只提交业务授权与 Artifact/Capability 意图；Platform 分配 Operation 后派生 Policy/Budget/Permissions/Gateway/ProviderResolution，并复用 Capability Invocation/Attempt、TechnicalUsage 与 Settlement。ArtifactIngest 也在 Session 分配后派生 Policy/Budget/Permissions，使用 Create/Status/Confirm/Scan/Platform Finalize 状态机且不调度 Provider。
- 终态用量在非空 UsageReport 与肯定的 NoUsageAttestation 间显式选择；Checkpoint/Snapshot 跨 Revision 恢复依赖 Platform CompatibilityDecision/Evidence；Secret 只经绑定目标 Intent 的 SecretGrant 和单操作 Credential Gateway 交付，均 fail-closed。
- Egress 绑定不可变 Owner-scoped DestinationRevision 并按 destination_class 授权；RuntimeSessionRoute 只携带不透明 Gateway/Provider Route Reference，不保存原始基础设施地址。
- CanonicalEvent 使用闭合 Metadata 和来源身份 Inbox 去重；Workspace 内容必须验证独立 Manifest Schema。
- Sandbox 由 Capability 按需创建；轻量 Run 可以没有 Sandbox，非空 Slot 只引用统一 ProviderResolution。
- RuntimeRecording 原始证据只读；调试和重跑必须创建新的授权与执行链路。
- 系统只承诺至少一次投递、幂等、Fencing、对账、事务 Outbox 和不可变版本，不承诺全局 Exactly-once。

## 本地验证

```bash
./scripts/bootstrap_contracts.sh
make validate-architecture
```

当前精确基线为 CPython 3.14.6、Node 24.18.0 Active LTS + pnpm 11.15.1、Go 1.26.5；CPython 3.13 只保留为 CI 回滚兼容通道。禁止使用浮动 `latest`，生产镜像还必须固定 OCI Digest。`make validate-all` 的仓库供应链与 CI 准入留到正式冻结准备阶段；实际结果与计数见 `CONTRACT_VALIDATION_REPORT.md`。

## 下一里程碑

0A.2 契约收口完成并通过本地 Gate 后，按 `tasks/PHASE0.md` 实现持久化脊柱和 Native Runtime Core，再进入 Business 纵向链、Native Runtime General/Sandbox、Runtime Gateway/Recording、nexu Provider、独立 Reference Contract Probe、故障注入和最小恢复证据。第三方 Agent 项目只作参考；GitHub CI 只在正式冻结前补齐。
