# Codex Phase 0 Prompt

请完整阅读 `START_HERE.md` 和 `AGENTS.md`。

首先执行：

```bash
python3 -m pip install -r requirements-contracts.txt
npm ci
./scripts/lint_contracts.sh
npm run bundle:openapi
```

任何校验失败都必须先修复，不能开始业务实现。

然后只执行 `tasks/PHASE0.md`。

## 架构依赖测试必须阻止

- Agent 模块 import Business internal package
- HTTP Handler 使用正文身份代替认证上下文
- Browser 将 WorkSession Token 写入 URL/localStorage
- Scenario import Plugin Implementation
- Plugin Adapter import Platform Database internal package
- DeerFlow/Agent Runtime 直接调用 Model Provider，绕过 ModelGateway Port
- 外部 Tool/MCP 调用绕过 Invocation Ledger
- Sandbox 任意公网出站绕过 EgressPolicy
- Frontend 直接调用 DeerFlow
- Redis 作为 Event/Session 权威存储
- ArtifactVersion 内容被 Update
- Callback/Input 使用任意 URL
- ProviderResolution 只保存可变 ProviderInstance ID

## 完成报告

输出：

- 实际目录
- Contract Codegen 和 Digest 策略
- Auth/Grant 事务边界
- Browser WorkSession 安全模式
- WorkOrder/Invocation 状态机
- Temporal Workflow ID 与 Worker Versioning
- Event Cursor/Event Type Registry
- ProviderRevision/Resolution
- Artifact Ingest/Staging/Delivery
- Kubernetes 多副本策略
- 测试命令和证据
- 未实现项
- 发现的契约矛盾

不得自行进入 Phase 1。

## Sandbox Provider 要求

1. 阅读 `docs/33_SANDBOX_PROVIDER_CONTRACT.md` 至 `docs/36_SANDBOX_CONFORMANCE_AND_MIGRATION.md`。
2. 建立 SandboxProvider Port，不调用 DeerFlow Sandbox 内部类型。
3. 创建 DeerFlowSandboxAdapter Stub 和 sandbox-runtime Adapter Stub。
4. SandboxRegistry/Lease/Operation 属于 Agent Platform Core。
5. 后端 Pod/VM/Container ID 只能存在于 Adapter internal package。
6. 建立 Capability Negotiation、Idempotency、Generation 和 Fencing 测试骨架。
7. 不实现 CRI。
