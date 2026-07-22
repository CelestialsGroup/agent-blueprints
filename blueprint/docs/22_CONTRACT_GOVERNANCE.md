# 契约治理

## 受治理范围

JSON Schema、OpenAPI、状态机、JCS/I-JSON 向量和契约清单由独立 Contract 治理。Blueprint 保存架构意图与责任 ID；叙述性“必须”只有在 Contract、Application 数据库约束、Conformance 或 CI 中有对应执行点时才算完成。

Contract 的 `VALIDATION.json` 与 `CONTRACT_VALIDATION_REPORT.md` 不手工维护。Contract Gate 的各步骤先把成功证据写入 `build/validation/`，全部步骤和连续两次 Bundle 确定性验证通过后，生成器才从同一机器结果原子生成两份报告；任一步失败都不得刷新“passed”状态。

## 准入 Gate

| Gate | 强制执行方式 |
|---|---|
| Strict I-JSON/JCS | Python、Node、Go 共用全部正反向向量 |
| Schema | Draft 2020-12 元验证、绝对 `$id`、Registry `$ref`、正反向 Fixture |
| 语义 | 每条 contract_gate 约束映射注册 Check ID，且 Check 必须在当前运行真实执行；Conversation/Runtime/Recording 序列、可续期授权、Provider/Decision 摘要、Slot、Snapshot、Fencing、状态可达性均有反向夹具 |
| OpenAPI | Registry 投影后 Redocly Lint 为 0 个错误、0 个警告，8 个确定性 Bundle |
| 完整性 | 当前契约清单自摘要和全资源摘要 |
| 兼容性 | 与受保护变量指定的冻结基线比较删除/收窄；CI 缺基线时默认失败 |
| 供应链 | 摘要锁、pnpm lock 完整性校验、公开 Registry、Git 跟踪文件无 Bytecode/`.DS_Store` |

## URN 与 OpenAPI

原始 JSON Schema 只使用绝对 URN `$ref`，这是可移植事实源。Redocly 不支持外部 Registry 注入，因此 `prepare_openapi.py` 生成一次性本地文件投影；生成物不得反向成为契约源。

## 可复现工具链

- 主基线 CPython 3.14.6，3.13 仅作 CI 回滚兼容通道，依赖使用精确版本/摘要锁；
- Node 24.18.0 Active LTS（Krypton）与 pnpm 11.15.1，使用 `packageManager`、package engine、frozen lockfile 和完整性校验；
- Go 1.26.5，`go.mod` 固定语言版本并由 `toolchain` 固定补丁版本；
- Redocly CLI 2.39.0；
- 外部 CI 使用的第三方组件必须绑定不可变 Revision。

验证报告必须记录真实工具版本、命令、计数和未运行项。`.tool-versions` 的精确版本是当前候选基线，但生产仍须固定 OCI Digest 并在 BuildProvenance 记录工具链、依赖锁、SBOM 和镜像摘要；不得使用浮动 `latest`。DDL 唯一性、HTTP 解析前 413、跨进程恢复等无法由静态契约证明的责任必须标记 `phase0_implementation_required`，不得借文件存在或函数名写成通过。公共准入前不能写“已冻结”；契约 Gate 也不能证明生产就绪。

## 兼容性策略

契约清单只证明当前资源未被静默修改，不代表兼容。`check_contract_compatibility.py` 是保守策略 Gate，检测 Schema/Endpoint/Operation/响应/Media Type/状态迁移删除、Required 输入增加，`$ref`、type/enum/const/not/if-then/dependentRequired/contains/unevaluatedProperties/组合与边界收窄，以及参数（含链式本地 `$ref`）、Request Body、Response 和有效 Security 变化。

该比较器不构成通用兼容性证明。冻结审批还必须包含人工兼容性审查、`DECISIONS.md` 变更、版本迁移策略，并在实现存在后执行消费者契约、历史载荷回放和双版本互操作测试；不得用“比较器通过”替代这些证据。

CI 的唯一基线权威是受保护仓库变量 `AGENT_PLATFORM_FROZEN_CONTRACT_REF`，且值必须是已 Fetch 的完整小写 Commit SHA；PR 内可修改的 `baseline-policy.json` 仅用于说明。CI 缺基线时默认失败；只有第一个冻结基线产生前，受保护变量 `AGENT_PLATFORM_ALLOW_NO_FROZEN_BASELINE=true` 才允许输出 `N/A`，不得宣称通过。明确的破坏性变更必须升级契约版本、更新 `DECISIONS.md`、给出迁移窗口，不能靠忽略规则绕过。

## 仓库布局

Blueprint、Contract 与 Application 独立版本化，完整依赖和证据规则见 `52_BLUEPRINT_CONTRACT_APPLICATION_BOUNDARY.md`。同一 Git 根下的兄弟目录只是当前开发布局，不构成相对路径或共同 Commit History 的稳定依赖。

CI 配置由各部署仓库独立拥有，不进入 Blueprint 或 Contract。无论采用哪种 CI，均必须显式设置 Contract/Blueprint 根、锁定完整 Revision，并通过受保护变量注入冻结基线；本地目录关系和可由变更分支改写的配置不能成为基线权威。

Application CI 必须分别解析并只读挂载精确 Blueprint Revision 与 Contract Revision，验证 Contract Manifest Digest，再生成绑定代码和运行 Conformance。相对路径可以作为本地默认值，但分支名、目录名或未锁定的 Checkout 不能构成发布证据。

## 冻结规则

公共 CI 全绿只是冻结的必要条件。冻结仍需审查批准；生产批准属于另一套实现、安全、性能和恢复证据。
