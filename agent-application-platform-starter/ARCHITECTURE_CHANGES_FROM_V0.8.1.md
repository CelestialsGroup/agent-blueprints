# v0.8.1 to v0.8.2

- ProviderRevision 认证/撤销改为 append-only ProviderAdmissionDecision。
- RunManifest 语义约束进入可执行 Validator 和反向 Fixture。
- SandboxOperation 改为 Platform Record + Attempt + Reconciliation + ManualReview 完整闭环；Provider transport response 独立。
- SandboxSpec、ProviderResolution、ProviderRevisionSnapshot 使用共享 `$ref`。
- Redocly 使用 Registry 投影，强制 4 个 OpenAPI 0 error/0 warning 和 deterministic bundle。
- Strict I-JSON 的 duplicate/unsafe integer 在 Python、Node、Go 共享向量中全部执行。
- Compatibility 与 Manifest Integrity 拆分；首个冻结基线前为 N/A。
- Python wheel hash lock 覆盖 Linux x86_64/aarch64、CPython 3.11–3.13；GitHub Actions full SHA；bytecode Gate。
- Workflow 支持独立仓库和 monorepo 根目录安装。

这些是 Contract Hardening，不是生产可靠性证明。
