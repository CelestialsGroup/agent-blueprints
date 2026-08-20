# C02 Sandbox Provider Admission Context 执行计划

日期：2026-08-19

状态：revision/snapshot closure 进行中；机器 Wire Contract、fixtures、Conformance、Manifest、Application dependency lock 和
Provider 实现均未开始。本计划的最高目标是可审查的 Contract candidate；在完整 Contract Gate 和
独立审查前，不得将其描述为 sandbox-runtime、Agent Platform、sandbox-core-v1、可靠性、
多租户安全或生产就绪的通过证据。

## 1. 问题、权威和停止条件

`sandbox-operation-token-claims:v1` 已要求受保护 Sandbox Operation Token 绑定
`provider_revision_id`、`aud`、`tenant_id`、`work_order_id`、`policy_digest`、Operation、
Sandbox、Attempt、Fencing、Contract/Profile/Digest 与 deadline。当前 mutation Envelope 和 read
descriptor 却不能从 HTTP 请求独立提供其中的 Platform admission facts。因此 Provider 若只验
Bearer，无法区分 Token 声明与实际已准入 Operation；若从 Provider 本地缓存、ledger 或运行时
配置补齐，就会错误拥有 Platform 业务事实或提前进入 P1.2。

权威顺序固定为 Blueprint 安全/所有权决策、Contract Schema/OpenAPI/semantic rules/fixtures/Suite、
再到 Application 和外部 Provider。`sandbox-runtime` 不得在本计划完成、审查、合并并由消费者显式
更新 Contract lock 前添加私有 header、默认值、缓存或 protected route。

以下任一情形必须停止并回到本计划审查，不能用实现猜测补足：

- 发现 Admission Context 需要 Provider 查询或持久化 Platform ledger 才能验证；
- 不存在能同时覆盖 mutation body、read descriptor、HTTP path 和规范化 query 的唯一摘要输入；
- 需要原地改变已锁定 ProviderRevision、Run、Token 或 Conformance evidence 的语义；
- 新输入不能由 mTLS authenticated controller 独立提供，或需要相信 Bearer 中的同一字段；
- Contract Gate 无法把新增 OpenAPI、Schema、semantic、fixture、Suite、Manifest 和 compatibility
  资源闭合为同一 Revision。

## 2. 决策与边界

新 Revision 为每个受保护操作定义一个 `SandboxProviderAdmissionContext` HTTP carrier。Carrier 的
精确 header 名称、媒体类型/编码、最大 encoded bytes、JSON Schema ID 和 digest profile 必须由
OpenAPI 和 Schema 一起定义，不能只写在叙述性说明或实现常量中。它必须是闭合、有界、严格解析的
I-JSON document，拒绝未知字段、重复字段、多个 JSON value、歧义编码、超长输入和与目标路由不符
的 operation。

Context 至少携带并声明精确格式/上限：

- admitted control-plane caller identity、ProviderRevision ID 和 Provider Instance audience；
- tenant ID、WorkOrder ID、PolicyDecision digest 与 PolicyDecision decided-at；
- operation、sandbox ID、operation ID、attempt ID、fencing token、deadline；
- request Contract ID、digest profile、request/descriptor digest；
- Context Contract ID、Context digest profile 与 Context digest，使 JWS 能绑定精确 Context Revision；
- mutation 的 digest 输入或 read descriptor 的 route/path/normalized-query digest input，确保 HTTP
  target 不能在发送 Context 后被替换。

Context 是已验证 mTLS control-plane caller 提供的独立 Platform admission snapshot，不是用户输入、
Provider 配置、Bearer claim 的副本来源，也不是对 Platform ledger 的替代。Provider 必须先以 mTLS
admit caller，再严格解析 Context 与 HTTP target，随后验证 JWS header/signature/claims，最后逐项比较
caller、ProviderRevision/audience、tenant、WorkOrder、policy digest/decided-at、operation、sandbox、
operation/attempt/fencing、deadline、Contract/profile/digest 和 Context digest。任一不匹配、过期、
非法编码、未知 key 或不可唯一化的 target 均 fail closed，且不得 dispatch repository/driver。

Capability discovery 保持 mTLS-only，既不携带也不要求 Operation Token/Admission Context。Context
不授权 mutation、replay、fencing advancement、Provider-local reconciliation、Operation ledger、
snapshot/restore 或 P1.2 lifecycle。

## 3. 兼容性与版本策略

这是 stable Sandbox Provider wire behavior 的新增安全输入，不能在 `v1.0.0` 原地增加为 required。
本 C02 选择发布并冻结 `sandbox-provider@1.0.0` 的 immutable snapshot，active Contract/Suite
发行 `1.1.0`，新 ProviderRevision 显式锁定 `1.1.0`。不创建 `sandbox-provider-v2` 路径，也不以
同一 v1.0.0 身份重写历史资源。

不得以 optional header、content negotiation fallback 或“缺失则从 Token 推导”伪造向后兼容。旧
ProviderRevision、Run、Operation、Conformance evidence 和 consumer lock 继续只使用旧 revision；
新 Platform controller 和 Provider 必须作为同一审查发布单元锁定新 revision 后才可互调。

## 4. 机器资源闭包与实施顺序

每个阶段均在 clean worktree、精确 base/HEAD、无暂存修改下开始；提交按下列逻辑切片，不混入
Application 或 sandbox-runtime 实现。

