# Contract CI and Provenance — v0.8.4

## Reproducible toolchain

- CPython 3.11–3.13；Linux x86_64/aarch64 wheels exact hash locked；
- Node 22.16；npm lock integrity；
- Go 1.23.2；
- Redocly CLI 2.39.0；
- GitHub Actions pinned by full commit SHA。

默认只使用 public PyPI、npm Registry 和 Go proxy/checksum database。Bootstrap 在创建环境前拒绝不支持的 Python；Python 3.9 的失败应报告为环境不满足要求。

## Workflow placement

GitHub 只加载 Git 根 `.github/workflows`。独立仓库直接使用当前文件；monorepo 运行 `scripts/install_github_workflow.sh`，提交 Git 根 Workflow，并设置 `AGENT_PLATFORM_CONTRACT_ROOT`。脚本只完成复制，未提交就不算激活。

Compatibility 基线来自受保护仓库变量 `AGENT_PLATFORM_FROZEN_CONTRACT_REF`，必须是已 fetch 的完整小写 Commit SHA，不能是 branch/tag/缩写。CI 缺失时 fail-closed；首个冻结基线前只能由受保护的 `AGENT_PLATFORM_ALLOW_NO_FROZEN_BASELINE=true` 显式允许 N/A，PR 修改仓库文件不能关闭该 Gate。

## Required Gates

Supply chain、source-only static audit、Schema/fixture、semantic invariant、Compatibility、Manifest、Python/Node/Go JCS、Go format、OpenAPI 0 error/0 warning、deterministic bundle 全部必跑。

## Reporting

报告必须记录实际工具版本、命令、计数和未运行项。公共 CI 前不得写“frozen”；Contract Gate 不能证明 production ready。

Compatibility 与 Integrity 分离。首个公开冻结基线前，Compatibility 只能是显式授权的 N/A；冻结后必须比较最新 frozen Git Ref，并阻止 Schema validation narrowing、新增 OpenAPI 必填输入、Endpoint/Operation/响应/状态迁移删除。比较器是保守 Gate，不是对 JSON Schema/OpenAPI 兼容性的形式化完备证明。
