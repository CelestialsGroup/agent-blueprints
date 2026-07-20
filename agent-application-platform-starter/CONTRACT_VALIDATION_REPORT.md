# 契约验证报告 - v0.9.0

状态：**本地 Architecture Contract Gate 已通过；GitHub CI 与仓库准入延后；版本尚未冻结，产品尚未实现，生产可靠性尚未证明**

验证日期：2026-07-20

| 检查项 | 本地结果 |
|---|---|
| 纯源码静态审计 | 通过：378 个 JSON、24 个 YAML、6 个 OpenAPI、46 个 Markdown 文件 |
| JSON Schema 与测试夹具 | 通过：183 个 Schema、127 个有效夹具、33 个 Schema 无效夹具 |
| 语义不变量 | 通过：6 个确定性且与 Schema 对齐的状态机，以及 105 个负向夹具 |
| 架构闭合 | 通过：Control 内外 ID/CAS 分离、互斥 ExecutionGrant Claim、PrincipalContextSnapshot、可续期 RuntimeAuthorization、商业授权到期上限与内部 Scope 闭合、Runtime/Capability ArtifactGrant 时间窗、ArtifactAccessRequirement/Grant 分离、Provider Staging/UsageObservation 所有权、显式 Gateway Disabled 模式、17 类 Platform Core Event |
| 语义追踪 | 通过：17 个关键 Schema 的 77 条约束；63 个 Contract Gate 映射引用 58 个已注册且本次真实执行的 Check ID；24 个 DDL/Conformance 映射明确保留为 Phase 0 实现责任 |
| 契约清单 | 通过：204 项受治理资源；Python 与 Node 结果一致 |
| 兼容性比较器 | 自测通过；本地未提供已冻结 Git 引用，显式首次冻结前模式为 N/A，不记为兼容性通过 |
| Python JCS/Strict I-JSON | 主基线 CPython 3.14.6 与回滚兼容通道 3.13.14 均通过；3.14 Linux aarch64 wheel 哈希已进入锁文件 |
| Node/pnpm JCS/Lock | Node 24.18.0 Active LTS + pnpm 11.15.1 通过 frozen lock 安装与 Node JCS；项目不再使用 npm/package-lock |
| Go JCS/Strict I-JSON | Go 1.26.5 linux/arm64 通过；gofmt 通过 |
| OpenAPI | 通过：6 份文档均为 0 个错误、0 个警告 |
| OpenAPI Bundle | 通过：6 个 Bundle，第二次生成结果逐字节一致 |
| 包内供应链 | 独立 Docker/Linux 包模式通过：Python `--require-hashes`、pnpm lock integrity、固定 Action SHA、公开 Registry 与文件卫生 |
| 仓库与 GitHub CI | 本阶段不验收；Git 根 Workflow、受保护变量和公共 CI 运行证据延后 |

本次 Gate 证明 v0.9.0 候选契约内部一致，并具备进入 Phase 0 实现的准入基础。它验证了三种 ExecutionGrant 的互斥请求绑定与 Snapshot 时间窗、客户端 Control Input 到平台 RuntimeInputEnvelope 的身份分配、同一 RunManifest 下不越过 CommercialAuthorization 到期上限的等价/缩权 RuntimeAuthorization 续期、Budget/Policy/Permissions 内部 Scope 闭合、Runtime 与 Capability ArtifactGrant Scope/时间窗、Provider 仅 Staging/UsageObservation、PrincipalContextSnapshot、显式 Gateway 模式、17 类 Platform Core Event，以及真实执行 Check ID 的语义追踪。工具链已固定为 CPython 3.14.6、Node 24.18.0 Active LTS/pnpm 11.15.1、Go 1.26.5，并保留 CPython 3.13.14 回滚验证。DDL 唯一性、HTTP 解析前 413、Outbox/Inbox、跨进程恢复和 Conformance 行为仍明确属于 Phase 0 实现证据。它不证明真实 Business -> Conversation -> Temporal -> Runtime/Sandbox -> Recording -> Settlement 链路已经存在，也不证明 Migration/RLS、Adapter、Gateway、Controller、Workbench 或多租户隔离、故障恢复、容量、SLO、备份恢复已经实现或达到生产要求。

GitHub CI、仓库级 Workflow 和受保护兼容性变量不属于本阶段结论。首次正式冻结前允许显式 N/A；冻结后必须设置不可变 `AGENT_PLATFORM_FROZEN_CONTRACT_REF`，缺失时 CI 应 fail-closed。
