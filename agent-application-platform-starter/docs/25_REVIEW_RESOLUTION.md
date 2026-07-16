# 历史审查说明

本文原用于记录 v0.5 到 v0.6 的修正。

v0.6 后续复审发现仍存在以下结构性缺口：

- Schema `$id/$ref` 不可移植
- Browser WorkSession Bearer 模式不适合原生 SSE/WebSocket
- Invocation Result 缺少 Attempt/Fencing 标识
- Capability SchemaReference 与 Provider Revision 不够不可变
- Agent Runtime 无法强制执行 ExecutionGrant 预算
- Input/Callback/Delivery 任意 URL 存在 SSRF 边界
- Temporal Worker Versioning 表述过度简化

这些问题已由 v0.7 修正。

最终审查结论与修订映射见：

- `32_V06_AUDIT_AND_V07_RESOLUTION.md`
