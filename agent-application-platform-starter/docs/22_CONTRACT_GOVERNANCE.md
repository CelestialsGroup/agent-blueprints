# Contract Governance — v0.8.6

## Governed surfaces

JSON Schema、OpenAPI、状态机、JCS/I-JSON 向量、数据不变量和 Contract Manifest 都是受治理契约。叙述性“必须”只有在 Schema、语义 Validator、数据库约束、状态机或 CI 中有对应执行点时才算完成。

## Admission Gates

| Gate | Enforcement |
|---|---|
| Strict I-JSON/JCS | Python、Node、Go 共用全部正反向向量 |
| Schema | Draft 2020-12 meta-validation、绝对 `$id`、Registry `$ref`、正反向 Fixture |
| Semantic | RunManifest、CapabilityDefinition/Provider Kind/Conformance、Provider/Decision 摘要、Slot、Snapshot、Fencing、状态可达性 |
| OpenAPI | Registry 投影后 Redocly lint 0 error/0 warning，4 个 deterministic bundle |
| Integrity | v0.8.6 Contract Manifest 自摘要和全资源摘要 |
| Compatibility | 与受保护变量指定的冻结基线比较删除/收窄；CI 缺基线 fail-closed |
| Supply chain | hash lock、npm integrity、Action SHA、公开 Registry、Git 跟踪文件无 bytecode/`.DS_Store`、Git 根 Workflow 已激活 |

## URN 与 OpenAPI

原始 JSON Schema 只使用绝对 URN `$ref`，这是可移植事实源。Redocly 不支持外部 Registry 注入，因此 `prepare_openapi.py` 生成一次性本地文件投影；生成物不得反向成为契约源。

## Compatibility policy

Contract Manifest 只证明当前资源未被静默修改，不代表兼容。`check_contract_compatibility.py` 是保守策略 Gate，检测 Schema/Endpoint/Operation/响应/Media Type/状态迁移删除，required 输入增加，`$ref`、type/enum/const/not/if-then/dependentRequired/contains/unevaluatedProperties/组合与边界收窄，以及参数（含链式本地 `$ref`）、Request Body、Response 和 effective Security 变化。

该比较器不构成通用兼容性证明。冻结审批还必须有人审阅的 Compatibility Review/ADR、版本迁移策略，并在实现存在后执行 Consumer Contract、历史载荷回放和双版本互操作测试；不得用“比较器通过”替代这些证据。

CI 的唯一基线权威是受保护仓库变量 `AGENT_PLATFORM_FROZEN_CONTRACT_REF`，且值必须是已 fetch 的完整小写 Commit SHA；PR 内可修改的 `baseline-policy.json` 仅用于说明。CI 缺基线时默认失败；只有第一个冻结基线产生前，受保护变量 `AGENT_PLATFORM_ALLOW_NO_FROZEN_BASELINE=true` 才允许输出 `N/A`，不得宣称 pass。明确 breaking change 必须升级契约版本、给迁移窗口和 ADR，不能靠忽略规则绕过。

## Repository layout

GitHub 只读取 Git 根目录 `.github/workflows`。包独立成库时直接使用当前 Workflow；嵌入 monorepo 时运行 `scripts/install_github_workflow.sh`，提交 Git 根 Workflow 与 `.gitignore`，并设置 `AGENT_PLATFORM_CONTRACT_ROOT`。Supply-chain Gate 在受 Git 跟踪的嵌套包中检查根 Workflow 一致性、根 `.gitignore` 和被跟踪的 `.DS_Store`。Workflow 中的全部第三方 Action 使用完整 commit SHA。

## Freeze rule

公共 CI 全绿只是冻结的必要条件。冻结仍需审查批准；生产批准属于另一套实现、安全、性能和恢复证据。
