# 契约验证报告 - v0.9.0

状态：**本地 Architecture Contract Gate 已通过；组件实现、集成链路、生产可靠性与正式冻结均未完成**

验证日期：2026-07-20

本报告由 `scripts/generate_validation_evidence.py` 从本次成功 Gate 的 `build/validation/*.json` 生成；`VALIDATION.json` 是同源机器结果，不手工维护计数。

| 检查项 | 本地结果 |
|---|---|
| 纯源码静态审计 | 通过：513 个 JSON、26 个 YAML、8 个 OpenAPI、47 个 Markdown 文件 |
| JSON Schema 与夹具 | 通过：214 个 Schema、196 个有效夹具、67 个 Schema 负例 |
| 语义不变量 | 通过：6 个状态机、179 个语义负例 |
| 语义追踪 | 通过：41 个关键 Schema、193 条约束、175 个 Contract Gate 映射、122 个本次执行 Check ID、59 个 Phase 0 DDL/Conformance 责任 |
| Core Event Registry | 通过：Platform 18 类、Agent Runtime 16 类闭合 Event Type；CanonicalEvent 按 Producer 所有权绑定对应 Registry |
| 契约清单 | 通过：239 项受治理资源；Python/Node 一致 |
| OpenAPI | 通过：8 份文档，0 Error / 0 Warning |
| Bundle | 通过：8 个 Bundle，连续两次逐字节一致 |
| JCS / Strict I-JSON | Python：CPython 3.13.14, CPython 3.14.6；Node.js 24.18.0；Go/gofmt 均通过 |
| 兼容性 | 比较器自测通过；尚无冻结基线，显式记为首次冻结前 N/A，不记为兼容性通过 |
| 仓库/供应链/公共 CI | 本轮延后，不计入 Architecture Contract Gate 通过条件 |

本次 Gate 已验证请求与授权绑定、Turn/Control 与 CAS 分离、sender-constrained Business 撤销、Platform-only fenced SafetyControl、用途隔离的闭合 JWS Header/Claims Profile、Runtime/Sandbox/Egress 时间窗、Runtime/Capability/Plugin/Sandbox/Artifact/Egress 单操作 Contract/Profile/Digest、读路径与 Cursor、不可变 EgressDestinationRevision、按 Destination Class 授权、不透明 RuntimeSessionRoute、逻辑 Placement、Workspace Manifest、按 Producer 所有权绑定的双 Event Registry、来源去重、有界 Metadata、全部 JSON 写接口解析前大小上限和可执行语义追踪。

该结论仅为“架构/契约验证通过”。仓库仍没有真实 Agent Platform 组件，因此不能声称组件实现完成；Business -> Conversation -> Temporal -> Runtime/Sandbox -> Event/Artifact/Usage/Recording 的纵向链尚未完成；多租户隔离、故障注入、容量、SLO、Temporal Replay、备份恢复和密钥轮换也尚未提供生产证据。

GitHub CI、仓库供应链准入和受保护冻结基线按当前阶段明确延后。首次正式冻结前，兼容性基线缺失可以显式 N/A；冻结后必须 fail-closed。
