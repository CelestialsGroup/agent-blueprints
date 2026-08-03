# C01 Runtime Status/Event HTTP 400/429 Authority Patch 执行计划

日期：2026-08-03

状态：Stage 1/1.1/1.2 已在提交
`793215cbe1b79c0f4cb7f16b13ec71b9483920fd` 修改 Runtime OpenAPI 与两个专用 error Schema，
Stage 2A Contract draft 已经总控/R02 审查并保持未提交。Stage 3A 随后因固定 ID 历史对象的摘要
传递闭包与原“八文件传播”拓扑冲突而按停止条件中止；三个 partial Script 文件未验收、未完成且
不得描述为 green。当前只执行双 snapshot 的 plan-only correction。Contract candidate 尚未闭合，
Manifest、Application dependency lock、Application 实现、evidence 与 full Gate 均未进入后继阶段。

## 1. 目标与权威边界

本计划源于 Stage 0 输入基线中 AgentRuntimeProvider Status/Event read 的两个历史机器契约缺口：

1. `GET /v1/runs/{runtime_run_id}` 与
   `GET /v1/runs/{runtime_run_id}/events` 缺少 HTTP 400 响应权威；
2. 两个 read 操作缺少 HTTP 429、强制 `Retry-After` 及调用方重试边界。

交付物是新的、不可变的 AgentRuntimeProvider v1 patch Contract Revision。Stage 1 已将 active
OpenAPI `info.version` 从 `1.0.0` 提升为 `1.0.1`，Stage 2A 已将 active Runtime Suite draft 提升为
`1.0.1`。在 active candidate finalize 前，必须先把旧 OpenAPI 与旧 Suite 固化为 Manifest-governed
immutable historical snapshots；任何历史 ProviderRevision、AdmissionDecision、Capabilities、
Checkpoint、Compatibility、Run 或 passed evidence 都不得传播或原地升级到 `1.0.1`。

权威顺序固定为：Blueprint 文档 -> Contract 机器资源 -> Application 消费与实现。现有 Native
Runtime、Go adapter、测试或历史 evidence 只能说明旧 Revision 的消费者事实，不能反向决定、
放宽或补写本次 Contract 含义。Contract Script 只验证上述含义，不能成为意义来源。

## 2. 精确基线与 Source Digest

阶段 0 开始前的只读门禁：

| 项目 | 精确值 | 解释 |
|---|---|---|
| Repository authority base commit | `a8024901547df93453685ecb8044fe58399c30df` | 历史 Blueprint/Contract 输入基线；Stage 2.0 当前 HEAD 包含它但不再与它相同 |
| 阶段 0.1 plan base commit | `68c3fb956228c7cb657c733c8b3763cdb2c9422c` | 总控与 R01 只读审查后的计划提交；阶段 0.1 开始前 HEAD 精确相同且工作树干净 |
| Stage 1 Contract commit | `793215cbe1b79c0f4cb7f16b13ec71b9483920fd` | 总控与 R02 最终复审并独立验收；Stage 2.0 开始时 HEAD 精确相同、工作树/暂存区干净，`a802490...` 为祖先 |
| Blueprint Source Revision | `8e767457c808d148af371cd5e85d98a723bcfb282584b0726e7d207dbb2edbda` | `governed_source_snapshot_sha256`，48 个 Markdown 文件 |
| Blueprint Source Tree Digest | `sha256:8e767457c808d148af371cd5e85d98a723bcfb282584b0726e7d207dbb2edbda` | 使用 Application lock verifier 的长度前缀、路径排序算法只读计算；未刷新 lock |
| Contract Source Revision | `c7548d4a7e181895ca6c7c0ccfb585ccc2352433da8856c57d1d09ca3cb9a7e7` | 阶段 0 写入前的 `governed_source_snapshot_sha256`，684 个 JSON/Markdown/YAML 文件 |
| Contract Source Tree Digest | `sha256:c7548d4a7e181895ca6c7c0ccfb585ccc2352433da8856c57d1d09ca3cb9a7e7` | 是本计划的 Contract 输入基线，不是未来 patch 的输出摘要 |
| Stage 0 Contract Manifest Digest | `sha256:fac0299efcf04471f58f1f0668818a5148526371bd413deb5993c5aacb2762ce` | Stage 0 输入基线声明 269 个受治理 Manifest resources；状态为 `candidate-not-frozen` |
| Stage 0 Runtime Suite | `agent-runtime-provider@1.0.0` / `runtime-core-v1` | Stage 0 输入基线 Suite 声明；Stage 2.0 现场仍未修改该 Suite |
| Runtime Suite Digest | `sha256:9ef6d50df9f1032476ea2ada2c16d70c15d88368acf59794062df7dfce0bb356` | Suite 内声明的内容摘要 |
| Suite Manifest resource digest | `sha256:268ff34c549e01f223201262f2dab96d2718146aea383a8180d8cbf26a52eb44` | Manifest 对当前 Suite 文件的资源摘要 |

阶段 0 输入基线的辅助原始文件 SHA-256：Manifest 文件为
`7d08437ef48add8ef8638c61d76878050bcb544e96a1e44d6dc122b55c165dfb`，Runtime OpenAPI 为
`f75bd9484d9059435021f65147cab1a22b4cb0376ea47ce6e165fde0494f5811`，semantic constraints 为
`82500752b4689c4c87c4c849c2432c25d98831137753f25f11d99fb7201b52ff`。原始文件摘要、
Manifest 声明摘要和 Suite 内声明摘要用途不同，不得互换。

本计划自身加入 Contract 后会改变 Contract Source Revision，因此最终 Gate evidence 必须在所有
Contract 文档和机器资源冻结后重新计算并绑定输出 Revision；不能把上述输入基线写成未来输出。

### 2.1 双 snapshot 诊断输入与重算边界

R02 在 Stage 3A 停止审查中给出以下双 snapshot 诊断值。它们只用于复核拓扑与发现漂移，不是本轮
plan-only authority 产物，也不得硬编码为 Stage 2B 成功条件；snapshot Contract 子阶段与 Stage 2B
必须分别从实际字节独立重算并记录完整值：

| 资源 | R02 诊断值 | 使用边界 |
|---|---|---|
| historical Runtime Suite snapshot | tuple `agent-runtime-provider / 1.0.0 / sha256:9ef6d50d...bb356`；旧文件 byte SHA-256 `268ff34c...eb44` | Stage 2S 必须从 `a802490...` 独立提取、逐字核验并写入 immutable snapshot |
| historical Runtime OpenAPI snapshot | `info.version=1.0.0`；raw SHA-256 `f75bd948...f5811` | Stage 2S 必须从 `a802490...` 独立提取；R03 只读复算确认为 18 次 external ref / 6 个唯一 target，全部 occurrence 与具体 target/path/digest 必须现场枚举后逐项验证 |
| active Runtime Suite candidate | 诊断 final `suite_digest=sha256:8aae2621...e7e5`；诊断资源 SHA-256 `ef285c07...ecdc` | Stage 2B 现场重算；不接受计划常量或当前 stale placeholder |
| active Runtime OpenAPI candidate | `info.version=1.0.1`；诊断 raw SHA-256 `14360355...cc07`；20 次 external ref / 8 个唯一 target | Stage 2B 现场读取、独立枚举 refs 并与 historical snapshot 做 additive comparison |
| snapshot 后 Manifest candidate | R03 独立确认诊断 `count/listed/discovered=273/273/273`、`resources_digest=sha256:df88bcdd...21d0`、`manifest_digest=sha256:09ae3d01...cd7` | Stage 2B 仍须由 Python/Node inventory、path set 与 JCS 独立重算；不一致先停止解释，不能复制诊断值冒充 evidence |

双 snapshot 的权威路径固定为：

- `contract/conformance/runtime/v1/revisions/1.0.0/suite.json`；
- `contract/openapi/agent-runtime-provider-v1.0.0.snapshot.yaml`。

两者进入现有 Manifest inventory，成为 immutable historical resources。active semantic artifact 继续
引用 `conformance/runtime/v1/suite.json`，加载后派生完整
`(suite_id, suite_version, suite_digest)` tuple；不得改指 snapshot，也不得只按 `suite_id` 解析。

## 3. Stage 0 历史基线与 evidence 边界

以下 OpenAPI 缺口是 Stage 0 在 `a802490...` 输入基线上作出的历史审计，不是 Stage 1 提交后的
当前机器 Contract 事实。Stage 1 当前 OpenAPI 已为两个 GET operation 增加专用 400/429、结构化
HTTP/header/retry authority 与精确 precedence，但 fixture/semantic/Suite/Manifest/Script closure
仍未完成。Stage 0 Runtime OpenAPI 已为 Status/Event 声明规范化 read descriptor：

- Status：`urn:agent-platform:agent-runtime-status-operation-descriptor:v1`，
  `rfc8785-full-document-v1`；
- Events：`urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1`，
  `rfc8785-full-document-v1`；省略 query 时规范化为
  `after_event_sequence=0`、`limit=1000`。

Stage 0 历史响应表为 Status `200/401/403/404/500/503`，Events
`200/401/403/404/410/500/503`；两者均缺少 400 与 429。公共 `BadRequest`、
`TooManyRequests` 已存在并引用 `StandardError`，但当时 `TooManyRequests` 只把
`Retry-After` 描述为最小值为 1 的整数，没有证明两个 read 操作采用该响应，也没有把 body
的 `retryable` 与 status/header 闭合。

Application 的最新历史 evidence `B03.2a2.2.0` 只证明
`installed_cross_language_five_operation_component`，仍为
`conformance_profile_result=not_claimed`。其自身将 `status-event-http-400`、
`read-http-429-authority`、fresh-token issuer/durable reconciliation caller、平台父事实和生产
composition 记录为 blocked/not-in-slice。该 evidence 及 a1.1.4/a2.0/a2.1 均锁定旧 Blueprint
Source Revision `6e408d3d...`、旧 Contract Source Revision `c7548d4a...`、Manifest
`fac0299e...` 和 Suite `9ef6d50d...`；本 patch 不追溯提升其成熟度。

`script/evidence/CONTRACT_VALIDATION_REPORT.md` 与 `VALIDATION.json` 的日期是
2026-07-27。它们没有绑定 `a802490` 的 Blueprint Source Revision，也没有记录精确 Contract
Source Revision 或 Script Revision，因而不能证明本计划要求或未来 patch；只保留为旧
Contract candidate 的历史本地 Gate 结果。

### 3.1 R01 独立审查处置

R01 只读审查 thread `019fc53f-6f65-7291-9486-32030db8b938` 在精确 `a802490...`、clean
worktree 上独立确认：C01 是可分离的 v1 patch；Stage 0 基线两个 GET operation 确实缺少 400/429；
旧 Gate 缺少精确 Blueprint/Contract/Script revision binding；当时审查曾把 Suite patch 视为会传播到
八个固定 ID fixture，该拓扑已被 Stage 3A 摘要反向闭包证据否定并由双 snapshot 决策取代；兼容比较器
尚不能表达 Suite 收紧后的再认证要求；listener 在 operation 识别前的
连接饱和不构成 C01 429 evidence。阶段 0.1 对其结论作如下显式处置：

| R01 项 | 处置 | 理由 |
|---|---|---|
| v1 patch 范围、当时提出的八个 Suite 传播点、operation-level precedence、Suite 再认证、Gate binding 与 maturity 上限 | 部分采用；固定 ID 传播已作废 | v1 patch、precedence、recertification、binding 与 maturity 保留；固定 ID 传播会原地改写历史摘要，现由 immutable Suite/OpenAPI snapshots 与历史事实零传播取代 |
| 把 `semantic-constraints-v1.json` 新纳入 Manifest inventory，并同步修改 Python/Node verifier | 不采用 | 当前两个 verifier 明确定义的 inventory 不含该根；Blueprint/Contract 要求 semantic Gate closure，但未要求改变 Manifest inventory 定义。C01 以精确 Contract Source Revision 和真实 semantic Gate execution 绑定其变化 |
| 为 Status/Event 400/429 新增 `Cache-Control: no-store` | 不采用 | 未找到 C01 专属 Blueprint/Contract authority；其他 SSE/credential no-store 规则不能外推到 AgentRuntimeProvider read patch |
| 修改两个既有 read descriptor Schema 以承载 HTTP precedence | 不采用，保留停止条件 | descriptor Schema 当前只定义规范化文档与摘要输入；HTTP precedence 由 OpenAPI、semantic constraint 与 Suite 验证。若实现证明必须改 descriptor wire/schema，先停止并重新审查范围 |
| 429 后在原 token 有效期内重试原 Attempt | 不采用 | 本计划保持更严格的 durable caller fresh authorized read Attempt 边界；C01 不把 adapter 自动重试或旧 JTI 重放授权为新能力 |
| 400 code 改为 `RUNTIME_READ_REQUEST_REJECTED`、全面禁止 `details/violations` | 不采用 | 本计划保留已明确的 `RUNTIME_READ_REQUEST_INVALID` 和有界公开 reason；二者仍由闭合 Schema/Fixture/validator 保证无敏感信息泄漏 |

Manifest inventory 决策不是永久豁免：若后续找到现有 Blueprint/Contract 的明确条款，要求
`semantic-constraints-v1.json` 必须进入 Manifest inventory，C01 立即停止并把该问题升级为独立
治理前置，不得顺手修改 inventory/verifier 或假定新的 resource count。

## 4. Scope

本 C01 后续实施只允许：

- 发布 AgentRuntimeProvider v1 patch Revision，为 Status/Event 增加精确 400 与 429；
- 使用 `StandardError` 的闭合派生 Schema 固化错误 `code` 与 `retryable`；
- 固化 429 的强制整数 delta-seconds `Retry-After >= 1`；
- 固化 Status/Event request 到 read descriptor 的语法、默认值、摘要和认证边界；
- 增加正向 Example、反向 Fixture 和四个 Status/Event 400/429 Suite case；
- 更新 semantic traceability、Runtime Suite digest、Contract Manifest 和候选兼容性检查；
- 增强 Contract Script，使 Gate 真实验证 400/429、Retry-After、错误 body、双版本兼容及
  Blueprint/Contract/Manifest/Script/Suite 精确绑定；
- 在所有源文件冻结后生成新的 Script-owned Gate evidence。

## 5. Non-goals

本 C01 不允许：

- 引入 `AgentRuntimeInvocationTokenClaimsV2` 或实现
  `execution/observation/reduction_control`；该项属于后续 C02；
- 修改 v1 `safety_control` 的旧含义，或原地迁移旧 Run/ProviderRevision；
- 修改 RunManifest、RuntimeAuthorization、Invocation/ReconciliationCase、Checkpoint、Event
  Registry、Runtime Event Payload 或 Agent Loop Contract；
- 修改 Application dependency lock、generated projection、Native Runtime、Go adapter、测试、
  evidence generator 或任何 Application 源码；
- 声称 fresh-token issuer、durable reconciliation caller、ProviderResolution、CanonicalEvent、
  Platform Safety Controller、PostgreSQL/Temporal authority 或 production composition 已实现；
- 提升 `runtime-core-v1` aggregate、0B、0C-0G、0H、正式冻结、安全审批或生产就绪；
- 将未知 HTTP 路由、所有 HTTP/1.1 parser error 或代理行为扩展成新的公共协议范围；
- 在没有 C01 专属 Blueprint/Contract authority 时新增 `Cache-Control` 或其他响应 header；现有
  SSE/credential `no-store` 规则不得外推到 AgentRuntimeProvider Status/Event read；
- 运行 `make validate-all` 并据此宣称正式冻结。C01 的最高结论只有新 candidate Contract
  Revision 的本地 Contract Gate 通过。

## 6. Authority Matrix

| 行为 | Blueprint/Contract 权威 | C01 精确结论 | 不得推导 |
|---|---|---|---|
| Status success | OpenAPI 200 + AgentRuntimeRunStatus | 合法、已授权 read 返回 Schema-valid 200 | 平台状态已对账 |
| Event success | OpenAPI 200 + AgentRuntimeEventPage/Registry | 合法 cursor read 返回严格有序的 200 | 已成为 CanonicalEvent |
| Read descriptor | descriptor Schema + OpenAPI path/query defaults | 只由精确 path、允许 query、token-bound InvocationAttempt/fencing 合成；完整 JCS 摘要匹配 | header、trace 或实现私有值进入摘要 |
| 400 | 新 read bad-request error Schema + OpenAPI 400 | 无法合成合法 read descriptor 的已识别 Status/Event 请求；`retryable=false` | token digest mismatch 变成 400，或读取 Run 是否存在 |
| 401 | 既有 OpenAPI | 缺失/非法 mTLS 或 Bearer/JWS | 400/429 覆盖认证失败 |
| 403 | 既有 OpenAPI + token binding | 已认证但 ProviderRevision/operation/descriptor/attempt/fencing/Run binding 不符 | 以 400 暴露绑定差异 |
| 404 | 既有 OpenAPI | crypto 与 descriptor binding 全部通过后，目标 RuntimeRun 不存在 | 未认证存在性 oracle |
| 410 | 既有 Event OpenAPI | 合法且已授权 cursor 已过 retention boundary | malformed cursor 被误判为过期 |
| 429 | 新 read throttled error Schema + OpenAPI 429 | 已完成语法、认证、descriptor binding 后，read admission/rate/concurrency 暂无容量；不产生 read 结果 | RuntimeRun 存在、原 mutation 成败或可自动重试 |
| 500/503 | 既有 OpenAPI | 保持现有内部/暂时不可用边界，不由 C01 重写 | 由 429 取代所有临时失败 |
| 重试 authority | Blueprint reliability + Runtime token binding | 只允许 durable caller 在等待后创建 fresh authorized read Attempt | adapter 内部自动重试或重发原 mutation |
| 历史 Revision | RunManifest/ProviderResolution 锁定事实 | 旧 Run 继续只消费旧 Contract/Profile；新 Revision 只用于新 ProviderRevision/新 Run | 原地改变旧 Run 解释 |

## 7. 400 精确响应与 read descriptor 边界

### 7.1 响应 body

新增一个闭合的 Runtime read bad-request Schema，保持 body 是
`urn:agent-platform:standard-error:v1` 的合法收窄：

- `code` 固定为 `RUNTIME_READ_REQUEST_INVALID`；
- `retryable` 固定为 `false`；
- `message` 使用固定、无敏感信息文案；
- `trace_id` 必填且非空；
- `details`/`violations` 只能引用有界公开字段名或 reason code，不回显原始 target、Bearer、
  mTLS identity、SQL/Provider state 或跨租户标识；
- 400 不发送 `Retry-After`。

不能只在 OpenAPI description 中叙述上述值；Schema、Example、negative Fixture 和 Script
validator 必须共同使错误 code/retryable 机器可执行。

