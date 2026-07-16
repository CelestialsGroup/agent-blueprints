# 第一阶段范围

## Phase 0：架构骨架

- Monorepo
- Contract Schemas
- Go module boundaries
- Web shell
- Temporal local development
- PostgreSQL migrations
- Object Storage
- CI
- Architecture tests

## Phase 1A：最小 Work 流程

- ClientApplication
- InternalTenant mapping
- Service OAuth / WorkSession
- WorkOrder idempotency
- ExecutionGrant 单次消费
- Scenario registry
- CapabilityDefinition registry
- Capability Conformance
- Plugin Registry / approved permissions
- Deterministic Provider Resolver
- Temporal Workflow
- Invocation Ledger / Reconciliation
- DeerFlow Governed Runtime Adapter
- Model Gateway / Tool Gateway / Egress Gateway MVP
- Canonical Event
- SSE
- Technical Usage
- DeliveryPackage

## Phase 1B：Artifact

- Artifact
- ArtifactVersion
- ArtifactRelation
- Object Storage
- HTML Preview
- Text/Markdown/Code/HTML source edit
- EditSession
- ConversionJob
- html-to-pptx Fast Profile

## Phase 1C：参考业务应用

- 自有 User
- Personal Organization
- Free / Pro Plan
- Membership
- 商业 Entitlement
- 创建 WorkOrder
- 预留/结算业务额度
- WorkSession One-time Exchange / Cookie Session
- Agent Workbench 接入

## 不做

- 用户上传任意 Plugin
- 动态远程 UI Plugin
- 全量 Office 编辑器
- 所有 Artifact IR
- 自研 Workflow Engine
- 完整 Marketplace
- 智能成本路由
- 多区域容灾

## Phase 0 Kubernetes 基线

必须建立：

- `deploy/k8s/base`
- agent-api Deployment/Service
- agent-worker Deployment
- Migration Job
- Runtime Gateway 空壳
- NetworkPolicy 基线
- Probe
- PDB
- Resource Request/Limit
- Graceful Shutdown 测试
- 多副本 SSE 恢复测试骨架
- 多 Worker 幂等测试骨架
