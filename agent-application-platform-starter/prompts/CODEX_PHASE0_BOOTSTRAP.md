# Codex Phase 0 Prompt

完整阅读：

- `START_HERE.md`
- `AGENTS.md`
- `tasks/PHASE0.md`
- `docs/37_JCS_AND_IJSON_PROFILE.md`
- `docs/38_CONTRACT_CI_AND_PROVENANCE.md`

## 第一步：验证基线

执行：

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

任何失败先修复，不能开始应用代码。

不得：

- 修改 Test Vector 以适配错误实现
- 放宽 Invalid Fixture
- 删除 Supply-chain 检查
- 用 Python `json.dumps(sort_keys=True)` 代替 RFC 8785
- 使用内部 Registry 或未固定版本

## 第二步：只实现 Phase 0A

先完成：

```text
WorkOrder
 -> Temporal
 -> Invocation/Attempt
 -> Reference Plugin
 -> Artifact
 -> Event
 -> Delivery
```

必须加入 `tasks/PHASE0.md` 规定的故障注入。

在 Phase 0A 通过前，不要批量创建全部空壳服务。

## 第三步：实现 Phase 0B 骨架

Phase 0A 有运行证据后，再建立：

- WorkSession
- Gateway Ports
- Capability/Provider
- Artifact Workspace Ports
- SandboxProvider
- Kubernetes Skeleton

## 架构依赖测试必须阻止

- Agent 包导入 Business Internal Package
- Handler 使用正文身份替代认证上下文
- Browser Token 写 URL/localStorage
- Scenario 依赖 Plugin Implementation
- Plugin 访问 Platform Database
- 外部调用绕过 Invocation Ledger
- Agent Runtime 绕过 Model/Tool/Egress Gateway
- Sandbox Backend 类型进入 Stable Kernel
- Frontend 直接调用 DeerFlow
- Redis 成为 Event/Session 事实源
- ArtifactVersion 内容 Update
- 任意 Input/Callback/Delivery URL
- ProviderResolution 只保存 ProviderInstance
- RunManifest 没有 AgentRuntime、CapabilityResolution、Conformance 或 Sandbox Revision
- Sandbox Mutation 缺少统一 Envelope

## Sandbox Provider

1. 使用 `sandboxes[]` 和 `sandbox_slot_key`，支持同一 Workspace 多 Sandbox。
2. Stable Kernel 只保存 opaque `provider_state_reference`。
3. Pod、Namespace、VM、Container ID 留在 Adapter Private Store。
4. 所有 Mutation 继承 SandboxMutationEnvelope。
5. DeerFlowSandboxAdapter 与 sandbox-runtime Adapter 只实现同一 Port。
6. 不实现 CRI。

## 完成报告

必须输出：

- Git Commit
- 工具和依赖版本
- 公共 Registry 安装证据
- JCS 三语言结果
- 数据库 Migration 与唯一约束
- WorkOrder/Grant 事务测试
- Temporal Workflow ID、Build ID、Replay Test
- Invocation Retry/Reconciliation/Manual Review 证据
- Artifact Staging/Commit 证据
- Event Cursor/SSE 证据
- Webhook 幂等/DLQ 证据
- 故障注入结果
- Phase 0B 目录与依赖测试
- 未实现项和剩余风险

只完成 Phase 0，不得进入 Phase 1。