### 7.2 Status descriptor

Status 只接受精确 `GET /v1/runs/{runtime_run_id}`：

- `runtime_run_id` 是一个非空、最大 200 的单一 path segment；不得 case-fold、Unicode
  normalize、合并 slash、处理 dot segment 或把编码后的 path separator 解释成同一 ID；
- Status 不接受 query。空 query marker、未知 query、重复 query 均不能进入 descriptor；
- Status 没有 request body。非零 body、歧义 Content-Length、Transfer-Encoding/Expect 等使
  已识别 Status read 无法形成唯一请求时返回 400；
- descriptor 还从已验证 token 取得 `invocation_id`、`invocation_attempt_id` 和
  `fencing_token`，固定 `operation=read_status`，然后按
  `rfc8785-full-document-v1` 计算摘要；
- syntactically valid descriptor 与 token 的 `operation_request_digest` 不匹配是 403，不是 400。

### 7.3 Event descriptor

Events 只接受精确 `GET /v1/runs/{runtime_run_id}/events`，除相同 path 规则外：

- query 只允许 `after_event_sequence` 与 `limit`，每项最多一次，任意顺序；
- 省略值在摘要前分别规范化为 `0` 与 `1000`；省略和显式默认值必须生成同一逻辑
  descriptor；
- 显式值只接受无符号 ASCII 十进制 canonical lexical form：`0` 或非零首位的数字串；拒绝
  正负号、前导零、空值、空格、指数、小数、重复字段、未知字段和歧义 percent-encoding；
- `after_event_sequence` 范围为 `0..9007199254740991`，`limit` 范围为 `1..1000`；越界
  返回 400，不读取 cursor state；
- descriptor 固定 `operation=read_events` 并包含规范化后的两个 query 值、token-bound
  InvocationAttempt/fencing，再计算完整 JCS 摘要；
- schema-valid cursor 已越过 retention boundary 才返回 410；malformed/out-of-range cursor
  始终是 400。

完全无法归属到 Status/Event operation 的未知 route 或在 route 归属前失败的底层 HTTP parser
行为不由 C01 新增状态承诺；Conformance 不得用这些行为替代上面的 operation-level 400。

## 8. 429、Retry-After 与重试规则

新增一个闭合的 Runtime read throttled Schema，仍是 `StandardError` 的合法收窄：

- `code` 固定为 `RUNTIME_READ_THROTTLED`；
- `retryable` 固定为 `true`；
- `trace_id` 必填且非空；`message` 不固定单一文案，但必须是非空 string 且 `maxLength=2000`，
  与既有 `BoundedDetails` string 同量级；
- `details` 继续由 `BoundedDetails` 保持结构有界。message/details/violations 的敏感信息排除和公开
  reason vocabulary 由 Stage 2A semantic/正反向 fixture draft、Stage 3A validator 与 Stage 2B
  focused execution 闭合，阶段 1 不声称已证明；
- 响应必须带一个 `Retry-After`，Wire 表示固定为十进制整数 delta-seconds，最小值 1；
- 缺失、重复、非整数、0/负数或无法安全解析的 `Retry-After` 使响应不符合新 Contract，调用方
  将其分类为 invalid response，不得据此重试；
- body `retryable=true` 不能替代 header，header 也不能把 400/401/403/404/410 变成可重试。

429 的操作顺序固定为：请求语法/read descriptor -> mTLS/Bearer/JWS ->
ProviderRevision/operation/descriptor/Attempt/fencing binding -> read admission -> provider-local
state/cursor read。429 只能表示 read admission/rate/concurrency 暂无容量，不能证明目标 Run
存在，也不能改变任何 Run/Event/Invocation 事实。

对已经被 listener 精确识别为 Status/Event operation 的请求，可观察处理优先级固定为：
`400 -> 401 -> 403 -> 429 -> 404 -> 410 -> 200`。其中 410 只适用于 Events；含义依次是请求/描述符
无法规范化、身份或 token 缺失/无效、caller/operation/binding/digest 不匹配、已授权 read
admission 暂时拒绝、目标 Run 不存在、合法 Event cursor 已过 retention boundary、成功读取。
只有在 400/401/403 均排除后才能产生 429；只有在 429 admission 通过后才能读取 provider-local
Run/cursor state 并决定 404/410/200。不得先查询 Run 是否存在再选择 429，也不得让 429 暗示
Run 存在。

TLS/HTTP listener 尚未识别出精确 operation 时的连接饱和、accept backlog、握手失败或通用代理
限流不属于 C01 Status/Event response；它们不能作为 operation-level 429、`Retry-After` 或四个
新 Suite case 的通过证据。C01 不为这些 pre-operation 失败新增 wire 映射。

重试规则：

1. Provider、Native Runtime HTTP process 和 Go adapter 都不得内部自动重试 Status/Event；
2. durable caller 可以等待至少 `Retry-After`，再创建新的 authorized read
   InvocationAttempt、fresh token、non-stale fencing 和对应的新 descriptor digest；
3. 新 Attempt 可保持同一逻辑 `runtime_run_id`、Status target 或 Event cursor/limit，但不能重放
   原 Bearer/JTI 或伪造父 Invocation；
4. 本规则只允许重新观察。若读取是为解决 Start/Command `outcome_unknown`，429 绝不授权重发
   原 mutation；caller 继续 reconciliation/waiting；
5. C01 只发布上述 Contract 许可和限制，不证明 fresh-token issuer/durable scheduler 已实现。

400 对同一非法 descriptor 不重试。调用方只有修正 path/query、重新生成 descriptor digest 并
取得新 authority 后才能发起不同请求；这不是原请求自动重试。

## 9. Contract Revision 与兼容窗

- Git 历史之外，当前 Contract 还必须以两个 Manifest-governed immutable snapshots 保留旧 Suite
  `1.0.0` 与 Runtime OpenAPI `1.0.0` 的可解析字节；active `1.0.1` 不覆盖 snapshot；
- 新 `1.0.1` 在 active Contract Revision 下增加 400/429，是 additive response patch；
- compatibility 必须同时比较 OpenAPI version 与 Runtime Suite version/digest/profile/有序 test
  set；允许的结论仅为 `wire-additive + requires recertification`，不能简写为无条件 compatible；
- 旧 ProviderRevision、RunManifest、Run、token/profile 与 evidence 继续绑定旧 Source
  Revision/Manifest/Suite，不修改其响应集合或 conformance case 数；
- C01 只发布 contract-defined active `1.0.1` candidate；不得创建或伪造 passed ProviderRevision、
  AdmissionDecision、Run、Checkpoint、CompatibilityDecision 或 conformance evidence。未来独立准入
  流程真实再认证后，才可创建绑定新 Contract Source Revision/Manifest/Suite tuple 的新事实；
- 兼容窗内消费者双读旧 `1.0.0` 与新 `1.0.1`，但每个 Run 只按其锁定 Revision 解释；写入、
  token issuance 和 evidence 只使用目标 Revision 的唯一表示；
- 历史事实零传播且逐字/摘要不变：ProviderRevision digest
  `sha256:3a68cf38...a4cd`、AdmissionDecision digest `sha256:29b5fe38...178a6`、
  `port.contract_digest=sha256:f75bd948...f5811`、Suite `1.0.0` tuple、原八个直接消费者及其全传递
  闭包均不得由 C01 refresh 改写；新 400/429 case 不追溯判定旧 evidence；
- R03 独立复算确认 11 个 historical positive objects 必须逐字零 diff；Stage 2S/2B evidence 必须现场
  输出完整路径清单并逐项比对，不得在本计划缺少最终清单时猜写路径。active `1.0.1` 不得存在或
  伪造任何 passed/certified fact；
- 正式移除旧 reader/provider 支持必须等待没有 Run、token、checkpoint、reconciliation case 或
  retained evidence 引用旧 Revision，并走单独冻结/迁移批准。

Suite registry 必须发现所有 active/snapshot Suite，并以完整
`(suite_id, suite_version, suite_digest)` 唯一解析；Port registry 必须以
`(protocol, protocol_version, contract_digest)` 唯一解析本地 active/snapshot OpenAPI。缺失、重复、
资源自摘要错误、tuple/digest 冲突、active/snapshot 互换或 unresolved reference 均 fail closed。

## 10. 受影响文件族与写所有权

后续实施必须串行移交；同一时间只有 C01 一个 writer，且只能持有一个 ownership domain。修正后的
顺序固定为 `已审查 Stage 2A -> 已停止 partial Stage 3A -> plan-only correction -> Contract Stage 2S
snapshot -> resumed Script Stage 3A -> Contract Stage 2B -> Script Stage 3B -> frozen Stage 4`。每次
跨域前由总控与独立 reviewer 只读审查；未通过不得释放 ownership 或进入下一阶段。

### 10.1 Contract writer 独占

| 文件/目录 | 计划变化 |
|---|---|
| `contract/openapi/agent-runtime-provider-v1.yaml` | patch version；Status/Event 400/429；read-specific response/header/descriptor description |
| `contract/schemas/agent-runtime-read-bad-request-error.schema.json` | 新增 StandardError 收窄、code/retryable/trace 约束 |
| `contract/schemas/agent-runtime-read-throttled-error.schema.json` | 新增 StandardError 收窄、code/retryable/trace 约束 |
| `contract/examples/contracts/agent-runtime-read-bad-request-error.json` | 400 正例 |
| `contract/examples/contracts/agent-runtime-read-throttled-error.json` | 429 正例；header 由 OpenAPI/Script 单独验证 |
| `contract/tests/invalid/agent-runtime-read-bad-request-retryable.json` | 400 body 反例 |
| `contract/tests/invalid/agent-runtime-read-throttled-not-retryable.json` | 429 body 反例 |
| `contract/semantic-constraints-v1.json` | 新 error Schema 的稳定 constraint/check 映射；保持 Contract/implementation 责任分层 |
| `contract/conformance/runtime/v1/suite.json` | `1.0.1`；新增 Status 400、Event 400、Status 429、Event 429 四个 case；重算 Suite digest |
| `contract/conformance/runtime/v1/revisions/1.0.0/suite.json` | Stage 2S 新增；Manifest-governed immutable historical Suite snapshot |
| `contract/openapi/agent-runtime-provider-v1.0.0.snapshot.yaml` | Stage 2S 新增；Manifest-governed immutable historical Port snapshot |
| `contract/compatibility/contract-manifest.json` | 重算新增/变化资源、resource count/digest/manifest digest；保持 candidate-not-frozen |
| `contract/doc/plan/C01-runtime-status-event-http-authority-patch.md` | 在最终 Gate 前回填阶段 ledger、偏差和剩余风险；随后冻结 |

`standard-error.schema.json`、两个现有 read descriptor Schema、Runtime state machine 与 Event
Registry 先视为 reviewed-but-unchanged。若实施发现必须修改它们才能闭合，立即停止并先更新
本文 Authority Matrix/兼容分析；不得顺手扩大 writer 范围。

Stage 2S snapshot writer 的唯一机器 owner 是上述两个新 snapshot 路径；另可写本计划 ledger。
该阶段 active Suite、active OpenAPI、semantic constraints、fixtures、Manifest、全部历史 facts 与所有
Script 均只读。snapshot 必须从 `a802490...` 独立提取，不能从 active `1.0.1` 反推或手工降版。

Stage 2B 只 finalize active Suite 自摘要和 Manifest，不传播到任何既有固定 ID fixture。以下历史文件
及其全传递闭包全部为 verify-only，绝不属于 C01 writer：

- `agent-runtime-capabilities.json`、`agent-runtime-checkpoint-manifest.json`、
  `agent-runtime-provider-revision.json`、`agent-runtime-run-status.json`；
- `run-admission-context.json`、`runtime-compatibility-decision.json`、
  `runtime-compatibility-evidence.json`、`compatibility-decision-cases.json`；
- 所有引用相同 ProviderRevision、AdmissionDecision、Port、Suite、Run、Checkpoint、Compatibility 或
  evidence ID/digest 的下游对象。

`contract/semantic-constraints-v1.json` 继续不属于当前 Manifest inventory。它的变化由最终精确
Contract Source Revision 与 `validate_semantics.py` 中真实执行的 check 共同绑定；Manifest 只按
现有 inventory 定义重算。Stage 2B 不修改 Python/Node Manifest verifier 的 inventory 根，且不会
因 semantic constraints 产生新的 resource count。

Stage 2.0 历史现场的 Manifest 文件声明 `resource_count=269`，`resources` 长度也是 269；当时未变化的
Python/Node inventory roots 在工作树发现 271 个路径。Manifest 相对 discovered inventory
唯一缺少 Stage 1 新增的：

- `schemas/agent-runtime-read-bad-request-error.schema.json`；
- `schemas/agent-runtime-read-throttled-error.schema.json`。

这是 Stage 1 形成、Stage 2.0 登记的历史 drift，不是 Stage 2A 新引入。Stage 2S 增加两个属于现有
inventory roots 的 snapshot 后，R02 诊断预期为 273，但该数值不是成功常量。Stage 2B 必须现场独立
计算 declared/listed/discovered、完整 path set、`resources_digest` 与 `manifest_digest`；任何结果与
诊断不一致都先停止并解释具体新增、删除或摘要差异，不得为匹配计划硬写 count/digest。

C01 对两个 Runtime read error semantic 条目采用 **Contract-owned supplemental preservation**，不回改
或扩大两个 Stage 1 专用 error Schema：

- `semantic-constraints-v1.json` 中所有 entry 均接受 enforcement artifact、check ID、Suite reference、
  全局 ID 唯一性检查；只有列入 `critical_schema_ids` 的 generated critical entry 才逐项与其 Schema
  `x-semantic-constraints` 做 statement/index source alignment；
- 两个 Runtime read supplemental entry 不是 Schema `x-semantic-constraints`，不加入
  `critical_schema_ids` 的 source-alignment 集合。其 Contract authority 来自 Stage 1 结构化 Runtime
  OpenAPI、两个专用 error Schema 与 Stage 2A semantic traceability ordered objects 的组合；
- Script 只能从当前 Contract semantic 文件识别、解析、校验并原样保留 supplemental ordered
  objects，不得硬编码、生成替代 statement 或重写 statement/index/id/enforcements 来成为意义来源；
- 每个 supplemental `schema_id` 必须解析到当前 Contract 的既有 Schema；其 `constraint_id` 必须等于
  `sha256(schema_id + "\\n" + constraint_index + "\\n" + statement)` 前 16 位的 `sem-` ID，且全局
  唯一；不得与 generated critical constraint 发生 ID 或 `(schema_id, constraint_index)` 碰撞；
- 每项 enforcement artifact/check/Suite reference 必须存在，`contract_gate` check 必须已注册且在当前
  Gate 真实执行。任何删除、改写、重排、重复、碰撞或 unresolved reference 都 fail closed。

Contract ownership 后续分两次重新取得：

- Stage 2S 只新增两个 immutable snapshots 并写本计划 ledger；所有 active/historical 机器对象和
  partial Script 只读，完成后必须经总控与独立 reviewer 审核；
- resumed Stage 3A 审查通过后，Stage 2B 才可 finalize active Suite 自摘要并刷新包含 snapshots 的
  Manifest；历史 tuple/Port/ID/digest 与所有固定 ID 消费者保持逐字不变。

Stage 2A Contract draft、Stage 2S snapshots、resumed Stage 3A 与 Stage 2B 可位于同一未提交工作树中
串行完成，但禁止提交 unknown semantic mapping、stale active Suite digest、未审查 snapshots、
未闭合 tuple registry、旧 Manifest/comparator 或 partial Script 红色中间态。

### 10.2 Script writer 独占

当前 partial Stage 3A 已停止且未验收。只有 Stage 2S 经总控与独立 reviewer 通过后，Script writer
才能恢复；恢复时 Contract 全部只读。resumed Stage 3A 审查通过后释放 Script ownership，Stage 2B
再取得 Contract ownership；Stage 2B 通过后 Stage 3B 才可写 source binding/evidence generator：

| 文件/目录 | 计划变化 |
|---|---|
| `script/contract/validation/offline_static_audit.py` | resumed Stage 3A：强制 active 1.0.1 read authority；historical OpenAPI snapshot 只做 immutable/version/ref/registry 校验，不套用 C01 1.0.1 authority |
| `script/contract/validation/validate_contracts.py` | 发现全部 Suite，以完整 tuple 建立唯一 registry；注册 C01 正反例；禁止 `suites_by_id` 覆盖版本 |
| `script/contract/validation/validate_semantics.py` | 从 evidence 的完整 Suite tuple 与 Port tuple 唯一解析 active/snapshot 资源；注册并真实执行 `runtime_read.http_authority` |
| `script/contract/maintenance/refresh_example_digests.py` | 只 finalize active Suite artifact 并 verify-only immutable registry；normal/guarded path 均禁止改写 snapshot、历史 tuple/Port/ID/传递摘要或伪造 passed 事实 |
| `script/contract/compatibility/check_contract_compatibility.py` | 证明 snapshots 等于 baseline、active 1.0.1 wire-additive、历史 facts 未重绑；唯一成功结论 `wire-additive + requires recertification` |
| `script/contract/validation/lint_openapi_zero.mjs` | resumed Stage 3A 必写 owner；证明 active + historical 共 10 个 OpenAPI 文档均被 lint 且 fail closed |
| `script/package.json` | resumed Stage 3A 必写 owner；固定并证明 10 lint / 10 bundle 的命令与工具拓扑 |
| `script/contract/validation/generate_validation_evidence.py` | Stage 3B：输出精确 Blueprint/Contract/Manifest/Script/Suite revisions/digests 和 C01 closure |
| `script/evidence/VALIDATION.json` | Stage 4 完整 Gate 的机器 evidence；不得手改或在 Stage 2A/3A/2B 生成 |
| `script/evidence/CONTRACT_VALIDATION_REPORT.md` | Stage 4 同源人类报告；明确不提升 Application/冻结/生产成熟度 |
| `script/build/validation/**` | 临时 Gate 输出，不提交为 Contract 资源 |

以下源在 resumed Stage 3A 精确登记为 reviewed unchanged，不属于 writer：

- `script/contract/validation/prepare_openapi.py`；
- `script/contract/manifest/verify_contract_manifest.py`；
- `script/contract/manifest/verify_contract_manifest.mjs`；
- `script/redocly.yaml`；
- `script/contract/validation/verify_openapi_bundle_determinism.py`。

只读审查必须证明它们支持 active/historical 投影、现有 inventory 与 deterministic bundle；若任一确实
需要修改，立即停止并先更新 owner/计划，不能借 lint/Manifest/bundle 失败顺手扩域。Redocly 与 bundle
必须分别发现 10 个 OpenAPI 文档；每个 lint 为 0 error/0 warning，historical snapshot 不接受 active
C01 1.0.1 extension 断言。`reviewed unchanged` 只约束这些源文件的 writer 状态，不免除 Stage 3A/2B
在隔离临时树或当前受控 finalize 阶段实际执行其命令。

