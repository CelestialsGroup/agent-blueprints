# Application 编码与工程规范

状态：Phase 0 候选开发规范。

本文规定 Agent 产品实现的代码结构、编码、测试和评审规则。它不复制 Contract 字段，不记录 Application 实时进度，也不把工具运行成功写成组件完成或生产批准。

## 1. 规范层级

实现必须同时服从以下事实源：

1. Blueprint 的架构边界、技术选型、数据不变量和阶段验收；
2. 锁定 Contract Revision 的 Schema、OpenAPI、状态机、Event Registry、Semantic Constraints 和 Conformance Suite；
3. 本文的编码与工程规则；
4. Application 内更靠近代码的 README、工具配置和测试，但它们不得放宽前三项。

出现冲突时停止实现：架构意图变化先改 Blueprint，Wire 行为变化先改 Contract，纯实现细节只改 Application。不得让已有代码、框架默认行为或一次测试结果反向成为规范。

本文使用以下强度：

- **必须**：违反即不能合并；
- **应当**：默认遵守，偏离时在 PR 中说明原因和替代保护；
- **可以**：局部选择，不形成平台承诺。

## 2. 总体编码原则

- 代码以正确性、可恢复性、可审计性和清晰边界优先，不以减少文件数、隐藏 SQL 或追求框架一致性为目标。
- 每个模块只有一个主要职责。新增抽象必须消除真实重复、隔离不稳定依赖或表达稳定 Port；禁止提前建立通用 `utils`、`common`、`base` 大包。
- 领域规则只依赖领域值、稳定 Port 和标准库。HTTP、pgx、sqlc、Temporal、Redis、Kubernetes、Pydantic、React 等类型不得进入领域事实模型。
- Composition Root 负责读取配置、创建依赖和管理进程生命周期。领域代码不得读取环境变量、创建全局客户端或隐式连接外部服务。
- 所有外部输入必须有大小、数量、时间和并发上限。超限在昂贵解析、对象查询或副作用前失败。
- 权威写入必须显式表达事务、幂等键、请求摘要、Expected State/CAS、Fencing 和 Outbox；不得藏在 ORM Hook、HTTP Middleware 或框架 Callback 中。
- 重试只包围有明确幂等和对账语义的操作。未知结果进入 `outcome_unknown`/reconciliation，不得根据超时推断失败或成功。
- Redis、本地文件、进程内 Cache、Hook、Trace 和第三方 Checkpoint 只能优化或提供证据，不能成为唯一事实源。
- 代码、标识符、日志键、Metric 名和错误码使用英文 ASCII。架构说明和用户文案可以使用目标语言；用户文案必须通过本地化边界，不散落在领域代码中。

## 3. 目录与依赖方向

Application 顶层责任目录使用单数命名；语言生态强制约定的 `src` 等目录可以保留。依赖方向固定为：

```text
cmd / app composition roots
          |
          v
use cases and consumer-owned ports
          |
          v
domain values and invariants
          ^
          |
persistence / gateway / orchestration / provider adapters
```

- `cmd/` 只做配置、依赖装配、Signal、健康检查和优雅退出，不实现领域决策。
- `internal/domain/` 不导入基础设施包；领域对象不得携带数据库 Row、HTTP Request、JWT Library 或 Workflow SDK 类型。
- Port 由使用方拥有，Adapter 依赖 Port。不要为了 Mock 在提供方旁边创建大接口。
- `internal/persistence/`、`internal/gateway/`、`internal/orchestration/` 等 Adapter 可以依赖领域和 Port，领域不能反向依赖它们。
- `internal/generated/` 只保存可由锁定输入重建的代码。禁止手改生成文件；生成差异必须与输入和生成器版本同 PR 提交。
- Python Native Runtime 只能通过 Runtime Port 与 Go 平台交互，不读取平台 PostgreSQL 或 Temporal Persistence。
- TypeScript Application 只消费公开 Agent Access/SSE/Gateway 契约，不导入 Go/Python 私有模型或直写平台数据库。
- Business Reference 的 API、Web、数据库、依赖锁和签名身份独立，不导入 Agent Platform 内核包。

