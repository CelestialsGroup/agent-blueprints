# Blueprint、Contract、Application 与辅助工具边界

状态：候选治理规则。

## 1. 三个独立产品

### Blueprint

Blueprint 是纯 Markdown 的架构与工程规范产品，负责：

- 领域边界、事实所有权、控制面/执行面和可靠性语义；
- 技术选型、语言边界、数据不变量、安全规则和开发规范；
- Phase 范围、入口/退出条件、成熟度分层和人工验收标准。

Blueprint 不拥有 Schema、OpenAPI、状态机 JSON、Fixture、验证脚本、产品源码、Migration、部署物或运行证据。

### Contract

Contract 是声明式机器规范产品，只负责：

- JSON Schema、OpenAPI、状态机、Event Registry 和 Semantic Constraints；
- 正向/反向 Fixture、Conformance Suite、兼容性 Manifest 和 Digest；
- 解释这些资源所需的 Markdown 说明。

Contract 只允许 Markdown、JSON 和 YAML。它不拥有校验器、生成器、Makefile、依赖清单、锁文件、构建产物、Gate 报告、产品实现、数据库 Migration、CI 或生产部署配置。它可以使用稳定 Blueprint URN 分配规范责任，但不得依赖 Blueprint 或 Script 的目录名和共同 Git History。

### Application

Application 是产品实现，负责：

- 服务、Worker、Native Runtime、Sandbox、Gateway 和 Workbench 源码；
- PostgreSQL Migration/RLS/Repository、Temporal Workflow、Outbox/Inbox 和 Ledger；
- 依赖锁、生成代码、容器、Kubernetes 配置和发布流水线；
- DDL、组件、Conformance、集成、Replay、故障与恢复证据。

Application 通过 `AGENT_BLUEPRINT_ROOT` 读取人类规范，通过 `AGENT_CONTRACT_ROOT` 读取机器契约。不得复制并修改 Contract 形成第二套 Wire Contract。

### Contract Scripts

Contract Scripts 是辅助工具包，不是第四个权威产品。它负责校验器、生成器、兼容性比较器、依赖锁、临时构建物和 Contract Gate 报告。它通过 `AGENT_CONTRACT_ROOT` 与 `AGENT_BLUEPRINT_ROOT` 读取显式 Checkout；`../contract` 和 `../blueprint` 只允许作为本地默认值。

Contract Scripts 可以被替换或独立升级，但替换后必须对同一锁定 Contract Revision 产生等价 Gate 结论。Contract 中的语义责任以稳定 Validation URN 表示，不能写入脚本文件路径。Script 的版本、代码和报告都不是 Contract 资源，不能改变 Contract 的含义。

## 2. 依赖方向

```text
Blueprint revision
        |
        +------> Contract revision + manifest/suite digests
        |                         |
        +-------------------------+------> Application dependency lock
                                                  |
                                                  v
                                    implementation and runtime evidence

Contract Scripts revision -- validates --> locked Blueprint + Contract inputs
                          -- produces  --> external Contract Gate evidence
```

Blueprint 不依赖 Contract 构建产物、Script 或 Application 源码。Contract 是 Blueprint 的声明式投影，不依赖某套校验代码。Application 同时消费 Blueprint 规则和 Contract 资源。当前同一 Git 根下的兄弟目录只是开发便利，不是稳定接口。

## 3. 不可变消费绑定

Contract 发布证据必须记录 Blueprint 的精确 Source Revision、Contract 的精确 Source Revision、Contract Manifest Digest，以及执行 Gate 的 Script Revision。Application 的 CI、BuildProvenance 和 Conformance Evidence 必须记录：

- Blueprint 的完整 Source Revision；
- Contract 的完整 Source Revision；
- 外部 Gate Evidence 中的 Contract Manifest Digest；
- 实际消费的 Conformance Suite ID、Version、Digest 和 Profile；
- 通过发布制品消费时的制品内容摘要。

分支名、`main`、`latest`、相对路径和可变 Release 标签不能单独构成依赖锁。生成代码必须能从锁定 Contract 重建；实现私有 DTO、Migration 和 Adapter 必须显式映射公共契约。

## 4. 变更流

1. 架构意图、所有权、可靠性、安全或验收责任变化，先修改 Blueprint 并完成文档评审。
2. Wire 行为变化，在独立 Contract 变更中同步 Schema/OpenAPI/状态机、语义约束、Fixture、Conformance 和兼容性 Manifest。
3. 锁定的 Contract Scripts 对锁定 Blueprint/Contract 输入运行 Gate，并在 Script 或发布治理系统中产生证据。
4. Gate 通过并产生新 Contract Revision/Manifest Digest 后，Application 才升级依赖锁。
5. Application 完成生成代码、Migration、组件、集成、Replay 和故障测试，并记录独立证据。
6. 纯实现重构不修改 Blueprint/Contract；实现若必须放宽上游约束，应停止并回到对应上游变更。

跨仓变更不得依赖提交顺序或共同 Commit History。PR 必须明确列出前驱 Revision/Digest 和兼容性影响。

## 5. Gate 与成熟度

| 结论 | 权威位置 | 最小证据 |
|---|---|---|
| Contract Gate 通过 | Contract Scripts/发布治理 | 绑定锁定 Contract Revision 的 Schema/语义/状态机/JCS/OpenAPI/Manifest 与候选兼容性结果 |
| 0B 实现完成 | Application | Persistence/Runtime Core 组件、数据库事务、Replay 与 Core Conformance Evidence |
| 0C-0G 集成完成 | Application | Business 纵向链、主 Runtime/Sandbox、Workbench、Experience 与 Reference Probe 验收 |
| 0H 可靠性证据 | Application/运行环境 | 故障、安全、隔离、容量和恢复报告 |
| 正式冻结 | Blueprint + Contract 治理 | 公共 CI、受保护基线、消费者兼容性和人工批准 |
| 生产批准 | 发布治理系统 | 独立 SLO、安全、容量、恢复和变更批准 |

这些结论互不替代。Blueprint 定义目标，Contract 定义机器约定，Contract Scripts 证明选定约定内部一致，Application 证明实现行为；任何一层全绿都不能自动提升下一层成熟度。