Script Revision 使用独立的 `governed_source_snapshot_sha256`：以 `script/` 为根，确定性纳入
Contract Gate 源码、Makefile、`.tool-versions`、requirements/package/pnpm/Go locks，排除
`.venv/`、`node_modules/`、`build/` 与 `evidence/` 输出；按相对路径排序并以路径/内容长度前缀
计算 SHA-256。若实际仓库已有更正式且等价的 Script Revision 规则，应在 Stage 3B 先统一，不能
同时输出两个含义不明的 revision。

### 10.3 Application 只读

`application/dependency-lock.json`、`application/doc/plan/**`、generated projection、Native
Runtime、Go adapter、Application evidence/generator/tests 全部不属于 C01 writer。C01 只读取旧
evidence 证明兼容边界；Application lock refresh 和实现必须由 C08/后续已授权 Application
任务完成。

## 11. 分阶段步骤、验证与 evidence

### 阶段 0：计划与索引（本轮）

交付：新增本计划和 `contract/doc/plan/README.md`，根 Contract README 加索引；无机器资源、
Script 或 Application 变化。

验证：

```bash
cd /Users/echo/.codex/worktrees/65b0/agent
test "$(git rev-parse HEAD)" = a8024901547df93453685ecb8044fe58399c30df
git merge-base --is-ancestor a8024901547df93453685ecb8044fe58399c30df HEAD
git diff --check
git diff --name-only -- blueprint application script
git diff --name-only -- contract
git status --short --branch
```

退出条件：只有三个 Contract Markdown 文件发生计划内变化；不运行会改写 evidence 的完整
Gate。证据是 Git diff/status 和本计划的基线表，不产生 Contract Gate 成熟度。

### 阶段 0.1：R01 审查修订（本轮）

交付：只修订本计划，纳入 R01 的必要机械传播、兼容性再认证、响应优先级和 operation-level
429 边界；明确不扩大 Manifest inventory、不新增无权威的 Cache-Control。无 Contract 机器资源、
Script、Application 或 evidence 变化。

验证：

```bash
cd /Users/echo/.codex/worktrees/65b0/agent
test "$(git rev-parse HEAD)" = 68c3fb956228c7cb657c733c8b3763cdb2c9422c
git merge-base --is-ancestor a8024901547df93453685ecb8044fe58399c30df HEAD
git diff --check
test "$(git diff --name-only)" = \
  contract/doc/plan/C01-runtime-status-event-http-authority-patch.md
git diff --name-only -- blueprint application script
git status --short --branch
```

退出条件：只有本计划 Markdown 发生变化；R01 采用/不采用决策及理由已记录；不运行完整 Gate。
证据是 R01 thread、Git diff/status 和阶段 0.1 本地提交，不产生 Contract Gate 成熟度。

### 阶段 1：Schema/OpenAPI authority patch

1. 新增两个 StandardError 收窄 Schema；
2. Runtime OpenAPI 提升 patch version；为 Status/Event 分别加入 400/429；
3. 400 不含 Retry-After；429 Header 为 required integer delta-seconds、minimum 1；
4. OpenAPI description 固化第 7-8 节的 descriptor/precedence/retry 规则；
5. 不改 Token claims、state machine 或 Event Registry。

focused 验证：

```bash
cd /Users/echo/.codex/worktrees/65b0/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
.venv/bin/python contract/validation/offline_static_audit.py
.venv/bin/python contract/validation/validate_contracts.py
node contract/validation/lint_openapi_zero.mjs
```

Evidence：`script/build/validation/static.json`、`contracts.json`、`openapi.json`，以及阶段 ledger
记录的命令、exit code、OpenAPI 0 error/0 warning。任何 validator 尚未验证新增规则时不得把
lint green 记为 authority closure。

### 阶段 1.1：R02 authority 纠偏

R02 只读审查 thread `019fc56d-b49d-7a51-ae01-491f34587e44` 指出两个 P1：原始 HTTP 到 400
的分类没有进入机器契约，retry/header 的关键规则仍只能靠 prose 判断。Stage 1.1 先固定以下
结构决策，再修改 OpenAPI；不修改 descriptor Schema。所有 `x-runtime-read-*` object 都是封闭
authority：Stage 3A validator 必须按完整键集、值类型、枚举和数组顺序 fail closed，缺键、多键、
未知枚举或仅有 description substring 均不得通过。

#### Status 原始 HTTP authority

`getAgentRuntimeRun.x-runtime-read-http-authority` 的精确形状：

```yaml
authority-version: runtime-read-http-authority-v1
operation-recognition:
  method: GET
  path-shape: /v1/runs/{runtime_run_id}
  match: exact
  unknown-route: c01-out-of-scope
  pre-operation-parser-failure: c01-out-of-scope
runtime-run-id:
  segment-count: 1
  min-length: 1
  max-length: 200
  case-fold: forbidden
  unicode-normalization: forbidden
  slash-collapse: forbidden
  dot-segment-processing: forbidden
  encoded-path-separator-equivalence: forbidden
query:
  mode: forbidden
  empty-marker: reject-400
  unknown-parameter: reject-400
  repeated-parameter: reject-400
body:
  mode: forbidden
  nonzero-content-length: reject-400
  ambiguous-content-length: reject-400
  transfer-encoding: reject-400
  expect: reject-400
descriptor-digest-mismatch: reject-403
```

只有精确 GET path shape 进入该 operation；未知 route 和 operation 识别前 parser failure 不由
C01 承诺。operation 已识别后，上述 path/query/body 任一拒绝项都是 400，且不得读取 Run。

#### Events 原始 HTTP authority

`readAgentRuntimeEvents.x-runtime-read-http-authority` 复用与 Status 完全相同的
`authority-version`、`operation-recognition` 和 `runtime-run-id` 键集，`path-shape` 固定为
`/v1/runs/{runtime_run_id}/events`；其余精确形状为：

```yaml
query:
  mode: allowlist
  allowed-parameters: [after_event_sequence, limit]
  multiplicity: at-most-once-each
  ordering: any
  unknown-parameter: reject-400
  repeated-parameter: reject-400
  ambiguous-percent-encoding: reject-400
  lexical-format: canonical-unsigned-ascii-decimal
  lexical-pattern: '^(0|[1-9][0-9]*)$'
  rejected-lexical-forms: [sign, leading-zero, empty, whitespace, exponent, fraction]
  parameters:
    after_event_sequence:
      omission-default: 0
      explicit-default-equivalent: true
      minimum: 0
      maximum: 9007199254740991
    limit:
      omission-default: 1000
      explicit-default-equivalent: true
      minimum: 1
      maximum: 1000
  malformed-or-out-of-range: reject-400
  valid-retention-expiry: respond-410
descriptor-digest-mismatch: reject-403
```

#### Retry 与 response header authority

两个 GET 的 `x-runtime-read-retry` 保持相同封闭键集。Status 的精确对象为：

```yaml
authority-version: runtime-read-retry-authority-v1
durable-caller-minimum-wait: at-least-retry-after
attempt: fresh-authorized-read-attempt
token: fresh
fencing: non-stale
descriptor-digest: recompute-for-new-attempt-token-fencing
logical-status-target: unchanged
event-cursor-limit: not-applicable
event-cursor-advance-on-429: not-applicable
adapter-auto-retry: forbidden
mutation-replay: forbidden
```

Events 的精确对象为：

```yaml
authority-version: runtime-read-retry-authority-v1
durable-caller-minimum-wait: at-least-retry-after
attempt: fresh-authorized-read-attempt
token: fresh
fencing: non-stale
descriptor-digest: recompute-for-new-attempt-token-fencing
logical-status-target: not-applicable
event-cursor-limit: unchanged
event-cursor-advance-on-429: forbidden
adapter-auto-retry: forbidden
mutation-replay: forbidden
```

新 descriptor digest 必须绑定新 Attempt、fresh token 和 non-stale fencing，不得复用旧 digest。
Events 的 cursor/limit 保持同一逻辑值且 429 不推进 cursor。

两个专用 response component 使用 `x-runtime-read-header-authority`。400 的精确对象为：

```yaml
authority-version: runtime-read-header-authority-v1
retry-after:
  presence: forbidden
```

429 的精确对象为：

```yaml
authority-version: runtime-read-header-authority-v1
retry-after:
  presence: required
  cardinality: exactly-one
  wire-format: canonical-decimal-integer-delta-seconds
  minimum: 1
  invalid-response-on: [missing, repeated, non-integer, zero, negative, unsafe-parse]
  invalid-response-retry: forbidden
```

OpenAPI Header Object 的 `required: true/type: integer/minimum: 1` 与该 authority 必须同时存在；
未声明 header 不能替代 400 的显式 `presence: forbidden`。429 header 缺失、重复、非整数、0、
负数或不安全解析都分类为 invalid response，调用方不得据此重试。

### 阶段 1.2：R02 二次 authority 纠偏

R02 二次只读复审 thread `019fc56d-b49d-7a51-ae01-491f34587e44` 指出 Stage 1.1 仍有两个
P1：Events 没有像 Status 一样结构化禁止 body/framing，429 的 canonical
`Retry-After` 也没有展开为可检查的原始 wire lexical grammar。Stage 1.2 只补这两个封闭对象，
不修改 descriptor Schema 或其他切片。

`readAgentRuntimeEvents.x-runtime-read-http-authority` 在 Stage 1.1 精确对象中、`query` 之后和
`descriptor-digest-mismatch` 之前加入以下完整 `body` 对象；键集和值必须与 Status 的 `body`
对象逐键一致：

```yaml
body:
  mode: forbidden
  nonzero-content-length: reject-400
  ambiguous-content-length: reject-400
  transfer-encoding: reject-400
  expect: reject-400
```

只有 listener 已通过精确 GET path shape 识别 Events operation 后，这些 body/framing 拒绝才是
C01 400；未知 route 或 operation 识别前 parser failure 仍为 `c01-out-of-scope`。Stage 3A
validator 必须比较 Events/Status `body` 的完整键集和值，不能依赖 description substring。

429 `x-runtime-read-header-authority.retry-after` 的 Stage 1.2 精确对象为：

```yaml
authority-version: runtime-read-header-authority-v1
retry-after:
  presence: required
  cardinality: exactly-one
  wire-format: canonical-decimal-integer-delta-seconds
  lexical-pattern: '^[1-9][0-9]*$'
  rejected-lexical-forms: [leading-zero, plus-sign, minus-sign, whitespace, decimal-point, exponent, non-ascii-digit, empty]
  minimum: 1
  invalid-response-on: [missing, repeated, non-integer, zero, negative, unsafe-parse]
  invalid-response-retry: forbidden
```

`lexical-pattern` 约束未经解析的单个 `Retry-After` header field value；OpenAPI Header Object 的
`type: integer/minimum: 1` 只约束成功解析后的值，不能替代 wire grammar。`rejected-lexical-forms`
顺序是 authority 的一部分；overflow 或其他不安全解析继续由 `invalid-response-on` 的
`unsafe-parse` 覆盖。400 header authority 保持只有 `presence: forbidden`，不增加 lexical 键。
Stage 3A Script 必须按封闭键集、数组顺序和原始 wire value fail closed，不得自行解释
`canonical-decimal-integer-delta-seconds` 枚举或依赖 prose。

### 阶段 2.0：readiness/topology 只读审计（本轮）

本阶段已经完成，以下内容只保留当时现场诊断，不是后继执行指令。其“固定 ID 传播 guard”与
`269/271` finalize 拓扑已被 Stage 3A 停止证据和第 2.1、9--13 节双 snapshot 决策取代，后继阶段
不得执行旧拓扑。本阶段只读取现场并修订本文，未修改 Contract/Script 机器资源或 evidence。精确
历史现场证据：

| 资源 | 当前 SHA-256 / 结构 | 现场结论 |
|---|---|---|
| `script/contract/validation/validate_semantics.py` | `88b5bfad57267f3687dbeac66919dddab29f81a562670ee6c913c5c3671ea200`；167 个 KNOWN、166 个静态 literal mark | `runtime_read.http_authority` 不在 KNOWN，也没有被 mark；traceability 对 unknown check 和未执行 check 分别在当前 validator 中 fail closed。Stage 3A 注册并真实执行前，Stage 2A 新 mapping 必然不能作为 green evidence |
| `script/contract/compatibility/check_contract_compatibility.py` | `f4d8ed6dabb1fe64648b3eadbf675f39cd8e4132cc3028d673515c803e8d707d` | 当前 316 行 comparator 从 Manifest/baseline inventory 比较 Schema、OpenAPI、state machine 等 wire 资源；不读取 Runtime Suite version/digest/profile/有序 test set，也没有 `requires recertification` 输出。按旧 Stage 2 直接执行必触发停止条件 |
| `script/contract/maintenance/refresh_example_digests.py` | `2d37d4606807527c73f56f77fc69c18724114abe7ddff87cc4799a3b4208fe85`；5629 行、280 个 `write()` 调用点 | 当时入口先重算并写回七套 Suite，随后广泛重建 examples/invalid fixtures；没有 C01 mode。Stage 3A 后续证明原固定 ID 传播 guard 拓扑无效；后继 helper 必须改为 active-only finalize + immutable registry verify-only，不能执行本行旧设想 |
| `verify_contract_manifest.py` / `.mjs` | `e9b8a3ed619e7c6cb65899aa505f26858d31c9b21232d2d280e2f9da456491ae` / `c641f7eea75223d4ddf848570b484012985be205bf7d93d1cbe981dd556ebd30` | Python 支持 `--print-values`/`--refresh` 后再核验；Node 只重建 inventory 并核验。Manifest 声明 `resource_count=269`、`resources` 长度 269；未变的 Python/Node roots 都发现 271，差集精确为 Stage 1 两个新 error Schema。Runtime Suite 已在 inventory，semantic constraints 不在；当前是已知 drift，不是 green |
| `offline_static_audit.py` / `validate_contracts.py` | `e403f820208a99da9b001365169d69e874d3f03f6a1da9886e2cae88314bbea4` / `85108ae8be9d9594d7ad806a896f440542c4e59d38fb8745fca9b516e06c3a95` | Stage 3A 必须补 C01 结构化解析与正反例/self-test，不能把 Stage 1 的临时 equality assertion 当成长期 Gate |

只读命令为 `git rev-parse/status/merge-base`、定向 `rg/sed/nl/wc`、Python AST/JSON 读取和
`shasum -a 256`；没有执行 validator、refresh、Manifest `--refresh`、compatibility comparator 或
full Gate。Stage 2.0 non-goals 是所有机器 Contract、Script、Application、evidence 与 dependency
lock；唯一交付是本文 topology/ledger 未提交 diff。

### 阶段 2A：Contract authoritative draft

本阶段已经完成并经总控/R02 审查。以下 `269/271` 只记录 snapshot 创建前的历史 inventory 现场，
不得当作 Stage 2B final count；原固定 ID 传播设想已作废且不得执行。Contract writer 当时只编辑
10.1 中的两个正例、两个反例、`semantic-constraints-v1.json`、Runtime
Suite `suite.json` 和本计划 ledger：

1. 正反例精确表达 400/429 body；header/raw HTTP 规则仍由结构化 OpenAPI 与后续 Script 验证；
2. 新增 `runtime_read.http_authority` `contract_gate` mapping，但明确当前 Script 尚不认识它；
3. Runtime Suite 将 `suite_version` 提升为 `1.0.1`，只在 `runtime-core-v1` read 邻近位置加入 Status
   400、Event 400、Status 429、Event 429 四个唯一 case，保持其他 profile/test 顺序不变；
4. `suite_digest` 在 Stage 2B guarded finalize 前不视为最终，不手工伪造已验证 digest；
5. 不运行 broad refresh，不修改任何历史固定 ID consumer 或 Manifest，不运行/不声称 semantic、
   Manifest 或 compatibility green；保留未提交 Contract draft 供总控只读审查；
6. 保留 Stage 1 已产生的 Manifest 269 -> discovered 271 drift，不把它归因于 Stage 2A。只读重算
   inventory path set；Stage 2A 结束时仍须仅缺两个 Stage 1 Schema，且不得出现新的 inventory 路径。

#### Stage 2A correction：四 case 精确可执行边界

R02 审查后的下一次机器 Contract 修订只收紧四个现有新增 case 的 description，不增加第五个 case，
不改变既有 case、profile、category/evidence type 或相对顺序：

1. Status 400 case 必须在 listener 已精确识别 operation 后，覆盖计划/OpenAPI 封闭 authority 中全部
   path shape、单一 `runtime_run_id` segment/长度/禁止等价化、Status 禁止 query、禁止 body 及非零或
   歧义 Content-Length、Transfer-Encoding、Expect 的 400 拒绝；syntactically valid descriptor digest
   mismatch 保持 403；400 无 `Retry-After`，body 使用专用 bad-request Schema，diagnostics 仅为公开、
   有界 field/reason 且不含敏感或跨租户数据；
2. Event 400 case 除相同 path/`runtime_run_id`/body/framing 边界外，必须覆盖 query allowlist、最多一次、
   任意顺序、默认值等价、canonical unsigned ASCII decimal、percent encoding、范围等全部拒绝；
   malformed/out-of-range 是 400，只有合法 cursor 超出 retention 才是 410；descriptor digest mismatch
   保持 403；400 无 `Retry-After`，body 与 diagnostics 边界同上；
3. Status 429 case 必须同时覆盖完整合法响应与负向响应矩阵：只在 operation、caller-token-descriptor、
   Attempt、fencing binding 全部通过后、provider-local state 前产生，且与 Run 是否存在无关；body 使用
   专用 throttled Schema；`Retry-After` 必须是 exactly-one raw field，lexical/value 同时满足
   `^[1-9][0-9]*$` 和安全解析值 `>=1`。missing、repeated、noncanonical、unsafe parse、zero、negative
   均是 invalid response 且禁止重试；durable caller 至少等待该值，再用 fresh Attempt/token、non-stale
   fencing 重算 descriptor digest，logical Status target 不变；adapter 不自动重试，不重放 mutation；
   diagnostics 仅为公开、有界且无敏感/跨租户数据；
4. Event 429 case 必须覆盖相同合法/负向 header、body、admission、fresh Attempt/token/fencing/digest、
   no auto-retry/no mutation replay 边界，并明确 cursor/limit 保持不变且 429 不推进 cursor；
5. 四个 case 始终只是 `contract-defined` / `phase0_implementation_required`，不表示任何现有 Provider
   passed。Stage 3A Script focused self-test 只证明 validator/helper 能 fail closed，也不能冒充四个
   case 的 Provider conformance execution。