## 4. 命名、类型与确定性

### 4.1 命名

- 名称表达领域含义，不使用 `data`、`info`、`manager`、`handler2` 等无所有权词；HTTP Handler、Temporal Activity 等确有技术职责时可以使用技术后缀。
- 缩写按语言惯例统一：Go 使用 `ID`、`URL`、`HTTP`；SQL 和 Wire Contract 使用 `snake_case`；TypeScript 内部使用 `camelCase`，通过显式 Mapper 映射 Wire `snake_case`。
- ID 在领域层使用有意义的独立类型或值对象，不把 Tenant、WorkOrder、Run、Attempt 等 ID 当作可互换的裸字符串。
- Provider、Business 或外部系统 ID 视为不透明值；除非 Contract 明确规定，不解析其前缀、UUID 版本或排序语义。

### 4.2 时间与数字

- 持久时间使用 UTC；PostgreSQL 使用 `timestamptz`，Wire 使用 Contract 指定的 RFC 3339 表示。不得持久化本地时区时间。
- 领域逻辑通过可注入 Clock 获取当前时间；测试不得依赖真实等待。进程内单调时间只用于测量，不写入 Wire 或数据库。
- Deadline、TTL、Lease 和 Clock Skew 使用有单位的类型或明确后缀，禁止无单位整数。
- Budget、Quota、Usage、金额和可结算数量不得使用二进制浮点作为权威值；使用 Contract 规定的整数基础单位或精确十进制表示。
- `null`、缺失、未知、零、空集合和未采集必须保持不同语义。尤其不得把 missing Usage 解释为零。

### 4.3 摘要与序列化

- 需要跨语言比较的摘要严格使用锁定 Contract 的 Strict I-JSON 和 RFC 8785 JCS Profile。
- 摘要输入必须明确包含/排除字段；禁止对语言对象的默认序列化结果直接哈希。
- SHA-256 Wire 值使用 Contract 规定的 `sha256:` 表示。数据库需要索引或比较时应使用固定 32 字节并加长度约束，在 Adapter 边界转换，不在同一列混用文本和字节表示。
- Map、文件遍历、依赖清单、SBOM 和证据输出必须稳定排序；测试不得依赖随机 Map 顺序。

## 5. 错误与失败语义

- 错误分为输入/契约、认证、授权、冲突、未找到、限额、依赖暂时失败、未知结果和内部不变量等稳定类别；Transport 只映射类别，不根据错误文本判断。
- 内部错误保留 Cause Chain；对外响应使用 Contract 的错误码、边界化 Details 和 Trace ID，不返回 SQL、Token、Secret、Provider Endpoint、堆栈或跨租户存在性。
- Not Found 与 Forbidden 的选择必须服从对象所有权和防枚举规则，不能为了调试泄漏资源存在。
- 冲突错误必须区分 CAS/Fencing 冲突、Idempotency Digest 冲突和领域状态冲突，调用方不得把所有冲突无条件重试。
- Cancel requested、请求超时、连接断开和 Worker 关闭都不是远端副作用已经取消的证明。
- `panic`/未捕获异常只用于不可继续的程序员不变量或启动期配置错误；请求、消息和 Activity 失败必须返回有类型的错误并保留可对账状态。
- 日志可以包含稳定错误类别和 Cause 摘要，不以完整错误对象为由记录敏感 Payload。

## 6. Go 规范

### 6.1 包与 API

- 包名使用简短小写单词，避免 `util`、`common`、`model` 大包。文件按职责命名，不按类一文件机械拆分。
- 导出符号必须服务于跨包边界；默认保持未导出。导出 API 有 Go Doc，说明不明显的不变量、所有权和失败语义。
- 接口由消费者定义，保持最小。返回具体类型，接收满足需要的接口；不要为每个 Struct 自动生成接口。
- 构造函数校验必需依赖并返回完整可用对象。禁止依赖调用方按隐式顺序设置字段。
- 领域值不得用 `map[string]any` 表达。扩展 Metadata 只能使用 Contract 允许的闭合、有界类型。

