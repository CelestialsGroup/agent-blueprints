# v0.8.4 Architecture Acceptance

## Contract admission

- [ ] `./scripts/bootstrap_contracts.sh` 在公共 Registry 和 Python 3.11/3.13 成功。
- [ ] `make validate-all` 全绿，包括 Python/Node/Go Strict I-JSON。
- [ ] monorepo 的 Git 根 Workflow 已提交，`AGENT_PLATFORM_CONTRACT_ROOT` 与受保护 Compatibility 变量已配置。
- [ ] 4 个 OpenAPI 0 error/0 warning 且 Bundle deterministic。
- [ ] Contract Manifest Python/Node 一致。
- [ ] Compatibility 明确为受保护 frozen baseline pass，或由受保护变量显式批准首冻前 N/A；缺失配置时 CI 必须失败。
- [ ] Supply-chain Gate 全绿。

## Boundary acceptance

- [ ] Business/Platform 所有权无交叉事实源。
- [ ] Provider 选择只经 Capability/Resolution/immutable Revision/Admission。
- [ ] Sandbox 多 Slot 唯一且主 Slot 存在。
- [ ] 稳定模型无 Pod/Namespace/Container/VM/Node/raw endpoint。

## Reliability acceptance

- [ ] Invocation 与 SandboxOperation 都有逻辑记录、append-only Attempt、fencing 和 reconciliation。
- [ ] unknown outcome 可到达 success/failure/retry/manual review/abandoned，不存在永久悬空状态。
- [ ] Outbox/Inbox、Event sequence、Artifact staging/finalization 和 Delivery Attempt 有数据库约束。

## Production acceptance（不属于 Contract Gate）

- [ ] Phase 0A 真实链路、Temporal Replay、故障注入、安全隔离、容量/SLO、备份恢复演练和 Provider Conformance 均有运行证据。