Stage 2A 只读/focused 检查：

```bash
cd /Users/echo/.codex/worktrees/65b0/agent
git diff --check
git status --short
git diff --name-status 793215cbe1b79c0f4cb7f16b13ec71b9483920fd
git diff --name-only 793215cbe1b79c0f4cb7f16b13ec71b9483920fd | LC_ALL=C sort
python3 - <<'PY'
import json
from pathlib import Path

root = Path("contract")
manifest = json.loads((root / "compatibility/contract-manifest.json").read_text())
paths = [
    *sorted((root / "schemas").glob("*.json")),
    *sorted((root / "examples/schemas").glob("*.json")),
    *sorted((root / "openapi").glob("*.yaml")),
    *sorted((root / "state-machines").glob("*.json")),
    *sorted((root / "event-types").rglob("*.json")),
    *sorted((root / "conformance").rglob("*.json")),
    *sorted((root / "testdata").rglob("*")),
]
python_discovered = {path.relative_to(root).as_posix() for path in paths if path.is_file()}
node_discovered = set()
for relative, suffix in (
    ("schemas", ".json"),
    ("examples/schemas", ".json"),
    ("openapi", ".yaml"),
    ("state-machines", ".json"),
    ("event-types", ".json"),
    ("conformance", ".json"),
    ("testdata", None),
):
    for path in (root / relative).rglob("*"):
        if path.is_file() and (suffix is None or path.name.endswith(suffix)):
            node_discovered.add(path.relative_to(root).as_posix())
listed = {item["path"] for item in manifest["resources"]}
expected_missing = {
    "schemas/agent-runtime-read-bad-request-error.schema.json",
    "schemas/agent-runtime-read-throttled-error.schema.json",
}
assert manifest["resource_count"] == len(manifest["resources"]) == len(listed) == 269
assert python_discovered == node_discovered
assert len(python_discovered) == 271
assert python_discovered - listed == expected_missing
assert listed - python_discovered == set()
PY
```

Evidence 仅为未提交 owner diff、JSON parse、四 case 的 ID/顺序/唯一性断言和明确的 expected-red
清单：unknown semantic mapping、待 finalize active Suite digest、historical snapshots 尚未建立、
comparator 缺双版本 Suite/Port registry 能力，以及 Stage 1 已存在的 Manifest declared/listed 269 对
discovered 271 drift。该 drift 不是
Stage 2A 新增；若 Stage 2A 结束时 Manifest path 差集不再精确等于上述两个 Schema，立即停止并解释。
任何人不得提交或把该中间态描述为 Contract green。总控只读审查通过后，Contract writer 停止并
释放 ownership。

### 阶段 2S：immutable historical snapshots Contract substage

这是恢复 Stage 3A 前的强制 Contract 子阶段，必须由总控与独立 reviewer 审核。唯一机器写 owner 为：

- `contract/conformance/runtime/v1/revisions/1.0.0/suite.json`；
- `contract/openapi/agent-runtime-provider-v1.0.0.snapshot.yaml`。

另只允许回填本计划 ledger。active Suite/OpenAPI、semantic、fixtures、Manifest、全部 historical facts、
三个 partial Script 与其他 Script 全程只读。执行步骤：

1. 从精确 `a8024901547df93453685ecb8044fe58399c30df` 读取旧 Runtime Suite/OpenAPI 原始字节，分别写入
   snapshot 路径；不得从 active `1.0.1` 降版生成；
2. 独立重算旧 Suite 自摘要、tuple、文件 byte SHA 与旧 OpenAPI `info.version`/raw SHA，并与
   `a802490...` 逐字比较；第 2.1 节诊断值只能辅助核对；
3. 解析旧 OpenAPI 的全部 external Schema ref occurrences，必须得到 R03 只读复算的 18 次 occurrence
   与 6 个 unique targets；现场记录 occurrence、target/path 与独立摘要，并逐个证明目标在当前 Contract
   与 `a802490...` 字节完全相同。计划不预写尚未取得的完整清单。数量不符、漏项、重复解析歧义或
   任一 target 漂移即停止并升级为 immutable bundle/full Revision snapshot 治理前置，不得复制 active
   Schema 冒充历史依赖；
4. 证明两个 snapshot 路径符合现有 Manifest inventory roots，但本阶段不刷新 Manifest；记录预期
   Manifest drift，留给 Stage 2B 现场重算；
5. snapshot diff 经总控与独立 reviewer 通过后，Contract writer 停止并释放 ownership。未通过前
   不得恢复 partial Stage 3A。

只允许 JSON/YAML parse、`git show`/byte comparison、外部 ref path/byte equality、owner/status/diff-check
等只读验证；不运行 validator、refresh、Manifest verifier、comparator 或 Gate。

### 阶段 3A：Script enforcement resume

本阶段从“partial Script 未验收”的停止点恢复，而不是沿用其 green 结论。Stage 2S 通过后，单一
Script writer 取得 ownership；全部 Contract 只读。实施要求：

1. `offline_static_audit.py` 只对 active Runtime OpenAPI 1.0.1 执行 C01 400/429 封闭 authority，并验证
   active 为 20 次 external ref / 8 个唯一 target；historical 1.0.0 snapshot 只校验 immutable bytes/
   version、18 次 external ref / 6 个唯一 target 与 Port registry，不要求存在 1.0.1 extensions；
2. `validate_contracts.py` 发现 active 与所有 revision snapshots Suite，以完整
   `(suite_id,suite_version,suite_digest)` 建立唯一 registry，验证每个 Suite 自摘要；重复、缺失、
   digest 冲突、仅按 `suite_id` 覆盖版本均 fail closed；
3. `validate_semantics.py` 从 semantic/evidence 加载完整 Suite tuple，从 Provider Port 加载完整
   `(protocol,protocol_version,contract_digest)`，唯一解析本地 active/snapshot resource；先成功验证
   C01 结构再真实 mark `runtime_read.http_authority`，并保持 supplemental Contract-owned preservation；
4. `refresh_example_digests.py` 的 C01 finalize 只更新 active Suite 自摘要；immutable Suite/OpenAPI
   snapshots 与所有历史 ProviderRevision/AdmissionDecision/Capabilities/Checkpoint/Compatibility/
   Run/passed evidence 只读。normal broad 与 guarded mode 都必须 verify-only historical registry，禁止
   自动升级 tuple、Port、ID 或任何传递摘要；
5. comparator 证明 historical snapshots 与 `a802490...` 相等、active OpenAPI/Suite 1.0.1 additive、
   四 case 要求再认证且历史事实未重绑；唯一成功结论是
   `wire-additive + requires recertification`，不得退化为普通 pass；
6. 必须修改 `lint_openapi_zero.mjs` 与 `script/package.json`，使正常命令 fail closed 证明 10 lint / 10
   bundle；`prepare_openapi.py`、两个 Manifest verifier、`redocly.yaml`、
   `verify_openapi_bundle_determinism.py` 按 10.2 reviewed unchanged。historical snapshot 不套用 active
   C01 authority check，Redocly 必须发现 10 个文档且逐个 0 error/0 warning；
7. 所有 self-test 在临时 Contract copy 且任何正常顶层写入前分流。snapshot 缺失/漂移、historical
   `18/6` 或 active `20/8` external ref 枚举/target bytes 漂移、
   重复 Suite/Port tuple 或 digest、active/snapshot 互换、unresolved Suite/Port、refresh 改写任一历史
   事实、R03 确认的 11 个 historical positive objects 任一非零 diff、1.0.1 冒充 passed/certified、
   normal refresh 改写 snapshot、Manifest 非现场重算结果或 lint/bundle 非 10 均稳定失败，当前
   Contract/Manifest/build/evidence 零写入；
8. 原 Stage 3A supplemental、raw YAML duplicate-key、Retry-After、single-factor fixture、40/64 位 base
   ref、nested Contract layout、missing baseline blob、profile/test reorder/stale digest 等 negative coverage
   继续保留，但不得把 Script statement 变成 Contract authority。

五个 C01 focused self-test CLI 已在任何 normal 顶层写入前完成参数分流，并在内部使用临时 Contract；
因此这五条可以从主检出运行。除此之外，还必须在隔离的临时 Script/Contract tree 实际执行
`prepare_openapi.py`、10-document Redocly lint、`package.json` 的 `bundle:openapi` 命令与
`verify_openapi_bundle_determinism.py`。必须证明恰好 10 个相互独立的 bundle 且重复生成 byte-
deterministic；不能用 source/topology 评估代替真实运行。任一失败时当前 Contract、Manifest、build、
evidence 必须零写入。所有测试完成后由总控与独立 reviewer 审核 Script diff，未通过不得进入 Stage 2B。

```bash
cd /Users/echo/Projects/nightingales/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
.venv/bin/python contract/validation/offline_static_audit.py --self-test-c01-runtime-read
.venv/bin/python contract/validation/validate_contracts.py --self-test-c01-runtime-read
.venv/bin/python contract/validation/validate_semantics.py --self-test-c01-runtime-read
.venv/bin/python contract/maintenance/refresh_example_digests.py --self-test-c01-runtime-read
.venv/bin/python contract/compatibility/check_contract_compatibility.py --self-test-c01-runtime-read
```

额外四条必须在同一 pinned runtime/container 中按以下隔离步骤执行。`rsync` 读取的是当前工作树字节，
因此会保留未提交 Contract candidate、partial Script、package/requirements/pnpm locks；禁止改用
`git archive HEAD`，因为它会丢失这些未提交输入。只排除 Script 的 `.venv/node_modules/build/evidence`
输出，完整复制当前 Contract candidate：

```bash
C01_MAIN_ROOT=/Users/echo/Projects/nightingales/agent
C01_PINNED_PYTHON="$(command -v python)"
C01_TMP_PARENT="${TMPDIR:-/tmp}"
C01_TMP_PARENT="${C01_TMP_PARENT%/}"
C01_TMP_ROOT="$(mktemp -d "$C01_TMP_PARENT/c01-stage3a.XXXXXX")"

case "$C01_TMP_ROOT" in
  "$C01_TMP_PARENT"/c01-stage3a.*) ;;
  *) echo "invalid C01 temp root" >&2; exit 1 ;;
esac

c01_cleanup() {
  case "$C01_TMP_ROOT" in
    "$C01_TMP_PARENT"/c01-stage3a.*)
      test ! -d "$C01_TMP_ROOT" || rm -rf -- "$C01_TMP_ROOT"
      ;;
    *) echo "refusing unsafe C01 cleanup" >&2; return 1 ;;
  esac
}
trap c01_cleanup EXIT HUP INT TERM

mkdir -p "$C01_TMP_ROOT/script" "$C01_TMP_ROOT/contract"
rsync -a \
  --exclude='.venv/' --exclude='node_modules/' --exclude='build/' --exclude='evidence/' \
  "$C01_MAIN_ROOT/script/" "$C01_TMP_ROOT/script/"
rsync -a "$C01_MAIN_ROOT/contract/" "$C01_TMP_ROOT/contract/"

cd "$C01_TMP_ROOT/script"
export AGENT_CONTRACT_ROOT="$C01_TMP_ROOT/contract"
pnpm install --frozen-lockfile --ignore-scripts
"$C01_PINNED_PYTHON" contract/validation/prepare_openapi.py
node contract/validation/lint_openapi_zero.mjs
pnpm run bundle:openapi
"$C01_PINNED_PYTHON" contract/validation/verify_openapi_bundle_determinism.py
```

Stage 3A evidence 必须在隔离命令前后分别锁定主检出 Contract、Manifest、Script、build、evidence 的
byte/path set，并证明即使任一 setup/额外命令失败也为零变化。cleanup 只能命中上述已通过 `case`
验证的 `mktemp` 路径；不得对空变量、工作树、workspace root 或未验证父目录执行递归删除。

Stage 3A green 只证明 Script enforcement 能力，不证明 active Contract finalized、Provider passed、
Application conformance 或任何 maturity 提升。

### 阶段 2B：active Contract deterministic finalize

Contract writer 在 resumed Stage 3A 审查通过后重新取得 ownership；Script 与 snapshots 只读：

1. 记录 active Suite、两个 immutable snapshots、所有历史 facts 与 Manifest 的 preimage bytes/digests；
2. 使用已审查 helper 只重算 active `conformance/runtime/v1/suite.json` 的 `suite_digest`，禁止修改
   Suite version/test/profile 之外的已审查 draft，也禁止向任何历史 fixture/evidence 传播；
3. 运行 verify-only Suite/Port registry，证明 active semantic artifact 仍指 active Suite 并派生完整
   tuple，historical Suite/OpenAPI snapshots 唯一可解析且自摘要/字节未变；
4. 在当前 inventory roots 上现场独立计算 discovered path set/count，再执行 Manifest `--refresh`；
   以 Python `--print-values`/verify、Node verify、Manifest resources 与双实现 JCS 证明
   declared/listed/discovered、完整 path set、`resources_digest`、`manifest_digest` 一致。R02 的 273 与
   两个诊断摘要不是硬编码成功值；任何不一致先停止并解释；
5. 真实执行 focused Contract/semantic lanes，确认 `runtime_read.http_authority` 注册并本轮执行；
   执行 Redocly/bundle，必须分别发现 10 个 OpenAPI 文档且 lint 全部 0 error/0 warning；重新枚举
   historical `18/6` 与 active `20/8` external ref occurrence/unique-target topology；
6. 对 `a802490...` 运行增强 comparator，唯一接受
   `wire-additive + requires recertification`；同时逐字证明 ProviderRevision digest
   `3a68cf38...a4cd`、AdmissionDecision digest `29b5fe38...178a6`、Port digest
   `f75bd948...f5811`、Suite 1.0.0 tuple、R03 确认的 11 个 historical positive objects 与全传递闭包
   均逐字未变化；
7. active 1.0.1 只保持 contract-defined/requires-recertification；不得新增、重算或宣称任何 passed
   ProviderRevision、AdmissionDecision、Run、Checkpoint、CompatibilityDecision 或 evidence。

```bash
cd /Users/echo/Projects/nightingales/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
.venv/bin/python contract/maintenance/refresh_example_digests.py --c01-runtime-read-finalize
.venv/bin/python contract/manifest/verify_contract_manifest.py --print-values
.venv/bin/python contract/manifest/verify_contract_manifest.py --refresh
.venv/bin/python contract/manifest/verify_contract_manifest.py --print-values
.venv/bin/python contract/manifest/verify_contract_manifest.py
node contract/manifest/verify_contract_manifest.mjs
.venv/bin/python contract/validation/offline_static_audit.py
.venv/bin/python contract/validation/validate_contracts.py
.venv/bin/python contract/validation/validate_semantics.py
.venv/bin/python contract/validation/prepare_openapi.py
node contract/validation/lint_openapi_zero.mjs
pnpm run bundle:openapi
.venv/bin/python contract/validation/verify_openapi_bundle_determinism.py
CONTRACT_FROZEN_BASE_REF=a8024901547df93453685ecb8044fe58399c30df \
  .venv/bin/python contract/compatibility/check_contract_compatibility.py
```

Stage 2B evidence 必须记录现场完整摘要/count/path set、10-document Redocly、10 个独立且
deterministic 的 bundle、
registry resolution、historical zero-diff 与 structured comparison，不得复制第 2.1 节诊断常量。

### 阶段 3B：Script source binding/evidence generator

Stage 2B 审查通过并释放 Contract ownership 后，Script writer 再取得 ownership：

1. 实现确定性 Blueprint、Contract、Script governed source snapshot；
2. `generate_validation_evidence.py` 必须输出
   `blueprint_source_revision`、`contract_source_revision`、`contract_manifest_digest`、
   `script_source_revision`、Runtime Suite ID/version/digest/profile、base commit、工具版本和生成时间；
3. generator 重新读取 Manifest/Suite 并核对各 lane 同 digest，禁止复制计划常量；
4. self-tests 使缺字段、旧 digest、非法 Retry-After、错误 retryable、响应回退、source drift 均
   fail closed，并明确 2026-07-27 evidence 不覆盖 `a802490` 或 C01；
5. 本阶段只测试 generator/source binding，不生成最终 `script/evidence/*`。

```bash
cd /Users/echo/Projects/nightingales/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
.venv/bin/python contract/validation/check_supply_chain.py
.venv/bin/python contract/validation/generate_validation_evidence.py --self-test
```

Stage 3B 只证明 source binding/evidence generator 可 fail closed；还不能声称完整 Gate 通过。

### 阶段 4：冻结源文件与完整 Contract Gate

先回填本计划阶段 1、2A、已停止 partial 3A、2S、resumed 3A、2B、3B 的实际差异、验证、偏差、
停止条件和剩余风险，然后冻结所有 Contract 与 Script source。冻结后运行一次完整 Gate；Gate 后
不得再编辑纳入 source revision 的文件。

```bash
cd /Users/echo/Projects/nightingales/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
export CONTRACT_FROZEN_BASE_REF=a8024901547df93453685ecb8044fe58399c30df
make validate-contract
```

Gate 后只读复核：

```bash
cd /Users/echo/Projects/nightingales/agent
jq -e '
  .status == "local_candidate_contract_gate_passed" and
  .source_bindings.blueprint.source_revision != null and
  .source_bindings.contract.source_revision != null and
  .source_bindings.contract.manifest_digest != null and
  .source_bindings.script.source_revision != null and
  .source_bindings.runtime_suite.suite_digest != null and
  .maturity.contract_validation == "passed_locally" and
  .maturity.phase0b_implementation == "external_not_assessed" and
  (.maturity.frozen | not)
' script/evidence/VALIDATION.json
git diff --check
git status --short --branch
```

若实际 evidence shape 与上述 jq 路径有经评审的更佳命名，Stage 3B 必须先更新本文并冻结，不能在
Gate 后为通过 jq 再改报告。

### 阶段 5：兼容审查与下游 handoff

1. 审查 diff 只包含第 10 节 owner 文件；
2. 记录旧/新 OpenAPI、Suite、Manifest、source revisions 的双版本矩阵；
3. 确认旧 17-case evidence 仍为历史 component maturity，四个新 case 没有 Application 结果；
4. 输出给 C02/C08/Application 的只读 handoff：新 digests、旧 Revision 保留规则、blocked
   fresh authority 与实现缺口；
5. C01 结束，不刷新 Application lock、不修改 Application 代码、不产生 ProviderRevision。

## 12. 停止条件

出现任一项立即停止受影响阶段并报告：

- HEAD 不包含 `a802490...`，或存在无法由当前阶段 owner 解释的工作树变化；
- 必须修改 Blueprint 才能决定 400/429、authority 或可靠性语义；
- 必须引入 Token Claims V2、observation/reduction_control、RunManifest 或 Application 变化才能
  让 C01 Gate 通过；
