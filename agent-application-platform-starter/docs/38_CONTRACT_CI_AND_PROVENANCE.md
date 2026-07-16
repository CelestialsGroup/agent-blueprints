# Contract CI 与验证溯源

## 1. 公共可复现环境

默认依赖源：

```text
Python: https://pypi.org/simple
Node:   https://registry.npmjs.org/
Go:     https://proxy.golang.org + checksum database
```

仓库禁止提交：

- `.internal` Registry URL
- 私有 Artifactory URL
- 未固定版本依赖
- 缺少 npm integrity 的 Lock Entry

## 2. CI Matrix

Contract Gate 在以下环境执行：

- Python 3.11
- Python 3.13
- Node 22.16
- Go 1.23

必须执行：

- Supply-chain configuration
- Strict I-JSON parsing
- RFC 8785 Python/Node/Go Test Vector
- JSON Schema meta-validation
- Positive/negative fixtures
- Semantic invariant tests
- OpenAPI lint
- OpenAPI deterministic bundle

## 3. Validation Report

`CONTRACT_VALIDATION_REPORT.md` 只能由验证脚本生成或根据真实 CI 结果更新。

报告必须包含：

- baseline version
- Git commit
- UTC timestamp
- tool versions
- dependency sources
- command results
- schema/fixture counts
- OpenAPI results
- generated bundle digest

禁止手工声明未经运行证明的：

```text
0 warnings
all passed
production ready
```

## 4. 兼容性

Phase 0 建立后，CI 必须比较 Merge Base 与当前 Contract：

- OpenAPI breaking changes
- JSON Schema required/type/enum narrowing
- State machine transition removal
- Capability semantic version
- Event Data Schema version
- Provider Protocol version

破坏性变更只能通过：

- Major Contract Version
- ADR
- Migration Plan
- Compatibility Window
