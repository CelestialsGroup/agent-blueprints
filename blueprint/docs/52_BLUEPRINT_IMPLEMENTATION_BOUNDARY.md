# Blueprint 与实现边界

状态：v0.9.0 候选治理规则。

## 1. 职责分离

Blueprint 是独立版本化的架构与工程规范产品，负责：

- 领域边界、事实所有权、控制面/执行面和可靠性语义；
- Schema、OpenAPI、状态机、Event Registry、Semantic Constraints 和 Conformance Suite；
- 技术选型、语言边界、数据不变量、安全规则、开发规范和验收门槛；
- 用于验证设计的 Fixture、参考配置和可执行架构 Profile。

Blueprint 不负责：

- Agent Platform 产品源码、数据库 Migration、生成代码和 Runtime 私有实现；
- 可部署镜像、环境 Overlay、发布流水线和生产配置；
- PR、Issue、迭代进度或某个实现仓库的实时完成状态；
- 将某次组件测试、集成测试或生产运行结果提升为架构事实。

实现仓库负责产品代码、Migration、部署物、依赖锁、组件测试、集成测试和运行证据。Blueprint 中的 `deploy/`、`examples/` 和 `prompts/` 只属于架构 Profile、契约 Fixture 或开发规范，不是可直接发布的产品实现。

## 2. 单向依赖

依赖方向固定为：

```text
Blueprint release/revision
        ↓
Implementation dependency lock
        ↓
Generated bindings / DDL / components / tests / evidence
```

实现可以依赖 Blueprint，Blueprint 不得依赖实现源码、实现包、实现数据库或实现 CI 产物。实现便利不能反向改写领域所有权、可靠性、安全或兼容性边界。

当前可将 Blueprint 与实现放在同一 Git 根的兄弟目录中，本地工具也可以使用相对路径定位；这只是开发便利，不是稳定接口。拆成两个仓库后，必须能通过显式路径、只读 Checkout 或内容寻址制品消费同一 Blueprint，不得要求固定目录名或共同 Git History。

## 3. 不可变消费绑定

实现仓库的 CI、BuildProvenance 和 Conformance Evidence 必须记录：

- Blueprint 版本；
- Blueprint 完整 Git Commit SHA 或等价不可变 Source Revision；
- `VALIDATION.json` 中的 Contract Manifest Digest；
- 实际消费的 Conformance Suite ID、Version、Digest 和 Profile；
- 若通过发布制品消费，制品自身的内容摘要。

分支名、`main`、`latest`、相对路径和可变 Release 标签都不能单独构成依赖锁。实现可以声明兼容版本范围，但每次 CI、构建、测试和发布都必须解析到一个精确 Revision 与 Digest。

实现仓库不得复制并修改 Blueprint 契约。生成代码必须可由锁定的 Blueprint 重建；必须存在的实现私有 DTO、Migration 和 Adapter 只能通过显式映射与公共契约连接，不能成为第二套 Wire Contract。

## 4. 变更流

1. 实现发现契约缺口时，先在 Blueprint 中提出可独立评审的架构或契约变更。
2. Blueprint 完成影响分析，并按需要同步 Decision、Schema/OpenAPI、状态机、语义约束、Fixture、Conformance 和兼容性证据。
3. Blueprint Gate 通过并产生新的精确 Revision/Manifest Digest 后，实现仓库再升级依赖锁。
4. 实现仓库完成生成代码、Migration、组件、集成、Replay 和故障测试，并记录其独立证据。
5. Blueprint 兼容不代表实现升级成功；实现升级成功也不能反向证明 Blueprint 已正式冻结或获得生产批准。

纯实现重构若不改变公共行为，不修改 Blueprint。实现若需要绕过、放宽或复制 Blueprint 约束，必须停止并按契约变更处理，不能以临时兼容代码长期漂移。

## 5. Gate 与成熟度

| 结论 | 权威位置 | 最小证据 |
|---|---|---|
| Blueprint 契约通过 | Blueprint | Architecture Gate、Manifest Digest、兼容性状态 |
| 0B 实现完成 | 实现仓库 | Persistence/Runtime Core 组件、数据库事务、Replay 与 Core Conformance Evidence |
| 0C-0G 集成完成 | 实现仓库 | Business 纵向链、主 Runtime/Sandbox、Workbench、Experience 与 Reference Probe 验收 |
| 0H 可靠性证据 | 实现/运行环境 | 故障、安全、隔离、容量和恢复报告 |
| Blueprint 正式冻结 | Blueprint | 公共 CI、受保护基线、消费者兼容性和人工批准 |
| 生产批准 | 发布治理系统 | 独立 SLO、安全、容量、恢复和变更批准 |

这些结论互不替代。Blueprint 只定义实现必须满足什么，不在自身状态页中追踪某个实现仓库当前完成了多少。
