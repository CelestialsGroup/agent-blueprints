# v0.9.0 交付路线图

`tasks/PHASE0.md` 是唯一 Phase 0 验收计划。Phase 1 只在真实纵向链路、第二 Runtime Adapter、故障测试和最小恢复证据完成后开始。

## Phase 0：纵向链路

实现一条经过 Business 授权、WorkOrder/Temporal、AgentRuntimeProvider、SandboxProvider、Invocation/Event、Artifact、RuntimeRecording、TechnicalUsage 和 Delivery 的真实 Conversation Turn 链路。目录、生成代码、Schema 或单次 Happy Path 不代表 Phase 0 完成。

## Phase 1A：产品能力补全

- 完善 Conversation 列表、归档、分支和 Context Builder
- 产品化 Experience Catalog 管理和 html-anything 导入器
- 接入 Open Design、motion-anything Renderer/Editor Profile
- 补全 html-to-pptx 和 html-video Converter Profile
- 完成 Terminal、Browser、Desktop Recording 和多通道回放
- 增加 Provider 管理、Draining、Canary 和跨 Provider 观测
- 评估 Native Runtime，但不将其预设为平台依赖

## Phase 1B：Business 产品化

- 完善账户、Organization、Membership 和恢复流程
- 增加套餐变更、发票、退款和计费运营
- 产品化 Reservation、Settlement、Release 和 Reconciliation
- 完善 Business UI、可观测性和 Workbench 交接体验

## 后续阶段

- Agent Engineering Workbench 的持久 Evaluation/Rubric 领域
- 自研 sandbox-runtime、影子验证、Canary 和 Provider 迁移
- 用户可安装 Plugin、Marketplace 和收入分成
- 智能成本路由和更大规模多租户容量治理
- 多区域双活和区域级灾难恢复

任意远程 JavaScript、未隔离 UI Extension 和未经验证的跨 Provider Checkpoint 恢复始终不属于默认开放能力。