- 400 无法与 401/403/404/410 保持无歧义 precedence，或会形成跨租户存在性 oracle；
- 429 无法强制 `Retry-After` 与 `StandardError.retryable=true` 同时成立；
- Script validator 只能靠文件路径、字符串存在或实现行为证明 Contract，而不能解析结构化资源；
- Script 硬编码/重写 supplemental statement、index、ID 或 enforcements 才能验证 C01，或无法在不让
  Script 成为意义来源的前提下从当前 Contract 识别并保留 supplemental ordered objects；
- Stage 2A 的 `runtime_read.http_authority` unknown/unexecuted 是已记录的 expected-red draft，禁止
  在此状态运行 Gate、声称 green 或提交；Stage 3A 审查结束时若仍未注册并真实执行，则停止，不得
  进入 Stage 2B；
- Stage 2A correction 后四个 Suite case 仍未分别覆盖第 2A 节固定的完整 400/429 正负向边界，或
  任何描述/self-test 把 `phase0_implementation_required` 冒充 Provider passed/conformance execution；
- Stage 2A/2S/resumed 3A/2B/3B handoff 未经总控只读审查、同一时刻出现两个 domain writer，或有人
  尝试提交 unknown semantic mapping、stale active Suite digest、未审查 snapshots、未闭合 registry、
  旧 Manifest/comparator 或 partial Script 红色中间态；
- Stage 2S 创建前的 inventory path set 不再等于 Stage 2.0 记录的 preimage，或不再只表现为两个
  Stage 1 error Schema 的既存 drift；必须先列出并解释精确新增/删除路径，禁止为匹配计划硬写 count；
- historical Suite/OpenAPI snapshot 缺失、不是从 `a802490...` 原始字节提取、与 baseline 漂移，或
  external ref 现场枚举不能得到 historical `18 occurrences / 6 unique targets` 与 active
  `20 occurrences / 8 unique targets`；全部 occurrence 与 target/path/digest 必须现场列举，任一
  historical target 在 current 与 `a802490...` 字节不同即停止并升级 immutable bundle/full Revision
  snapshot 前置；
- Suite registry 或 Port registry 出现缺失、重复 tuple、重复 digest 冲突、自摘要错误、仅按 ID 覆盖
  版本、active/snapshot 互换或 unresolved reference；
- Stage 2S 审查通过前恢复 partial Stage 3A，或把当前三个 partial Script 描述为完成、验收或 green；
- Stage 3A 在任何顶层 normal validation/build 写入前不能分流 C01 self-test，mutation 未限定在临时
  Contract tree，或失败路径对当前 Contract/Manifest/Script/build/evidence 产生写入；
- `refresh_example_digests.py` 的 normal 或 guarded 路径修改 immutable snapshot、任一历史 tuple/Port/
  ID/digest/直接消费者/传递闭包，不能把 finalize 限定为 active Suite artifact，或伪造 active 1.0.1
  ProviderRevision、AdmissionDecision、Run、Checkpoint、CompatibilityDecision 或 passed evidence；
- R03 确认的 11 个 historical positive objects 任一不是逐字零 diff，或 active 1.0.1 出现任何
  passed/certified ProviderRevision、AdmissionDecision、Run 或 evidence；
- normal broad regeneration 或 guarded finalize 不能证明 supplemental ordered objects 前后递归完全
  相等；不能对删除、改写、重排、重复、stable-ID/`(schema_id,index)` 碰撞、unresolved reference、
  unknown/unexecuted check fail closed；或任一失败路径会写当前工作树；
- Stage 2B semantic check 未注册/未执行、四个 Suite case 未进入现场重算的 active Suite digest/Manifest，
  或 Manifest 的 declared/listed/discovered/path set/JCS resources/manifest digest 不能由 Python/Node
  一致证明。R02 诊断预期为 273；若现场独立结果不是 273，必须先停止并解释精确路径差异，不得硬写
  count 或摘要；
- Redocly/lint 与 deterministic bundle 不能分别现场发现恰好 10 个 OpenAPI 文档并逐个保持 lint
  0 error/0 warning，historical snapshot 被错套 active C01 1.0.1 authority check，或 normal refresh
  改写任一 snapshot；
- Stage 3A 结束后 compatibility comparator 仍未比较 OpenAPI version 与 Suite version/digest/profile/有序 test set、无法
  证明 snapshot 等于 baseline、历史 facts 未重绑，无法唯一表达
  `wire-additive + requires recertification`、报告 breaking change，或新 Revision 需要覆盖旧
  Suite/ProviderRevision；
- 找到 Blueprint/Contract 明确要求 `semantic-constraints-v1.json` 必须进入 Manifest inventory；
  该项升级为独立治理前置，不在 C01 内顺手扩大 inventory/verifier；
- 需要在无 C01 专属 authority 下新增 `Cache-Control` 或把 pre-operation listener saturation 当作
  Status/Event 429 evidence；
- 生成/维护命令改写第 10 节之外的 Contract/Script 文件且无法解释；
- 完整 Gate 任一 lane 失败、0 warning 不能保持、source binding 与当前 frozen source 不一致；
- 需要把历史 component evidence 提升为 aggregate/platform/production 结论才能宣称完成。

## 13. Rollback 与兼容窗口

阶段 0 只有 Markdown，可整体回退三个计划/索引变更；阶段 0.1 也只有本计划 Markdown，可单独
回退到 `68c3fb9...`。两者均不触碰任何 durable fact。

当前 candidate 在任何新 ProviderRevision 准入前，只能撤销 active `1.0.1` Contract candidate、两个
尚未发布的 snapshot candidate、对应 Manifest candidate 与 Script candidate，并保留失败记录供审计。
rollback 绝不原地重写、删除或重绑旧 ProviderRevision、AdmissionDecision、Capabilities、Checkpoint、
Compatibility、Run、Port、Suite tuple 或 evidence；也不得通过更新原固定 ID 消费者来“回退”。snapshot
一旦随 Revision 发布为 Manifest-governed historical resource，同样不得删除或改写。

若未来新 ProviderRevision 经独立准入，rollback 只能停止新 Run 选择该 Revision，并保留新
provider/reader 支持处理已锁定 Run 和 reconciliation；不能把这些 Run 改绑 `1.0.0`。旧
ProviderRevision 可继续服务其旧 Run，但只按 immutable historical OpenAPI/Suite 与旧 digest 解释。

Script rollback 必须保留能验证所有仍受支持 Contract Revision 的 validator。Gate evidence 是
append-only 发布证据：错误报告可以被新报告否定，不能原地改写日期/digest 冒充原运行。

当前三个 partial Stage 3A Script 未验收；恢复前或恢复后审查失败时，rollback 只撤销相应 Script
candidate，不把 partial 代码描述为已完成，也不改写 Contract draft/historical facts。Stage 2S 被拒绝时
只撤销两个尚未发布的 snapshot candidate 与本计划 ledger；不得修改 active draft、旧 facts 或 partial
Script。在 supplemental preservation 修复并审查前禁止运行会覆盖 semantic traceability 的 normal broad
regeneration。任何 rollback 都不得以删除、重排或把 supplemental statement 搬入 Script 常量的方式
“解决”失败；若无法做到 Contract-owned preservation，触发停止条件并返回总控重新选择方案，不得
擅自回改两个 Stage 1 Schema。

## 14. Maturity 上限

C01 当前仍是未闭合的 Contract candidate：Stage 2S 尚未创建/审核，partial Stage 3A 未完成/未验收，
active Suite digest、Manifest、registry/comparator、source binding 与 full Gate 均未闭合。Application
dependency lock、Application 实现与 Application evidence 继续禁止修改。

C01 最多得出：新的 AgentRuntimeProvider v1 patch candidate Contract Revision 在锁定 Blueprint、
Contract、Manifest、Script、Suite 输入下通过本地 Contract Gate，并得到候选
`wire-additive + requires recertification` compatibility 结论。

以下状态全部保持原值：

- 旧 B03.2 lifecycle/component evidence：只保留各自历史 maturity；
- aggregate `runtime-core-v1`：`not_claimed`；
- 0B：不提升；
- 0C-0G：不提升；
- 0H：不提升；
- formal freeze：`false`；
- security/production approval：未评估、未授予。

四个新 Runtime Suite case 在 Application 重新锁定并真实执行前只能是 contract-defined、
implementation-not-assessed，不能用 Contract Gate 标为 provider passed。
Stage 3A validator/helper/comparator focused self-test 即使全绿，也只证明 Script enforcement 能力，
不构成上述四个 case 的 Provider execution、`runtime-core-v1` conformance 或任何 maturity 提升。

## 15. 剩余风险

- HTTP intermediary 可能重写、合并或丢弃 `Retry-After`；真实 transport/proxy evidence 属于
  Application/0H，不由 Contract Gate 证明；
- 新 429 允许 durable retry，但 C01 不提供 jitter、backoff、fairness、queue capacity 或防惊群
  实现；
- fresh token issuer、reconciliation scheduler 和持久 InvocationAttempt 仍未实现；C02 与后续
  Application authority 是硬前置；
- 增加 read 400/429 对旧 adapter 是新响应集合。虽然 Contract comparator 应判定 additive，
  旧 consumer 仍可能把它们视为 invalid response，因此必须使用新 ProviderRevision 与双版本窗；
- `StandardError` 是 JSON body，不能单独证明 HTTP header；必须保留结构化 OpenAPI + Script
  validator 双重检查；
- 当前没有正式 frozen baseline；相对 `a802490...` 的 comparison 只是候选审查，不能宣称正式
  compatibility pass；
- Contract Manifest 不替代完整 Contract Source Revision，Script evidence 也不替代 Application
  evidence；缺少任一绑定都不能发布 C01 完成结论；
- Suite 与 Port 双 registry 的 discovery、完整 tuple 唯一性、自摘要和 active/snapshot resolution 是
  新增 fail-closed 面；任何只按 ID 覆盖版本或把 active 与 snapshot 互换都会误绑历史事实；
- historical OpenAPI 的 external ref bundle 尚未由 Stage 2S 现场完整枚举。R03 只读复算得到 6 个
  unique targets；若任一 target 相对 `a802490...` 漂移，两个顶层 snapshot 不足以形成 immutable
  history，必须先升级 immutable bundle/full Revision snapshot 治理；
- Stage 2A 会形成有意保留的未提交 expected-red draft；若 ownership handoff、总控审查或“不提交
  红色中间态”约束失守，semantic/Manifest/compatibility 结论会互相矛盾；
- 当前三个 partial Stage 3A Script 未完成且未验收，可能需要基于双 snapshot/registry topology 重做；
  refresh helper 的 broad rebuild、comparator 的 Suite blindness、10-document lint discovery 都是 resumed
  Stage 3A 必须先关闭的 tooling risk，在审查通过前任何 refresh/compatibility 输出都不是 C01 evidence；
- Manifest inventory 不含 semantic constraints 是显式治理选择，因此最终 closure 必须同时绑定精确
  Contract Source Revision 与真实 semantic execution，不能只引用 Manifest digest。

## 16. 阶段台账

**历史作废声明：**16.1--16.7 保留各阶段当时的命令、判断与失败链路，供审计使用；其中任何“固定
ID 八传播”“第九路径即失败”“final 271”或让旧对象原地升级 `1.0.1` 的文字均已由 Stage 3A 停止
证据和双 snapshot 决策作废，绝不得作为后继执行指令。当前可执行 authority 只取第 2.1、9--13 节、
下表当前状态与 16.8；历史 ledger 不得覆盖它们。

| 阶段 | 状态 | 交付 | 验证/证据 | 偏差、风险与成熟度 |
|---|---|---|---|---|
| 0. 计划与索引 | 已完成 | 新增本计划、Contract 计划索引；根 README 增加索引入口；未改机器资源、Script、Application | 基线 HEAD/clean/ancestor 只读核对通过；阶段末执行 `git diff --check`、owner path diff、status | 仅计划成熟度；旧 Gate/evidence 不提升；后续阶段未授权、未执行 |
| 0.1 R01 审查修订 | 已完成（历史传播设想已作废） | 当时登记固定 ID Suite 传播点、Suite 再认证比较、operation precedence、Manifest inventory 与 Cache-Control 治理决策；只改本计划 | 总控只读检查 + R01 thread `019fc53f-6f65-7291-9486-32030db8b938`；基线 `68c3fb9...` clean/ancestor；阶段末执行 Markdown-only diff/status | precedence、recertification、binding 等仍有效；固定 ID 传播已被双 snapshot/历史零传播取代且不得执行。其余不采用项见 3.1；仍仅计划成熟度 |
| 1/1.1/1.2 Schema/OpenAPI + R02 纠偏 | 已完成并提交 | 总控与 R02 最终复审通过；提交 `793215cbe1b79c0f4cb7f16b13ec71b9483920fd` 只含计划、Runtime OpenAPI、两个新 error Schema | 初始 focused checkpoint 见 16.1；R02 两次纠偏见 16.2/16.3；固定容器均 exit 0，Redocly 9/9 为 0 error/0 warning；总控独立验收 commit | 仅 Stage 1 authority；Script/fixture/Suite/Manifest closure 仍未执行，maturity 不提升 |
| 2.0 readiness/topology | 已完成并提交 `ba5ff1d624a7019e118cbbfc964d7ecd33decea6` | 只读审计五类 Script/Manifest 能力；当时 topology 后由 Stage 3A 停止证据再次修订 | 精确 HEAD/clean/ancestor；定向 source read、AST/JSON inventory、SHA-256、declared/listed/discovered/path-set/owner diff，见 16.4 | 当时 269/271 仅为 pre-snapshot 历史现场；不再是 final 规则，无 Contract maturity |
| 2A Contract authoritative draft | 总控/R02 最终审查通过，Contract ownership 已释放 | R02 task `019fc56d-b49d-7a51-ae01-491f34587e44` 最终通过；七个 Contract draft 保持未暂存、未提交 | 原 draft 见 16.5，plan-only 决策见 16.6，四 description、两条 400 前像递归断言与最终 handoff 见 16.7 | `runtime_read.http_authority` unknown/unexecuted、active Suite digest stale、Manifest/comparator 未闭合；固定 ID 传播设想已作废，不提升 maturity |
| partial 3A Script enforcement | 已按停止条件中止；三个 partial Script 未验收 | 只形成三个 partial Script diff；refresh/comparator 保持基线 | 原始 ID/digest closure 诊断与当前 SHA 见 16.8；未 compile/self-test/运行 validator | 不能称完成或 green；Contract/Manifest/evidence 未闭合，maturity 不提升 |
| 2S immutable snapshots | candidate 已完成，待总控/R02审查 | 只新增 historical Suite/OpenAPI 两个 snapshot 与本计划 ledger | 两个 snapshot 与 `a802490...` blob 逐字相同；Suite tuple/JCS、OpenAPI `18 occurrences / 6 unique targets`、inventory 273 与锁定 SHA 见 16.9 | 仅 immutable snapshot candidate；Manifest 保持 269 未刷新，expected-red 与 maturity 不变；审查通过前不得恢复 Script ownership |
| resumed 3A Script enforcement | 被 2S 审查阻塞 | Suite/Port registries、active-only refresh、snapshot/baseline comparator；`lint_openapi_zero.mjs` 与 `script/package.json` 必写以证明 10 lint/10 bundle | 临时 tree mutation、11 个 historical positive objects 零 diff、历史事实零写入、总控/独立 reviewer 审查 | 指定的 prepare/verifier/redocly/bundle 源 reviewed unchanged；Script 不得成为意义来源，不 finalize Contract、不生成 evidence |
| 2B active Contract deterministic finalize | 未开始 | 只重算 active Suite 自摘要，verify-only historical registry，并刷新含两个 snapshots 的现有 inventory Manifest | Python/Node/JCS 现场独立 count/path/digest；R03 诊断 `273/273/273`；10-document lint/bundle、semantic 与 Suite-aware compatibility focused checkpoint | 11 个 historical positive objects 与全部 historical facts 零传播；若现场结果不是诊断 273，先解释精确差异，禁止硬写 count/digest；active 1.0.1 无 passed/certified fact，semantic constraints 不入 Manifest |
| 3B source binding/evidence generator | 未开始 | 精确 Blueprint/Contract/Manifest/Script/Suite source binding 与 generator/self-tests | supply-chain + generator fail-closed self-tests | 不提前生成最终 evidence；还不是 full Gate |
| 4. 完整 Gate | 未开始 | 待独立授权 | 待冻结后运行一次完整 Gate | 2026-07-27 报告不适用 |
| 5. Handoff | 未开始 | 待独立授权 | 待双版本与 owner diff 审查 | Application lock/实现保持不变 |

### 16.1 阶段 1 实际执行记录

基线与所有权：阶段开始时 HEAD 精确为
`717b0c29e1f3d3062496b01b28d9f9da13d0f2c7`，`a802490...` 为祖先，工作树无 staged、
unstaged 或 untracked 变化。阶段末计划内源差异只有：

- `contract/schemas/agent-runtime-read-bad-request-error.schema.json`；
- `contract/schemas/agent-runtime-read-throttled-error.schema.json`；
- `contract/openapi/agent-runtime-provider-v1.yaml`；
- 本计划的阶段 1 ledger。

实际命令与结果：

| 命令 | Exit | 结果 |
|---|---:|---|
| `git rev-parse HEAD`、`git merge-base --is-ancestor a802490... HEAD`、`git status --porcelain` | 0 | 精确基线、祖先关系、clean worktree 通过 |
| `cd script && .venv/bin/python contract/validation/offline_static_audit.py` | 127 | host 缺少 `script/.venv`，未进入 validator |
| `cd script && .venv/bin/python contract/validation/validate_contracts.py` | 127 | host 缺少 `script/.venv`，未进入 validator |
| `cd script && node contract/validation/lint_openapi_zero.mjs` | 127 | host PATH 无 Node，未进入 validator |
| `docker run --rm ... python:3.14.6-bookworm ... python contract/validation/offline_static_audit.py` | 0 | hash-pinned requirements；通过 668 JSON、15 YAML、9 OpenAPI、5 Markdown |
| `docker run --rm ... python:3.14.6-bookworm ... python contract/validation/validate_contracts.py` | 0 | 244 Schema、293 valid fixture、82 invalid fixture、Strict I-JSON 全部通过 |
| `docker run --rm ... python:3.14.6-bookworm ... python contract/validation/prepare_openapi.py` | 0 | lint 前置投影：236 Registry-backed Schema、9 OpenAPI；只写 ignored `script/build/` |
| `docker run --rm ... node:24.18.0-bookworm ... node contract/validation/lint_openapi_zero.mjs` | 0 | `pnpm@11.15.1` + `@redocly/cli@2.39.0`；9/9 OpenAPI 均 0 error、0 warning |
| `git diff --check`、owner path diff、`Cache-Control` absence、Schema/OpenAPI 结构断言 | 0 | 无空白错误、越界源文件或无权威 header；400 无 Retry-After，429 header required/integer/minimum 1 |

