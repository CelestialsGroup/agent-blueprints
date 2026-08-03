# C01 Runtime Status/Event HTTP 400/429 Authority Patch 执行计划

日期：2026-08-03

状态：阶段 0.1 已完成；已建立、索引并按 R01 独立只读审查修订计划，尚未修改任何 Contract
机器资源、Script validator、Gate evidence、Application dependency lock 或 Application 实现。
后续阶段必须在独立授权下按本文顺序执行。

## 1. 目标与权威边界

本计划为 AgentRuntimeProvider 的 Status/Event read 关闭两个既有机器契约缺口：

1. `GET /v1/runs/{runtime_run_id}` 与
   `GET /v1/runs/{runtime_run_id}/events` 缺少 HTTP 400 响应权威；
2. 两个 read 操作缺少 HTTP 429、强制 `Retry-After` 及调用方重试边界。

交付物是新的、不可变的 AgentRuntimeProvider v1 patch Contract Revision。建议将 OpenAPI
`info.version` 从 `1.0.0` 提升为 `1.0.1`，Runtime Suite 从 `1.0.0` 提升为 `1.0.1`；最终版本号
如与仓库发布规则冲突必须停止评审，不能沿用旧摘要冒充新 Revision。

权威顺序固定为：Blueprint 文档 -> Contract 机器资源 -> Application 消费与实现。现有 Native
Runtime、Go adapter、测试或历史 evidence 只能说明旧 Revision 的消费者事实，不能反向决定、
放宽或补写本次 Contract 含义。Contract Script 只验证上述含义，不能成为意义来源。

## 2. 精确基线与 Source Digest

阶段 0 开始前的只读门禁：

| 项目 | 精确值 | 解释 |
|---|---|---|
| Repository base commit | `a8024901547df93453685ecb8044fe58399c30df` | 当前 HEAD 与要求提交精确相同；工作树、暂存区均干净 |
| 阶段 0.1 plan base commit | `68c3fb956228c7cb657c733c8b3763cdb2c9422c` | 总控与 R01 只读审查后的计划提交；阶段 0.1 开始前 HEAD 精确相同且工作树干净 |
| Blueprint Source Revision | `8e767457c808d148af371cd5e85d98a723bcfb282584b0726e7d207dbb2edbda` | `governed_source_snapshot_sha256`，48 个 Markdown 文件 |
| Blueprint Source Tree Digest | `sha256:8e767457c808d148af371cd5e85d98a723bcfb282584b0726e7d207dbb2edbda` | 使用 Application lock verifier 的长度前缀、路径排序算法只读计算；未刷新 lock |
| Contract Source Revision | `c7548d4a7e181895ca6c7c0ccfb585ccc2352433da8856c57d1d09ca3cb9a7e7` | 阶段 0 写入前的 `governed_source_snapshot_sha256`，684 个 JSON/Markdown/YAML 文件 |
| Contract Source Tree Digest | `sha256:c7548d4a7e181895ca6c7c0ccfb585ccc2352433da8856c57d1d09ca3cb9a7e7` | 是本计划的 Contract 输入基线，不是未来 patch 的输出摘要 |
| Contract Manifest Digest | `sha256:fac0299efcf04471f58f1f0668818a5148526371bd413deb5993c5aacb2762ce` | 269 个受治理 Manifest resources；状态为 `candidate-not-frozen` |
| Runtime Suite | `agent-runtime-provider@1.0.0` / `runtime-core-v1` | 当前 Suite 声明 |
| Runtime Suite Digest | `sha256:9ef6d50df9f1032476ea2ada2c16d70c15d88368acf59794062df7dfce0bb356` | Suite 内声明的内容摘要 |
| Suite Manifest resource digest | `sha256:268ff34c549e01f223201262f2dab96d2718146aea383a8180d8cbf26a52eb44` | Manifest 对当前 Suite 文件的资源摘要 |