### 6.2 Context、并发与生命周期

- `context.Context` 是可能阻塞或跨边界方法的第一个参数；不得存入 Struct、数据库或异步任务 Payload。
- Context 取消必须向下传播，但不能代替持久取消事实。启动后台任务前明确 Owner、退出条件、错误通道和 Drain 行为。
- 禁止无界 Goroutine、Channel、队列和并发 Fanout。并发上限必须来自配置或准入事实，并有背压/拒绝路径。
- 共享可变状态优先通过数据库事务或所有权单一的 Goroutine 管理；使用 Mutex 时记录锁顺序，禁止在持锁期间做网络 I/O。
- 所有 Server、Worker、Dispatcher 和 Provider Adapter 必须支持有界优雅关闭；关闭超时后保留可恢复状态，不伪造成功。

### 6.3 错误、日志与配置

- 使用 `%w`、`errors.Is/As` 和有类型错误保留 Cause；禁止匹配错误字符串或丢弃返回错误。
- 只在处理错误的层记录一次日志；低层返回上下文，高层决定 Retry、映射和日志级别。
- 使用 `log/slog` 结构化日志。稳定键至少覆盖适用的 `trace_id`、`tenant_id`、`work_order_id`、`execution_scope`、`attempt_id` 和 `error_kind`；不得记录 Token、Secret、Prompt、用户文件或完整 Contract Payload。
- 环境变量只在 Composition Root 读取并转换为有类型配置；缺失、冲突或不安全默认值在启动时失败。
- 时间、ID、随机数、签名器和外部客户端通过窄依赖注入；测试不修改进程全局状态。

### 6.4 Go Gate

- 所有 Go 文件必须通过 `gofmt`，并通过锁定 Go Toolchain 的 `go vet ./...`、锁定版本的 Staticcheck 与 `go test ./...`。
- 涉及 Goroutine、锁、Dispatcher、Cache 或连接池的改动必须通过 Race Test；不支持目标架构时在受支持的 CI 架构运行并绑定证据。
- 新依赖必须使用精确 Module Version、`go.sum`、许可证/来源记录和 SBOM；不接受浮动 Branch 或未审查 `replace`。
- 生成代码必须先重建再验证 Git Diff 为空。

## 7. PostgreSQL、Migration 与 Repository 规范

### 7.1 DDL 与命名

- 表、列、索引、Constraint 和 SQL 参数使用 `snake_case`。表使用复数领域名；主键使用 `<entity>_id`，外键保持被引用 ID 名。
- 所有租户业务表显式包含非空 `tenant_id`；不能只通过多级 Join 间接推导 Tenant。
- 时间列使用 `*_at timestamptz`；版本、Sequence、Attempt 和 Fencing 使用有范围检查的整数类型。`updated_at` 不是 CAS。
- 必填事实使用 `NOT NULL`。状态使用可迁移的文本加 `CHECK`/外键并与 Contract 状态机同步；默认不使用难以演进的 PostgreSQL ENUM。
- JSONB 只保存 Contract 允许的有界快照、证据或扩展对象，不替代可约束的所有权、状态、序列、金额、权限和外键列。
- Tenant-qualified Unique/FK/Index 必须显式包含 Tenant/Owner Scope。每个外键和高频查询都要审查支持索引及删除行为。
- 不使用通用 ORM、数据库 Trigger 或隐式 Cascade 承载核心状态机。必要 Trigger 必须小、可测试、可解释，且不能发网络请求或隐藏领域授权。

### 7.2 Migration

- 使用 SQL-first goose Migration，文件有单调编号和单一主题。Migration 不由应用进程启动时自动执行。
- 每个 Migration 说明锁影响、数据影响、向前/向后兼容窗口和回滚分类。可能丢数据的 Down 不得伪装为安全回滚，应显式失败并提供前滚恢复步骤。
- 生产演进遵循 expand -> backfill -> verify -> contract。重命名、改类型和收紧非空不得在一个不可回滚事务中直接完成。
- Migration 使用独立 Migrator Role；Application Role 不拥有表、不具备 `BYPASSRLS`，也不能执行 DDL。
- 每组 Migration 必须在真实 PostgreSQL 上验证空库 Upgrade、允许的 Rollback、再次 Upgrade，以及从最近受支持基线升级。

