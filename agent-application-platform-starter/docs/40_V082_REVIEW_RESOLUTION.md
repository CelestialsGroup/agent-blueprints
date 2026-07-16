# v0.8.2 Review Resolution

本文件对 v0.8.1 审查中的九类问题给出权威结论；与旧文档冲突时本文件优先。

| Finding | 判定 | v0.8.2 resolution |
|---|---|---|
| Redocly URN `$ref` / warnings | 真实契约工具链问题 | 保留 Registry URN 事实源，生成本地 lint 投影；0 error/0 warning wrapper；4 个 bundle |
| Workflow 不在 Git 根 | 取决于宿主仓库布局，但当前嵌套布局真实 | Workflow 支持 `CONTRACT_ROOT`，提供根目录安装脚本；独立仓库无需移动 |
| 脚本 644 / Python 3.9 | 权限是真问题；Python 3.9 是不支持的环境 | 可执行入口、3.11–3.13 preflight、hash lock |
| RunManifest 语义只在注释 | 真实契约问题 | 独立语义 Validator + 4 个 RunManifest 反例 + digest/slot/snapshot enforcement |
| SandboxOperation 不闭合 | 真实架构/契约问题 | v2 aggregate、Attempt、Reconciliation、ManualReview、Abandon 状态机 |
| Manifest 不等于兼容性 | 真实治理问题 | Integrity 与 Compatibility 两个独立 Gate；首冻前 N/A |
| ProviderRevision 可变认证状态 | 真实模型问题 | immutable Revision + append-only ProviderAdmissionDecision |
| Node/Go Strict I-JSON 跳过 | 真实实现/测试问题 | 三语言执行全部 invalid vectors；Go safe-integer preflight |
| Schema 复制 | 真实演进风险 | SandboxSpec、ProviderResolution、ProviderRevisionSnapshot 以绝对 `$ref` 复用 |
| Mutable Actions/no Python hashes/pyc | 真实供应链问题 | full SHA、Linux x86_64/aarch64 hash lock、bytecode Gate |

## 边界影响

Business/Platform 所有权、Provider Port、Sandbox Adapter 私有边界和可靠性原则未改变。变更发生在稳定内核契约内部：Provider 认证生命周期和 SandboxOperation 持久化模型被强化，属于兼容性敏感变更，因此版本提升至 v0.8.2，v0.8.1 不得冻结。

## 架构评价

Provider/Capability、Port/Adapter、多 Sandbox Slot、Temporal + PostgreSQL + Ledger/Outbox/Event/Artifact Staging 的总方向合理且可扩展。v0.8.2 消除了已知契约级阻塞，但仍只是 public CI admission candidate。实际稳定性必须由 Phase 0 实现和生产验证证明。