辅助原始文件 SHA-256：Manifest 文件为
`7d08437ef48add8ef8638c61d76878050bcb544e96a1e44d6dc122b55c165dfb`，Runtime OpenAPI 为
`f75bd9484d9059435021f65147cab1a22b4cb0376ea47ce6e165fde0494f5811`，semantic constraints 为
`82500752b4689c4c87c4c849c2432c25d98831137753f25f11d99fb7201b52ff`。原始文件摘要、
Manifest 声明摘要和 Suite 内声明摘要用途不同，不得互换。

本计划自身加入 Contract 后会改变 Contract Source Revision，因此最终 Gate evidence 必须在所有
Contract 文档和机器资源冻结后重新计算并绑定输出 Revision；不能把上述输入基线写成未来输出。

## 3. 已审计事实与历史 evidence 边界

当前 Runtime OpenAPI 已为 Status/Event 声明规范化 read descriptor：

- Status：`urn:agent-platform:agent-runtime-status-operation-descriptor:v1`，
  `rfc8785-full-document-v1`；
- Events：`urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1`，
  `rfc8785-full-document-v1`；省略 query 时规范化为
  `after_event_sequence=0`、`limit=1000`。

当前响应表为 Status `200/401/403/404/500/503`，Events
`200/401/403/404/410/500/503`；两者均缺少 400 与 429。公共 `BadRequest`、
`TooManyRequests` 已存在并引用 `StandardError`，但当前 `TooManyRequests` 只把
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
worktree 上独立确认：C01 是可分离的 v1 patch；当前两个 GET operation 确实缺少 400/429；
旧 Gate 缺少精确 Blueprint/Contract/Script revision binding；Suite patch 会机械传播到八个
候选 fixture；兼容比较器尚不能表达 Suite 收紧后的再认证要求；listener 在 operation 识别前的
连接饱和不构成 C01 429 evidence。阶段 0.1 对其结论作如下显式处置：

| R01 项 | 处置 | 理由 |
|---|---|---|
| v1 patch 范围、八个 Suite 传播点、operation-level precedence、Suite 再认证、Gate binding 与 maturity 上限 | 采用 | 与 Blueprint/Contract 权威顺序及 C01 non-goals 一致，并补齐原计划的机械传播和兼容审查缺口 |
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
  reason vocabulary 由阶段 2 semantic、正反向 fixture 与 validator 闭合，阶段 1 不声称已证明；
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

- Git 中 `a802490...` 和其 Contract Source Revision 永久保留旧 `1.0.0` 可解析状态；
- 新 `1.0.1` 在新 Contract Source Revision 下增加 400/429，是 additive response patch；
- compatibility 必须同时比较 OpenAPI version 与 Runtime Suite version/digest/profile/有序 test
  set；允许的结论仅为 `wire-additive + requires recertification`，不能简写为无条件 compatible；
- 旧 ProviderRevision、RunManifest、Run、token/profile 与 evidence 继续绑定旧 Source
  Revision/Manifest/Suite，不修改其响应集合或 conformance case 数；
- 新 ProviderRevision 必须显式声明新 Contract Source Revision、Manifest、Suite
  `1.0.1`/Digest 后，ProviderResolution 才能为新 Run 选择；
- 兼容窗内消费者双读旧 `1.0.0` 与新 `1.0.1`，但每个 Run 只按其锁定 Revision 解释；写入、
  token issuance 和 evidence 只使用目标 Revision 的唯一表示；
- 不允许把旧 ProviderRevision 的 Suite digest 原地替换为新 digest，也不允许用新 400/429
  case 追溯判定旧 17-case evidence；
- 正式移除旧 reader/provider 支持必须等待没有 Run、token、checkpoint、reconciliation case 或
  retained evidence 引用旧 Revision，并走单独冻结/迁移批准。

## 10. 受影响文件族与写所有权

