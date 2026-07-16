# v0.7 到 v0.8

## Sandbox 成为正式可替换基础设施 Provider

- 新增 Sandbox Provider OpenAPI。
- 新增 Sandbox Capability Negotiation。
- 新增 SandboxSpec、Status、Lease、Operation、Exec、RuntimeSession、Snapshot、Restore 和 Usage Schema。
- SandboxRegistry、Lease、Operation、RuntimeSession 和 Usage 归入稳定内核。
- DeerFlow Built-in Sandbox 与 sandbox-runtime 使用同一 Contract。
- RunManifest 锁定 Sandbox ProviderRevision、RuntimeProfile、Spec Digest 和 Conformance Report。
- 引入 Desired/Observed State、Generation、Attempt 和 Fencing。
- 固定 `/inputs`、`/workspace`、`/outputs`、`/tmp` 语义。
- 增加 Sandbox 安全基线、网络默认拒绝、Egress Gateway 和 Secret Grant。
- Snapshot 分为 Workspace、Filesystem 和 Process 三个等级。
- 增加 Sandbox Conformance 与 DeerFlow -> sandbox-runtime 迁移方案。
- 明确普通 sandbox-runtime 不需要实现 Kubernetes CRI。