### 7.3 TenantContext 与 RLS

- 每个 Repository 事务先通过参数化 `set_config(..., true)` 设置事务局部 `agent.tenant_id`，再执行任何对象查询或写入；禁止拼接 Tenant 值或使用 Session 级 `SET`。
- RLS Policy 对缺失或非法 TenantContext fail-closed。Application Role 不得拥有绕过 RLS 的权限；租户表使用 `ENABLE ROW LEVEL SECURITY` 与 `FORCE ROW LEVEL SECURITY`。
- Repository 查询仍显式携带 `tenant_id`/Owner Scope；RLS 是纵深防御，不替代授权和查询条件。
- 事务 Commit/Rollback 后连接池复用测试必须证明 TenantContext 不泄漏。禁止在事务外执行租户 Repository 方法。
- Migrator、后台治理和跨租户维护使用独立、最小权限 Role 与显式审计路径，不能通过空 Tenant 或万能 Tenant 绕过。

### 7.4 事务、锁与 Repository

- Repository 暴露原子 Use Case，不暴露表形 CRUD，不向领域层泄漏 pgx/sqlc 类型。
- 事务由上层 Use Case/Transaction Runner 拥有；Repository 不静默开启嵌套事务。需要 Savepoint 时必须由用例显式声明和测试。
- CAS 使用 `UPDATE ... WHERE expected_version/state/fencing ... RETURNING` 并检查受影响行数；禁止先读后写而没有锁/CAS。
- Sequence 通过受锁定的 Owner/Ledger 行分配，禁止 `MAX(sequence)+1`。跨表锁顺序固定并在 Repository 测试中覆盖竞争。
- `FOR UPDATE SKIP LOCKED` 只用于有 Lease/Fencing/重试语义的 Dispatcher，不用于普通领域查询或绕过竞争。
- 网络 I/O、对象存储、Provider 调用和 Temporal 调用不得发生在数据库事务内；事务只提交意图、Outbox 和状态。
- sqlc Query 必须让 Tenant Scope、锁、CAS、排序、Limit 和返回行数可见；动态 SQL 只能通过受限 Builder 生成，禁止拼接用户输入。

### 7.5 Outbox、Inbox 与 Idempotency

- Outbox 与拥有它的业务变化、状态 Sequence 和 CanonicalEvent 在同一事务提交。Dispatcher 至少一次发送，消费者必须幂等。
- Dispatcher Claim 有 Lease、Attempt、Fencing、下次重试时间和有界批量；网络调用在 Claim 事务之外，完成写回验证相同 Fencing。
- 传输 Inbox 在副作用前按 `(consumer, message_id)` 唯一插入；Provider Event 另按 Contract 的 Source Identity 去重。
- Idempotency Record 保存 Scope、Key Digest、Request Digest、结果引用和状态；相同 Key 不同 Request Digest 返回稳定冲突，不能覆盖旧记录。
- 不得以 Redis Lock、进程 Mutex 或 Broker 去重替代数据库 Unique/Inbox/Fencing。

## 8. Temporal 规范

- Workflow 代码必须确定性：禁止直接读取时间、随机数、环境变量、网络、数据库或文件系统；使用 Workflow API、版本化输入和 Activity。
- Workflow Payload 只包含稳定 ID、有界值和不可变摘要，不放 Secret、Prompt、用户文件、大型 Contract Payload、Provider Endpoint 或数据库 Row。
- Activity 表达一个可重试或可对账的外部边界，设置 Start-to-Close/Schedule-to-Close、Heartbeat 和 Retry Policy。非幂等 Activity 不自动重试。
- Workflow 只拥有编排历史，不取代 PostgreSQL 当前状态、Ledger、Outbox 或业务事务。
- Workflow 演进使用 Patch/版本、Worker Build ID 和历史 Replay；删除旧分支前必须证明所有相关 History 可 Replay 或已完成迁移。
- Signal/Update 先通过权威授权和数据库事实；Temporal 接收成功不等于领域状态已经提交。
- Activity 响应丢失进入同一 Invocation/Operation 的对账路径，不创建第二个逻辑 Run。