后续实施必须串行移交；同一时间不得有两个 writer 修改同一文件或生成同一 digest/evidence。

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
| `contract/examples/contracts/agent-runtime-capabilities.json` | 机械传播目标 Suite `1.0.1` version/digest；候选对象，不追溯修改旧发布事实 |
| `contract/examples/contracts/agent-runtime-checkpoint-manifest.json` | 机械传播目标 Suite `1.0.1` version/digest；候选对象，不追溯修改旧发布事实 |
| `contract/examples/contracts/agent-runtime-provider-revision.json` | 机械传播目标 Suite `1.0.1` version/digest；只表示新候选 ProviderRevision |
| `contract/examples/contracts/agent-runtime-run-status.json` | 机械传播目标 Suite `1.0.1` version/digest；只表示新候选 Run 状态 |
| `contract/examples/contracts/run-admission-context.json` | 机械传播目标 Suite `1.0.1` version/digest；只表示新候选 admission 输入 |
| `contract/examples/contracts/runtime-compatibility-decision.json` | 机械传播目标 Suite `1.0.1` version/digest 和再认证决策 |
| `contract/examples/contracts/runtime-compatibility-evidence.json` | 机械传播目标 Suite `1.0.1` version/digest/profile binding |
| `contract/tests/semantic-invalid/compatibility-decision-cases.json` | 机械传播目标 Suite `1.0.1` version/digest 的负向兼容语义输入 |
| `contract/compatibility/contract-manifest.json` | 重算新增/变化资源、resource count/digest/manifest digest；保持 candidate-not-frozen |
| `contract/doc/plan/C01-runtime-status-event-http-authority-patch.md` | 在最终 Gate 前回填阶段 ledger、偏差和剩余风险；随后冻结 |

`standard-error.schema.json`、两个现有 read descriptor Schema、Runtime state machine 与 Event
Registry 先视为 reviewed-but-unchanged。若实施发现必须修改它们才能闭合，立即停止并先更新
本文 Authority Matrix/兼容分析；不得顺手扩大 writer 范围。

上述八个传播文件是当前 source tree 中 Suite `1.0.0` version/digest 的完整机械消费者集合。
refresh 后必须证明只有这些计划内候选 fixture 发生传播；它们表示目标 `1.0.1` Revision 的新候选
对象，不是对已发布 ProviderRevision、Run、Checkpoint 或 CompatibilityDecision 的原地修改。
Git 中旧 Contract Revision 和其历史 `1.0.0` 对象仍须可解析、可验证。

`contract/semantic-constraints-v1.json` 继续不属于当前 Manifest inventory。它的变化由最终精确
Contract Source Revision 与 `validate_semantics.py` 中真实执行的 check 共同绑定；Manifest 只按
现有 inventory 定义重算。阶段 2 不修改 Python/Node Manifest verifier 的 inventory 根，也不预设
因 semantic constraints 产生新的 resource count。

### 10.2 Script writer 独占

Contract writer 冻结机器资源后，Script writer 才可写：

| 文件/目录 | 计划变化 |
|---|---|
| `script/contract/validation/offline_static_audit.py` | 强制两个 read operation 的 400/429、错误 Schema、必需 Retry-After 和 operation descriptor 边界 |
| `script/contract/validation/validate_contracts.py` | 注册两个正例和两个反例的 Schema validation |
| `script/contract/validation/validate_semantics.py` | 注册并真实执行 `runtime_read.http_authority`，验证 code/retryable/descriptor/error closure |
| `script/contract/maintenance/refresh_example_digests.py` | 将新 Suite version/digest 只传播到 10.1 列出的八个候选 fixture；禁止无关资源或历史对象漂移 |
| `script/contract/compatibility/check_contract_compatibility.py` | 比较 OpenAPI version、Suite version/digest/profile/有序 test set；结论必须为 `wire-additive + requires recertification`，并 fail closed 检查删除/重排/收紧和 base commit |
| `script/contract/validation/generate_validation_evidence.py` | 输出精确 Blueprint/Contract/Manifest/Script/Suite revisions/digests 和 C01 closure |
| `script/evidence/VALIDATION.json` | 最终完整 Gate 的机器 evidence；不得手改 |
| `script/evidence/CONTRACT_VALIDATION_REPORT.md` | 同源人类报告；明确不提升 Application/冻结/生产成熟度 |
| `script/build/validation/**` | 临时 Gate 输出，不提交为 Contract 资源 |