临时 build 输出（均被 `script/.gitignore` 的 `build/` 规则排除，未暂存）：

| 输出 | SHA-256 | 内容摘要 |
|---|---|---|
| `script/build/validation/static.json` | `6286695ad924f5aa57653034fa9e6d4f2a23a12e44507b5ff324504b16afeaec` | 668 JSON / 15 YAML / 9 OpenAPI / 5 Markdown |
| `script/build/validation/contracts.json` | `2f1cd4dc520d9487bb3755ba9ca228b5953cbe58bed69a4f0aac82151d468a23` | 244 Schema / 293 valid / 82 invalid / Strict I-JSON passed |
| `script/build/validation/openapi.json` | `7ae418dbee9cbd592737722bf7651eeea85e9f21287a561c99bc794ff0a45450` | 9 documents / 0 errors / 0 warnings |

偏差与判断：

- host 缺少计划假定的本地 `.venv` 与 Node，且系统 Python 3.9/3.12 不满足锁定的 3.13-3.14；
  未运行 bootstrap、未在仓库安装依赖，改用已有的精确 Python 3.14.6/Node 24.18.0 一次性容器。
- `lint_openapi_zero.mjs` 要求先存在 Registry 投影，因此运行同仓 `prepare_openapi.py` 作为 lint
  前置；它不是额外 Gate lane，只产生 ignored build 输出。
- 400 的固定 message 有第 7.1 节明确 authority，故 Schema 使用 const。第 8 节没有授权 429
  单一 message；Stage 1.1 接受 R02 的有界性澄清，只收窄为非空 string、`maxLength=2000`，不使用
  const。敏感信息与公开 reason vocabulary 留给 Stage 2A/3A/2B semantic/fixture/validator closure。

剩余风险与成熟度：现有 `offline_static_audit.py`、`validate_contracts.py` 尚未结构化断言两个新
Schema 的 code/retryable、429 required Retry-After、两操作 precedence/admission/retry 扩展，也
没有 Stage 2A/3A/2B 正反向 fixture/semantic/Suite/Manifest 绑定；Redocly 只证明 OpenAPI 结构与 lint。
因此上述 green 只是阶段 1 focused checkpoint，不是 C01 authority closure、完整 Contract Gate、
Provider conformance、Application 实现或任何 maturity 提升。

停止条件复核：未发现 C01 专属 Cache-Control authority；无需修改 descriptor Schema、公共
`standard-error`、Claims、state machine、Event Registry、Script 或 Application；429 可以在
operation 识别和 caller/token/descriptor binding 后、provider-local state read 前闭合，且不依赖
Run 是否存在。阶段 1 无停止条件触发。

### 16.2 阶段 1.1 R02 纠偏实际执行记录

基线与所有权：纠偏开始和结束时 HEAD 均精确为
`717b0c29e1f3d3062496b01b28d9f9da13d0f2c7`，`a802490...` 为祖先；暂存区始终为空。开始时
工作树只含已经总控与 R02 只读审查的四个 Stage 1 计划内路径，Stage 1.1 没有撤销这些改动，也
没有把写入扩到 descriptor Schema、公共 `standard-error`、semantic/Suite/Manifest、Script、
Application 或 evidence source。

R02 findings 与处置：

- 接受 P1-1。先在本计划第 1.1 节固定封闭键集，再为两个 GET operation 加入精确
  `x-runtime-read-http-authority` 并同步 description。它结构化覆盖 operation 识别边界、单 path
  segment 与禁止等价化、Status query/body/framing 拒绝、Events query/default/lexical/range、
  descriptor digest mismatch 403；不修改 descriptor Schema。
- 接受 P1-2。为两个 operation 加入封闭 `x-runtime-read-retry`，为专用 400/429 response 加入
  封闭 `x-runtime-read-header-authority`；明确 fresh Attempt/token/non-stale fencing、新 digest 不复用、
  caller 至少等待、Events cursor 不推进、adapter auto retry 与 mutation replay 均禁止。400 显式
  禁止 Retry-After；429 缺失/重复/非法/不安全解析均为 invalid response 且不得重试。
- 接受 P2 clarification。throttled Schema 的 message 不固定单一文案，只增加 `minLength=1` 与
  `maxLength=2000`。message/details/violations 敏感信息排除、公开 reason vocabulary，以及 400
  details/violations 仍由 Stage 2A/3A/2B semantic、正反向 fixture 和 validator 闭合，本阶段不声称证明。

Stage 1.1 实际命令与结果：

| 命令 | Exit | 结果 |
|---|---:|---|
| `git rev-parse HEAD`；`git merge-base --is-ancestor a802490... HEAD`；`git status --short`；`git diff --cached --name-only` | 0 | 精确基线、祖先关系、四路径 owner diff、空暂存区通过 |
| `git diff --check`；JSON parse；owner path 与 `Cache-Control` absence 检查 | 0 | 无 whitespace error、越界路径、JSON 解析错误或新增 Cache-Control |
| `docker run --rm -v /Users/echo/.codex/worktrees/65b0/agent:/workspace -w /workspace/script python:3.14.6-bookworm sh -lc 'python -m pip install --require-hashes -r requirements-contracts.txt; ...'` | 0 | 临时安装 hash-pinned requirements；YAML/JSON 递归 equality 断言精确匹配第 1.1 节三个封闭 authority、response 集合、error Schema 与 header 规则 |
| 同一 Python 3.14.6 容器：`python contract/validation/offline_static_audit.py` | 0 | 668 JSON、15 YAML、9 OpenAPI、5 Markdown |
| 同一 Python 3.14.6 容器：`python contract/validation/validate_contracts.py` | 0 | 244 Schema、293 valid fixture、82 invalid fixture、Strict I-JSON passed |
| 同一 Python 3.14.6 容器：`python contract/validation/prepare_openapi.py` | 0 | 236 Registry-backed Schema、9 OpenAPI；只写 ignored `script/build/` |
| `docker run --rm -v /Users/echo/.codex/worktrees/65b0/agent:/workspace node:24.18.0-bookworm sh -lc 'corepack prepare pnpm@11.15.1 --activate; ...; pnpm add --save-dev --ignore-scripts @redocly/cli@2.39.0; node contract/validation/lint_openapi_zero.mjs'` | 0 | 在容器 `/tmp/script` 安装依赖并复制未修改 lint script；仓库无 node_modules；9/9 OpenAPI 均 0 error、0 warning |
| `shasum -a 256 script/build/validation/{static,contracts,openapi}.json`；`git check-ignore -v ...` | 0 | 三份输出摘要已复核，均由 `script/.gitignore` 的 `build/` 规则排除 |

Stage 1.1 刷新后的临时 build 输出：

| 输出 | SHA-256 | 内容摘要 |
|---|---|---|
| `script/build/validation/static.json` | `6286695ad924f5aa57653034fa9e6d4f2a23a12e44507b5ff324504b16afeaec` | 668 JSON / 15 YAML / 9 OpenAPI / 5 Markdown |
| `script/build/validation/contracts.json` | `2f1cd4dc520d9487bb3755ba9ca228b5953cbe58bed69a4f0aac82151d468a23` | 244 Schema / 293 valid / 82 invalid / Strict I-JSON passed |
| `script/build/validation/openapi.json` | `7ae418dbee9cbd592737722bf7651eeea85e9f21287a561c99bc794ff0a45450` | 9 documents / 0 errors / 0 warnings |

三个 digest 与 Stage 1 相同，因为当前报告只记录文档/fixture 计数和 lint totals，而这些 totals 在
Stage 1.1 没有变化；文件已由本轮命令实际覆盖和重新计算，不能据相同 digest 推断新增 authority
已被现有 Script 检查。

偏差、剩余未闭合边界与停止条件：本轮没有重复执行预期必然 exit 127 的 host `.venv`/Node 命令，
直接复用 Stage 1 已记录的环境偏差与精确一次性容器。最终 Node refresh 的第一次尝试发生 Corepack
网络下载失败；该 shell 未设置 fail-fast，随后 fallback 到非锁定 pnpm 并返回 0，因此整次结果主动
作废。随后以 `set -eu`、前后两次 `pnpm --version == 11.15.1` 和
`@redocly/cli == 2.39.0` 断言重跑，exit 0，才接受 9/9 lint 结果。现有 Script 仍没有 C01 专属
fail-closed validator，递归 equality 断言只是本阶段 focused review check，不是 Script authority
closure；Stage 2A 仍需形成 semantic/fixture/Suite draft，Stage 3A 实现 enforcement，Stage 2B
finalize digest/八文件传播/Manifest/compatibility，Stage 3B 再固化 source binding/evidence generator。
未发现 C01 专属 Cache-Control authority，也无需扩大到 descriptor Schema 或其他禁止路径；未触发
停止条件。没有运行 full Gate，没有暂存或提交，所有 maturity 上限保持不变。

### 16.3 阶段 1.2 R02 二次纠偏实际执行记录

基线与所有权：开始和结束时 HEAD 均精确为
`717b0c29e1f3d3062496b01b28d9f9da13d0f2c7`，`a802490...` 为祖先；暂存区始终为空，源差异
始终只含两个新 error Schema、Runtime OpenAPI 和本计划。没有撤销已验收改动，也没有触碰
descriptor/`standard-error`/semantic/Suite/Manifest/Script/Application/evidence。

R02 二次 findings 与处置：

- 接受 P1 Events body/framing。计划先固定与 Status 逐键一致的五键 `body` 对象；OpenAPI 随后在
  Events authority 的 `query` 与 `descriptor-digest-mismatch` 之间加入该对象，并同步 description，
  明确只有 operation 精确识别后的拒绝才是 C01 400。
- 接受 P1 Retry-After wire lexical grammar。计划先固定 `^[1-9][0-9]*$` 和稳定有序的八项
  `rejected-lexical-forms`；OpenAPI 随后逐键同步。pattern 约束单个原始 header field value，Header
  Object 的 integer/minimum 只约束解析值，`unsafe-parse` 继续覆盖 overflow/不安全解析。400
  authority 保持只有 `presence: forbidden`。
- Stage 3A validator 责任同步收紧为封闭键集、数组顺序和 raw wire value fail closed；不能解释
  `canonical-*` prose/枚举来替代精确对象。本阶段没有修改 Script。

Stage 1.2 实际命令与结果：

| 命令 | Exit | 结果 |
|---|---:|---|
| `git rev-parse HEAD`；`git merge-base --is-ancestor a802490... HEAD`；`git status --short`；`git diff --cached --name-only` | 0 | 精确基线、祖先关系、四路径 owner diff、空暂存区通过 |
| Python 3.14.6 容器内 YAML parse + Stage 1.2 plan fenced YAML/OpenAPI recursive equality、键序与数组序断言 | 0 | Events/Status body 完全相等；429 header authority 与有序八项 lexical reject 完全相等；400 authority 未扩张；description 边界存在 |
| `docker run --rm ... python:3.14.6-bookworm ... python contract/validation/offline_static_audit.py` | 0 | 668 JSON、15 YAML、9 OpenAPI、5 Markdown；ledger 完成后再次刷新同一最终 source，仍为 exit 0 |
| 同一 Python 3.14.6 容器：`python contract/validation/validate_contracts.py` | 0 | 244 Schema、293 valid fixture、82 invalid fixture、Strict I-JSON passed |
| 同一 Python 3.14.6 容器：`python contract/validation/prepare_openapi.py` | 0 | 236 Registry-backed Schema、9 OpenAPI；只写 ignored `script/build/` |
| `docker run --rm ... node:24.18.0-bookworm ... pnpm@11.15.1 ... @redocly/cli@2.39.0 ... lint_openapi_zero.mjs` | 0 | 前后断言 pnpm 11.15.1、Redocly 2.39.0；临时 `/tmp/script` 安装；9/9 OpenAPI 均 0 error、0 warning |
| `git diff --check`；owner path/empty staged/`Cache-Control` absence；`shasum -a 256`；`git check-ignore -v` | 0 | 无 whitespace error、越界源文件、暂存内容或 Cache-Control；三份输出被 `script/.gitignore` 排除 |

Stage 1.2 刷新后的临时 build 输出：

| 输出 | SHA-256 | 内容摘要 |
|---|---|---|
| `script/build/validation/static.json` | `6286695ad924f5aa57653034fa9e6d4f2a23a12e44507b5ff324504b16afeaec` | 668 JSON / 15 YAML / 9 OpenAPI / 5 Markdown |
| `script/build/validation/contracts.json` | `2f1cd4dc520d9487bb3755ba9ca228b5953cbe58bed69a4f0aac82151d468a23` | 244 Schema / 293 valid / 82 invalid / Strict I-JSON passed |
| `script/build/validation/openapi.json` | `7ae418dbee9cbd592737722bf7651eeea85e9f21287a561c99bc794ff0a45450` | 9 documents / 0 errors / 0 warnings |

digest 再次相同是因为三份报告只保存数量/totals，Stage 1.2 没有改变这些值；不能据此声称现有
Script 已检查新 authority。第一次 equality 工具调用因 Markdown fence 与调用封装的反引号冲突，
在 Docker 启动前即失败，无 validator exit 或仓库写入；改用 Python `chr(96)` 构造 fence 后，
完整命令 exit 0。

剩余风险与成熟度：现有 Script 不检查 Events body 键集、Retry-After raw lexical pattern 或有序
reject vocabulary；Stage 2A 先形成未提交 authority draft，Stage 3A 才实现 validator/refresh/
comparator enforcement，Stage 2B 才能 finalize semantic、正反向 fixture、Suite 1.0.1/digest、八文件
传播与 Manifest/compatibility，Stage 3B 再完成 source binding/evidence generator。
focused equality/validator/Redocly green 不构成 authority closure、完整 Gate、Provider conformance、
Application 实现或 maturity 提升。未触发停止条件，未运行 full Gate，未暂存或提交。

### 16.4 阶段 2.0 readiness/topology 修订实际记录

基线与 owner：开始时 HEAD 精确为
`793215cbe1b79c0f4cb7f16b13ec71b9483920fd`，工作树与暂存区干净，`a802490...` 为祖先。
本阶段唯一写入是本计划 Markdown；没有修改 Schema/OpenAPI/fixture/semantic/Suite/Manifest、Script、
Application、dependency lock 或 evidence，也没有运行任何生成/refresh/Gate 命令。

只读命令与结果：

| 命令 | Exit | 结果 |
|---|---:|---|
| `git rev-parse HEAD`、`git merge-base --is-ancestor a802490... HEAD`、`git status --porcelain`、`git diff --cached --name-only` | 0 | 精确 Stage 1 commit、祖先关系、初始 clean worktree/空暂存区通过 |
| `rg/sed/nl/wc` 定向读取五个 Script、两个 Manifest verifier、Runtime Suite 与当前 Manifest | 0 | 未执行被审计代码；确认真实控制流、CLI 和 inventory 边界 |
| Python AST 只读统计 `KNOWN_CONTRACT_CHECKS` 与 literal `mark_checks` | 0 | 167 known、166 marked；`runtime_read.http_authority` 在两者均为 false |
| 定向读取 semantic traceability fail-closed 分支 | 0 | unknown check 与 known-but-unexecuted check 都抛出 AssertionError；Stage 2A mapping 在 Stage 3A 前不能 green |
| 定向读取 comparator `baseline_resources/compare` 与最终输出 | 0 | 只比较 Manifest inventory 的 Schema/OpenAPI/state-machine wire 行为；无 Runtime Suite compare 或 `requires recertification` 结果 |
| `wc -l` + `rg` refresh helper | 0 | 5629 行、280 个 `write()` 调用点；入口重算七套 Suite并广泛写 fixture；无 C01 guard |
| Python JSON + 独立 inventory path-set 只读断言、定向读取 Python/Node verifier | 0 | declared count=269、listed length=269；未变 roots 的 Python/Node discovered 都为 271 且集合相等；Manifest 唯一缺少两个 Stage 1 error Schema，无 stale-only path；Runtime Suite 在 inventory，semantic constraints 不在；Python 有 `--print-values`/`--refresh`，Node 只核验 |
| `shasum -a 256` 七个 readiness Script 文件 | 0 | 摘要与 11 节 Stage 2.0 evidence table 一致 |
| `git diff --check`、owner path、empty staged | 0 | 阶段末只允许本计划未提交 Markdown diff；无 whitespace/staged/越界变化 |

拓扑决策：旧 Stage 2 同时要求新增 unknown semantic mapping、立即执行 semantic、运行无 guard broad
refresh，并调用不具备 Suite 语义的 comparator，执行上自相矛盾。修订后固定为单 writer 串行
`2A Contract draft -> 总控审查 -> 3A Script enforcement -> 总控审查 -> 2B Contract finalize ->
总控审查 -> 3B source binding -> frozen Stage 4`。2A/3A/2B 可以保留在同一未提交工作树，但禁止
提交任何 known-red intermediate；最终 semantic/compatibility 仍必须真实执行，没有被删除或弱化。

R02 对 Stage 2.0 plan-only 的 findings 与处置：

- 接受 P1。原计划把 Manifest 写成笼统“当前 269 resources”，没有区分声明/列举与现场 discovered
  inventory。只读断言确认 declared=269、listed=269、Python/Node discovered=271，唯一缺失路径为
  两个 Stage 1 新 error Schema；已将其登记为 Stage 1 既存 drift，并同步 2A expected-red、2B
  preflight/final 271 + path-set/JCS 证明、停止条件和 ledger。若实施时 discovered 不再是 271，先
  解释精确路径变化，绝不硬写 count。
- 接受 P2。首页已改为 Stage 1/1.1/1.2 在 `793215c...` 修改机器 Contract 并经总控/R02 验收，
  当前仅 Stage 2.0 plan-only 未提交；第 1/3 节的“缺 400/429”改为 Stage 0 历史基线事实。历史阶段
  ledger 保持原样，不把历史执行记录改写为当前状态。

Stage 2.0 non-goals：不实现 Script 能力、不创建 Stage 2A fixture/Suite draft、不刷新 digest/Manifest、
不生成 evidence、不运行 full Gate、不提交。当前 maturity 与 Stage 1 后完全相同，Stage 2A 尚未授权。

### 16.5 阶段 2A Contract authoritative draft 实际记录

基线与 owner：开始时 HEAD 精确为
`ba5ff1d624a7019e118cbbfc964d7ecd33decea6`，`a802490...` 为祖先，工作树和暂存区干净。本阶段
只有一个 Contract writer，实际写入精确为：