## 9. Python Native Runtime 规范

- 使用 `src/` Layout、锁定 Python/uv 和精确依赖。公共包有类型标注；Runtime Port 边界禁止 `Any`、未约束 Dict 和隐式 Pydantic Coercion。
- Pydantic/生成 DTO 只用于 Wire 边界；内部 Agent Loop 使用明确的领域/运行值，并通过 Mapper 转换，不让第三方框架对象成为公共模型。
- Exception 分为 Contract、Authorization、Conflict、Deadline、Cancellation、Dependency 和 Outcome Unknown 等类别，在 Port 边界统一映射。
- Async 代码不得在 Event Loop 执行阻塞 I/O；阻塞库通过有界线程/进程 Adapter，显式 Timeout、Cancellation 和并发上限。
- Background Task 必须有 Owner 和 Await/Cancel 路径；禁止未追踪的 `create_task`、无界队列和模块级可变单例。
- Runtime 不访问平台 PostgreSQL、Temporal Persistence、Business 数据库或长期 Secret；全部模型、工具、Artifact 和 Egress 经版本化 Port/Gateway。
- Checkpoint 只保存 Provider 私有状态和 Platform 允许的不可变引用；恢复必须消费 Platform CompatibilityDecision，不自行宣布 portable。
- Python Gate 在 Runtime 功能扩展前锁定 Ruff、mypy 和测试版本；最低通过 Ruff Format/Lint、mypy 严格边界 Type Check、Unit/Component Test 和锁文件一致性检查。

## 10. TypeScript、Next.js 与前端规范

- TypeScript 开启 `strict`、`noUncheckedIndexedAccess`、`exactOptionalPropertyTypes`；禁止未经隔离的 `any`、非空断言和任意类型转换。
- Wire DTO 由锁定 Contract 生成或校验；Wire `snake_case` 与 UI `camelCase` 通过集中 Mapper 显式转换。禁止前端自行发明宽松 DTO。
- Server Component、Route Handler/BFF 与 Client Component 边界明确；Token、Cookie、签名和服务端 Secret 不进入 Client Bundle、浏览器存储或日志。
- TanStack Query/前端 Store 只保存可失效 Projection 和交互状态，不拥有授权、终态、Usage、Provider 健康或 Runtime 路由事实。
- SSE/Gateway 重连使用服务端 Cursor/Generation；禁止以数组长度、浏览器时间或本地递增值伪造 Sequence。
- 用户可见状态必须区分 pending、accepted、dispatched、outcome unknown、reconciling 和 terminal；点击 Cancel 不能立即显示已取消。
- 组件优先语义 HTML、键盘操作、可见焦点和可访问名称。用户文案通过本地化资源，不拼接内部错误。
- TypeScript Gate 在首个 Workspace 创建时锁定 pnpm、Prettier、ESLint/typescript-eslint、`tsc --noEmit`、Vitest 和 Playwright；Lockfile、生成代码和浏览器边界测试必须进入 Gate。

## 11. HTTP、Contract 与生成代码

- 公共 Handler 严格执行锁定 OpenAPI/Schema：先限制 encoded bytes，再解析、验证 Contract、绑定 Path/Query/Body、认证授权，最后查询或写入。
- Tenant、ClientApplication 和 PrincipalContext 从认证身份与服务端映射派生；请求体中的同名字段不能覆盖 TenantContext。
- Mutation 在消费 Grant 或产生副作用前验证 Idempotency Scope、Request Digest、Deadline、Fencing 和路径绑定。
- Wire DTO、领域值和数据库 Row 分层映射。Handler 不直接调用 sqlc Query；Repository 不返回 HTTP DTO。
- 生成器、输入 Revision 和输出目录固定。生成失败或 Diff 不干净时 Gate 失败，不允许手工修生成文件。
- 新增或改变公共行为时同步 Blueprint/Contract 影响矩阵；纯实现重构不得顺手修改 Wire Contract。