Script Revision 使用独立的 `governed_source_snapshot_sha256`：以 `script/` 为根，确定性纳入
Contract Gate 源码、Makefile、`.tool-versions`、requirements/package/pnpm/Go locks，排除
`.venv/`、`node_modules/`、`build/` 与 `evidence/` 输出；按相对路径排序并以路径/内容长度前缀
计算 SHA-256。若实际仓库已有更正式且等价的 Script Revision 规则，应在阶段 3 先统一，不能
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
authority：Stage 3 validator 必须按完整键集、值类型、枚举和数组顺序 fail closed，缺键、多键、
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
C01 400；未知 route 或 operation 识别前 parser failure 仍为 `c01-out-of-scope`。Stage 3
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
Stage 3 Script 必须按封闭键集、数组顺序和原始 wire value fail closed，不得自行解释
`canonical-decimal-integer-delta-seconds` 枚举或依赖 prose。

### 阶段 2：Fixture、semantic、Suite、Manifest 与 compatibility

1. 加入两个正例和两个反例；
2. 新增并执行 `runtime_read.http_authority` semantic check；每个 `contract_gate` mapping 必须在
   本次 Gate 注册且真实执行；
3. Runtime Suite 提升 `1.0.1`，在 `runtime-core-v1` 原顺序的 read 邻近位置加入四个唯一
   case；重算 Suite digest；
4. 运行 `refresh_example_digests.py`，将 Suite `1.0.1` version/digest 机械传播到 10.1 精确列出的
   七个 `contract/examples/contracts/*.json` 和一个 semantic-invalid fixture；refresh 后逐文件审查，
   不得出现第九个传播文件。候选 fixture 只描述目标 `1.0.1`，不得追溯改写旧 Revision 中已发布
   ProviderRevision、Run、Checkpoint 或 compatibility 事实；
5. 按现有 Manifest inventory 更新 resources/digests；Python/Node 结果必须一致。
   `semantic-constraints-v1.json` 不新纳入 inventory，其变化由 Contract Source Revision + 实际
   semantic Gate execution 绑定；若发现 Blueprint/Contract 明确要求纳入，立即停止并升级独立
   治理前置；
6. 用 base commit `a802490...` 做显式候选 compatibility comparison，同时比较 OpenAPI version、
   Runtime Suite version/digest/profile/有序 test set。唯一允许的 C01 结论是
   `wire-additive + requires recertification`：wire response 是 additive，但 Suite 增加四个必测 case，
   所有目标 `1.0.1` ProviderRevision 必须重新认证，不能继承 `1.0.0` 的 17-case 结果；
7. 若 compatibility comparator 无法结构化表达 Suite 收紧和 `requires recertification`，立即停止
   阶段 2；不得用 OpenAPI additive 结果替代 Suite 再认证结论，也不得写成正式 frozen-baseline
   通过。

focused 验证：

```bash
cd /Users/echo/.codex/worktrees/65b0/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
.venv/bin/python contract/maintenance/refresh_example_digests.py
.venv/bin/python contract/validation/validate_contracts.py
.venv/bin/python contract/validation/validate_semantics.py
.venv/bin/python contract/manifest/verify_contract_manifest.py
node contract/manifest/verify_contract_manifest.mjs
CONTRACT_FROZEN_BASE_REF=a8024901547df93453685ecb8044fe58399c30df \
  .venv/bin/python contract/compatibility/check_contract_compatibility.py
```

