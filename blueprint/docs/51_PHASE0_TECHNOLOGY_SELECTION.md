# ADR 候选：Phase 0 技术选型与升级边界

状态：0A.1 候选接受。本文固定 0B 的实现方向，不把尚未运行的组件写成“已完成”或“生产可靠”。精确依赖版本在每个组件首次创建时取当日官方稳定版并写入 Lockfile、OCI Digest 和 BuildProvenance；禁止浮动 `latest`。

## 选择原则

优先级固定为：可靠性与数据正确性 > 安全与可恢复性 > 长期维护和人才生态 > 可观测与可测试性 > 性能 > 开发速度。框架不能替代领域契约、数据库不变量、幂等、Fencing、对账和授权边界。

## 组件选型矩阵

| 组件 | 首选 | 备选 | 不选 | 结论与成熟度/生态/运维/性能/安全/许可证/升级风险 |
|---|---|---|---|---|
| 仓库布局与 Node 包管理 | Blueprint、Contract、Application 独立版本化；Contract 与 Application 各自拥有依赖锁和 Gate；Application 内使用 pnpm Workspace | 后续按证据增加 Turborepo；Nx | 三者共享可变依赖树；npm/yarn 混用；Phase 0 引入 Bazel | Blueprint 为纯 Markdown，不参与产品 Workspace；Contract 与 Application 通过精确 Revision/Digest 连接。pnpm 生态成熟、MIT、磁盘效率高；Make 透明且运维低。 |
| Go 构建 | Go modules；需要多 module 时使用 `go.work` | 单一 Go module | 自建构建器 | 官方工具链、低运维、强可复现；Go 为 BSD-3-Clause。模块和工具链精确锁定，升级先跑 Replay/Conformance。 |
| Python 构建 | 每个 Adapter 独立 `pyproject.toml` + uv 锁；生产 wheel/OCI | pip-tools 摘要锁 | Poetry 作为跨仓统一控制面；共享可变虚拟环境 | uv 只管理 Python Adapter 依赖，不成为平台事实源；若 CPython 3.14 兼容性不足，ProviderRevision 可暂留 3.13。uv/依赖许可证在锁定时进入 SBOM。 |
| Agent Access API | Go `net/http` + chi v5；OpenAPI-first | Connect/gRPC 仅内部实验；Gin | 重型全栈框架；GraphQL 作为主写 API | `net/http`/chi 小而稳定、人才多、性能和取消语义清晰；chi MIT。公共协议继续是 HTTP/OpenAPI，避免框架模型渗入领域。 |
| Workbench BFF | Next.js 同源 Route Handler 只处理 Cookie/CSRF/一次性交换 | 独立 Go edge BFF | BFF 保存 WorkOrder/Session 真相 | BFF 不拥有领域状态；服务端 Cookie 降低浏览器 Token 暴露。若 Next 升级风险上升，可无数据迁移替换。 |
| 领域内核 | Go 模块化单体，按 ownership package 分区 | 出现独立故障域后拆服务 | Phase 0 预拆大量微服务 | 编译时依赖可见、事务边界清晰、部署简单；通过 Port 隔离 Runtime/Sandbox/Provider。 |
| PostgreSQL 访问 | pgx v5 + sqlc；显式事务和 SQL | database/sql + pgx driver | 通用 ORM 作为账本/状态机事实源 | pgx/sqlc 均成熟、MIT；SQL/RLS/锁行为可审查，性能可预测。生成查询代码可重建，领域层不暴露 pgx 类型。 |
| Migration | goose v3 的 SQL-first Migration；独立 Job | golang-migrate | 应用启动自动迁移；ORM auto-migrate | goose/golang-migrate 均成熟、MIT；选择 goose 因 SQL/Go migration 与顺序管理简单。生产必须 expand -> backfill -> verify -> contract，回滚按 migration 证据决定。 |
| RLS | PostgreSQL 原生 RLS +事务内 `SET LOCAL` TenantContext | 独立数据库/Schema 做更强隔离等级 | 仅 Repository WHERE 条件 | RLS 是纵深防御，不替代应用授权；连接池归还前事务结束。策略、FK、Unique 和触发器由 Migration 与数据库集成测试证明。 |
| Outbox/Inbox | PostgreSQL 事务表 + `FOR UPDATE SKIP LOCKED` dispatcher | 成熟后评估 Debezium/Kafka Connect | DB + broker 双写；Redis Stream 作事实源 | Phase 0 运维低、可对账；吞吐证据不足再引入 CDC。至少一次、幂等和 Fencing 保持不变。 |
| Temporal | Temporal Server/Cloud + Go SDK；Worker Build ID/Deployment Versioning | 自建持久状态机仅用于局部短流程 | Celery/Redis 队列替代持久编排；框架 Checkpoint 作平台 History | Temporal 生态和长任务恢复成熟、MIT；运维中高。服务端与 SDK 分别精确锁定，Workflow Replay、Patch、Continue-as-New 和双 Worker 版本是升级前置。 |
| Native Runtime | Python Agent Loop/Context/Skill 层 + Go Platform/Gateway 边界，通过 AgentRuntimeProvider 独立部署 | 全 Go Runtime Core；Python Capability Worker | 直接拿 DeerFlow、Dify 或其他完整项目当产品 Runtime | 自研 Native Runtime 是正式主实现。Python 适合 Agent/模型生态，Go 负责治理、账本和强制 Gateway；内部框架可替换，公共 Port 不变。0B 先实现 Core Profile，0D 扩展 General/Governed。 |
| Adapter SDK | OpenAPI/JSON Schema 生成模型 + 手写薄 Port SDK；共享 JCS 向量 | 后续发布 Go/TS SDK | 跨语言共享数据库包；复制领域模型 | SDK 不拥有事实，只处理鉴权、摘要、错误、Cursor 和 Conformance。SDK major 与 Port major 对齐，生成代码不可手改。 |
| Reference Runtime Probe | 独立 Go 最小 Provider，只实现 `runtime-core-v1` | 第二个极简 Python Provider | 为证明抽象而适配完整第三方项目 | 只验证 Port/Recovery/Workbench 不依赖 Native Runtime 内部模型，不承担产品能力或第三方兼容承诺。 |
| 第三方 Agent 项目 | 锁定 Tag/Commit 研究模块边界、算法、功能和 UX | 周期性冻结新的只读研究快照 | Fork、包装或整体适配 DeerFlow/Dify/OpenHands 等 | 参考结论进入 ADR/Feature Radar；源码复用必须另做许可证、来源、安全和升级审查。参考不等于依赖或适配。 |
| Dify 参考 | 当期最新稳定 Tag/Commit 只作 Workflow、Plugin、RAG、契约生成和 SSE 参考 | Dify 2 Beta 只作 Knowledge Pipeline、Graph 模块和产品 Feature Radar | 整体嵌入或连接 Dify；复制前端；以 Dify Agent、Redis Run Store、Graph Engine 或 Local Sandbox 替代平台组件 | 2026-07-21 稳定参考为 `1.16.0@5c6372d`；`2.0.0-beta.2@2a84832` 创建更早且代码谱系分叉，不能因版本号更大而视为更稳定。修改版 Apache-2.0 存在多租户和前端附加限制，因此只提炼设计结论并由平台重新实现。 |
| Capability/Model/Tool/MCP Gateway | Go 服务实现统一 `capability-provider-v1`、Policy、Ledger 与限额；Provider connector 可用官方 SDK | 受控 LiteLLM/远程 MCP 作为 Connector | 让 Runtime 直连模型/工具；把 LiteLLM/MCP SDK 设为事实源 | 核心执行与审计留在平台；第三方 SDK 可替换。MCP transport/版本由 ProviderRevision 固化，未知能力 fail-closed。 |
| Sandbox Phase 0 | 平台 SandboxProvider + Native Controller/隔离执行后端 | Kubernetes Provider Adapter、远程 VM Provider | 包装第三方 Agent 项目的本地 Sandbox；把 Pod/VM/Endpoint 写入稳定模型 | 先验证 Port、隔离与对账，后端私有标识不外泄。Provider 独立升级/Draining。 |
| Sandbox Controller | Go controller；Kubernetes 后端使用 controller-runtime | sandbox-runtime；远程 VM Provider | Agent API/普通 Worker持有集群管理员权限 | controller-runtime 生态成熟、Apache-2.0；仅 Controller 有最小 RBAC。Phase 0 可先不部署自建 Controller。 |
| Runtime Gateway | Go `net/http` +维护中的 WebSocket 库；不透明路由表 | Envoy 扩展用于纯代理层 | API Pod 粘性代理；暴露 Sandbox 原始 Endpoint | Gateway 自己执行 Generation/Sequence/ACK/Token/Recording Gate。WebSocket 库在实现时核验维护状态和许可证并精确锁定。 |
| SSE | Go HTTP streaming + PostgreSQL Cursor 补拉 + Redis/Valkey 唤醒 | NATS 仅在容量证据后 | Redis Pub/Sub 作为 Event 真相 | SSE 可跨 Pod 重连；丢唤醒后按 `work_sequence` 补拉。标准库实现运维低。 |
| Recording | Gateway 内存有界缓冲 -> Scrub/Schema Gate -> Artifact Staging -> Chunk Manifest | 专用媒体 Worker | 原始帧先落对象存储再异步脱敏 | 默认 fail-closed；Terminal 先支持 asciicast，Browser/Desktop 在容量/隐私证据前关闭持久录制。 |
| Object Storage | 生产使用云 S3 兼容服务 + AWS SDK for Go v2；本地 MinIO | 其他经兼容测试的 S3 服务 | 数据库 Large Object 保存 Artifact/Recording Blob | S3 生态成熟；对象键不作为授权。MinIO AGPLv3 仅作本地候选，生产供应商与许可证在 Phase 1 决定。 |
| Redis 类服务 | Phase 0 本地 Redis；仅 Cache/Presence/Wakeup | Valkey | Redis 持有账本、授权、唯一 Cursor | 两者可通过非权威 Cache Port 替换；Redis 当前许可证必须由法务在生产选型时确认，故生产供应商不在 0A 冻结。 |
| Agent Workbench | Next.js + React + TypeScript；TanStack Query；xterm.js；Playwright | React Router/Vite SPA | 前端解释 Provider 私有事件；本地状态作事实源 | React/Next 生态和人才充足、MIT；精确版本在 scaffold 时锁定。服务端状态来自 REST/SSE/Gateway，UI 状态库可替换。 |
| Business Reference | 独立 Go API + Next.js UI +独立 PostgreSQL/签名密钥 | 现有 Business App 测试租户 | 与 Agent Platform 共库/共 Migration | 用最小 Product/Entitlement/Quota/Grant/Settlement 链证明双事实源，不作为正式计费产品。 |
| 身份与 JWS | OIDC/OAuth 2.0；Go `go-jose/v4`；独立 typ/aud/iss/kid allowlist | Keycloak 仅本地 IdP；企业 IdP | 自建密码系统；Header 动态 JWKS URL；浏览器 localStorage 长 Token | `go-jose` Apache-2.0，Keycloak Apache-2.0。签名/验证分权，短期 Token，Key Rotation 双 Key 窗口。 |
| 密钥管理 | 生产云 KMS/HSM 或 Vault；Kubernetes 只拿短期身份 | SOPS/age 管非运行时配置 | Git 明文 Secret；长期 Provider Key | 供应商推迟到生产，但 Key ID、轮换、撤销、审计接口现在固定。Vault MPL-2.0；云服务许可证/合规单独评审。 |
| Telemetry | OpenTelemetry SDK/Collector；Go `slog`；Prometheus metrics | Vendor exporter | Vendor SDK 侵入领域；记录 Prompt/Token/代码正文 | OTel/Prometheus Apache-2.0；Collector 隔离供应商。闭合 Attribute Registry 与双重脱敏 fail-closed。 |
| Trace/日志 UI | Tempo/Loki/Grafana 作为本地/运维候选 | 商业 APM | 第三方 Trace 作执行或计费事实源 | 只消费 Telemetry；许可证与托管方式在 Phase 1 法务评审。RuntimeRecording/CanonicalEvent 仍是独立证据。 |
| Contract codegen | Go oapi-codegen；TS openapi-typescript；Python Adapter 用 Pydantic v2/生成器并跑同一夹具 | OpenAPI Generator | 三套手写 DTO；生成代码成为领域事实源 | 生成器版本锁定并隔离在 generated 目录；Schema/OpenAPI 是源。生成前后执行 Bundle/JCS/兼容性测试。许可证在首次锁定时写入 SBOM。 |
| 测试与故障注入 | Go test/Testcontainers、pytest/Hypothesis、Vitest、Playwright、Temporal Replay、Toxiproxy | kind/k3d 集成环境 | 只有 mock/单次 Happy Path | Toxiproxy MIT；本地 Docker 固定 Postgres/Temporal/Redis/MinIO 镜像 digest。真实故障证据到 0H 才可声称完成。 |
| Kubernetes 发布 | Deployment/Stateful 依赖托管服务、Migration Job、Helm/Kustomize 中择一并固定 | Argo Rollouts/Argo CD 在生产阶段 | Pod 身份作领域 ID；应用启动迁移；所有逻辑 Worker立即拆 Deployment | Kubernetes Apache-2.0。0B 先维持最少工作负载；Canary、PDB、Topology、NetworkPolicy、最小 RBAC 在生产 Gate 验证。 |

