# Contract Governance

## 1. Source of Truth

- HTTP/SSE：OpenAPI 3.1.1
- 数据：JSON Schema 2020-12
- 状态机：Transition Table
- 架构：ADR

## 2. Schema Portability

每个 Schema 使用绝对 `$id`。

跨 Schema `$ref` 必须使用：

- 绝对 URI/URN，或
- 同一可发布 Schema Bundle 内的明确资源 ID

禁止在 URN `$id` 下使用不可移植的文件相对 `$ref`。

验证器使用标准 Registry，不得通过私有 RefResolver Hack 掩盖解析错误。

## 3. Immutable SchemaReference

业务契约引用 Schema 时保存：

- URI
- SHA-256 Digest
- Dialect

不能只保存相对文件名。

Schema Digest 使用 RFC 8785 JCS 对完整 Schema JSON（包含 `$schema`、`$id` 和 annotations）规范化后计算 SHA-256。Digest 算法变化必须提升 Contract 版本。

## 4. 工具固定

Contract CI 工具使用固定版本：

- Redocly CLI
- jsonschema
- referencing
- PyYAML

禁止 `@latest`。

## 5. Gate

```text
OpenAPI errors = 0
OpenAPI warnings = 0
Schema meta validation = pass
Positive fixtures = pass
Negative fixtures = rejected
Portable reference scan = pass
Compatibility check = pass
```

## 6. 语义校验

JSON Schema 不能表达的约束必须进入：

- Semantic Validator
- Test Vector
- Contract Test

例如：

- exp > iat
- Grant TTL
- JCS Digest
- WorkSession owner/delegated
- State Transition
- Fencing Token

## 7. Compatibility

兼容：

- 新增可选字段
- 新 Endpoint
- 新 Event Type（消费者容忍未知）

不兼容：

- 删除字段
- 修改类型/语义
- 新增必填字段
- 修改状态语义
- 修改 Capability Artifact Contract