Evidence：新的 Suite ID/version/digest/profile/有序 test set、八个且仅八个机械传播文件、Manifest
resource count/resources digest/manifest digest、semantic check inventory/实际执行结果、Fixture
正反向结果，以及结构化 `wire-additive + requires recertification` base comparison。不得覆盖旧
Suite digest、追溯改写旧对象，或把 comparison 写成正式冻结兼容结论。

### 阶段 3：Script Gate source binding

1. 实现确定性 Blueprint、Contract、Script governed source snapshot；
2. `generate_validation_evidence.py` 必须输出：
   `blueprint_source_revision`、`contract_source_revision`、
   `contract_manifest_digest`、`script_source_revision`、Runtime Suite
   ID/version/digest/profile、base commit、验证工具版本和生成时间；
3. evidence generator 重新读取 Manifest/Suite 并核对各 lane 属于同一 digest，禁止从计划常量
   复制；
4. 报告明确旧 2026-07-27 evidence 不覆盖 `a802490` 或 C01；
5. Script self-tests 覆盖缺字段、旧 digest、缺/非法 Retry-After、错误 retryable、响应集合回退和
   source snapshot 漂移均 fail closed。

focused 验证：

```bash
cd /Users/echo/.codex/worktrees/65b0/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
.venv/bin/python contract/validation/check_supply_chain.py
.venv/bin/python contract/validation/offline_static_audit.py
.venv/bin/python contract/validation/validate_contracts.py
.venv/bin/python contract/validation/validate_semantics.py
```

此阶段只证明 Script validator 可以 fail closed；还不能声称完整 Gate 通过。

### 阶段 4：冻结源文件与完整 Contract Gate

先回填本计划阶段 1-3 的实际差异、验证、偏差、停止条件和剩余风险，然后冻结所有 Contract 与
Script source。冻结后运行一次完整 Gate；Gate 后不得再编辑纳入 source revision 的文件。

```bash
cd /Users/echo/.codex/worktrees/65b0/agent/script
export AGENT_BLUEPRINT_ROOT=../blueprint
export AGENT_CONTRACT_ROOT=../contract
export CONTRACT_FROZEN_BASE_REF=a8024901547df93453685ecb8044fe58399c30df
make validate-contract
```

Gate 后只读复核：

