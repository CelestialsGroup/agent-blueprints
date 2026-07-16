# ADR-0019：外部输入和交付使用注册制引用

## Status

Accepted

## Context

WorkOrder 接受任意输入 URL、Callback URL 或 Upload URL 会引入 SSRF、数据外带和凭据泄漏。

## Decision Drivers

- SSRF 防护
- 数据驻留
- 凭据隔离
- 稳定交付

## Considered Options

- 任意 URL
- 仅 URL Allowlist
- Ingest Session + Connector + Callback/Target Registry

## Decision

WorkOrder 只引用 IngestReference、已有 Artifact、预注册 Connector、CallbackRegistration 和 DeliveryTarget。所有网络访问经 Egress Gateway。

## Consequences

- 网络边界清晰
- 增加注册与 Ingest API
- 业务系统需先配置 Connector

## Risks

- 注册 Endpoint 后续变恶意
- DNS Rebinding
- Webhook 重放

## Migration Plan

- 移除 callback_url/external download URL
- 建立 Registry 与签名 Webhook

## Validation

- SSRF 测试
- Redirect/DNS Rebinding 测试
- Webhook Replay 测试
