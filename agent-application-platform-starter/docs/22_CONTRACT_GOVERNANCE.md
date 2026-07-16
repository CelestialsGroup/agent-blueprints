# Contract Governance — v0.8.2

## Governed surfaces

JSON Schema、OpenAPI、状态机、JCS/I-JSON 向量、数据不变量和 Contract Manifest 都是受治理契约。叙述性“必须”只有在 Schema、语义 Validator、数据库约束、状态机或 CI 中有对应执行点时才算完成。

## Admission Gates

| Gate | Enforcement |
|---|---|
| Strict I-JSON/JCS | Python、Node、Go 共用全部正反向向量 |
| Schema | Draft 2020-12 meta-validation、绝对 `$id`、Registry `$ref`、正反向 Fixture |
| Semantic | RunManifest、Provider/Decision 摘要、Slot、Snapshot、Fencing、状态可达性 |
| OpenAPI | Registry 投影后 Redocly lint 0 error/0 warning，4 个 deterministic bundle |
| Integrity | v0.8.2 Contract Manifest 自摘要和全资源摘要 |
| Compatibility | 与最新公开冻结基线比较删除/收窄；首个冻结前 N/A |
| Supply chain | hash lock、npm integrity、Action SHA、公开 Registry、无 bytecode |

## URN 与 OpenAPI

原始 JSON Schema 只使用绝对 URN `$ref`，这是可移植事实源。Redocly 不支持外部 Registry 注入，因此 `prepare_openapi.py` 生成一次性本地文件投影；生成物不得反向成为契约源。

## Compatibility policy

Contract Manifest 只证明当前资源未被静默修改，不代表兼容。`check_contract_compatibility.py` 单独检测：Schema/Endpoint/Operation/状态迁移删除、required 增加、type/enum 收窄和 const 变化。

`contracts/compatibility/baseline-policy.json` 只指向最新公开接纳且冻结的 Git Ref。在第一个冻结基线产生前，输出必须是 `N/A`；不得宣称 pass。明确 breaking change 必须升级契约版本、给迁移窗口和 ADR，不能靠忽略规则绕过。

## Repository layout

GitHub 只读取 Git 根目录 `.github/workflows`。包独立成库时直接使用当前 Workflow；嵌入 monorepo 时运行 `scripts/install_github_workflow.sh`，并设置 `AGENT_PLATFORM_CONTRACT_ROOT`。Workflow 中的全部第三方 Action 使用完整 commit SHA。

## Freeze rule

公共 CI 全绿只是冻结的必要条件。冻结仍需审查批准；生产批准属于另一套实现、安全、性能和恢复证据。