## Dify 双轨参考基线

- 稳定代码轨：每次实施检查点只审阅当期最新正式稳定 Tag，记录完整 Commit、发布日期、镜像 Digest、许可证与安全公告；不追随 `main`、RC、Beta 或浮动镜像。当前调研快照为 `1.16.0@5c6372d2f76d240265b92fd27c16bc772ffcb107`。稳定 Release 中仍标为 Beta 的子功能继续按 Beta 治理；Dify Agent 不能继承 `1.16.0` 整体的稳定性标签。
- Feature Radar 轨：Dify 2 Beta 的 Knowledge Pipeline、Graph 模块、Agent/Workflow Builder 只用于识别产品和模块候选。当前 `2.0.0-beta.2@2a84832998b4a005373859a82919a62a1bbbec42` 早于稳定快照且已分叉，不能直接回移代码或据此宣称成熟。
- 实现轨：被采纳的行为在产品实现仓库中按 Blueprint 的 Scenario、ProviderRevision、Temporal Workflow、CanonicalEvent、Artifact、Usage 和 Workbench 契约重新实现；Dify 原生 Tenant、WorkflowRun、Thread、Snapshot、Redis Event、SQLite/tmux 或 Endpoint 不进入稳定事实源。
- 非连接边界：当前不规划 Dify Workflow、Agent、MCP 或 Sandbox Provider；通用 Provider Port 继续为平台自有实现和未来独立需求服务，不能反向推导出第三方适配承诺。