```bash
cd /Users/echo/.codex/worktrees/65b0/agent
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

若实际 evidence shape 与上述 jq 路径有经评审的更佳命名，阶段 3 必须先更新本文并冻结，不能在
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
- semantic `contract_gate` check 未注册/未执行，Fixture/Suite case 未进入 Manifest/digest，或
  Python/Node Manifest 结果不一致；
- Suite version/digest refresh 改写 10.1 八个候选 fixture 之外的文件，或把候选 `1.0.1` 传播解释
  为旧 ProviderRevision/Run/Checkpoint/compatibility 事实的原地迁移；
- compatibility comparator 未比较 OpenAPI version 与 Suite version/digest/profile/有序 test set、无法
  表达 `wire-additive + requires recertification`、报告 breaking change，或新 Revision 需要覆盖旧
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

未来 patch 在任何新 ProviderRevision 准入前可整体回退 Contract/Script candidate diff，并保留
失败 evidence 供审计；不得删除旧 Revision。新 ProviderRevision 准入后，rollback 只能停止
新 Run 选择该 Revision，并保留新 provider/reader 支持处理已锁定 Run 和 reconciliation；不能
把这些 Run 改绑 `1.0.0`。旧 ProviderRevision 可继续服务其旧 Run，但只按旧 response set 与
Suite digest 解释。

Script rollback 必须保留能验证所有仍受支持 Contract Revision 的 validator。Gate evidence 是
append-only 发布证据：错误报告可以被新报告否定，不能原地改写日期/digest 冒充原运行。

## 14. Maturity 上限

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
  evidence；缺少任一绑定都不能发布 C01 完成结论。

## 16. 阶段台账

| 阶段 | 状态 | 交付 | 验证/证据 | 偏差、风险与成熟度 |
|---|---|---|---|---|
| 0. 计划与索引 | 已完成 | 新增本计划、Contract 计划索引；根 README 增加索引入口；未改机器资源、Script、Application | 基线 HEAD/clean/ancestor 只读核对通过；阶段末执行 `git diff --check`、owner path diff、status | 仅计划成熟度；旧 Gate/evidence 不提升；后续阶段未授权、未执行 |
| 0.1 R01 审查修订 | 已完成 | 补齐八个 Suite 传播文件、Suite 再认证比较、operation precedence、Manifest inventory 与 Cache-Control 治理决策；只改本计划 | 总控只读检查 + R01 thread `019fc53f-6f65-7291-9486-32030db8b938`；基线 `68c3fb9...` clean/ancestor；阶段末执行 Markdown-only diff/status | 采用最小切片、传播、precedence、recertification、binding；不采用 Manifest inventory 扩张、Cache-Control 外推、descriptor Schema 扩张、旧 token/JTI 重放、替代 error code；理由见 3.1。仍仅计划成熟度 |
| 1/1.1/1.2 Schema/OpenAPI + R02 纠偏 | 已完成，待总控与 R02 最终复审 | 新增两个 Runtime read error Schema；Runtime OpenAPI `1.0.1` 为 Status/Event 增加专用 400/429、封闭的 HTTP/header/retry 与既有 precedence/admission authority；Stage 1.2 补齐 Events body/framing 与 Retry-After 原始 wire grammar；未改其他机器资源 | 初始 focused checkpoint 见 16.1；R02 首次纠偏见 16.2；二次 findings、equality 与重跑见 16.3；固定容器均 exit 0，Redocly 9/9 为 0 error/0 warning | 现有 Script 尚未 fail-closed 断言新增 authority，Stage 2 semantic/fixture/Suite/Manifest 仍未执行，green 不是 authority closure；未暂存、未提交，阶段 2 未授权 |
| 2. Fixture/Suite/Manifest/compatibility | 未开始 | 待独立授权 | 待执行 semantic/manifest/八文件传播/结构化 base comparison | 新 digest 尚不存在；必须得到 `wire-additive + requires recertification` |
| 3. Script source binding | 未开始 | 待独立授权 | 待执行 validator fail-closed tests | Script 仍未绑定新 source revisions |
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
  const。敏感信息与公开 reason vocabulary 留给阶段 2 semantic/fixture/validator。

剩余风险与成熟度：现有 `offline_static_audit.py`、`validate_contracts.py` 尚未结构化断言两个新
Schema 的 code/retryable、429 required Retry-After、两操作 precedence/admission/retry 扩展，也
没有阶段 2 正反向 fixture/semantic/Suite/Manifest 绑定；Redocly 只证明 OpenAPI 结构与 lint。
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
  details/violations 仍由阶段 2 semantic、正反向 fixture 和 validator 闭合，本阶段不声称证明。

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
closure；阶段 2 仍需完成 semantic、正反向 fixture、Suite 1.0.1/digest/八文件传播、Manifest
source binding 与 compatibility recertification，阶段 3 才能固化 Script validator/self-test。
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
- Stage 3 validator 责任同步收紧为封闭键集、数组顺序和 raw wire value fail closed；不能解释
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
reject vocabulary；Stage 2 仍需 semantic、正反向 fixture、Suite 1.0.1/digest/八文件传播、Manifest
source binding 和 compatibility recertification，Stage 3 才能实现 fail-closed validator/self-test。
focused equality/validator/Redocly green 不构成 authority closure、完整 Gate、Provider conformance、
Application 实现或 maturity 提升。未触发停止条件，未运行 full Gate，未暂存或提交。
