# 契约验证报告 — v0.9.0

状态：**本地产品边界契约验证已通过；仓库/CI 集成不在本次架构审查范围内；候选版本尚未冻结，也未达到生产就绪状态**

验证日期：2026-07-17

| 检查项 | 本地结果 |
|---|---|
| 纯源码静态审计 | 通过：271 个 JSON、22 个 YAML、5 个 OpenAPI、46 个 Markdown 文件 |
| JSON Schema 与测试夹具 | 通过：143 个 Schema、79 个有效夹具、16 个 Schema 无效夹具 |
| 语义不变量 | 通过：6 个确定性且与 Schema 对齐的状态机，以及 60 个负向夹具 |
| 产品边界契约覆盖 | 通过：Conversation/Branch/Turn、Agent Runtime、Recording、Experience 准入和显式 CommercialAuthorization 绑定 |
| 契约清单 | 通过：157 项受治理资源；Python 3.11/3.13 与 Node 22.16 结果一致 |
| 兼容性比较器 | 自测通过；由于未提供已冻结的 Git 引用，本地基线为 N/A |
| Python JCS/Strict I-JSON | Python 3.11 和 3.13 通过 |
| Node JCS/Strict I-JSON | Node 22.16 通过 |
| Go JCS/Strict I-JSON | Go 1.23.2 linux/arm64 通过；gofmt 通过 |
| OpenAPI | 通过：5 份文档均为 0 个错误、0 个警告 |
| OpenAPI Bundle | 通过：5 个 Bundle，第二次生成结果逐字节一致 |

本次审查有意排除了仓库根 Workflow、隐藏文件策略和受保护 CI 变量。这不会削弱运行时验收边界：在作出任何生产声明前，Phase 0 仍需要真实 Migration、至少两个 Agent Runtime Adapter 的可替换性证据、Sandbox Adapter、故障注入、Temporal Replay、隔离、容量和恢复证据。