## 推荐总体栈

```text
Implementation repository: pnpm Workspace + Make
  app/agent-workbench        TypeScript / Next.js
  app/business-reference     TypeScript / Next.js UI

Go 1.26.5
  agent-access + domain kernel + pgx/sqlc + goose
  Temporal workers + Outbox/Inbox dispatchers
  Capability/Artifact/Egress/Runtime Gateways
  Reference Runtime Contract Probe + Sandbox Controller

Python 3.14.6 primary, 3.13 compatibility channel
  Native Runtime Core/General/Governed
  Agent/Model ecosystem workers behind platform-owned Ports

PostgreSQL + Temporal + S3-compatible Object Storage
Redis/Valkey only for Cache, Presence and Wakeup
OpenTelemetry Collector + Prometheus-compatible metrics
```

Node 固定 Active LTS 24.18.0 与 pnpm 11.15.1。Node Current 不进入生产基线。所有库、镜像和 Helm Chart 首次引入时必须使用精确版本或 Digest，不接受 `^`、`~`、`latest` 或未锁定 Git branch。

## 语言边界

Go 负责稳定内核、SQL 事务、Temporal Workflow/Activity、Outbox/Inbox、Gateway、Controller 和 Native Probe。这些组件共享同一错误分类、TenantContext、Fencing 和 Observability 基础库，但不共享可变全局状态。