1. **Revision/snapshot closure**：从当前锁定 Sandbox OpenAPI 和 Suite 提取 immutable historical
   snapshot；更新 compatibility manifest/policy、resource inventory 和 version references。先证明旧
   revision 不被改写，再创建 active candidate。
2. **Wire Contract**：新增 Admission Context Schema、必要的 schema references、OpenAPI security/
   header/operation extensions、每个 protected route 的 bound Context mapping，及 JWS claims 中对
   Context Contract/profile/digest 的显式 binding。所有 mutation 和五个 read descriptor route 必须被
   枚举；capabilities 必须显式排除。
3. **Semantic closure**：新增稳定 check IDs，验证 caller/mTLS binding、Context/JWS/HTTP target
   equality、JCS digest order、PolicyDecision time/deadline、unknown/duplicate/oversized encoding、
   route/query substitution、operation/attempt/fencing replay boundary，以及 no Provider-owned ledger
   inference。Schema 能表达的约束不应只留在 prose。
4. **Examples and negative fixtures**：为每个 operation family 提供正向向量；至少覆盖 Context
   caller、provider/audience、tenant/WorkOrder、policy digest/time、operation、sandbox、attempt,
   fencing、deadline、Contract/profile/digest、path/query/body substitution 和 missing/malformed/unknown/
   duplicate/oversized carrier 的失败向量。所有摘要在资源冻结后由受治理维护工具重新生成。
5. **Sandbox Conformance Suite**：创建新 profile/version 的 Context binding test，要求真实 Provider
   在 repository/driver dispatch 前拒绝不一致输入；保留并不夸大 multi-node replay/fencing、ledger、
   reconciliation、tenant isolation 和 deployment evidence。Suite digest、manifest reference 和
   compatibility decision 同步更新。
6. **Validation support and Gate**：仅在 Contract 已定义精确语义后，更新 `script/contract` validation
   support，使其读取新资源并执行全部 stable check IDs。运行 `make validate-contract`，记录 command,
   exact Blueprint/Contract/Script revisions、manifest/suite digest 和失败项；修复 closure 后重跑。
7. **Consumer handoff**：独立审查、合并 Contract candidate 后，sandbox-runtime 才能更新 lock，做
   projection/harness，再实现 protected transport。该 Consumer 工作不得回填本计划的 Contract Gate
   evidence。

## 5. 验收矩阵和结论边界

| 证据 | 可得结论 | 不能得出的结论 |
|---|---|---|
| Schema/OpenAPI/semantic/fixture/Suite/manifest 资源互相闭合 | 新 Contract candidate 的机器资源一致 | Provider 实现已兼容 |
| `make validate-contract` 通过并绑定精确 revisions/digests | 当前 Contract Gate 的本地通过 | Platform E2E、生产或 sandbox-core-v1 通过 |
| 新 Suite profile 的 Provider evidence | 该 Provider/profile 的输入拒绝行为 | 多控制器 replay/fencing、Platform ledger 或 tenant isolation 已证明 |
| sandbox-runtime component/projection tests | 特定 consumer 对锁定 revision 的局部兼容 | Agent Platform PKI、签发/轮换/吊销端到端互通 |

回滚只允许停止 active candidate 的采用并让消费者继续锁定前一 immutable revision；不得修改
historical snapshot、重写既有 evidence、静默放宽 Context，或用 Provider-local state 维持新 wire
behavior。

## 6. 非目标与后续入口

本 C02 不修改 Application、sandbox-runtime、Provider adapter、runtime driver、repository、operation
ledger、reconciliation、P1.2 lifecycle、PKI registration/issuance/rotation/revocation、deployment 或
production configuration。它也不宣称 aggregate `sandbox-core-v1`、Agent Platform E2E、多控制器可靠性、
多租户安全、部署或生产就绪。

下一入口是先完成 revision/snapshot closure 的只读 inventory 和具体新 revision 选择；若不能同时给出
old/new revision 的 immutable snapshot 与 compatibility closure，本 C02 保持阻塞，P1.1c protected
transport 不得开始。

## 7. 实施台账

### 2026-08-20 revision/snapshot closure 第一步

基线 `e7d7e1f` 的 active Sandbox OpenAPI 与 Suite 都是 `1.0.0`；其 Git blob 分别为
`e304a7f431b79154f7b901497653c47a0b6c35f6` 与
`3a768e82a37bf6bfa3d2ac83e6a7cf9c95844fbd`。本阶段以这两个精确 blob 创建
`openapi/sandbox-provider-v1.0.0.snapshot.yaml` 与
`conformance/sandbox/v1/revisions/1.0.0/suite.json`，不重格式化、不修改内容。

在历史快照创建后，活动 OpenAPI 与 Suite 已分别提升到 `1.1.0`；活动 Suite 自摘要是
`sha256:0fb0f0007ec6450aac3357f0c3e78de4a22eb8dafb7239d8f52ef0e339437483`。这仍未添加
Admission Context wire 资源或更新 Manifest、fixtures、semantic checks、validation support 或任何
consumer lock。因此 P1.1c protected transport 仍阻塞，不能由快照/版本提升本身推出 Contract Gate、
sandbox-core-v1、Platform E2E 或生产就绪结论。
