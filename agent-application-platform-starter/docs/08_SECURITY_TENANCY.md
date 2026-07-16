# 安全与多租户

## 1. Tenant Isolation

所有权威数据含内部 tenant_id。

防线：

- Repository Tenant Scope
- PostgreSQL RLS
- Object Storage Prefix
- Cache/Search Tenant Filter
- Signed URL Tenant Binding
- Audit

## 2. Token Profiles

- OAuth Access Token：RFC 9068 `at+jwt`
- ExecutionGrant
- WorkSession
- Plugin Invocation

四类 Token 使用互斥 typ/aud/claims/keys。

## 3. SSRF

禁止运行时任意 URL。

所有 Callback、Remote Provider、Connector 和 Storage Endpoint 预注册并通过：

- Scheme/Host Policy
- DNS/IP Validation
- Rebinding Protection
- Redirect Limit
- Egress Gateway
- Metadata/Private IP Block

## 4. Plugin

- 无数据库凭据
- 短期 Artifact Grant
- 最小 Secret Grant
- 默认无公网
- Digest Lock
- Signature/SBOM/Provenance
- Resource Limit
- Kill Switch

## 5. Sensitive Payload

- Secret 不进入 Event/Log/Temporal History
- Temporal Payload Codec 加密
- 大内容使用 Artifact Reference
- Audit 默认不保存用户正文
- 数据删除通过 Retention/Tombstone/Crypto Erasure