## 12. 安全、配置与可观测性

- Secret 只以引用、Grant 和单操作 Delivery 存在。明文、可重放 Token、Credential Handle 不进入数据库、Redis、Temporal、Queue、Event、Trace、Recording、Artifact、日志或错误。
- 日志、Metric 和 Trace 使用有界 Attribute Allowlist。高基数字段、用户内容、Prompt、代码、文件内容和第三方原始 Payload 不作为 Label/Attribute。
- W3C Trace Context 只用于关联，不作为身份、授权、幂等或执行成功证明。
- 配置有类型、可验证、分环境注入；禁止不安全生产默认值、浮动 Endpoint、动态远程代码和运行时下载未验证依赖。
- 健康检查分 Startup/Readiness/Liveness。Readiness 只表达当前是否接收流量，不改写领域状态；依赖短暂不可用不应通过 Liveness 制造重启风暴。
- Audit/CanonicalEvent 是受治理事实；Telemetry 丢失不得改变授权、状态机、Usage 或 Settlement 结论。

## 13. 测试与证据

### 13.1 测试层级

| 层级 | 证明内容 | 不能替代 |
|---|---|---|
| Unit | 纯领域规则、Mapper、边界值、错误分类 | SQL 锁、RLS、Temporal Replay |
| Repository | 真实 PostgreSQL Constraint、事务、锁、CAS、Fencing | 跨进程集成 |
| Component | 单进程公开 Port、生命周期和依赖错误 | 完整业务链 |
| Conformance | 锁定 Suite/Profile 对公开 Port 的行为 | 产品 E2E、容量、恢复 |
| Integration | 真实进程和 PostgreSQL/Temporal/Redis/对象存储边界 | 生产拓扑与 SLO |
| Replay | Temporal History、Event/Cursor/Recording 兼容 | 外部副作用恢复 |
| Fault | 丢响应、重复、重启、旧 Fencing、依赖故障 | 未测试故障或容量 |
| E2E | 公开入口到用户可见结果的纵向链 | 0H 可靠性与生产批准 |

### 13.2 测试规则

- 测试使用固定 Clock、受控 ID/随机源和显式 Fixture；禁止依赖执行顺序、真实 Sleep、开发机时区或共享外部状态。
- 并发不变量必须有竞争测试：至少覆盖重复请求、不同 Digest、旧 Fencing、丢响应和两个事务同时更新。
- Repository/RLS/锁/DDL 必须使用真实、固定 Digest 的 PostgreSQL；Mock 不能证明数据库行为。
- Temporal 变更必须运行历史 Replay；Redis 正确性边界必须包含清空/丢通知后从权威源恢复。
- 正向测试证明接受路径，负向测试证明越权、跨租户、过期、摘要冲突、超限和非法状态被拒绝且无副作用。
- 测试名称表达 Given/When/Then 的行为，不复述函数实现。失败信息包含期望、实际和关键身份，不包含敏感 Payload。
- 只有测试源、环境、命令、结果、Blueprint/Contract/Suite Digest 和制品摘要完整绑定时，运行结果才可提升为证据。
- `phase0_implementation_required` 只能在真实实现与要求的 DDL/测试证据同时存在后标记完成；README、空测试或函数名不算证据。

## 14. 依赖、构建与供应链

