# 交付路线图 — v0.9.0

`tasks/PHASE0.md` 是唯一的 Phase 0 验收计划。本文描述其后的工作，不得把 Phase 0 重新定义为目录或 Schema 骨架。

## Phase 0：契约准入的纵向链路

实现一条真实 Conversation Turn 链路，依次经过 Business 授权、WorkOrder/Temporal、已认证 AgentRuntimeProvider、已认证 SandboxProvider、Invocation/Event、Artifact、RuntimeRecording 和 Delivery。DeerFlow 可作为主参考 Adapter，但进入 Phase 1 前还必须完成第二个最小 Runtime Adapter、故障和回放证据，以证明平台不依赖单一框架。

## Phase 1A：产品能力补全

- Conversation 列表、归档、分支体验和 Context Builder Provider；
- Experience Catalog 管理和 html-anything 模板导入器；
- Open Design/motion-anything Renderer/Editor 集成 Profile；
- html-to-pptx 和 html-video Converter Profile；
- Terminal/Browser/Desktop 的完整 RuntimeRecording 回放；
- Provider 管理、Draining 和升级 Canary 界面。
- Agent Runtime 选型矩阵、Provider 对比观测和 Native Runtime 可行性评估。

## Phase 1B：参考 Business Application

- 将 Phase 0 的参考身份/会员流程产品化，补充账户管理与恢复；
- 增加组织成员关系、套餐升降级、发票/退款和计费操作；
- 暴露 Reservation/Settlement/Release/Reconciliation 操作及支持工具；
- 补全 Business UI 导航、可观测性和 Agent Workbench 交接体验。

## 延后事项

- 用户上传的任意 Plugin；
- 任意远程 JavaScript 或未隔离的 UI Extension；
- 完整 Office 编辑套件；
- 完整 Marketplace 与收入分成；
- 智能成本路由；
- 多区域双活灾难恢复。