- `contract/examples/contracts/agent-runtime-read-bad-request-error.json`；
- `contract/examples/contracts/agent-runtime-read-throttled-error.json`；
- `contract/tests/invalid/agent-runtime-read-bad-request-retryable.json`；
- `contract/tests/invalid/agent-runtime-read-throttled-not-retryable.json`；
- `contract/semantic-constraints-v1.json`；
- `contract/conformance/runtime/v1/suite.json`；
- 本计划的 Stage 2A ledger。

实际变更：两个正例只含公开的 `code/message/retryable/trace_id`，不含可识别 target、credential、
mTLS identity、Provider state 或跨租户数据；两个反例分别只翻转对应正例的 `retryable`。semantic
traceability 保留既有 496 个 constraint 和 `critical_schema_ids` 顺序，在尾部追加稳定 ID
`sem-05ee41967cf0b073`、`sem-610d8569f7bda04c`，二者唯一的 Contract Gate check 均为
`runtime_read.http_authority`，并分别绑定 400/429 两个新 Suite case。Runtime Suite 只把
`suite_version` 改为 `1.0.1`，在 `typed-event-payloads` 与 `cursor-resume` 之间依次加入 Status 400、
Event 400、Status 429、Event 429；其他 profile、既有 test 对象和相对顺序不变。`suite_digest` 故意
保留旧 `sha256:9ef6d50d...` 作为 stale placeholder，等待 Stage 2B guarded finalize。

只读/focused 命令与结果：

| 命令/断言 | Exit | 结果 |
|---|---:|---|
| `git rev-parse HEAD`、`git merge-base --is-ancestor a802490... HEAD`、初始 `git status --porcelain`、cached name-only | 0 | 精确 Stage 2.0 commit、祖先、初始 clean/empty staged 通过 |
| Python `json.loads` 六个机器 Contract 文件 | 0 | 两正例、两反例、semantic traceability、Runtime Suite 均为合法 JSON |
| Python fixture 精确字段与单因子 diff 断言 | 0 | 两正例满足 Stage 1 code/message/retryable/trace 边界；两个负例各自只改变 `retryable` |
| Python base/current Suite profile/test 对象比较、ID/顺序/唯一性断言 | 0 | `1.0.1`、四 profile、runtime-core 21 case；四个新 case 顺序正确，全部既有 case 相对顺序和内容不变，全局 ID 唯一；旧 digest 明确 stale |
| Python semantic base-prefix、稳定 ID hash、enforcement/check/Suite reference 与唯一性断言 | 0 | 496 个既有 constraint 不变，新增 2 个稳定条目；`runtime_read.http_authority` 两次映射到两个 error Schema，四个 phase0 check 均解析到本次 Suite case |
| Python/Node inventory roots 与 Manifest path-set 只读断言 | 0 | declared/listed=269、双方 discovered=271，仍只缺 Stage 1 两个 error Schema；Stage 2A 未新增 inventory path |
| 首次合并 owner shell 断言 | 1 | 内容断言均已先通过；最后使用 `git diff --name-only` 比较六路径时，Git 按设计不列出四个 untracked fixture。没有文件写入或 authority 偏差，该 owner 检查结果作废 |
| 改用 `git status --porcelain=v1 -uall` 联合 tracked base diff 的完整 owner 断言 | 0 | 精确 6 个机器 Contract 路径：tracked=2、untracked=4、staged=0；新文件 newline/尾随空白检查通过 |
| 最终 `git diff --check`、完整七路径 owner/status 与 empty staged | 0 | 无 whitespace、越界 writer 或暂存内容；未执行任何禁止 lane |

Expected-red 与未闭合边界：当前 Script 的 KNOWN/EXECUTED checks 仍没有
`runtime_read.http_authority`，本轮没有运行 `validate_semantics.py`，不能声称 semantic green。Suite
digest 仍旧；八个 `1.0.1` version/digest 传播文件和 Manifest 未更新；Manifest 继续 declared/listed
269 对 discovered 271；现有 comparator 仍不读取 Suite version/digest/profile/有序 test set，也不能
输出 `requires recertification`。新增正反 fixture 尚未由 Stage 3A 注册，OpenAPI authority 也尚未由
长期 Script fail closed。没有运行 refresh helper、Manifest refresh/verify、semantic validator、
compatibility comparator、full Gate 或 evidence generator。

停止、回滚与 maturity：未发现必须修改本阶段 owner 之外 Schema/OpenAPI/Script/Application 的情况，
没有停止条件触发。总控拒绝 draft 时，可删除四个新 fixture，并把 semantic、Suite 与本 ledger 回退到
`ba5ff1d...`；这不删除旧 Revision、不改 durable fact。四个新 case 仅为 contract-defined、
implementation-not-assessed；`runtime-core-v1`、0B、0C-0G、0H、freeze、security/production 均不提升。

原拟 Stage 3A handoff 已被 R02 两个 P1 阻断并由 16.6 取代。Contract writer 继续持有 ownership；
在本 plan-only correction 经总控/R02 通过、下一机器修订按第 2A 节收紧四个 Suite case、且该机器
diff 再次只读审查通过前，不得释放 Contract ownership 或修改任何 Script。

### 16.6 R02 Stage 2A findings 与 plan-only 处置

R02 task `019fc56d-b49d-7a51-ae01-491f34587e44` final 结论为“Stage 2A draft 暂不可移交
Stage 3A”，包含两个 P1。本子阶段只修订本文，六个机器 Contract 文件完全不变。

P1-1 处置：采用 Contract-owned supplemental preservation。R02 明确确认当前 validator 对所有 entry
先检查 enforcement，但只对 `critical_schema_ids` 与 Schema `x-semantic-constraints` 做 source
alignment；因此 Stage 3A 注册并真实 mark check 后，两个 supplemental entry 可以合法通过，它们并非
因不在 critical list 而非法。真实缺口是现有 normal broad regeneration 只从 Schema 重建并整体覆盖
semantic 文件，会静默删除 supplemental。本文已同步 10.1/10.2、Stage 3A 步骤/self-test、停止条件与
rollback：两条 refresh 路径都必须从当前 Contract 原样保留 ordered objects，并对 stable ID、Schema
resolution、全局 ID/`(schema_id,index)` collision、enforcement/reference、registered+executed check
fail closed；Script 不得复制 statement 成为权威。若无法在不让 Script 成为事实源的前提下做到，立即
停止并报告，不回改两个 Stage 1 Schema。

P1-2 处置：本文 Stage 2A correction 已为下一机器修订固定四个 case 的完整可执行边界。Status/Event
400 分别覆盖 recognized-operation 下全部 path/runtime_run_id/query/body/framing 拒绝、403 digest
mismatch、Event 400/410 区分、无 Retry-After、专用 body 与公开有界/no-sensitive diagnostics；
Status/Event 429 分别覆盖合法 429 和 missing/repeated/noncanonical/unsafe/zero/negative header 负向
矩阵、admission/state/existence precedence、fresh Attempt/token/fencing/digest、minimum wait、logical
target 或 cursor/limit 稳定、no cursor advance、no auto-retry/no mutation replay 及 diagnostics。
本子阶段没有修改 Suite；下一机器修订与复审完成前该 P1 仍未在机器 Contract 中关闭。

本轮只读门禁与结果：

| 命令/断言 | Exit | 结果 |
|---|---:|---|
| R02 task final 只读复读 | 0 | 精确取得两个 P1、validator critical/supplemental 区分及 broad helper 覆盖风险 |
| HEAD/ancestor、`git status --short -uall`、cached name-only | 0 | HEAD 精确 `ba5ff1d...`、`a802490...` 为祖先、初始/最终均精确七路径、暂存区为空 |
| 首次六摘要多行 shell 变量比较 | 1 | 即时逐路径 `shasum -a 256` 输出仍与预期六摘要完全相同；失败来自比较包装器而非文件漂移，无文件写入，该结果作废 |
| 逐路径 `shasum -a 256` 与 Python `hashlib` path-to-digest 映射断言 | 0 | 四 fixture、semantic、Suite 摘要与 Stage 2A 审查输入完全相同；唯一额外 diff 是本文 |
| 首次 Markdown content 字面断言 | 1 | 仅因断言错误要求整个 stable-ID 公式连同说明都位于同一 inline-code token；计划实际公式与语义完整，无文件写入，该结果作废 |
| 修正后的 Markdown owner/content 断言、`git diff --check` | 0 | supplemental preservation、四 case 边界、Stage 3A self-test、stop/rollback/maturity 与本 ledger 均存在，无越界/whitespace |

状态仍为 expected-red、未暂存、未提交：`runtime_read.http_authority` 仍 unknown/unexecuted，Suite
digest 仍 stale，八传播/Manifest/comparator 未闭合；四 case 机器描述仍待下一修订。没有运行或修改
任何 validator/refresh/Gate/Script/Manifest/Application/evidence。四 case 仍只是 contract-defined /
`phase0_implementation_required`；plan correction 与未来 Stage 3A self-test 都不构成 Provider passed。

下一步只能在总控/R02 通过本 plan-only diff 后，继续由 Contract writer 做最窄机器修订：只修改
`contract/conformance/runtime/v1/suite.json` 的四个新增 case description 与本计划 correction ledger，
保持 suite version、stale digest、四 case ID/category/evidence type/顺序、其他 profile/test、semantic、
fixture、Schema/OpenAPI、Manifest、Script 和所有下游文件不变；仍不暂存、不提交，完成后再次只读审查。

### 16.7 Stage 2A correction 四 description 机器修订

总控与 R02 批准 16.6 plan-only 决策后，Contract writer 在同一未提交工作树继续持有 ownership。
入口 HEAD 精确为 `ba5ff1d624a7019e118cbbfc964d7ecd33decea6`，`a802490...` 为祖先；状态精确
七路径且暂存区为空。入口计划 SHA-256 为
`364041ea08cd66ec49dc1cd271e729bd40112ffbe456f648701e408fe877ffc7`，Runtime Suite SHA-256 为
`0f5f93ec0f96501e57e07779ee3ea125b216f035a87c0632206e2639aa889b64`，均与授权输入一致。

本轮机器 Contract 只替换 Runtime Suite 四个既有新增 case 的 `description`：

- Status 400 在 listener 已识别精确 route/method 并隔离 path slot 中 raw `runtime_run_id` candidate 后，
  覆盖 single segment/1..200 与禁止 case-fold/Unicode normalize/slash collapse/dot-segment/encoded-separator
  等价化、全部 query、body/framing 拒绝；unknown route、route-shape mismatch 与 operation 识别前 parser
  failure 明确为 `c01-out-of-scope` 且不能作为 case evidence；同时固定 digest mismatch 403、无
  `Retry-After`、专用 body 与公开有界无敏感/跨租户 diagnostics；
- Event 400 使用相同的 listener/raw candidate/out-of-scope 与 path/body/framing 边界，并展开 query
  allowlist、multiplicity/order/default equivalence、canonical unsigned ASCII decimal、percent encoding 与
  两个范围；固定 malformed/out-of-range 400、合法 retention expiry 410、digest mismatch 403、无
  `Retry-After`、专用 body/diagnostics；
- Status 429 展开 operation/caller-token-descriptor/Attempt/fencing binding 后、provider-local state 前且与
  Run existence 无关的 admission；专用 body；exactly-one raw `Retry-After` 的 lexical/safe-value 正向及
  missing/repeated/noncanonical/unsafe/zero/negative invalid-response/no-retry 矩阵；minimum wait、fresh
  Attempt/token、non-stale fencing、重算 digest、logical target 不变及 adapter no auto-retry/no mutation replay；
- Event 429 保持相同 admission/header/body/fresh retry 边界，并固定 cursor/limit 不变且不 advance；
- 四条 description 均明确 `contract-defined` / `phase0_implementation_required` 且不声称 Provider passed。

只读/focused 验证与结果：

| 命令/断言 | Exit | 结果 |
|---|---:|---|
| HEAD/ancestor、入口七路径、cached name-only、计划/Suite SHA | 0 | 精确匹配授权输入，暂存区为空 |
| Python JSON parse 与四 case description content 断言 | 0 | 四条分别包含第 2A 节固定的完整 400/429 正负向边界 |
| 修改前后 Suite description-only 递归断言 | 0 | 将四 description 归一化后的 canonical JSON SHA-256 前后均为 `4680095a532ad165eab5716dca6dc0df0bcbb8d0d28d87fb5113afbfab93f255`；`suite_version=1.0.1`、旧 `suite_digest`、四 ID/category/evidence type/顺序、其他 profile/test 完全不变 |
| 四个 fixture 与 semantic SHA-256 断言 | 0 | 分别仍为 `914249c...`、`b35813d...`、`65d216e...`、`44f25ad...`、`e7583af...`，未发生漂移 |
| Python/Node inventory roots 与 Manifest path-set 内联只读断言 | 0 | declared/listed=269、双方 discovered=271，唯一缺失仍是 Stage 1 两个 error Schema |
| 最终七路径 owner、empty staged、`git diff --check` 与四个 untracked fixture newline/尾随空白断言 | 0 | 无越界 writer、暂存内容或 whitespace；Suite 新 SHA-256 为 `95e54466749b0b107bf4569274493a34ee3eff0829bb03943ff51a6dd67a7df7` |

Expected-red 保持不变：`runtime_read.http_authority` 尚未由 Script 注册/真实执行，Suite digest 是明确的
stale placeholder，八个传播文件、Manifest 271 finalize、Suite-aware comparator 与 source-bound evidence
均未闭合。本轮未运行任何仓库 validator、refresh、Manifest verify/refresh、comparator、Gate 或 evidence
generator；四 case 仍只是 contract-defined / implementation-not-assessed，不提升任何 maturity。

若总控/R02 拒绝本候选，rollback 只把四个 description 精确恢复到本轮入口文本并撤销本节/status
ledger，使 Suite 回到入口 SHA-256 `0f5f93ec...`；semantic、fixture、Schema/OpenAPI、Script、Manifest、
Application/evidence 均不得触碰。当前 Contract ownership 在最终机器复审前不释放；只有复审明确通过后
才允许串行移交 Stage 3A，当前不得暂存、提交或声称 Contract green。

R02 最终机器审查随后确认唯一 P1：两条 400 description 在 “exactly recognized operation” 后又使用
“every invalid path shape”，会让 unknown route 或 operation 识别前 parser failure 是否能作为 400 case
evidence 产生歧义。最窄纠偏只再次替换 Status/Event 400 两个 `description`：先要求 listener 已识别
精确 route/method 并隔离其 path slot 中 raw `runtime_run_id` candidate，再对 candidate、各自 query、
body/framing 做 400 分类；unknown route、route-shape mismatch 与识别前 parser failure 明确为
`c01-out-of-scope` 且不能满足 case。两条 429 及所有其他 Suite 对象保持只读。

本次纠偏只读验证与结果：

| 命令/断言 | Exit | 结果 |
|---|---:|---|
| HEAD/ancestor、七路径、cached name-only、入口 Suite/计划 SHA | 0 | 精确匹配 `ba5ff1d...`、`95e5446...`、`2350594...`，暂存区为空 |
| Python JSON 与两条 400 content 断言 | 0 | 不再含笼统 `every invalid path shape`；精确包含 listener/route/method/raw candidate、`c01-out-of-scope`、不能满足 case 及原有 query/body/framing/403/410/header/body/diagnostic/maturity 边界 |
| 首次手写 429 description 摘要断言 | 1 | 前像重建与 400 content 已先通过；手写的两个 expected digest 值错误，实际文件未漂移且无写入，该结果作废 |
| 从入口 `95e5446...` 前像递归比较 | 0 | 只把两条 400 description 替回入口文字即可逐字重建入口 Suite SHA；归一化两条 400 后全部 Suite 对象递归相等，两条 429 完整对象不变 |
| semantic/四 fixture SHA、inventory 269/271 exact-two-schema、最终七路径/empty staged/`git diff --check`/untracked whitespace | 0 | 无越界写入或 Manifest drift；最终 Suite SHA-256 为 `cc9bb28419790d77cfbbc44e193a897a978b3ff99f7c1641eb46d20f6386432b` |

Expected-red 与 maturity 上限仍与上文完全相同，且本纠偏未运行 validator、refresh、Manifest verifier、
comparator、Gate 或 evidence generator。若仅拒绝本次 R02 纠偏，rollback 只恢复这两条 400 description
与本段/status，使 Suite 回到 `95e5446...`，不得触碰已审查的两条 429 或 semantic/fixture；若拒绝整个
四 description 候选，才适用上文恢复到 `0f5f93ec...` 的整体 rollback。再次最终复审明确通过前，
Contract ownership 不释放，不得暂存、提交、移交 Stage 3A 或声称 Provider passed。

最终 handoff：总控与 R02 task `019fc56d-b49d-7a51-ae01-491f34587e44` 已确认“未发现阻断项。
Stage2A draft 最终通过，可释放 Contract ownership 并移交 Stage3A”。本 ledger 的精确输入为 Runtime
Suite SHA-256 `cc9bb28419790d77cfbbc44e193a897a978b3ff99f7c1641eb46d20f6386432b` 与计划
SHA-256 `be58bb9ad4ef82494080e35fb098bf6efccc52a34332d777375c2a580775ad03`；semantic 与四 fixture
摘要仍与上表一致。该结论只关闭 Stage 2A 审查与 ownership handoff，不关闭 expected-red：
`runtime_read.http_authority` 尚未注册/真实执行，Suite digest、八传播、Manifest 271 finalize、
Suite-aware comparator 与 source-bound evidence 仍未完成；四 case 仍是 contract-defined /
implementation-not-assessed，所有 maturity 上限不变。

本 handoff ledger 完成后，plan/Contract writer 停止写入并释放 ownership。下一写域严格只有 Stage 3A
Script writer 的以下五个文件：

- `script/contract/validation/offline_static_audit.py`；
- `script/contract/validation/validate_contracts.py`；
- `script/contract/validation/validate_semantics.py`；
- `script/contract/maintenance/refresh_example_digests.py`；
- `script/contract/compatibility/check_contract_compatibility.py`。

Stage 3A 全程只读锁定当前七个 Contract 路径：

- `contract/conformance/runtime/v1/suite.json`；
- `contract/doc/plan/C01-runtime-status-event-http-authority-patch.md`；
- `contract/semantic-constraints-v1.json`；
- `contract/examples/contracts/agent-runtime-read-bad-request-error.json`；
- `contract/examples/contracts/agent-runtime-read-throttled-error.json`；
- `contract/tests/invalid/agent-runtime-read-bad-request-retryable.json`；
- `contract/tests/invalid/agent-runtime-read-throttled-not-retryable.json`。

不得写任何其他 Contract/Manifest/Application/evidence。Stage 3A 尚未执行，只有 Script writer 实际
取得 ownership 后才可开始；Contract 只读输入发生任何漂移即触发停止并返回总控。