- 只引入解决当前切片真实问题的依赖。采用前记录版本、来源、许可证、维护状态、安全公告、替代方案和升级/回滚策略。
- Go Module、Python/uv、pnpm、OCI Image、生成器和外部 Action 使用精确版本或 Digest；禁止 `latest`、宽松范围和未锁定 Git Branch。
- Blueprint/Contract Dependency Lock 在编译前验证；BuildProvenance、SBOM、SLSA Statement 和 Conformance Evidence 绑定相同输入。
- 构建不得依赖开发机未声明工具、未跟踪文件、网络返回的浮动内容或宿主机 Secret。
- 可重复构建只证明给定输入产物一致，不证明功能、集成、安全、可靠性或生产批准。
- 漏洞扫描结论必须绑定扫描器版本、数据库时间和 Artifact Digest；允许项有 Owner、Reason 和 Expiry。

## 15. Change 与 PR 规范

- 一个 PR 只交付一个可独立评审、测试和回滚的行为切片。架构、Contract、Application 和生产证据按所有权拆分，不用超大 PR 同时铺满后续 Phase。
- Commit 使用 Conventional Commits 风格并描述事实，不使用“production ready”“exactly once”等无证据结论。
- PR 必须说明：问题/范围、权威输入 Revision/Digest、事务/安全/兼容影响、Migration/回滚、测试证据、Traceability Check ID 和未证明属性。
- 数据库 PR 附 DDL、锁影响、Query Plan/Index 理由、RLS 正反向测试和 Upgrade/Rollback 分类。
- Temporal PR 附 Workflow 兼容策略、Replay 结果、Activity 幂等/Retry 和 Worker Build ID 推进方式。
- Provider/Runtime PR 附 Port/Profile、Token/Deadline/Fencing、Conformance Case 和失败对账路径。
- Review 优先检查事实所有权、越权、事务边界、未知结果、回滚和负向测试，再检查风格。
- 不在功能 PR 中顺手格式化无关文件、升级无关依赖或重构不相关模块。

## 16. Definition of Done

实现切片只有同时满足以下条件才可称为完成：

- 行为范围与明确的 Blueprint/Contract 责任一致；没有复制或放宽上游事实源；
- 依赖方向、语言边界、Tenant/ExecutionScope 所有权未被破坏；
- 成功、拒绝、冲突、超时、取消、未知结果和恢复路径均有明确语义；
- 权威写入的事务、CAS/Fencing、Idempotency、Outbox/Inbox 和审计边界可见且已测试；
- 格式、Lint、类型、Unit、Repository/Component 及所需 Conformance/Integration/Replay Gate 通过；
- Migration、配置、依赖、SBOM/Provenance、部署和回滚影响已更新；
- 新增实现责任已更新 Traceability Map，未实现项继续明确为未实现；
- 文档只陈述当前证据允许的成熟度，不把 Contract Gate、组件完成、E2E、0H、冻结或生产批准混为一谈；
- 工作树不包含生成缓存、Secret、临时证据、Bytecode 或未解释的大型制品。

## 17. Gate 落地顺序

规范可以先确定，但只有机器执行后才形成持续保护：

| 时点 | Application Gate 要求 |
|---|---|
| 当前 B01 已有 | Dependency Lock、精确 Toolchain/依赖、Go/Python 测试、可重复构建、SBOM/Provenance、Traceability |
| 首个 0B PostgreSQL PR | `gofmt`、`go vet`、Staticcheck、`sqlc vet`/生成一致性、空库 Upgrade/Rollback、真实 RLS/Repository/锁测试 |
| 首个 Temporal PR | Workflow Unit、History Replay、Activity Idempotency/Retry 与 Worker Build ID 证据 |
| Native Runtime Core 扩展 | Ruff Format/Lint、mypy 严格边界 Type Check、Component Test、`runtime-core-v1` |
| 首个 TypeScript Workspace | Prettier、ESLint、`tsc --noEmit`、Vitest、生成 DTO Diff、Playwright 边界测试 |
| Kubernetes Base 首次扩展 | 锁定 Kustomize/Kubernetes Schema 工具、Render、Server-side Dry Run 或等价 Schema/Policy 检查 |
| 0H | Race、Fault、隔离、容量、备份恢复和依赖丢失/重启证据 |

某项 Gate 尚未落地时必须明确记录为缺口，不能因本文已经写出规则而声称规范已被执行。
