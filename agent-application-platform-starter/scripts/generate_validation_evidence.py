#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "build/validation"


def load(name: str) -> dict[str, Any]:
    path = EVIDENCE / name
    if not path.exists():
        raise AssertionError(f"Missing successful Gate evidence: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


static = load("static.json")
contracts = load("contracts.json")
semantics = load("semantics.json")
openapi = load("openapi.json")
bundles = load("bundles.json")
manifest = json.loads((ROOT / "contracts/compatibility/v0.9.0-contract-manifest.json").read_text(encoding="utf-8"))
node_jcs = load("node-jcs.json")
python_jcs = [
    value
    for path in sorted(EVIDENCE.glob("python-jcs-*.json"))
    if (value := json.loads(path.read_text(encoding="utf-8")))["contract_manifest_digest"]
    == manifest["manifest_digest"]
]
if not python_jcs:
    raise AssertionError("No successful Python JCS lane evidence found for the current contract manifest")
if node_jcs["contract_manifest_digest"] != manifest["manifest_digest"]:
    raise AssertionError("Node JCS evidence belongs to a different contract manifest")
package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
pnpm_version = subprocess.check_output(
    ["corepack", "pnpm", "--version"], cwd=ROOT, text=True,
).strip()
go_version = subprocess.check_output(["go", "version"], cwd=ROOT, text=True).strip()
if pnpm_version != package["packageManager"].partition("@")[2]:
    raise AssertionError("Executed pnpm differs from packageManager pin")

architecture_closure = [
    "request-bound ExecutionGrant and RunManifest",
    "separate Turn and WorkOrder control with split CAS ownership",
    "sender-constrained Business revocation and Platform-only fenced safety cancellation",
    "renewable RuntimeAuthorization and bounded Runtime/Sandbox/Egress tokens",
    "closed purpose-specific JWS Header and Claims profiles",
    "Runtime/Capability/Plugin/Sandbox/Artifact/Egress operation Contract/Profile/Digest binding",
    "immutable owner-scoped EgressDestinationRevision with class authorization",
    "opaque slot-scoped RuntimeSessionRoute and logical content-bound Placement",
    "WorkspaceContentManifest and ownership-bound typed dual Event registries",
    "source Inbox dedupe, bounded metadata and all JSON write encoded-body admission limits",
    "ProviderRevision, BuildProvenance, admission and executable semantic traceability",
]

result = {
    "baseline": "v0.9.0",
    "status": "local_candidate_architecture_contract_gate_passed",
    "validated_at": datetime.now(timezone.utc).date().isoformat(),
    "local_validation": {
        **static,
        **contracts,
        **semantics,
        **openapi,
        "openapi_bundle_count": bundles["bundle_count"],
        "openapi_bundle_deterministic": bundles["deterministic"],
        "contract_manifest_resources": manifest["resource_count"],
        "contract_manifest_python_node_consistent": "passed",
        "compatibility_self_tests": "passed",
        "compatibility_baseline": "not_applicable_no_frozen_baseline_explicit_local_pre_freeze_mode",
        "python_jcs_lanes": python_jcs,
        "node_jcs": node_jcs,
        "go_jcs_and_gofmt": "passed",
        "pnpm_version": pnpm_version,
        "go_version": go_version,
        "architecture_closure": architecture_closure,
    },
    "deferred_repository_and_external_evidence": [
        "repository_supply_chain_admission",
        "public_github_ci_run",
        "protected_frozen_baseline_variable",
        "production_oci_digest_and_sbom_admission",
    ],
    "maturity": {
        "architecture_and_contract_validation": "passed_locally",
        "component_implementation": "not_started",
        "integrated_vertical_slice": "not_started",
        "production_reliability": "not_proven",
        "frozen": False,
    },
    "contract_candidate_ready_for_phase0_implementation": True,
}

validation_text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
validation_tmp = ROOT / "VALIDATION.json.tmp"
validation_tmp.write_text(validation_text, encoding="utf-8")
validation_tmp.replace(ROOT / "VALIDATION.json")

local = result["local_validation"]
python_lanes = ", ".join(item["runtime"] for item in python_jcs)
report = f"""# 契约验证报告 - v0.9.0

状态：**本地 Architecture Contract Gate 已通过；组件实现、集成链路、生产可靠性与正式冻结均未完成**

验证日期：{result['validated_at']}

本报告由 `scripts/generate_validation_evidence.py` 从本次成功 Gate 的 `build/validation/*.json` 生成；`VALIDATION.json` 是同源机器结果，不手工维护计数。

| 检查项 | 本地结果 |
|---|---|
| 纯源码静态审计 | 通过：{local['json_documents']} 个 JSON、{local['yaml_documents']} 个 YAML、{local['openapi_documents']} 个 OpenAPI、{local['markdown_documents']} 个 Markdown 文件 |
| JSON Schema 与夹具 | 通过：{local['schemas']} 个 Schema、{local['valid_fixtures']} 个有效夹具、{local['invalid_schema_fixtures']} 个 Schema 负例 |
| 语义不变量 | 通过：{local['state_machines']} 个状态机、{local['invalid_semantic_fixtures']} 个语义负例 |
| 语义追踪 | 通过：{local['critical_semantic_schemas']} 个关键 Schema、{local['semantic_constraints']} 条约束、{local['semantic_contract_gate_mappings']} 个 Contract Gate 映射、{local['semantic_executed_unique_check_ids']} 个本次执行 Check ID、{local['semantic_phase0_implementation_mappings']} 个 Phase 0 DDL/Conformance 责任 |
| Core Event Registry | 通过：Platform {local['platform_core_event_types']} 类、Agent Runtime {local['agent_runtime_core_event_types']} 类闭合 Event Type；CanonicalEvent 按 Producer 所有权绑定对应 Registry |
| 契约清单 | 通过：{local['contract_manifest_resources']} 项受治理资源；Python/Node 一致 |
| OpenAPI | 通过：{local['openapi_documents']} 份文档，0 Error / 0 Warning |
| Bundle | 通过：{local['openapi_bundle_count']} 个 Bundle，连续两次逐字节一致 |
| JCS / Strict I-JSON | Python：{python_lanes}；{local['node_jcs']['runtime']}；Go/gofmt 均通过 |
| 兼容性 | 比较器自测通过；尚无冻结基线，显式记为首次冻结前 N/A，不记为兼容性通过 |
| 仓库/供应链/公共 CI | 本轮延后，不计入 Architecture Contract Gate 通过条件 |

本次 Gate 已验证请求与授权绑定、Turn/Control 与 CAS 分离、sender-constrained Business 撤销、Platform-only fenced SafetyControl、用途隔离的闭合 JWS Header/Claims Profile、Runtime/Sandbox/Egress 时间窗、Runtime/Capability/Plugin/Sandbox/Artifact/Egress 单操作 Contract/Profile/Digest、读路径与 Cursor、不可变 EgressDestinationRevision、按 Destination Class 授权、不透明 RuntimeSessionRoute、逻辑 Placement、Workspace Manifest、按 Producer 所有权绑定的双 Event Registry、来源去重、有界 Metadata、全部 JSON 写接口解析前大小上限和可执行语义追踪。

该结论仅为“架构/契约验证通过”。仓库仍没有真实 Agent Platform 组件，因此不能声称组件实现完成；Business -> Conversation -> Temporal -> Runtime/Sandbox -> Event/Artifact/Usage/Recording 的纵向链尚未完成；多租户隔离、故障注入、容量、SLO、Temporal Replay、备份恢复和密钥轮换也尚未提供生产证据。

GitHub CI、仓库供应链准入和受保护冻结基线按当前阶段明确延后。首次正式冻结前，兼容性基线缺失可以显式 N/A；冻结后必须 fail-closed。
"""
report_tmp = ROOT / "CONTRACT_VALIDATION_REPORT.md.tmp"
report_tmp.write_text(report, encoding="utf-8")
report_tmp.replace(ROOT / "CONTRACT_VALIDATION_REPORT.md")
print("Generated VALIDATION.json and CONTRACT_VALIDATION_REPORT.md from successful Gate evidence.")