TypeScript 只负责 Workbench、Business Reference UI、BFF Cookie 边界和契约开发工具。BFF 不直写 Agent 数据库，不执行 Workflow，不成为 Event/Session 真相。

Python 只负责确实依赖 Python Agent/ML 生态的 Runtime/Capability Adapter。Adapter 通过版本化 HTTP Port、短期 Token 和标准 Event/Artifact/Usage 交接，不能读取平台数据库或 Temporal Persistence。

多语言是有意的，但限制为三种。跨语言只共享 OpenAPI、JSON Schema、Conformance Suite、JCS 向量、Error taxonomy 和 Telemetry conventions；不共享数据库表模型、框架对象或可变源码包。公共 Port v1 不在 Phase 0 改为 gRPC，以免同时维护两套权威传输契约。

## 升级通道

| 类型 | 隔离与并行 | Canary 证据 | Rollback |
|---|---|---|---|
| API/Schema | Contract major + media type；旧读/新写窗口 | 消费者契约、旧载荷、双版本请求 | 路由回旧 API；禁止回滚已提交的数据含义 |
| PostgreSQL | expand/backfill/verify/contract | 影子读、行数/摘要/约束核对 | 回旧代码只发生在 expand 兼容窗；破坏性 cleanup 延后 |
| Temporal | Workflow type/version、Patch、Worker Build ID | 历史 Replay、Canary Task Queue、History/latency | Drain 新 Build；旧 Build 保留到所有 pinned execution 结束 |
| Provider/Adapter | immutable ProviderRevision + BuildProvenance | Resolution 按 Tenant/Scenario 百分比；Suite Evidence | Admission Decision 设 draining/revoked，新 Run 回旧 Revision；旧 Run不切换 |
| Runtime checkpoint | Provider 声明兼容区间 | 恢复/重启/丢响应测试 | 不兼容时只允许新 Run；原证据只读 |
| Gateway | Port contract digest + route generation | 影子验证、拒绝率、预算与对账差异 | 路由回旧 Revision；Fencing 阻止迟到响应 |
| 前端 | API capability negotiation | 小流量/租户 Canary、Playwright | 静态资产回滚；服务端 Contract 保持兼容 |
| 语言/依赖/镜像 | Lockfile + OCI Digest + SBOM + Provenance | 双版本 CI、Conformance、漏洞和性能基线 | 保留旧 Artifact Digest；不得重打同一 tag |