### 16.8 Stage 3A authority/identity closure 停止与双 snapshot plan-only correction

停止结论：Stage 2A 经总控/R02 最终通过后，Script writer 曾串行取得 Stage 3A ownership，但在
refresh/comparator 实现前的 original-ID 临时树诊断中触发第 12 节停止条件。临时 candidate 保持原
ProviderRevision、AdmissionDecision、Capabilities、Checkpoint、Compatibility、Run 与 evidence ID，
只模拟 active Suite `1.0.1` 自摘要、原计划固定消费者的 version/digest 及现有维护规则要求的同文件摘要
字段。表面 diff 可限制为 active Suite 加原固定八文件，但 ProviderRevision 内容摘要会从历史
`sha256:3a68cf38...a4cd` 重算为诊断 `sha256:f964eda...69f3a`；同一
`provider_revision_id` 的 `contract/examples/contracts/agent-runtime-admission-decision.json` 仍引用旧
摘要，因此它成为精确第九路径。继续更新会改变 AdmissionDecision digest，并沿反向引用扩展到：

- `contract/examples/contracts/business-settlement-envelope.json`；
- `contract/examples/contracts/canonical-event-compatibility-decided.json`；
- `contract/examples/contracts/child-run-manifest-v2.json`；
- `contract/examples/contracts/run-manifest-no-sandbox.json`；
- `contract/examples/contracts/run-manifest-v2.json`；
- `contract/examples/contracts/technical-usage-entry.json`；
- `contract/examples/contracts/usage-report.json`。

这证明原固定 ID 传播与历史 identity/digest closure 不可同时满足；不得扩大 allowlist、弱化闭包或
通过新临时 ID 获得假绿。总控接受停止结论，采用第 2.1、9--13 节双 snapshot 与 historical zero-
propagation 决策。R03 随后独立确认 historical OpenAPI 为 18 次 external ref / 6 个唯一 target，active
OpenAPI 为 20 次 / 8 个唯一 target；snapshot 后 Manifest 诊断为 `273/273/273` 与第 2.1 节摘要，且
11 个 historical positive objects 必须逐字零 diff，active `1.0.1` 不得有 passed/certified fact。所有
诊断值仍须 Stage 2S/2B 从现场字节独立重算，不能作为硬编码成功常量。

partial Script 状态：只产生以下三个未暂存、未验收、未完成文件；本 plan-only correction 全程只读，
未 compile、未 self-test，也未运行其正常入口：

| 文件 | 锁定 SHA-256 |
|---|---|
| `script/contract/validation/offline_static_audit.py` | `e842944f97373e9028bb0b767d08227c52c3b2a1fdbdf10dd639e1c777b7c7da` |
| `script/contract/validation/validate_contracts.py` | `09bc93420ec8ad0edce5bc8123fe27312c285132fc47bd962295f3f648006f51` |
| `script/contract/validation/validate_semantics.py` | `618480d80cf55b806fe0242d64cad7f268b41a4aa3fa47a965c52397521a7f36` |

`refresh_example_digests.py` 与 comparator 始终保持基线 SHA-256
`2d37d4606807527c73f56f77fc69c18724114abe7ddff87cc4799a3b4208fe85`、
`f4d8ed6dabb1fe64648b3eadbf675f39cd8e4132cc3028d673515c803e8d707d`。本轮没有继续实现任何 partial
Script。resumed Stage 3A 的 writer 修订为原五个 Script 加必写的
`script/contract/validation/lint_openapi_zero.mjs` 与 `script/package.json`；10.2 列出的
`prepare_openapi.py`、两个 Manifest verifier、`redocly.yaml` 与 bundle determinism validator 必须
reviewed unchanged。

主检出迁移与 owner：总控把未提交状态安全迁移到
`/Users/echo/Projects/nightingales/agent` 后，本轮只读确认 branch=`main`、HEAD 精确
`ba5ff1d624a7019e118cbbfc964d7ecd33decea6`、`a8024901547df93453685ecb8044fe58399c30df`
为祖先、staged 为空，未提交集合精确为既有 7 个 Contract 路径加上述 3 个 partial Script，没有丢失或
新增源路径。本轮唯一写入是本计划；入口计划 SHA-256 为
`c95ce9c1ab957656f391c2ba25949059f06e4ff8df25ba8d94005cf06fa80559`。六个机器 Contract 输入保持：

- Suite `cc9bb28419790d77cfbbc44e193a897a978b3ff99f7c1641eb46d20f6386432b`；
- semantic `e7583af46f05996ff57c2d703126fead0e03c7258c2b531401b30fa60f723eff`；
- 四 fixture 依次为 `914249c1578109979753815944217f8de6ea04a6e9d537944f3fbf68ad7f9eb9`、
  `b35813de50ac97b0f54794cdf2c661200b3e0308b91218a1ca75a9a334fac5b0`、
  `65d216ed7c8b5c3e109c43c5d64604d19d3e1db546c8fe156b3bfa1da92580c0`、
  `44f25adeb6263b0d4a8fae5eeaedf6da7f7b05470666a1fa3ed5cba48872c390`。

只读验证使用 `pwd`、`git branch --show-current`、`git rev-parse HEAD`、
`git merge-base --is-ancestor`、`git status --short`、cached name-only、定向 `rg/sed/nl`、
`shasum -a 256` 与 `git diff --check`。迁移门禁、十路径 owner、empty staged、锁定 SHA 与 whitespace
检查均 exit 0。一次初始 `rg` 因 shell 引号错误 exit 非零、没有执行扫描或产生写入；修正为安全字面
pattern 后 exit 0，并确认第 10--13 节无仍可执行的固定 ID 传播、nine-path allowlist 或 final-271
规则。没有运行 validator、compile、self-test、refresh、Manifest verify/refresh、comparator、Gate 或
evidence generator，也没有暂存、提交、push/PR。

Expected-red、rollback 与 maturity：`runtime_read.http_authority` 尚未由已验收 Script 注册/真实执行，
active Suite digest 仍 stale，两个 snapshots、Manifest 273 candidate、Suite/Port registries、10 lint/10
bundle、comparator 与 source binding 均未闭合。拒绝本 correction 时只撤销本计划 diff；后继 rollback
只适用第 13 节 candidate 文件，绝不改写/删除历史 facts。`runtime-core-v1`、0B、0C-0G、0H、freeze、
security/production maturity 全部不提升，Application lock/实现/evidence 与 full Gate 继续禁止。

下一 handoff 固定为 Stage 2S：在当前未提交十路径与空暂存门禁通过后，Contract writer 只新增
`contract/conformance/runtime/v1/revisions/1.0.0/suite.json`、
`contract/openapi/agent-runtime-provider-v1.0.0.snapshot.yaml` 并回填本计划 ledger；从精确
`a802490...` 提取原始字节，现场重算 Suite tuple/self-digest 与 OpenAPI raw digest，枚举并验证 historical
`18 occurrences / 6 unique targets` 的所有 path/bytes。active Suite/OpenAPI、semantic、fixtures、
Manifest、11 个 historical positive objects、三个 partial Script 与所有其他源只读；不运行 refresh、
Manifest refresh、validator/comparator/Gate，不暂存、不提交，完成后交总控与独立 reviewer 审核。

R02 task `019fc56d-b49d-7a51-ae01-491f34587e44` 对上述 plan-only candidate 的最终复审仅提出一个
P1：原 Stage 3A 把 prepare/lint/package/bundle determinism 降为 source/topology 只读评估，不能证明
10 个文档被真实 lint、10 个独立 bundle 被真实生成且 byte-deterministic。本最小 correction 只修改
本文：在五个 C01 CLI 之外，要求隔离临时 Script/Contract tree 实际执行 pinned-venv prepare、
10-document Redocly lint、从 `script/` cwd 执行现有 package 命令 `pnpm run bundle:openapi`，再执行
reviewed-unchanged `verify_openapi_bundle_determinism.py`；Stage 2B 正常命令块同步加入后两条命令。
`lint_openapi_zero.mjs` 与 `script/package.json` 仍是 resumed Stage 3A 必写 owner，prepare 与 bundle-
determinism validator 仍是 reviewed unchanged source；后者表示不改源码，不表示跳过实际运行。

本 correction 入口只读门禁全部 exit 0：cwd 为主检出、branch=`main`、HEAD=`ba5ff1d...`、
`a802490...` 为祖先、计划输入 SHA-256 为
`ad3daffed524a736961d90a3f907b33492f181c884d9ab0c3fd5442f1687a507`，未提交集合仍精确 7 个
Contract + 3 个 partial Script，staged 为空；只读 `script/package.json` 确认现有脚本名和正确命令为
`bundle:openapi` / `pnpm run bundle:openapi`。阶段末只运行 Markdown content、owner、锁定 SHA 与
`git diff --check`；没有实际运行 prepare、lint、bundle、bundle determinism、任何 validator/refresh/
Manifest/Gate，也没有暂存或提交。最终计划 SHA-256 必须作为本轮外部交付摘要记录；它不能硬编码进
自身字节而同时保持该摘要不变，因此本 ledger 明确禁止伪造自引用 SHA。

R02 同一 task 的第二次窄复审确认上述 P1 仍有一个执行拓扑缺口：额外四条命令虽然被 prose 要求在
临时树运行，原命令块却仍从主检出 `script/` 执行，会改写主检出 `script/build`。本次最终最小处置
仍只修改本文：主检出命令块只保留五个已在 normal 顶层写前分流、内部使用 temp Contract 的 C01
self-test CLI；prepare/lint/package bundle/bundle determinism 改为在同一 pinned runtime/container 中
创建并验证 `C01_TMP_ROOT=$(mktemp -d ...)`，用 `rsync` 复制当前工作树的 Script/Contract candidate
bytes，保留 locks 与未提交 partial 源并排除 Script build/evidence/dependency 输出，然后只在临时
`script/` 下实际运行。示例明确禁止 `git archive HEAD`，并以 `case` 同时约束创建后的 temp 路径和
cleanup target；成功或失败都必须证明主检出 Contract/Manifest/Script/build/evidence 零写入。Stage 2B
受控 finalize 命令块保持主检出执行且未修改。

本次入口计划 SHA-256 为
`6bceb3a6f59ad6c145e83a208a548b30ef76887bf079c01810347395925fdf4b`；cwd、`main@ba5ff1d...`、
`a802490...` 祖先、精确 7 Contract + 3 partial Script、empty staged 门禁均 exit 0。本轮只执行
Markdown content、owner、锁定 SHA 与 `git diff --check`，不实际运行 temp setup、prepare、lint、
bundle、determinism 或任何 lane，不暂存、不提交。最终计划 SHA 仍按上段自引用边界在外部交付报告
记录。

### 16.9 Stage 2S immutable historical snapshots 实际记录

入口与 owner：本阶段在 `/Users/echo/Projects/nightingales/agent` 的 `main` 直接执行；入口 HEAD 精确为
`ba5ff1d624a7019e118cbbfc964d7ecd33decea6`，`a8024901547df93453685ecb8044fe58399c30df`
为祖先，计划输入 SHA-256 为
`31d05177834bfd679e439d72836ca1f266590e6c5f32f07bd35dd86f9507015f`，staged 为空，未提交集合精确
为 7 个 Contract + 3 个 partial Script。全部入口锁定摘要与授权值一致。唯一机器 writer 为：

- `contract/conformance/runtime/v1/revisions/1.0.0/suite.json`；
- `contract/openapi/agent-runtime-provider-v1.0.0.snapshot.yaml`。

另只写本节与阶段表。两个 snapshot 的源字节均由
`git show a802490...:<active-path>` 只读取得，再用 `apply_patch` 新增；没有从 active `1.0.1` 降版、
没有手改 snapshot 内容，也没有用 `cat`、重定向或 `cp` 写仓库。逐字与摘要结果：

| Snapshot | Historical source | Raw SHA-256 | 结构化结果 |
|---|---|---|---|
| `conformance/runtime/v1/revisions/1.0.0/suite.json` | `a802490...:contract/conformance/runtime/v1/suite.json` | `268ff34c549e01f223201262f2dab96d2718146aea383a8180d8cbf26a52eb44` | tuple `agent-runtime-provider / 1.0.0 / sha256:9ef6d50df9f1032476ea2ada2c16d70c15d88368acf59794062df7dfce0bb356`；删除 `suite_digest` 后独立 canonical JSON 9087 bytes 重算得到相同 digest |
| `openapi/agent-runtime-provider-v1.0.0.snapshot.yaml` | `a802490...:contract/openapi/agent-runtime-provider-v1.yaml` | `f75bd9484d9059435021f65147cab1a22b4cb0376ea47ce6e165fde0494f5811` | YAML safe parse；`info.version=1.0.0` |

两个 `cmp -s snapshot <(git show a802490...:active)` 均 exit 0。historical OpenAPI 全部 external
`$ref` 现场安全解析结果为 18 occurrences / 6 unique targets；每个 target 当前字节与 `a802490...`
逐字相同：

| Target | Occurrences | Current SHA-256 | `a802490...` SHA-256 |
|---|---:|---|---|
| `agent-runtime-capabilities.schema.json` | 1 | `02fd8a0c2176539a0807fe88aaf11b915eca7484d56ca0eb8973467614b85872` | `02fd8a0c2176539a0807fe88aaf11b915eca7484d56ca0eb8973467614b85872` |
| `agent-runtime-command.schema.json` | 1 | `0800078291c1b2544e188c6279d6febde27da7564dbb192babdfdb7f3eb1f930` | `0800078291c1b2544e188c6279d6febde27da7564dbb192babdfdb7f3eb1f930` |
| `agent-runtime-event-page.schema.json` | 1 | `450346bec4ccd9dccffaf9cf3d452f6461ed6581e3c3f864076ce66dd419070c` | `450346bec4ccd9dccffaf9cf3d452f6461ed6581e3c3f864076ce66dd419070c` |
| `agent-runtime-run-status.schema.json` | 3 | `d43ec7fcd43a7f6690b861aa0f88f2534444dc90a1f456b4e32d2a692ba6ba26` | `d43ec7fcd43a7f6690b861aa0f88f2534444dc90a1f456b4e32d2a692ba6ba26` |
| `agent-runtime-start-request.schema.json` | 1 | `47d15ab457e9d070a0246b078fbd2bcbf11f9a3d61072db2a04fb4d874f54704` | `47d15ab457e9d070a0246b078fbd2bcbf11f9a3d61072db2a04fb4d874f54704` |
| `standard-error.schema.json` | 11 | `1d24ba4f5bd8887603cf23bfcf2eef9e2dfc11292c87353682ef106a9d4bdf49` | `1d24ba4f5bd8887603cf23bfcf2eef9e2dfc11292c87353682ef106a9d4bdf49` |

只读 inventory-root discovery 精确复用了已审查 Python/Node verifier 的 root/path 规则但没有调用
verifier：新增两个 snapshot 均被发现，当前 discovered=273。Manifest 保持 byte SHA-256
`7d08437ef48add8ef8638c61d76878050bcb544e96a1e44d6dc122b55c165dfb`、declared/listed=269，唯一
missing-from-manifest 路径为两个 Stage 1 error Schema 和两个 Stage 2S snapshot，无 stale-in-manifest
路径。这是 Stage 2B 前的预期 drift，不是 green，也没有运行 `--refresh`。

锁定与历史零变化：active Runtime OpenAPI/Suite SHA-256 分别保持
`1436035510fc31e4d78f6fa1df52713e38d49d7ae40919b7ac977c5f254acc07`、
`cc9bb28419790d77cfbbc44e193a897a978b3ff99f7c1641eb46d20f6386432b`；semantic 与四 fixture 仍为
`e7583af46f05996ff57c2d703126fead0e03c7258c2b531401b30fa60f723eff`、
`914249c1578109979753815944217f8de6ea04a6e9d537944f3fbf68ad7f9eb9`、
`b35813de50ac97b0f54794cdf2c661200b3e0308b91218a1ca75a9a334fac5b0`、
`65d216ed7c8b5c3e109c43c5d64604d19d3e1db546c8fe156b3bfa1da92580c0`、
`44f25adeb6263b0d4a8fae5eeaedf6da7f7b05470666a1fa3ed5cba48872c390`。三个 partial Script 仍为
`e842944f97373e9028bb0b767d08227c52c3b2a1fdbdf10dd639e1c777b7c7da`、
`09bc93420ec8ad0edce5bc8123fe27312c285132fc47bd962295f3f648006f51`、
`618480d80cf55b806fe0242d64cad7f268b41a4aa3fa47a965c52397521a7f36`；refresh/comparator 仍为
`2d37d4606807527c73f56f77fc69c18724114abe7ddff87cc4799a3b4208fe85`、
`f4d8ed6dabb1fe64648b3eadbf675f39cd8e4132cc3028d673515c803e8d707d`。所有 pre-existing tracked
`contract/examples/contracts/**` 与 `contract/tests/semantic-invalid/**` 相对 HEAD 均 zero diff，覆盖
R03 的 11 个 historical positive objects；全工作树除本阶段三个 owner 和入口既有十路径外无源变化。
对 examples/tests 的 `suite_version=1.0.1` 搜索无匹配（预期 exit 1），active 1.0.1 仍无
passed/certified fact。

实际只读验证：入口 `pwd/branch/rev-parse/merge-base/status/cached`、锁定 `shasum`、两次 `git show`、
两次 `cmp`、JSON parse/JCS、Ruby YAML/ref/target byte comparison、independent inventory/path-set、
tracked historical consumer `git diff --quiet`、owner/status/diff-check 均按上述结果通过。首次尝试使用
仓库 `.venv` 做 YAML parse 因非当前主机架构 exit 126，未执行 Python 或写入；首次 Ruby 脚本因当前
Ruby 不支持 `Array#tally` exit 1，未写入，改为显式计数后 exit 0。没有运行 validator、compile、
self-test、refresh、Manifest verifier/refresh、comparator、Redocly/bundle、Gate 或 evidence，也没有
暂存、提交、push/PR。

Expected-red、停止、回滚与 maturity：Stage 2S 只证明两个 immutable historical snapshot candidates
的来源、字节与外部 Schema 依赖闭包；Manifest 仍 269、active Suite digest 仍 stale、partial Stage 3A
仍未验收，semantic/registry/comparator/source binding/full Gate 仍未闭合。若 reviewer 拒绝本候选，
rollback 只删除两个未发布 snapshot 并撤销本节/阶段表，不改 active Contract、Manifest、historical
facts 或 partial Script。若任一 target 后续漂移，立即触发 immutable bundle/full Revision snapshot
治理前置，不扩写 Schema。Contract Gate、Provider/Application conformance、`runtime-core-v1`、0B、
0C-0G、0H、freeze、security/production maturity 全部不提升；总控/R02 通过前不得恢复 Stage 3A。
