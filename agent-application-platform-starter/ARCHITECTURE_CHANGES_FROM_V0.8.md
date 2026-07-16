# v0.8 到 v0.8.1 Contract Hardening

- 真正的 RFC 8785 JCS 和 Strict I-JSON。
- Python/Node/Go 共享 Test Vector。
- ProviderRevision/Resolution/RunManifest 强制可复现性。
- RunManifest 支持多个 Sandbox Slot。
- 所有 Sandbox Mutation 使用统一 Envelope。
- Invocation Retry、Reconciliation、Manual Review 和 Abandoned 闭环。
- PluginInvocationStatus 绑定 Result/Error。
- Sandbox Backend 标识移入 Adapter Private Store。
- Kubernetes Base 增加双 Namespace、DNS、依赖和 Egress Policy。
- 公共 Registry 与 Supply-chain 检查。
- Contract Manifest 固化关键资源 Digest。
- Phase 0 改为故障注入的完整垂直链路优先。