## 冻结时点

现在固定：三语言边界、pnpm、Go 平台内核、自研 Native Runtime 主线、PostgreSQL/Temporal/对象存储/非权威 Redis 分工、HTTP/OpenAPI Port、pgx/sqlc/SQL-first Migration、Native Runtime Core 先行、独立 Reference Probe、Gateway 强制中介、OTel、ProviderRevision/BuildProvenance 升级模型，以及第三方项目“稳定 Tag/Commit 作代码参考、Beta 只作 Feature Radar”的版本策略。

仅作 Phase 0 候选：Native Runtime 内部 Agent Loop/Context/Skill 库、Python/TS 生成器、WebSocket 库、MinIO/Redis 本地镜像、Sandbox Kubernetes Adapter、Next/React 精确依赖版本。它们首次实现前完成维护状态、许可证、CPython/Node 兼容性和安全审查。

推迟到 Phase 1/生产：可复用 Agent Roster/可视化 Workflow Builder 的产品范围、Temporal Cloud 或自建拓扑、云 PostgreSQL/S3/KMS 供应商、Redis 或 Valkey、Kubernetes 发行版、Service Mesh、GitOps/Rollout Controller、跨 Region/Cell、GPU/MicroVM 后端和观测供应商。第三方 Agent 项目保持只读参考，不列入实施阶段。

## 七项缺口与技术落点

| 架构缺口 | 契约修复 | 实施落点 |
|---|---|---|
| Runtime Start 只有摘要 | RunManifest/Start 固化输入、Context、Grant、预算/策略/权限与 Gateway Binding | Go Admission Builder 原子创建 Manifest；Adapter fail-closed |
| Turn 与 Append/Interrupt 冲突、Branch 假 CAS | TurnRequest 与 ControlRequest 分离；Message/Workspace/Active Work 三个 CAS | PostgreSQL 独立版本列、条件 UPDATE 与 Outbox |
| Capability Port/Token 不完整 | `capability-provider-v1`、操作描述符、Contract/Profile/Digest 和前驱 Token | Go Gateway +各语言薄 Adapter SDK；重放防护由 Conformance 证明 |
| Tenant/Principal/Idempotency/Resolution 所有权 | Tenant + ClientApplication + WorkOrder/ArtifactOperation ExecutionScope、Principal Snapshot 与 Idempotency scope | RLS、Unique Index、事务 TenantContext；不靠框架默认中间件 |
| accepted 不能取消 | WorkOrder 状态机已有直接取消意图迁移 | Repository compare-and-set +结构化 Event |
| Workspace Manifest/多 Sandbox Slot | 独立 Content Manifest、`sandboxes[]`、`sandbox_slot_key`、不透明 Runtime Route | Artifact 校验、Slot-scoped Session、Controller 私有 Endpoint |
| Event Registry/来源去重/Metadata/大小上限 | 双 Registry、Source identity/Dedupe、闭合 Metadata、encoded-body limit | Inbox Unique、413 pre-parse middleware、Projection allowlist |

