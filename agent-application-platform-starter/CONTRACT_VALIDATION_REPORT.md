# 契约验证报告 - v0.9.0

状态：**本地 Architecture Contract Gate 已通过；GitHub CI 与仓库准入延后；版本尚未冻结，产品尚未实现，生产可靠性尚未证明**

验证日期：2026-07-20

| 检查项 | 本地结果 |
|---|---|
| 纯源码静态审计 | 通过：355 个 JSON、23 个 YAML、6 个 OpenAPI、46 个 Markdown 文件 |
| JSON Schema 与测试夹具 | 通过：174 个 Schema、117 个有效夹具、28 个 Schema 无效夹具 |
| 语义不变量 | 通过：6 个确定性且与 Schema 对齐的状态机，以及 93 个负向夹具 |
| 架构闭合 | 通过：真实 Runtime 执行上下文、Turn/Control 分离、通用 Capability Port/Token、Tenant-scoped Resolution/Idempotency、Fail-closed Limits、三域 CAS、Workspace Manifest/Slot、Platform Core Event Registry/来源 Inbox 和语义追踪闭合 |
| 契约清单 | 通过：195 项受治理资源；Python 与 Node 结果一致 |
| 兼容性比较器 | 自测通过；本地未提供已冻结 Git 引用，显式首次冻结前模式为 N/A，不记为兼容性通过 |
| Python JCS/Strict I-JSON | CPython 3.11.9 和 3.13 通过 |
| Node JCS/Strict I-JSON | Node 22.16 通过 |
| Go JCS/Strict I-JSON | Go 1.23.2 linux/arm64 通过；gofmt 通过 |
| OpenAPI | 通过：6 份文档均为 0 个错误、0 个警告 |
| OpenAPI Bundle | 通过：6 个 Bundle，第二次生成结果逐字节一致 |
| 仓库与 GitHub CI | 本阶段不验收；Git 根 Workflow、受保护变量和公共 CI 运行证据延后 |

本次 Gate 证明 v0.9.0 候选契约内部一致，并具备进入 Phase 0 实现的准入基础。它新增验证了三种 ExecutionGrant 请求绑定、完整 Runtime Start/RunManifest 执行值、Capability Provider 通用调用、租户与来源去重、分离 CAS、Workspace Manifest、Sandbox Slot 和关键语义追踪。它不证明真实 Business -> Conversation -> Temporal -> Runtime/Sandbox -> Recording -> Settlement 链路已经存在，也不证明 Migration/RLS、Adapter、Gateway、Controller、Workbench 或多租户隔离、故障恢复、容量、SLO、备份恢复已经实现或达到生产要求。

GitHub CI、仓库级 Workflow 和受保护兼容性变量不属于本阶段结论。首次正式冻结前允许显式 N/A；冻结后必须设置不可变 `AGENT_PLATFORM_FROZEN_CONTRACT_REF`，缺失时 CI 应 fail-closed。
