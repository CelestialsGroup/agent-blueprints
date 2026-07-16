# ADR-0005：Artifact Workspace 属于稳定核心

## Status

Accepted

## Context

生成代码、文档、PPT、图片等产物需要统一预览、编辑、版本和转换。

## Decision Drivers

- Artifact 一致性
- Agent 与用户共同编辑
- 格式插件化
- 历史可追溯

## Considered Options

- 文件作为聊天附件
- 每个场景自建编辑器
- 统一 Artifact Workspace

## Decision

Artifact Registry、Version、Relation、Staging、EditSession 和 Commit 属于核心；Renderer、Editor、Converter 与 Blob Adapter 可插拔。ArtifactVersion 不可变。

## Consequences

- 统一产物模型
- 复杂 Office 原生编辑仍需外部 Provider
- 需要对象存储

## Risks

- 错误的 MIME 或恶意文件
- 并发编辑冲突

## Migration Plan

- 先实现 Text/Markdown/Code/HTML
- Office 先预览和外部编辑

## Validation

- 不可变版本测试
- Staging 安全检查
- 并发 Commit 测试