补充安全闭合：Egress 使用不可变、owner-scoped `EgressDestinationRevision`，权限比较 `destination_class`；Runtime、Capability、兼容 Plugin、Sandbox、Artifact 与 Egress 的执行 Token 必须完整落在实际授权时间窗内。Runtime/Capability/Plugin `safety_control` 只保留到期后的读取、取消和对账能力，不能恢复执行、访问过期 Artifact Grant 或产生新副作用。平台自动止损不能依赖新的 Business Grant：Agent Access 接受 sender-constrained、幂等的 Business Revocation Notice；收据同步拒绝新授权并为 WorkSession、WorkOrder、ArtifactOperation 和 ArtifactIngest 持久化可恢复 CAS/Outbox intents。WorkOrder 由 Go Safety Controller Domain Activity 仅追加 `SystemSafetyControl + Platform Event + Outbox`，并由 Runtime Command/Token 绑定同一 Tenant/WorkOrder/RuntimeRun/action/digest；ArtifactOperation/Ingest 按自身状态机 reduction-only Cancel。Safety Controller 可先作为 Worker 内模块，只有它拥有 Runtime 安全控制签发权限；该技术落点不改变 Business/Platform 事实源边界。以上问题由契约和实施责任共同关闭，任何框架选型都不能替代数据库与运行证据。

## 0A.1 到 0B

1. 完成 Contract Gate、双次 Bundle 确定性、Python 3.14/3.13、Node/pnpm、Go JCS 和 `git diff --check`。
2. 记录“架构/契约验证通过”，不记录“组件已实现”。
3. 0B-1 建仓库骨架、锁定首次依赖与镜像，将许可证/SBOM/Provenance 写入构建证据。
4. 0B-2 实现 PostgreSQL Migration/RLS/Repository/Outbox/Inbox、AgentRuntimeCommand/SystemSafetyControl Ledger，并提供空库升级、兼容回滚和 Redis 清空测试。
5. 0B-3 实现 Temporal Workflow/Activity、Safety Controller 与 Replay；先接 Native Probe，通过含 fenced 系统 Cancel 的 `runtime-core-v1`。
6. 0C 先完成 Business Reference 到 Conversation/WorkOrder 的双事实源链路，以及 CommercialAuthorizationRevocation、WorkSession deny/revoke 和覆盖所有活动 AgentRun 的可恢复 fan-out。
7. 0D 将 Native Runtime 从 Core 扩展到 General/Governed 并完成平台 SandboxProvider；0E 完成 Gateway、Artifact、SSE、Recording 与 Workbench；0G 用独立 Reference Probe 验证 Port 可替换性；0H 才形成故障和恢复证据。

四种结论必须分开：Architecture/Contract Gate 只证明设计内部一致；组件测试证明单组件实现；端到端证据证明集成链路；容量、隔离、故障注入、Replay 和恢复演练才证明生产可靠性。

## 官方依据

- Go release policy 与下载：<https://go.dev/doc/devel/release>、<https://go.dev/dl/>
- Node release schedule：<https://github.com/nodejs/Release>
- Python releases：<https://www.python.org/downloads/>
- pnpm：<https://pnpm.io/installation>、<https://pnpm.io/workspaces>
- PostgreSQL RLS/locking：<https://www.postgresql.org/docs/current/ddl-rowsecurity.html>、<https://www.postgresql.org/docs/current/explicit-locking.html>
- Temporal Versioning/Replay：<https://docs.temporal.io/production-deployment/worker-deployments>、<https://docs.temporal.io/develop/go/testing-suite>
- OpenTelemetry：<https://opentelemetry.io/docs/collector/>；Kubernetes：<https://kubernetes.io/docs/concepts/workloads/controllers/deployment/>
- RFC 8785 JCS、RFC 9068 JWT Access Token Profile 与 OpenAPI 3.1.1 保持为协议依据。

外部项目的具体维护状态、许可证或 CPython 3.14 支持若未在仓库锁定 Commit/Release 上核验，本文明确视为未知，不以项目首页或“latest”标签推断。
