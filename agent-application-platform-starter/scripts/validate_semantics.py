#!/usr/bin/env python3
from __future__ import annotations

import copy
import base64
import hashlib
import json
import posixpath
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]


SCHEMA_REGISTRY = Registry()
for schema_path in sorted((ROOT / "contracts/schemas").glob("*.json")):
    schema_value = json.loads(schema_path.read_text(encoding="utf-8"))
    SCHEMA_REGISTRY = SCHEMA_REGISTRY.with_resource(schema_value["$id"], Resource.from_contents(schema_value))


KNOWN_CONTRACT_CHECKS = {
    "runtime_start.execution_topology",
    "runtime_start.workspace_binding",
    "runtime_start.sandbox_binding",
    "runtime_start.request_digest",
    "runtime_start.input_binding",
    "runtime_start.immutable_context_binding",
    "runtime_authorization.digest",
    "runtime_authorization.lineage",
    "runtime_authorization.ceiling",
    "runtime_authorization.internal_binding",
    "runtime_authorization.scope",
    "runtime_authorization.expiry",
    "runtime_authorization.artifact_coverage",
    "runtime_token.binding",
    "work_order.failure_paths",
    "work_order_control.grant_binding",
    "work_order_control.conditional_cas",
    "conversation_branch.head_consistency",
    "conversation_branch.workspace_binding",
    "provider_resolution.decision_digest",
    "provider_resolution.execution_scope",
    "provider_resolution.identity_dependency",
    "provider_resolution.selected_candidate",
    "capability_invocation.request_digest",
    "capability_invocation.resolution_binding",
    "capability_invocation.execution_context",
    "capability_invocation.token_binding",
    "capability_invocation.token_lifetime",
    "capability_invocation.token_lineage",
    "capability_invocation.operation_binding",
    "capability_invocation.artifact_grant_expiry",
    "capability_invocation.staging_grant",
    "workspace_manifest.digest",
    "workspace_manifest.path_policy",
    "workspace_manifest.counts",
    "workspace_manifest.symlink_policy",
    "runtime_session.requested_scope_subset",
    "runtime_session.sandbox_slot_binding",
    "runtime_session.scope_class",
    "runtime_session.channel_policy",
    "canonical_event.work_binding",
    "canonical_event.source_dedupe",
    "canonical_event.producer_binding",
    "canonical_event.registry_binding",
    "execution_grant.clock_skew",
    "execution_grant.expiration_order",
    "execution_grant.max_ttl",
    "execution_grant.request_digest",
    "execution_grant.principal_context",
    "execution_grant.request_identity",
    "execution_grant.commercial_limits",
    "execution_grant.snapshot_validity",
    "principal_context.digest",
    "principal_context.time_window",
    "principal_context.closed_attributes",
    "gateway_binding.closed_modes",
    "gateway_binding.port_contract",
    "gateway_binding.policy_alignment",
    "gateway_port.contract_mapping",
    "gateway_port.audience_binding",
    "artifact_grant.expiry",
    "artifact_grant.digest",
    "artifact_grant.scope",
    "artifact_grant.provider_permissions",
    "run_manifest.digest",
    "run_manifest.request_binding",
    "run_manifest.admission",
    "run_manifest.runtime_resolution",
    "run_manifest.sandbox_resolution",
    "run_manifest.experience_binding",
    "run_manifest.conversation_binding",
    "run_manifest.execution_inputs",
    "run_manifest.authorization_ceiling",
    "run_manifest.gateway_binding",
    "run_manifest.commercial_event_binding",
    "run_manifest.orchestration_binding",
    "artifact_staging_grant.digest",
    "artifact_staging_grant.scope",
    "artifact_staging_grant.expiry",
    "artifact_staging_grant.permissions",
    "artifact_gateway.operation_binding",
    "artifact_gateway.token_binding",
    "egress_gateway.request_binding",
    "egress_gateway.token_binding",
    "usage_observation.observation_identity",
    "usage_observation.meter_and_evidence",
    "usage_observation.incomplete_status",
    "usage_observation.provider_boundary",
    "semantic_traceability.known_but_unexecuted",
}
EXECUTED_CONTRACT_CHECKS: set[str] = set()


def mark_checks(*check_ids: str) -> None:
    unknown = set(check_ids) - KNOWN_CONTRACT_CHECKS
    if unknown:
        raise AssertionError(f"Validator attempted to mark unknown contract checks: {sorted(unknown)}")
    EXECUTED_CONTRACT_CHECKS.update(check_ids)


def load(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_self_digest(value: dict[str, Any], field: str) -> None:
    unsigned = copy.deepcopy(value)
    expected = unsigned.pop(field)
    actual = canonical_digest(unsigned)
    if actual != expected:
        raise AssertionError(f"{field} mismatch: expected {actual}, got {expected}")


def validate_principal_context(snapshot: dict[str, Any]) -> None:
    validate_self_digest(snapshot, "principal_context_digest")
    issued_at = parse_datetime(snapshot["issued_at"])
    expires_at = parse_datetime(snapshot["expires_at"])
    if expires_at <= issued_at:
        raise AssertionError("PrincipalContextSnapshot expiry is not later than issuance")
    forbidden_fragments = {"password", "secret", "token", "credential", "email", "display_name"}
    if any(fragment in key for key in snapshot["attributes"] for fragment in forbidden_fragments):
        raise AssertionError("PrincipalContextSnapshot contains credentials or mutable display attributes")
    mark_checks(
        "principal_context.digest",
        "principal_context.time_window",
        "principal_context.closed_attributes",
    )


def validate_execution_grant_request(
    grant: dict[str, Any], request: dict[str, Any], *, authenticated_conversation_id: str,
) -> None:
    if grant["nbf"] > grant["iat"] + 30 or grant["iat"] >= grant["exp"] or grant["exp"] - grant["iat"] > 300:
        raise AssertionError("ExecutionGrant time window is invalid")
    if grant["request_digest_profile"] != "rfc8785-request-excluding-execution-grant-v1":
        raise AssertionError("ExecutionGrant uses an unsupported request digest profile")
    unsigned = copy.deepcopy(request)
    unsigned.pop("execution_grant", None)
    if grant["request_digest"] != canonical_digest(unsigned):
        raise AssertionError("ExecutionGrant request_digest does not bind the submitted request")
    validate_principal_context(grant["principal_context"])
    principal = grant["principal_context"]
    if grant["principal_context_digest"] != principal["principal_context_digest"]:
        raise AssertionError("ExecutionGrant principal_context_digest does not bind its snapshot")
    principal_bindings = {
        "client_app_id": "client_app_id",
        "external_tenant_id": "external_tenant_id",
        "external_principal_id": "external_principal_id",
    }
    if any(grant[claim] != principal[field] for claim, field in principal_bindings.items()):
        raise AssertionError("ExecutionGrant claims differ from PrincipalContextSnapshot")
    commercial = grant["commercial_authorization"]
    validate_self_digest(commercial, "commercial_authorization_digest")
    commercial_issued_at = parse_datetime(commercial["issued_at"])
    commercial_expires_at = parse_datetime(commercial["expires_at"])
    if commercial_expires_at <= commercial_issued_at:
        raise AssertionError("CommercialAuthorizationSnapshot expiry is not later than issuance")
    grant_issued_at = datetime.fromtimestamp(grant["iat"], tz=timezone.utc)
    grant_expires_at = datetime.fromtimestamp(grant["exp"], tz=timezone.utc)
    if grant_issued_at < max(parse_datetime(principal["issued_at"]), commercial_issued_at) or grant_expires_at > min(
        parse_datetime(principal["expires_at"]), commercial_expires_at
    ):
        raise AssertionError("ExecutionGrant is not fully covered by its identity and commercial snapshots")
    contract_id = grant["request_contract_id"]
    if contract_id == "urn:agent-platform:conversation-turn-request:v1":
        if not {"branch_id", "client_message_id", "scenario"} <= set(request):
            raise AssertionError("ExecutionGrant request_contract_id does not match the submitted request shape")
        if authenticated_conversation_id != grant["conversation_id"]:
            raise AssertionError("ConversationTurn path and ExecutionGrant bind different Conversations")
        bindings = {
            "branch_id": request["branch_id"],
            "client_message_id": request["client_message_id"],
            "scenario_id": request["scenario"]["id"],
            "scenario_version": request["scenario"]["version"],
            "scenario_definition_digest": request["scenario"]["definition_digest"],
        }
    elif contract_id == "urn:agent-platform:work-order-request:v1":
        if "work" not in request:
            raise AssertionError("ExecutionGrant request_contract_id does not match the submitted request shape")
        work = request["work"]
        bindings = {
            "conversation_id": work["conversation_id"],
            "turn_id": work["turn_id"],
            "branch_id": work["branch_id"],
            "client_message_id": work["client_message_id"],
            "scenario_id": work["scenario_id"],
            "scenario_version": work["scenario_version"],
            "scenario_definition_digest": work["scenario_definition_digest"],
        }
    elif contract_id == "urn:agent-platform:work-order-control-request:v1":
        if not {"control_request_id", "work_order_id", "conversation_id", "branch_id", "action"} <= set(request):
            raise AssertionError("ExecutionGrant request_contract_id does not match the submitted request shape")
        if authenticated_conversation_id != request["conversation_id"]:
            raise AssertionError("WorkOrderControl path and request bind different Conversations")
        bindings = {
            "conversation_id": request["conversation_id"],
            "branch_id": request["branch_id"],
            "work_order_id": request["work_order_id"],
            "control_request_id": request["control_request_id"],
        }
        forbidden = {"turn_id", "client_message_id", "scenario_id", "scenario_version", "scenario_definition_digest"}
        if forbidden & set(grant):
            raise AssertionError("Control ExecutionGrant contains stale Turn or Scenario bindings")
    else:
        raise AssertionError("ExecutionGrant request_contract_id is unsupported")
    if any(grant[field] != value for field, value in bindings.items()):
        raise AssertionError("ExecutionGrant identity bindings differ from the submitted request")
    if not set(grant["capabilities"]) <= set(commercial["authorized_capabilities"]):
        raise AssertionError("ExecutionGrant capabilities exceed commercial authorization")
    if any(
        name not in commercial["authorized_limits"] or value > commercial["authorized_limits"][name]
        for name, value in grant["limits"].items()
    ):
        raise AssertionError("ExecutionGrant limits exceed commercial authorization")
    mark_checks(
        "execution_grant.clock_skew",
        "execution_grant.expiration_order",
        "execution_grant.max_ttl",
        "execution_grant.request_digest",
        "execution_grant.principal_context",
        "execution_grant.request_identity",
        "execution_grant.commercial_limits",
        "execution_grant.snapshot_validity",
    )
    if contract_id == "urn:agent-platform:work-order-control-request:v1":
        mark_checks("work_order_control.grant_binding")


def validate_provider_resolution(resolution: dict[str, Any]) -> None:
    validate_self_digest(resolution, "decision_digest")
    evaluations = resolution["candidate_evaluations"]
    candidate_keys = [
        (item["provider_instance_id"], item["provider_revision_id"], item["provider_audience"])
        for item in evaluations
    ]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise AssertionError("ProviderResolution contains duplicate candidate evaluations")
    selected = [item for item in evaluations if item["outcome"] == "selected"]
    if len(selected) != 1:
        raise AssertionError("ProviderResolution must contain exactly one selected candidate")
    snapshot = resolution["selected_provider_revision"]
    if selected[0]["provider_instance_id"] != resolution["selected_provider_instance_id"]:
        raise AssertionError("ProviderResolution selected instance conflicts with candidate evidence")
    if selected[0]["provider_revision_id"] != snapshot["provider_revision_id"]:
        raise AssertionError("ProviderResolution selected revision conflicts with candidate evidence")
    if selected[0]["provider_audience"] != resolution["selected_provider_audience"]:
        raise AssertionError("ProviderResolution selected audience conflicts with candidate evidence")
    if resolution["execution_scope"] != "work_order" or not resolution["tenant_id"] or not resolution["client_app_id"] or not resolution["work_order_id"]:
        raise AssertionError("ProviderResolution is missing its Tenant, ClientApplication or WorkOrder scope")
    identity_mode = resolution["identity_dependency"]["mode"]
    if (identity_mode == "principal_context") != (resolution["principal_context_digest"] is not None):
        raise AssertionError("ProviderResolution identity dependency conflicts with Principal context binding")
    mark_checks(
        "provider_resolution.decision_digest",
        "provider_resolution.execution_scope",
        "provider_resolution.identity_dependency",
        "provider_resolution.selected_candidate",
    )


def validate_provider_architecture(context: dict[str, Any], suites: list[dict[str, Any]]) -> None:
    protocol_by_kind = {
        "agent_runtime": "agent-runtime-provider",
        "sandbox": "sandbox-provider",
    }
    suites_by_id = {suite["suite_id"]: suite for suite in suites}
    for revision in context["provider_revisions"]:
        expected_protocol = protocol_by_kind.get(revision["provider_kind"], "capability-provider")
        if revision["port"]["protocol"] != expected_protocol:
            raise AssertionError("Provider kind is bound to the wrong stable Port")
        implementation = revision["implementation"]
        if implementation["provenance"]["build_artifact_digest"] != implementation["distribution_digest"]:
            raise AssertionError("Provider distribution and BuildProvenance bind different artifacts")
        if implementation["distribution_type"] == "oci_image" and "image_digest" not in implementation:
            raise AssertionError("OCI Provider implementation is missing image_digest")
        for result in revision["conformance"]:
            suite = suites_by_id.get(result["suite_id"])
            if suite is None or result["suite_version"] != suite["suite_version"] or result["suite_digest"] != suite["suite_digest"]:
                raise AssertionError("Provider conformance does not bind an admitted immutable Suite")
            if result["suite_profile_id"] not in {profile["profile_id"] for profile in suite["profiles"]}:
                raise AssertionError("Provider conformance binds an unknown Suite profile")


def permissions_are_subset(current: dict[str, Any], ceiling: dict[str, Any]) -> bool:
    if not set(current["model"]["allowed_model_profiles"]) <= set(ceiling["model"]["allowed_model_profiles"]):
        return False
    if not set(current["tool"]["allowed_capabilities"]) <= set(ceiling["tool"]["allowed_capabilities"]):
        return False
    for permission in ("read", "stage_new_version"):
        if current["artifact"][permission] and not ceiling["artifact"][permission]:
            return False
    egress_rank = {"none": 0, "restricted": 1, "full": 2}
    if egress_rank[current["egress"]["mode"]] > egress_rank[ceiling["egress"]["mode"]]:
        return False
    if not set(current["egress"]["allowed_destination_classes"]) <= set(
        ceiling["egress"]["allowed_destination_classes"]
    ):
        return False
    ceiling_slots = {
        item["sandbox_slot_key"]: set(item["allowed_operations"])
        for item in ceiling["sandbox_slots"]
    }
    return all(
        item["sandbox_slot_key"] in ceiling_slots
        and set(item["allowed_operations"]) <= ceiling_slots[item["sandbox_slot_key"]]
        for item in current["sandbox_slots"]
    )


def validate_gateway_bindings(
    bindings: dict[str, Any], budget: dict[str, Any], permissions: dict[str, Any],
) -> None:
    expected_contracts = {
        "model": (
            "urn:agent-platform:openapi:capability-provider:v1",
            ROOT / "contracts/openapi/capability-provider-v1.yaml",
        ),
        "tool": (
            "urn:agent-platform:openapi:capability-provider:v1",
            ROOT / "contracts/openapi/capability-provider-v1.yaml",
        ),
        "artifact": (
            "urn:agent-platform:openapi:artifact-gateway:v1",
            ROOT / "contracts/openapi/artifact-gateway-v1.yaml",
        ),
        "egress": (
            "urn:agent-platform:openapi:egress-gateway:v1",
            ROOT / "contracts/openapi/egress-gateway-v1.yaml",
        ),
    }
    for kind, binding in bindings.items():
        if binding["kind"] != kind:
            raise AssertionError("Runtime Gateway binding is stored under the wrong kind")
        if binding["mode"] == "disabled" and "port" in binding:
            raise AssertionError("Disabled Runtime Gateway binding exposes a routable identity")
        if binding["mode"] == "enabled":
            port = binding["port"]
            expected_contract_id, contract_path = expected_contracts[kind]
            contract_digest = "sha256:" + hashlib.sha256(contract_path.read_bytes()).hexdigest()
            if port["gateway_kind"] != kind:
                raise AssertionError("Runtime Gateway Port kind differs from its binding")
            if port["contract_id"] != expected_contract_id or port["contract_digest"] != contract_digest:
                raise AssertionError("Runtime Gateway Port does not bind the admitted executable contract")
            if not port["audience"] or not port["binding_digest"]:
                raise AssertionError("Runtime Gateway Port lacks audience or immutable binding digest")
    required_modes = {
        "model": budget["policies"]["model_gateway_required"]
        or bool(permissions["model"]["allowed_model_profiles"]),
        "tool": budget["policies"]["tool_gateway_required"]
        or bool(permissions["tool"]["allowed_capabilities"]),
        "artifact": permissions["artifact"]["read"] or permissions["artifact"]["stage_new_version"],
        "egress": budget["policies"]["egress_gateway_required"]
        or permissions["egress"]["mode"] != "none",
    }
    for kind, required in required_modes.items():
        if required and bindings[kind]["mode"] != "enabled":
            raise AssertionError(f"Required {kind} Gateway binding is disabled")
    mark_checks(
        "gateway_binding.closed_modes",
        "gateway_binding.port_contract",
        "gateway_binding.policy_alignment",
        "gateway_port.contract_mapping",
        "gateway_port.audience_binding",
    )


def validate_runtime_authorization(
    authorization: dict[str, Any], manifest: dict[str, Any], runtime_start: dict[str, Any],
    predecessor: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(authorization, "authorization_digest")
    validate_self_digest(authorization["execution_budget"], "budget_digest")
    validate_self_digest(authorization["policy_decision"], "decision_digest")
    validate_self_digest(authorization["effective_permissions"], "permissions_digest")
    if (
        authorization["policy_decision"]["execution_budget_id"] != authorization["execution_budget"]["budget_id"]
        or authorization["policy_decision"]["execution_budget_digest"] != authorization["execution_budget"]["budget_digest"]
        or authorization["policy_decision"]["effective_permissions_digest"]
        != authorization["effective_permissions"]["permissions_digest"]
    ):
        raise AssertionError("RuntimeAuthorization budget, policy and permission digests are not closed")
    expected_tenant = authorization["tenant_id"]
    expected_work_order = authorization["work_order_id"]
    for component_name in ("execution_budget", "policy_decision", "effective_permissions"):
        component = authorization[component_name]
        if component["tenant_id"] != expected_tenant or component["work_order_id"] != expected_work_order:
            raise AssertionError(f"RuntimeAuthorization {component_name} crosses its Tenant or WorkOrder")
    commercial_binding = authorization["commercial_authorization"]
    policy = authorization["policy_decision"]
    if (
        policy["commercial_authorization_id"] != commercial_binding["commercial_authorization_id"]
        or policy["commercial_authorization_digest"] != commercial_binding["commercial_authorization_digest"]
    ):
        raise AssertionError("RuntimeAuthorization PolicyDecision binds a different CommercialAuthorization")
    if authorization["authorization_sequence"] == 1:
        if predecessor is not None or authorization["predecessor_authorization_digest"] is not None:
            raise AssertionError("Initial RuntimeAuthorization cannot have a predecessor")
        if authorization["renewal_reason"] != "initial_dispatch":
            raise AssertionError("Initial RuntimeAuthorization uses the wrong reason")
    else:
        if predecessor is None:
            raise AssertionError("Renewed RuntimeAuthorization lacks its predecessor")
        if authorization["authorization_sequence"] != predecessor["authorization_sequence"] + 1:
            raise AssertionError("RuntimeAuthorization sequence contains a gap")
        if authorization["predecessor_authorization_digest"] != predecessor["authorization_digest"]:
            raise AssertionError("RuntimeAuthorization predecessor digest mismatch")
        if authorization["renewal_reason"] == "initial_dispatch":
            raise AssertionError("Renewed RuntimeAuthorization uses initial_dispatch")
    expected_scope = {
        "tenant_id": manifest["tenant_id"],
        "work_order_id": manifest["work_order_id"],
        "runtime_run_id": runtime_start["runtime_run_id"],
        "run_manifest_digest": manifest["run_manifest_digest"],
        "commercial_authorization": manifest["commercial_authorization"],
    }
    if any(authorization[field] != value for field, value in expected_scope.items()):
        raise AssertionError("RuntimeAuthorization crosses its immutable Run scope")
    if authorization["authorization_sequence"] == 1:
        for field in ("execution_budget", "policy_decision", "effective_permissions"):
            if authorization[field] != manifest[field]:
                raise AssertionError("Initial RuntimeAuthorization differs from the RunManifest ceiling")
    else:
        if any(
            authorization["execution_budget"]["limits"][name] > manifest["execution_budget"]["limits"][name]
            for name in authorization["execution_budget"]["limits"]
        ):
            raise AssertionError("Renewed RuntimeAuthorization widens the execution budget")
        if authorization["execution_budget"]["policies"] != manifest["execution_budget"]["policies"]:
            raise AssertionError("Renewed RuntimeAuthorization changes admitted enforcement policy")
        outcome_rank = {"deny": 0, "approval_required": 1, "allow": 2}
        if outcome_rank[authorization["policy_decision"]["outcome"]] > outcome_rank[manifest["policy_decision"]["outcome"]]:
            raise AssertionError("Renewed RuntimeAuthorization widens the policy outcome")
        if not permissions_are_subset(authorization["effective_permissions"], manifest["effective_permissions"]):
            raise AssertionError("Renewed RuntimeAuthorization widens effective permissions")
    issued_at = parse_datetime(authorization["issued_at"])
    expires_at = parse_datetime(authorization["expires_at"])
    if expires_at <= issued_at:
        raise AssertionError("RuntimeAuthorization expiry is not later than issuance")
    if (expires_at - issued_at).total_seconds() > manifest["authorization_renewal_policy"]["max_ttl_seconds"]:
        raise AssertionError("RuntimeAuthorization exceeds the admitted renewal TTL")
    expiry_ceiling = min(
        parse_datetime(commercial_binding["expires_at"]),
        parse_datetime(authorization["execution_budget"]["expires_at"]),
        parse_datetime(authorization["policy_decision"]["expires_at"]),
        *(
            parse_datetime(grant["expires_at"])
            for grant in authorization["artifact_grants"]
        ),
    )
    if expires_at > expiry_ceiling:
        raise AssertionError("RuntimeAuthorization outlives a bound budget, policy or ArtifactGrant")
    requirements = {
        (item["artifact_id"], item["version_id"], item["artifact_digest"]): item
        for item in manifest["artifact_access_requirements"]
    }
    covered: set[tuple[str, str, str]] = set()
    for grant in authorization["artifact_grants"]:
        validate_self_digest(grant, "grant_digest")
        grant_issued_at = parse_datetime(grant["issued_at"])
        grant_expires_at = parse_datetime(grant["expires_at"])
        if grant_expires_at <= grant_issued_at:
            raise AssertionError("Runtime ArtifactGrant expiry is not later than issuance")
        if grant_issued_at < issued_at or grant_expires_at > expires_at:
            raise AssertionError("Runtime ArtifactGrant is outside its RuntimeAuthorization window")
        key = (grant["artifact_id"], grant["version_id"], grant["artifact_digest"])
        requirement = requirements.get(key)
        if requirement is None or grant["tenant_id"] != manifest["tenant_id"] or grant["work_order_id"] != manifest["work_order_id"]:
            raise AssertionError("Runtime ArtifactGrant does not cover an admitted requirement")
        scope = grant["execution_scope"]
        if scope.get("kind") != "runtime_invocation" or any(
            scope[field] != runtime_start[field]
            for field in ("runtime_run_id", "invocation_id", "invocation_attempt_id")
        ):
            raise AssertionError("Runtime ArtifactGrant is not bound to the current InvocationAttempt")
        if not set(grant["permissions"]) <= set(requirement["allowed_permissions"]):
            raise AssertionError("Runtime ArtifactGrant exceeds admitted permissions")
        artifact_binding = manifest["gateway_bindings"]["artifact"]
        if artifact_binding["mode"] != "enabled" or grant["gateway_binding"] != artifact_binding["port"]:
            raise AssertionError("Runtime ArtifactGrant uses a Gateway outside the admitted RunManifest")
        covered.add(key)
    if covered != set(requirements) or len(authorization["artifact_grants"]) != len(requirements):
        raise AssertionError("Runtime ArtifactGrants do not exactly cover admitted requirements")
    validate_gateway_bindings(
        manifest["gateway_bindings"], authorization["execution_budget"], authorization["effective_permissions"]
    )
    mark_checks(
        "runtime_authorization.digest",
        "runtime_authorization.lineage",
        "runtime_authorization.ceiling",
        "runtime_authorization.internal_binding",
        "runtime_authorization.scope",
        "runtime_authorization.expiry",
        "runtime_authorization.artifact_coverage",
        "artifact_grant.expiry",
        "artifact_grant.digest",
        "artifact_grant.scope",
        "artifact_grant.provider_permissions",
    )


def validate_execution_topology(
    manifest: dict[str, Any], workflow_run: dict[str, Any], agent_run: dict[str, Any],
    runtime_start: dict[str, Any],
) -> None:
    validate_self_digest(manifest["orchestration_binding"], "binding_digest")
    validate_self_digest(runtime_start, "request_digest")
    tenant_ids = {manifest["tenant_id"], workflow_run["tenant_id"], agent_run["tenant_id"], runtime_start["tenant_id"]}
    if len(tenant_ids) != 1:
        raise AssertionError("Execution topology crosses tenants")
    if workflow_run["workflow_run_id"] != manifest["workflow_run_id"]:
        raise AssertionError("RunManifest and WorkflowRun IDs differ")
    if workflow_run["work_order_id"] != manifest["work_order_id"]:
        raise AssertionError("WorkflowRun belongs to a different WorkOrder")
    if workflow_run["workflow"] != manifest["workflow"] or workflow_run["orchestration_binding"] != manifest["orchestration_binding"]:
        raise AssertionError("WorkflowRun and RunManifest bind different orchestration evidence")
    if agent_run["agent_run_id"] != manifest["agent_run_id"] or runtime_start["agent_run_id"] != manifest["agent_run_id"]:
        raise AssertionError("AgentRun identity is not closed across Manifest and Runtime start")
    if agent_run["workflow_run_id"] != manifest["workflow_run_id"] or agent_run["work_order_id"] != manifest["work_order_id"]:
        raise AssertionError("AgentRun belongs to a different WorkflowRun or WorkOrder")
    if agent_run["runtime_run_id"] != runtime_start["runtime_run_id"]:
        raise AssertionError("One AgentRun must bind exactly one AgentRuntimeRun identity")
    if agent_run["run_manifest_digest"] != manifest["run_manifest_digest"] or runtime_start["run_manifest_digest"] != manifest["run_manifest_digest"]:
        raise AssertionError("Execution topology binds different RunManifest digests")
    if agent_run["run_kind"] == "root" and agent_run["root_agent_run_id"] != agent_run["agent_run_id"]:
        raise AssertionError("Root AgentRun must identify itself as root")
    if workflow_run["root_agent_run_id"] != agent_run["agent_run_id"]:
        raise AssertionError("WorkflowRun does not bind its unique root AgentRun")
    if runtime_start["workflow_run_id"] != manifest["workflow_run_id"]:
        raise AssertionError("Runtime start belongs to a different WorkflowRun")
    if agent_run["runtime_provider_resolution_id"] != manifest["agent_runtime"]["resolution_id"]:
        raise AssertionError("AgentRun and RunManifest bind different Runtime Provider resolutions")
    for resolution in manifest["capability_resolutions"]:
        if resolution["tenant_id"] != manifest["tenant_id"] or resolution["work_order_id"] != manifest["work_order_id"]:
            raise AssertionError("ProviderResolution crosses the RunManifest execution scope")
        validate_provider_resolution(resolution)
    for field in ("workspace_revision_id", "workspace_revision_digest"):
        if runtime_start[field] != manifest["conversation"][field]:
            raise AssertionError(f"Runtime start and RunManifest differ on {field}")
    if runtime_start["input_message_id"] != runtime_start["input"]["input_message_id"]:
        raise AssertionError("Runtime start input envelope belongs to a different input message")
    for field in ("input", "context_package", "gateway_bindings", "admission_limits"):
        if runtime_start[field] != manifest[field]:
            raise AssertionError(f"Runtime start and RunManifest differ on executable context {field}")
    if runtime_start["input"]["content_digest"] != canonical_digest(runtime_start["input"]["content"]):
        raise AssertionError("Runtime input content_digest does not bind the actual content")
    expanded_context_bytes = sum(item["size_bytes"] for item in runtime_start["context_package"]["items"])
    if expanded_context_bytes > runtime_start["runtime_authorization"]["execution_budget"]["limits"]["max_storage_bytes"]:
        raise AssertionError("Expanded Context Package exceeds the admitted storage budget")
    validate_runtime_authorization(runtime_start["runtime_authorization"], manifest, runtime_start)
    expected_sandboxes = {
        (item["sandbox_slot_key"], item["sandbox_id"])
        for item in manifest["sandboxes"]
    }
    actual_sandboxes = {
        (item["sandbox_slot_key"], item["sandbox_id"])
        for item in runtime_start["sandbox_bindings"]
    }
    if len(actual_sandboxes) != len(runtime_start["sandbox_bindings"]) or actual_sandboxes != expected_sandboxes:
        raise AssertionError("Runtime start Sandbox bindings do not exactly match RunManifest")
    mark_checks(
        "runtime_start.execution_topology",
        "runtime_start.workspace_binding",
        "runtime_start.sandbox_binding",
        "runtime_start.request_digest",
        "runtime_start.input_binding",
        "runtime_start.immutable_context_binding",
        "run_manifest.conversation_binding",
        "run_manifest.execution_inputs",
        "run_manifest.authorization_ceiling",
        "run_manifest.gateway_binding",
        "run_manifest.orchestration_binding",
    )


def validate_runtime_token(
    token: dict[str, Any], manifest: dict[str, Any], agent_run: dict[str, Any],
    runtime_start: dict[str, Any],
) -> None:
    authorization = runtime_start["runtime_authorization"]
    expected = {
        "tenant_id": manifest["tenant_id"],
        "runtime_run_id": runtime_start["runtime_run_id"],
        "agent_run_id": manifest["agent_run_id"],
        "workflow_run_id": manifest["workflow_run_id"],
        "work_order_id": manifest["work_order_id"],
        "run_manifest_digest": manifest["run_manifest_digest"],
        "runtime_authorization_digest": authorization["authorization_digest"],
        "request_digest": runtime_start["request_digest"],
        "invocation_id": runtime_start["invocation_id"],
        "invocation_attempt_id": runtime_start["invocation_attempt_id"],
        "fencing_token": runtime_start["fencing_token"],
        "policy_decision_digest": authorization["policy_decision"]["decision_digest"],
        "execution_budget_digest": authorization["execution_budget"]["budget_digest"],
        "effective_permissions_digest": authorization["effective_permissions"]["permissions_digest"],
    }
    for field, value in expected.items():
        if token[field] != value:
            raise AssertionError(f"Agent Runtime token differs from execution context on {field}")
    if token["operation"] != "start" or not token["iat"] <= token["nbf"] < token["exp"]:
        raise AssertionError("Agent Runtime token operation or lifetime is invalid")
    if agent_run["runtime_run_id"] != token["runtime_run_id"]:
        raise AssertionError("Agent Runtime token binds a different AgentRun")
    runtime_resolution = next(
        item for item in manifest["capability_resolutions"]
        if item["resolution_id"] == manifest["agent_runtime"]["resolution_id"]
    )
    if token["provider_revision_id"] != runtime_resolution["selected_provider_revision"]["provider_revision_id"]:
        raise AssertionError("Agent Runtime token binds a different ProviderRevision")
    mark_checks("runtime_token.binding")


def validate_capability_invocation(
    request: dict[str, Any], token: dict[str, Any], resolution: dict[str, Any],
    manifest: dict[str, Any], operation_request: dict[str, Any] | None = None,
    predecessor: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(request, "request_digest")
    validate_provider_resolution(resolution)
    for value, digest_field in (
        (request["execution_budget"], "budget_digest"),
        (request["policy_decision"], "decision_digest"),
        (request["effective_permissions"], "permissions_digest"),
        (request["output_staging_grant"], "grant_digest"),
    ):
        validate_self_digest(value, digest_field)
    selected_revision = resolution["selected_provider_revision"]
    if (
        request["provider_resolution_id"] != resolution["resolution_id"]
        or request["provider_instance_id"] != resolution["selected_provider_instance_id"]
        or request["provider_revision_id"] != selected_revision["provider_revision_id"]
        or resolution["tenant_id"] != request["tenant_id"]
        or resolution["client_app_id"] != request["client_app_id"]
        or resolution["work_order_id"] != request["work_order_id"]
        or resolution["capability"] != {
            "id": request["capability"]["id"],
            "version": request["capability"]["version"],
            "profile": request["capability"].get("profile"),
        }
    ):
        raise AssertionError("Capability request differs from its admitted ProviderResolution")
    budget = request["execution_budget"]
    policy = request["policy_decision"]
    permissions = request["effective_permissions"]
    commercial = request["commercial_authorization"]
    for component in (budget, policy, permissions):
        if component["tenant_id"] != request["tenant_id"] or component["work_order_id"] != request["work_order_id"]:
            raise AssertionError("Capability executable authorization crosses Tenant or WorkOrder")
    if (
        policy["execution_budget_id"] != budget["budget_id"]
        or policy["execution_budget_digest"] != budget["budget_digest"]
        or policy["effective_permissions_digest"] != permissions["permissions_digest"]
        or policy["commercial_authorization_id"] != commercial["commercial_authorization_id"]
        or policy["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]
    ):
        raise AssertionError("Capability executable Budget, Policy, Permissions or Commercial binding is not closed")
    if any(
        budget["limits"][name] > manifest["execution_budget"]["limits"][name]
        for name in budget["limits"]
    ) or not permissions_are_subset(permissions, manifest["effective_permissions"]):
        raise AssertionError("Capability executable authorization widens the RunManifest ceiling")
    if request["capability"]["id"] not in permissions["tool"]["allowed_capabilities"]:
        raise AssertionError("Capability is absent from EffectivePermissions")
    request_deadline = parse_datetime(request["deadline_at"])
    authorization_expiry = min(
        parse_datetime(commercial["expires_at"]),
        parse_datetime(budget["expires_at"]),
        parse_datetime(policy["expires_at"]),
    )
    if request_deadline > authorization_expiry:
        raise AssertionError("Capability request deadline outlives executable authorization")

    staging_grant = request["output_staging_grant"]
    if any(
        staging_grant[field] != request[field]
        for field in ("tenant_id", "work_order_id", "invocation_id", "invocation_attempt_id")
    ):
        raise AssertionError("ArtifactStagingGrant crosses its Capability InvocationAttempt")
    artifact_binding = manifest["gateway_bindings"]["artifact"]
    if artifact_binding["mode"] != "enabled" or staging_grant["gateway_binding"] != artifact_binding["port"]:
        raise AssertionError("ArtifactStagingGrant uses a Gateway outside the admitted RunManifest")
    staging_issued = parse_datetime(staging_grant["issued_at"])
    staging_expires = parse_datetime(staging_grant["expires_at"])
    if staging_expires <= staging_issued or staging_expires > min(request_deadline, parse_datetime(commercial["expires_at"])):
        raise AssertionError("ArtifactStagingGrant has an invalid authorization window")

    if operation_request is None:
        operation_request = request
    if token["operation"] == "invoke":
        operation_digest = request["request_digest"]
    elif "request_digest" in operation_request:
        validate_self_digest(operation_request, "request_digest")
        operation_digest = operation_request["request_digest"]
    else:
        operation_digest = canonical_digest(operation_request)
    expected = {
        "aud": resolution["selected_provider_audience"],
        "tenant_id": request["tenant_id"],
        "client_app_id": request["client_app_id"],
        "principal_context_digest": request["principal_context_digest"],
        "work_order_id": request["work_order_id"],
        "provider_resolution_id": request["provider_resolution_id"],
        "provider_instance_id": request["provider_instance_id"],
        "provider_revision_id": request["provider_revision_id"],
        "capability_id": request["capability"]["id"],
        "capability_version": request["capability"]["version"],
        "invocation_id": request["invocation_id"],
        "invocation_attempt_id": request["invocation_attempt_id"],
        "fencing_token": request["fencing_token"],
        "invocation_request_digest": request["request_digest"],
        "operation_request_digest": operation_digest,
        "policy_decision_digest": policy["decision_digest"],
        "execution_budget_digest": budget["budget_digest"],
        "permissions_digest": permissions["permissions_digest"],
        "staging_grant_digest": staging_grant["grant_digest"],
    }
    for field, value in expected.items():
        if token[field] != value:
            raise AssertionError(f"Capability operation token differs from admitted context on {field}")
    if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 900:
        raise AssertionError("Capability operation token lifetime is invalid")
    token_expiry = datetime.fromtimestamp(token["exp"], tz=timezone.utc)
    if token_expiry > min(request_deadline, parse_datetime(commercial["expires_at"])):
        raise AssertionError("Capability operation token outlives the admitted request")
    if token["authorization_sequence"] == 1:
        if predecessor is not None or token["predecessor_jti"] is not None or token["operation"] != "invoke":
            raise AssertionError("Initial Capability token has invalid lineage or operation")
    else:
        if predecessor is None:
            raise AssertionError("Renewed Capability operation token lacks its predecessor")
        if token["authorization_sequence"] != predecessor["authorization_sequence"] + 1:
            raise AssertionError("Capability operation token sequence contains a gap")
        if token["predecessor_jti"] != predecessor["jti"]:
            raise AssertionError("Capability operation token predecessor mismatch")
        invariant_fields = set(expected) - {"operation_request_digest"}
        if any(token[field] != predecessor[field] for field in invariant_fields):
            raise AssertionError("Renewed Capability operation token widens or changes Invocation scope")
        target_provider_operation_id = operation_request.get(
            "provider_operation_id", predecessor.get("provider_operation_id")
        )
        if token.get("provider_operation_id") != target_provider_operation_id:
            raise AssertionError("Capability operation token targets a different Provider operation")

    for grant in request["input_artifact_grants"]:
        validate_self_digest(grant, "grant_digest")
        scope = grant["execution_scope"]
        if scope.get("kind") != "capability_invocation" or any(
            scope[field] != request[field] for field in ("invocation_id", "invocation_attempt_id")
        ):
            raise AssertionError("Capability ArtifactGrant crosses its InvocationAttempt")
        if grant["tenant_id"] != request["tenant_id"] or grant["work_order_id"] != request["work_order_id"]:
            raise AssertionError("Capability ArtifactGrant crosses its Tenant or WorkOrder")
        grant_issued_at = parse_datetime(grant["issued_at"])
        grant_expires_at = parse_datetime(grant["expires_at"])
        if grant_expires_at <= grant_issued_at or grant_expires_at > min(
            request_deadline, parse_datetime(commercial["expires_at"])
        ):
            raise AssertionError("Capability ArtifactGrant has an invalid request window")
        if grant["gateway_binding"] != artifact_binding["port"] or "finalize" in grant["permissions"]:
            raise AssertionError("Capability Provider has invalid Artifact Gateway or finalize authority")
    mark_checks(
        "capability_invocation.request_digest",
        "capability_invocation.resolution_binding",
        "capability_invocation.execution_context",
        "capability_invocation.token_binding",
        "capability_invocation.token_lifetime",
        "capability_invocation.token_lineage",
        "capability_invocation.operation_binding",
        "capability_invocation.artifact_grant_expiry",
        "capability_invocation.staging_grant",
        "artifact_staging_grant.digest",
        "artifact_staging_grant.scope",
        "artifact_staging_grant.expiry",
        "artifact_staging_grant.permissions",
        "artifact_grant.digest",
        "artifact_grant.expiry",
        "artifact_grant.scope",
        "artifact_grant.provider_permissions",
    )


def validate_artifact_gateway(
    staging_grant: dict[str, Any], staging_object: dict[str, Any],
    stage_token: dict[str, Any], staging_commit: dict[str, Any], commit_token: dict[str, Any],
    artifact_grant: dict[str, Any], read_token: dict[str, Any], capability_request: dict[str, Any],
) -> None:
    validate_self_digest(staging_grant, "grant_digest")
    descriptor = copy.deepcopy(staging_object)
    descriptor.pop("request_digest")
    encoded_content = descriptor.pop("content_base64")
    if staging_object["request_digest"] != canonical_digest(descriptor):
        raise AssertionError("Artifact staging object request digest mismatch")
    content = base64.b64decode(encoded_content, validate=True)
    raw_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if len(content) != staging_object["size_bytes"] or raw_digest != staging_object["digest"]:
        raise AssertionError("Artifact staging object content does not match declared bytes")
    expected_scope = {
        "tenant_id": staging_grant["tenant_id"],
        "work_order_id": staging_grant["work_order_id"],
        "invocation_id": staging_grant["invocation_id"],
        "invocation_attempt_id": staging_grant["invocation_attempt_id"],
        "gateway_binding_digest": staging_grant["gateway_binding"]["binding_digest"],
        "staging_grant_digest": staging_grant["grant_digest"],
    }
    for token, operation_request, operation in (
        (stage_token, staging_object, "stage_object"),
        (commit_token, staging_commit, "commit_staging"),
    ):
        if token["operation"] != operation or token["aud"] != staging_grant["gateway_binding"]["audience"]:
            raise AssertionError("Artifact Gateway token operation or audience mismatch")
        if any(token[field] != value for field, value in expected_scope.items()):
            raise AssertionError("Artifact Gateway token crosses its StagingGrant scope")
        if token["fencing_token"] != operation_request["fencing_token"]:
            raise AssertionError("Artifact Gateway token fencing differs from the operation")
        if token["request_digest"] != operation_request["request_digest"]:
            raise AssertionError("Artifact Gateway token request digest mismatch")
        if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 300:
            raise AssertionError("Artifact Gateway token lifetime is invalid")
        if datetime.fromtimestamp(token["exp"], tz=timezone.utc) > parse_datetime(staging_grant["expires_at"]):
            raise AssertionError("Artifact Gateway token outlives its StagingGrant")
    validate_self_digest(artifact_grant, "grant_digest")
    artifact_scope = artifact_grant["execution_scope"]
    if (
        artifact_grant["tenant_id"] != capability_request["tenant_id"]
        or artifact_grant["work_order_id"] != capability_request["work_order_id"]
        or artifact_scope.get("invocation_id") != capability_request["invocation_id"]
        or artifact_scope.get("invocation_attempt_id") != capability_request["invocation_attempt_id"]
    ):
        raise AssertionError("Artifact read Grant crosses its Capability InvocationAttempt")
    read_descriptor = {
        "operation": "read_content",
        "tenant_id": capability_request["tenant_id"],
        "work_order_id": capability_request["work_order_id"],
        "invocation_id": capability_request["invocation_id"],
        "invocation_attempt_id": capability_request["invocation_attempt_id"],
        "fencing_token": capability_request["fencing_token"],
        "artifact_id": artifact_grant["artifact_id"],
        "version_id": artifact_grant["version_id"],
    }
    read_expected = {
        "operation": "read_content",
        "aud": artifact_grant["gateway_binding"]["audience"],
        "tenant_id": artifact_grant["tenant_id"],
        "work_order_id": artifact_grant["work_order_id"],
        "invocation_id": artifact_scope["invocation_id"],
        "invocation_attempt_id": artifact_scope["invocation_attempt_id"],
        "fencing_token": capability_request["fencing_token"],
        "gateway_binding_digest": artifact_grant["gateway_binding"]["binding_digest"],
        "request_digest": canonical_digest(read_descriptor),
        "artifact_grant_digest": artifact_grant["grant_digest"],
    }
    if artifact_scope.get("kind") != "capability_invocation" or "read" not in artifact_grant["permissions"]:
        raise AssertionError("Artifact read requires a Capability ArtifactGrant with read permission")
    if any(read_token[field] != value for field, value in read_expected.items()):
        raise AssertionError("Artifact read token differs from its ArtifactGrant or operation descriptor")
    if not read_token["iat"] <= read_token["nbf"] < read_token["exp"] or read_token["exp"] - read_token["iat"] > 300:
        raise AssertionError("Artifact read token lifetime is invalid")
    if datetime.fromtimestamp(read_token["exp"], tz=timezone.utc) > parse_datetime(artifact_grant["expires_at"]):
        raise AssertionError("Artifact read token outlives its ArtifactGrant")
    validate_self_digest(staging_commit, "request_digest")
    committed = staging_commit["objects"]
    if len(committed) > staging_grant["max_object_count"]:
        raise AssertionError("Artifact staging commit exceeds object-count limit")
    if sum(item["size_bytes"] for item in committed) > staging_grant["max_total_bytes"]:
        raise AssertionError("Artifact staging commit exceeds total-byte limit")
    if any(
        item["media_type"] not in staging_grant["allowed_media_types"]
        or item["size_bytes"] > staging_grant["max_object_bytes"]
        for item in committed
    ):
        raise AssertionError("Artifact staging commit exceeds media or object-byte limits")
    mark_checks("artifact_gateway.operation_binding", "artifact_gateway.token_binding")


def validate_egress_gateway(
    request: dict[str, Any], token: dict[str, Any], response: dict[str, Any],
    binding: dict[str, Any], authorization: dict[str, Any],
) -> None:
    validate_self_digest(request, "request_digest")
    expected = {
        "aud": binding["audience"],
        "tenant_id": request["tenant_id"],
        "work_order_id": request["work_order_id"],
        "runtime_run_id": request["runtime_run_id"],
        "invocation_id": request["invocation_id"],
        "invocation_attempt_id": request["invocation_attempt_id"],
        "fencing_token": request["fencing_token"],
        "destination_id": request["destination_id"],
        "gateway_binding_digest": binding["binding_digest"],
        "request_digest": request["request_digest"],
        "policy_decision_digest": authorization["policy_decision"]["decision_digest"],
        "execution_budget_digest": authorization["execution_budget"]["budget_digest"],
        "permissions_digest": authorization["effective_permissions"]["permissions_digest"],
    }
    if any(token[field] != value for field, value in expected.items()):
        raise AssertionError("Egress token differs from the admitted HTTP request")
    if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 300:
        raise AssertionError("Egress token lifetime is invalid")
    if request["destination_id"] not in authorization["effective_permissions"]["egress"]["allowed_destination_classes"]:
        raise AssertionError("Egress destination is absent from EffectivePermissions")
    if any(
        response[field] != request[field]
        for field in ("invocation_id", "invocation_attempt_id", "fencing_token", "request_digest")
    ):
        raise AssertionError("Egress response belongs to a different request")
    mark_checks("egress_gateway.request_binding", "egress_gateway.token_binding")


def validate_workspace_content_manifest(manifest: dict[str, Any]) -> None:
    validate_self_digest(manifest, "manifest_digest")
    paths = [entry["path"] for entry in manifest["entries"]]
    if len(paths) != len(set(paths)):
        raise AssertionError("Workspace Content Manifest contains duplicate paths")
    if any(posixpath.normpath(path) != path or path.startswith("/") or path in {".", ".."} for path in paths):
        raise AssertionError("Workspace Content Manifest contains a non-normalized path")
    if manifest["path_case_policy"] == "case_insensitive" and len({path.casefold() for path in paths}) != len(paths):
        raise AssertionError("Workspace Content Manifest contains a case-colliding path")
    if manifest["entry_count"] != len(manifest["entries"]):
        raise AssertionError("Workspace Content Manifest entry_count mismatch")
    total_bytes = sum(entry.get("size_bytes", 0) for entry in manifest["entries"] if entry["entry_type"] == "file")
    if manifest["total_file_bytes"] != total_bytes:
        raise AssertionError("Workspace Content Manifest total_file_bytes mismatch")
    symlinks = [entry for entry in manifest["entries"] if entry["entry_type"] == "symlink"]
    if manifest["symlink_policy"] == "forbid" and symlinks:
        raise AssertionError("Workspace Content Manifest forbids symlinks")
    symlink_paths = {entry["path"] for entry in symlinks}
    for entry in symlinks:
        target = entry["symlink_target"]
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(entry["path"]), target))
        if target.startswith("/") or resolved == ".." or resolved.startswith("../"):
            raise AssertionError("Workspace Content Manifest symlink escapes the root")
        target_parts = resolved.split("/")
        prefixes = {"/".join(target_parts[:index]) for index in range(1, len(target_parts) + 1)}
        if prefixes & (symlink_paths - {entry["path"]}):
            raise AssertionError("Workspace Content Manifest symlink traverses another symlink")
    mark_checks(
        "workspace_manifest.digest",
        "workspace_manifest.path_policy",
        "workspace_manifest.counts",
        "workspace_manifest.symlink_policy",
    )


def validate_canonical_event_source(event: dict[str, Any]) -> None:
    expected = canonical_digest({
        "tenant_id": event["tenant_id"],
        "producer_id": event["producer_id"],
        "source_stream_id": event["source_stream_id"],
        "source_event_id": event["source_event_id"],
    })
    if event["dedupe_key"] != expected:
        raise AssertionError("CanonicalEvent dedupe_key does not bind source identity")
    if event["producer_kind"] == "provider":
        if event["provider_revision_id"] is None or event["metadata"].get("provider_instance_id") is None:
            raise AssertionError("Provider-originated CanonicalEvent lacks immutable Provider binding")
    elif event["provider_revision_id"] is not None or event["metadata"].get("provider_instance_id") is not None:
        raise AssertionError("Platform-originated CanonicalEvent carries Provider identity")
    work_fields = {"work_order_id", "turn_id", "branch_id", "input_message_id", "work_sequence"}
    if work_fields & set(event) and not work_fields <= set(event):
        raise AssertionError("CanonicalEvent has a partial executable Work binding")
    mark_checks(
        "canonical_event.work_binding",
        "canonical_event.source_dedupe",
        "canonical_event.producer_binding",
    )


def validate_platform_event_registry_binding(event: dict[str, Any], registry: dict[str, Any]) -> None:
    expected_registry = {
        "registry_id": registry["registry_id"],
        "registry_version": registry["registry_version"],
        "registry_digest": registry["registry_digest"],
    }
    if event["event_registry"] != expected_registry:
        raise AssertionError("CanonicalEvent binds a different Platform Core Event Registry")
    definition = next(
        (item for item in registry["definitions"] if item["type"] == event["type"] and item["data_version"] == event["data_version"]),
        None,
    )
    if definition is None:
        raise AssertionError("CanonicalEvent type and data_version are not admitted")
    schema = {"$ref": definition["data_schema"]["uri"]}
    errors = list(
        Draft202012Validator(schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
        .iter_errors(event["data"])
    )
    if errors:
        raise AssertionError("CanonicalEvent data does not validate against the admitted Platform Event schema")
    mark_checks("canonical_event.registry_binding")


def validate_semantic_traceability(traceability: dict[str, Any]) -> None:
    schemas_by_id = {}
    for path in sorted((ROOT / "contracts/schemas").glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas_by_id[schema["$id"]] = schema
    entries_by_schema: dict[str, list[dict[str, Any]]] = {}
    identifiers: set[str] = set()
    for entry in traceability["constraints"]:
        if entry["constraint_id"] in identifiers:
            raise AssertionError("Semantic traceability contains duplicate constraint IDs")
        identifiers.add(entry["constraint_id"])
        entries_by_schema.setdefault(entry["schema_id"], []).append(entry)
        for enforcement in entry["enforcements"]:
            if not (ROOT / enforcement["artifact"]).exists():
                raise AssertionError("Semantic traceability references a missing enforcement artifact")
            if enforcement["status"] == "contract_gate":
                if enforcement["kind"] != "semantic_validator" or enforcement["artifact"] != "scripts/validate_semantics.py":
                    raise AssertionError("Contract-gate semantic evidence must be an executable semantic-validator check")
                if enforcement["check_id"] not in KNOWN_CONTRACT_CHECKS:
                    raise AssertionError("Semantic traceability references an unknown contract check ID")
                if enforcement["check_id"] not in EXECUTED_CONTRACT_CHECKS:
                    raise AssertionError("Semantic traceability references a contract check not executed in this Gate")
    for schema_id in traceability["critical_schema_ids"]:
        schema = schemas_by_id.get(schema_id)
        if schema is None:
            raise AssertionError("Semantic traceability references an unknown critical Schema")
        statements = schema.get("x-semantic-constraints", [])
        entries = sorted(entries_by_schema.get(schema_id, []), key=lambda item: item["constraint_index"])
        if len(entries) != len(statements):
            raise AssertionError("Semantic traceability does not cover every critical constraint")
        for index, (statement, entry) in enumerate(zip(statements, entries)):
            if entry["constraint_index"] != index or entry["statement"] != statement:
                raise AssertionError("Semantic traceability is stale relative to its source Schema")
            if not entry["enforcements"]:
                raise AssertionError("Critical semantic constraint has no enforcement responsibility")


def validate_work_order_control_contract(request: dict[str, Any]) -> None:
    has_message_cas = "expected_message_head_version" in request
    if request["action"] in {"append_input", "interrupt"}:
        if not has_message_cas or "content" not in request:
            raise AssertionError("Executable control input lacks Message CAS or content")
        if request["content"]["content_digest"] != canonical_digest(request["content"]["content"]):
            raise AssertionError("WorkOrder control content digest mismatch")
        forbidden_internal_ids = {"input_id", "input_message_id"} & set(request["content"])
        if forbidden_internal_ids:
            raise AssertionError("Client WorkOrder control contains Platform-owned input identity")
    elif has_message_cas:
        raise AssertionError("Non-message WorkOrder control incorrectly depends on Message CAS")
    mark_checks("work_order_control.conditional_cas")


def validate_runtime_session_request(
    request: dict[str, Any], manifest: dict[str, Any], authorized_scopes: set[str],
) -> None:
    slots = {item["sandbox_slot_key"] for item in manifest["sandboxes"]}
    if request["sandbox_slot_key"] not in slots:
        raise AssertionError("RuntimeSession selects a Sandbox slot outside the RunManifest")
    requested = set(request.get("requested_scopes", []))
    control_scopes = {"control", "input", "clipboard", "file-transfer"}
    required_scope = "runtime:control" if requested & control_scopes else "runtime:view"
    if required_scope not in authorized_scopes:
        raise AssertionError("RuntimeSession scopes exceed authenticated authorization")
    recording = request["recording"]
    if request["runtime_type"] == "port_forward" and recording["mode"] != "disabled":
        raise AssertionError("Port-forward RuntimeSession cannot be recorded")
    allowed_channels = {
        "terminal": {"terminal", "file_delta"},
        "browser": {"browser", "file_delta"},
        "desktop": {"desktop", "file_delta"},
        "port_forward": set(),
    }[request["runtime_type"]]
    if recording["mode"] == "platform_managed" and not set(recording["channels"]) <= allowed_channels:
        raise AssertionError("RuntimeSession recording channels conflict with runtime_type")
    mark_checks(
        "runtime_session.requested_scope_subset",
        "runtime_session.sandbox_slot_binding",
        "runtime_session.scope_class",
        "runtime_session.channel_policy",
    )


def validate_usage_observations(
    result: dict[str, Any], meter: dict[str, Any], technical_entry: dict[str, Any],
) -> None:
    observations = result["usage"]
    ids = [item["observation_id"] for item in observations]
    if len(ids) != len(set(ids)):
        raise AssertionError("Provider returned duplicate UsageObservation identities")
    platform_owned = {"entry_id", "tenant_id", "work_order_id", "recorded_at", "idempotency_key", "producer"}
    for observation in observations:
        if platform_owned & set(observation):
            raise AssertionError("Provider UsageObservation contains Platform-owned ledger fields")
        if observation["meter_id"] != meter["meter_id"] or observation["meter_version"] != meter["meter_version"]:
            raise AssertionError("UsageObservation binds a different MeterDefinition")
        if observation["unit"] != meter["base_unit"]:
            raise AssertionError("UsageObservation unit differs from MeterDefinition")
        if observation["evidence_digest"] != canonical_digest({"evidence_reference": observation["evidence_reference"]}):
            raise AssertionError("UsageObservation evidence digest mismatch")
    if observations and technical_entry.get("source_observation_id") not in set(ids):
        raise AssertionError("Platform TechnicalUsageEntry does not bind a validated UsageObservation")
    source = next(
        (item for item in observations if item["observation_id"] == technical_entry.get("source_observation_id")),
        None,
    )
    if source is not None and any(
        technical_entry[field] != source[field]
        for field in ("meter_id", "meter_version", "quantity", "unit", "measurement_status", "occurred_at")
    ):
        raise AssertionError("Platform TechnicalUsageEntry changes Provider observation semantics")
    mark_checks(
        "usage_observation.observation_identity",
        "usage_observation.incomplete_status",
        "usage_observation.provider_boundary",
        "usage_observation.meter_and_evidence",
    )


def validate_gateway_frames(connect: dict[str, Any], control: dict[str, Any]) -> None:
    channels = [cursor["channel"] for cursor in connect["resume_cursors"]]
    if len(channels) != len(set(channels)):
        raise AssertionError("Runtime Gateway resume cursors contain duplicate channels")
    control_payload = {
        field: control[field]
        for field in ("command", "columns", "rows", "text", "key", "url")
        if field in control
    }
    if control["control_digest"] != canonical_digest(control_payload):
        raise AssertionError("Runtime Gateway control_digest does not bind the command payload")
    if connect["runtime_session_id"] != control["runtime_session_id"] or connect["connection_generation"] != control["connection_generation"]:
        raise AssertionError("Runtime Gateway frames belong to different session generations")


def validate_event_registry(registry: dict[str, Any]) -> None:
    validate_self_digest(registry, "registry_digest")
    if registry["registry_id"] == "agent-runtime-core":
        root = load("contracts/schemas/agent-runtime-event-data.schema.json")
        dependencies = sorted(
            [
                load("contracts/schemas/capability-error.schema.json"),
                load("contracts/schemas/usage-observation.schema.json"),
            ],
            key=lambda schema: schema["$id"],
        )
        uri_prefix = "urn:agent-platform:agent-runtime-event-data:v1#/$defs/"
    elif registry["registry_id"] == "platform-core":
        root = load("contracts/schemas/platform-core-event-data.schema.json")
        dependencies = [load("contracts/schemas/work-order-state.schema.json")]
        uri_prefix = "urn:agent-platform:platform-core-event-data:v1#/$defs/"
    else:
        raise AssertionError("Unknown EventTypeRegistry ownership domain")
    expected_schema_digest = canonical_digest({
        "root": root,
        "dependencies": dependencies,
    })
    keys: set[tuple[str, int]] = set()
    for definition in registry["definitions"]:
        key = (definition["type"], definition["data_version"])
        if key in keys:
            raise AssertionError("EventTypeRegistry contains duplicate type plus data_version")
        keys.add(key)
        if definition["data_schema"]["digest"] != expected_schema_digest:
            raise AssertionError("EventTypeRegistry data schema digest is not admitted")
        if definition["data_schema"]["digest_profile"] != "rfc8785-schema-closure-v1":
            raise AssertionError("EventTypeRegistry uses an unsupported Schema closure digest profile")
        if not definition["data_schema"]["uri"].startswith(uri_prefix):
            raise AssertionError("Core event points outside its admitted payload registry")
        fragment = definition["data_schema"]["uri"].removeprefix(uri_prefix)
        if fragment not in root.get("$defs", {}):
            raise AssertionError("EventTypeRegistry points at a missing payload definition")


def validate_usage_contracts(
    meter: dict[str, Any], entry: dict[str, Any], report: dict[str, Any], settlement: dict[str, Any],
) -> None:
    validate_self_digest(meter, "definition_digest")
    validate_self_digest(report, "usage_report_digest")
    validate_self_digest(settlement, "settlement_envelope_digest")
    if entry["meter_id"] != meter["meter_id"] or entry["meter_version"] != meter["meter_version"]:
        raise AssertionError("TechnicalUsageEntry binds a different MeterDefinition")
    if entry["meter_definition_digest"] != meter["definition_digest"] or entry["unit"] != meter["base_unit"]:
        raise AssertionError("TechnicalUsageEntry Meter digest or unit mismatch")
    if any(item["tenant_id"] != report["tenant_id"] or item["work_order_id"] != report["work_order_id"] for item in report["entries"]):
        raise AssertionError("UsageReport contains cross-tenant or cross-WorkOrder entries")
    if len({item["entry_id"] for item in report["entries"]}) != len(report["entries"]):
        raise AssertionError("UsageReport contains duplicate entry IDs")
    if report["report_status"] == "final" and any(item["measurement_status"] not in {"confirmed", "corrected"} for item in report["entries"]):
        raise AssertionError("Final UsageReport cannot silently settle partial or estimated usage")
    if report["report_status"] == "correction" and any(item["measurement_status"] != "corrected" for item in report["entries"]):
        raise AssertionError("Correction UsageReport contains non-correction entries")
    if settlement.get("usage_report") != report:
        raise AssertionError("BusinessSettlementEnvelope binds a different UsageReport")
    for field in ("tenant_id", "work_order_id", "commercial_authorization_id", "commercial_authorization_digest", "quota_reservation_id", "quota_reservation_digest"):
        if settlement[field] != report[field]:
            raise AssertionError(f"Settlement and UsageReport differ on {field}")


def validate_policy_decision(decision: dict[str, Any]) -> None:
    validate_self_digest(decision, "decision_digest")
    actions = {item["action"] for item in decision["evaluations"]}
    expected = "deny" if "deny" in actions else "approval_required" if "ask" in actions else "allow"
    if decision["outcome"] != expected:
        raise AssertionError("PolicyDecision does not resolve deny greater than ask greater than allow")
    if datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(decision["decided_at"].replace("Z", "+00:00")):
        raise AssertionError("PolicyDecision expires_at must be later than decided_at")


def validate_conformance_suite(suite: dict[str, Any]) -> None:
    validate_self_digest(suite, "suite_digest")
    profile_ids = [profile["profile_id"] for profile in suite["profiles"]]
    if len(profile_ids) != len(set(profile_ids)):
        raise AssertionError("Conformance suite contains duplicate profiles")
    known = set(profile_ids)
    dependencies = {profile["profile_id"]: set(profile.get("depends_on", [])) for profile in suite["profiles"]}
    if any(not value <= known for value in dependencies.values()):
        raise AssertionError("Conformance profile depends on an unknown profile")
    test_ids = [test["test_id"] for profile in suite["profiles"] for test in profile["tests"]]
    if len(test_ids) != len(set(test_ids)):
        raise AssertionError("Conformance suite contains duplicate test IDs")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(profile_id: str) -> None:
        if profile_id in visiting:
            raise AssertionError("Conformance profile dependency cycle")
        if profile_id in visited:
            return
        visiting.add(profile_id)
        for dependency in dependencies[profile_id]:
            visit(dependency)
        visiting.remove(profile_id)
        visited.add(profile_id)
    for profile_id in profile_ids:
        visit(profile_id)


def snapshot_fields(revision: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    result = {
        "provider_revision_id": revision["provider_revision_id"],
        "provider_revision_digest": revision["provider_revision_digest"],
        "provider_kind": revision["provider_kind"],
        "implementation": revision["implementation"],
        "port": revision["port"],
        "configuration_digest": revision["configuration_digest"],
        "approved_permissions_digest": revision["approved_permissions_digest"],
        "credential_binding_digest": revision["credential_binding_digest"],
        "conformance_set_digest": revision["conformance_set_digest"],
        "admission_decision_id": decision["decision_id"],
        "admission_decision_digest": decision["decision_digest"],
        "admission_status": "certified",
    }
    return result


def provider_snapshot_bindings(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    bindings = [(item["selected_provider_revision"], item["selected_provider_instance_id"]) for item in manifest["capability_resolutions"]]
    bindings.extend((item["provider_revision"], item["provider_instance_id"]) for item in manifest["selected_experiences"])
    return bindings


def capability_key(value: dict[str, Any], id_field: str = "id") -> tuple[str, str, str | None]:
    return (value[id_field], value["version"], value.get("profile"))


def revision_supports(revision: dict[str, Any], key: tuple[str, str, str | None]) -> bool:
    return any((item["capability"], item["version"], item.get("profile")) == key and item["status"] == "passed" for item in revision["conformance"])


def validate_run_admission(manifest: dict[str, Any], context: dict[str, Any]) -> None:
    validate_self_digest(manifest, "run_manifest_digest")
    mark_checks("run_manifest.digest")
    if manifest["scenario"] != context["scenario"]:
        raise AssertionError("RunManifest scenario does not bind the admitted Scenario definition")
    scenario_definition = context["scenario_definition"]
    validate_self_digest(scenario_definition, "definition_digest")
    scenario_identity = {
        "id": scenario_definition["id"],
        "version": scenario_definition["version"],
        "definition_digest": scenario_definition["definition_digest"],
    }
    if scenario_identity != context["scenario"]:
        raise AssertionError("Run admission context does not bind its complete ScenarioDefinition")
    scenario_requirements = {item["id"]: item for item in scenario_definition["capabilities"]["required"]}
    if {item["id"] for item in context["required_capabilities"]} != set(scenario_requirements):
        raise AssertionError("Run admission capabilities do not exactly cover Scenario required capabilities")
    for item in context["required_capabilities"]:
        required_profiles = scenario_requirements[item["id"]].get("required_profiles", [])
        if required_profiles and item["profile"] not in required_profiles:
            raise AssertionError("Resolved capability profile is not allowed by the Scenario")
    if context["experience_requirements"] != scenario_definition.get("experience_requirements", []):
        raise AssertionError("Run admission Experience requirements differ from the ScenarioDefinition")
    commercial = context["commercial_authorization"]
    validate_self_digest(commercial, "commercial_authorization_digest")
    if commercial["authorized_limits_digest"] != canonical_digest(commercial["authorized_limits"]):
        raise AssertionError("Commercial authorization does not bind its explicit limits")
    expected_commercial = {
        "commercial_authorization_id": commercial["commercial_authorization_id"],
        "commercial_authorization_digest": commercial["commercial_authorization_digest"],
        "expires_at": commercial["expires_at"],
    }
    if manifest["commercial_authorization"] != expected_commercial:
        raise AssertionError("RunManifest does not bind the admitted CommercialAuthorizationSnapshot")
    required_items = [(item["id"], item["version"], item["profile"]) for item in context["required_capabilities"]]
    resolved_items = [(item["capability"]["id"], item["capability"]["version"], item["capability"]["profile"]) for item in manifest["capability_resolutions"]]
    required, resolved = set(required_items), set(resolved_items)
    if len(required_items) != len(required) or len(resolved_items) != len(resolved):
        raise AssertionError("Scenario requirements and CapabilityResolution entries must be unique by id/version/profile")
    if not required <= resolved:
        raise AssertionError(f"Capability resolution must cover every Scenario requirement: required={required}, resolved={resolved}")

    definitions: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for definition in context["capability_definitions"]:
        key = capability_key(definition)
        if key in definitions:
            raise AssertionError(f"Duplicate admitted CapabilityDefinition: {key}")
        definitions[key] = definition
    if required - set(definitions):
        raise AssertionError("Scenario requirements are missing admitted CapabilityDefinitions")
    runtime_key = capability_key(context["agent_runtime_capability"])
    if definitions.get(runtime_key) != context["agent_runtime_capability"]:
        raise AssertionError("Agent Runtime capability must bind one admitted CapabilityDefinition")

    revisions: dict[str, dict[str, Any]] = {}
    for revision in context["provider_revisions"]:
        validate_self_digest(revision, "provider_revision_digest")
        expected_conformance_digest = canonical_digest(revision["conformance"])
        if revision["conformance_set_digest"] != expected_conformance_digest:
            raise AssertionError("ProviderRevision conformance_set_digest mismatch")
        revision_id = revision["provider_revision_id"]
        if revision_id in revisions:
            raise AssertionError(f"Duplicate ProviderRevision in admission context: {revision_id}")
        revisions[revision_id] = revision

    decisions: dict[str, dict[str, Any]] = {}
    latest: dict[str, dict[str, Any]] = {}
    seen_sequences: set[tuple[str, int]] = set()
    for decision in context["admission_decisions"]:
        validate_self_digest(decision, "decision_digest")
        decision_id = decision["decision_id"]
        if decision_id in decisions:
            raise AssertionError(f"Duplicate AdmissionDecision: {decision_id}")
        key = (decision["provider_revision_id"], decision["decision_sequence"])
        if key in seen_sequences:
            raise AssertionError(f"Duplicate AdmissionDecision sequence: {key}")
        seen_sequences.add(key)
        revision = revisions.get(decision["provider_revision_id"])
        if revision is None or decision["provider_revision_digest"] != revision["provider_revision_digest"]:
            raise AssertionError("AdmissionDecision does not bind a verified ProviderRevision")
        decisions[decision_id] = decision
        current = latest.get(decision["provider_revision_id"])
        if current is None or decision["decision_sequence"] > current["decision_sequence"]:
            latest[decision["provider_revision_id"]] = decision

    for revision_id in revisions:
        chain = sorted(
            (item for item in decisions.values() if item["provider_revision_id"] == revision_id),
            key=lambda item: item["decision_sequence"],
        )
        if not chain:
            continue
        if [item["decision_sequence"] for item in chain] != list(range(1, len(chain) + 1)):
            raise AssertionError(f"AdmissionDecision sequence must be contiguous from one: {revision_id}")
        if "supersedes_decision_id" in chain[0]:
            raise AssertionError(f"First AdmissionDecision cannot supersede another decision: {revision_id}")
        for previous, current in zip(chain, chain[1:]):
            if current.get("supersedes_decision_id") != previous["decision_id"]:
                raise AssertionError(f"AdmissionDecision must supersede the immediate predecessor: {revision_id}")

    by_revision: dict[str, dict[str, Any]] = {}
    for snapshot, provider_instance_id in provider_snapshot_bindings(manifest):
        revision_id = snapshot["provider_revision_id"]
        revision = revisions.get(revision_id)
        decision = decisions.get(snapshot["admission_decision_id"])
        if revision is None or decision is None:
            raise AssertionError("RunManifest snapshot is missing verified Revision/Admission context")
        if provider_instance_id != revision["provider_instance_id"]:
            raise AssertionError("Provider instance binding does not match immutable Revision")
        if decision is not latest[revision_id] or decision["decision"] != "certified":
            raise AssertionError("RunManifest must bind the latest effective certified AdmissionDecision")
        if snapshot != snapshot_fields(revision, decision):
            raise AssertionError(f"Forged or incomplete ProviderRevision snapshot: {revision_id}")
        previous = by_revision.setdefault(revision_id, snapshot)
        if previous != snapshot:
            raise AssertionError(f"Conflicting snapshots for ProviderRevision {revision_id}")

    for resolution in manifest["capability_resolutions"]:
        validate_provider_resolution(resolution)
        key = capability_key(resolution["capability"])
        definition = definitions.get(key)
        revision = revisions[resolution["selected_provider_revision"]["provider_revision_id"]]
        if definition is None or resolution["capability_definition_digest"] != definition["definition_digest"]:
            raise AssertionError(f"CapabilityResolution does not bind the admitted CapabilityDefinition: {key}")
        if revision["provider_kind"] not in definition["allowed_provider_kinds"]:
            raise AssertionError(f"Provider kind {revision['provider_kind']} is not allowed for {key}")
        if not revision_supports(revision, key):
            raise AssertionError(f"ProviderRevision conformance does not cover selected capability: {key}")

    referenced_resolution_ids = {
        manifest["agent_runtime"]["resolution_id"],
        *(sandbox["resolution_id"] for sandbox in manifest["sandboxes"]),
    }
    for resolution in manifest["capability_resolutions"]:
        key = capability_key(resolution["capability"])
        if key not in required and resolution["resolution_id"] not in referenced_resolution_ids:
            raise AssertionError("RunManifest contains an unreferenced non-Scenario ProviderResolution")

    runtime_resolutions = [
        resolution for resolution in manifest["capability_resolutions"]
        if resolution["resolution_id"] == manifest["agent_runtime"]["resolution_id"]
    ]
    if len(runtime_resolutions) != 1:
        raise AssertionError("RunManifest agent_runtime must reference exactly one CapabilityResolution")
    runtime_resolution = runtime_resolutions[0]
    runtime_revision = revisions[runtime_resolution["selected_provider_revision"]["provider_revision_id"]]
    if runtime_revision["provider_kind"] != "agent_runtime" or "agent_runtime" not in context["agent_runtime_capability"]["allowed_provider_kinds"]:
        raise AssertionError("RunManifest agent_runtime must bind an admitted Agent Runtime Provider")
    if not revision_supports(runtime_revision, runtime_key):
        raise AssertionError("Agent Runtime Provider conformance does not cover its governed execution capability")

    for sandbox in manifest["sandboxes"]:
        sandbox_resolutions = [
            resolution for resolution in manifest["capability_resolutions"]
            if resolution["resolution_id"] == sandbox["resolution_id"]
        ]
        if len(sandbox_resolutions) != 1:
            raise AssertionError("Sandbox slot must reference exactly one ProviderResolution")
        sandbox_resolution = sandbox_resolutions[0]
        revision = revisions[sandbox_resolution["selected_provider_revision"]["provider_revision_id"]]
        if revision["provider_kind"] != "sandbox":
            raise AssertionError("Sandbox slot must bind a Sandbox ProviderRevision")
        required_keys = {capability_key(item) for item in sandbox["required_capabilities"]}
        if capability_key(sandbox_resolution["capability"]) not in required_keys:
            raise AssertionError("Sandbox ProviderResolution does not select one of the slot's required capabilities")
        for required_capability in sandbox["required_capabilities"]:
            key = capability_key(required_capability)
            definition = definitions.get(key)
            if definition is None or "sandbox" not in definition["allowed_provider_kinds"] or not revision_supports(revision, key):
                raise AssertionError(f"Sandbox ProviderRevision does not conform to required capability: {key}")

    experience_revisions: dict[str, dict[str, Any]] = {}
    for revision in context["experience_revisions"]:
        validate_self_digest(revision, "revision_digest")
        revision_id = revision["template_revision_id"]
        if revision_id in experience_revisions:
            raise AssertionError(f"Duplicate Experience revision: {revision_id}")
        experience_revisions[revision_id] = revision

    selected_counts: dict[tuple[str, str], int] = {}
    selected_revisions: dict[tuple[str, str], list[dict[str, Any]]] = {}
    authorized_entitlements = set(commercial["authorized_entitlements"])
    for selected in manifest["selected_experiences"]:
        selection = selected["selection"]
        if selection["kind"] != "template":
            raise AssertionError("v1 Experience admission only accepts governed TemplateRevision resources")
        revision = experience_revisions.get(selection["revision_id"])
        if revision is None or revision["revision_digest"] != selection["revision_digest"]:
            raise AssertionError("Selected Experience does not bind an admitted immutable revision")
        if revision["template_id"] != selection["catalog_entry_id"] or revision["capability"]["id"] != selection["capability_id"]:
            raise AssertionError("Selected Experience identity/capability conflicts with its TemplateRevision")
        if revision["provider_revision"] != selected["provider_revision"]:
            raise AssertionError("Selected Experience ProviderRevision snapshot conflicts with Catalog admission")
        provider = revisions[selected["provider_revision"]["provider_revision_id"]]
        capability = capability_key(revision["capability"])
        if provider["provider_kind"] != "template" or not revision_supports(provider, capability):
            raise AssertionError("Selected Template ProviderRevision is not conformant")
        if not set(revision.get("required_entitlements", [])) <= authorized_entitlements:
            raise AssertionError("Selected Experience requires an unauthorized commercial entitlement")
        count_key = (selection["kind"], selection["capability_id"])
        selected_counts[count_key] = selected_counts.get(count_key, 0) + 1
        selected_revisions.setdefault(count_key, []).append(revision)

    for requirement in context["experience_requirements"]:
        count = selected_counts.get((requirement["kind"], requirement["capability_id"]), 0)
        if not requirement["minimum"] <= count <= requirement["maximum"]:
            raise AssertionError("Selected Experience cardinality conflicts with Scenario requirements")
        required_tags = set(requirement.get("required_tags", []))
        if any(not required_tags <= set(revision.get("tags", [])) for revision in selected_revisions.get((requirement["kind"], requirement["capability_id"]), [])):
            raise AssertionError("Selected Experience does not satisfy Scenario required_tags")
    required_keys = {(item["kind"], item["capability_id"]) for item in context["experience_requirements"]}
    if set(selected_counts) - required_keys:
        raise AssertionError("RunManifest contains an Experience not requested by the Scenario")

    slots = [sandbox["sandbox_slot_key"] for sandbox in manifest["sandboxes"]]
    if len(slots) != len(set(slots)):
        raise AssertionError("sandbox_slot_key must be unique")
    if slots:
        if slots.count(manifest.get("primary_sandbox_slot_key")) != 1:
            raise AssertionError("primary_sandbox_slot_key must reference exactly one Sandbox")
    elif "primary_sandbox_slot_key" in manifest:
        raise AssertionError("A Sandbox-free RunManifest cannot declare primary_sandbox_slot_key")
    mark_checks(
        "run_manifest.admission",
        "run_manifest.runtime_resolution",
        "run_manifest.sandbox_resolution",
        "run_manifest.experience_binding",
        "run_manifest.commercial_event_binding",
    )


def validate_run_manifest_request_binding(
    manifest: dict[str, Any], grant: dict[str, Any], request: dict[str, Any],
) -> None:
    expected = {
        "request_contract_id": grant["request_contract_id"],
        "request_digest_profile": grant["request_digest_profile"],
        "request_digest": grant["request_digest"],
    }
    if manifest["request_binding"] != expected:
        raise AssertionError("RunManifest request binding differs from the consumed ExecutionGrant")
    if grant["request_digest"] != canonical_digest({
        key: value for key, value in request.items() if key != "execution_grant"
    }):
        raise AssertionError("RunManifest source ExecutionGrant does not bind the submitted request")
    if (
        manifest["conversation"]["conversation_id"] != grant["conversation_id"]
        or manifest["conversation"]["turn_id"] != grant["turn_id"]
        or manifest["conversation"]["branch_id"] != grant["branch_id"]
        or any(
            resolution["client_app_id"] != grant["client_app_id"]
            or resolution["principal_context_digest"] != grant["principal_context_digest"]
            for resolution in manifest["capability_resolutions"]
        )
    ):
        raise AssertionError("RunManifest source request crosses its admitted execution scope")
    mark_checks("run_manifest.request_binding", "run_manifest.conversation_binding")


def validate_state_machine(machine: dict[str, Any], allowed_states: set[str]) -> None:
    transitions = {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}
    if len(transitions) != len(machine["transitions"]):
        raise AssertionError("Duplicate state transition")
    transition_keys = {(item["from"], item["event"]) for item in machine["transitions"]}
    if len(transition_keys) != len(machine["transitions"]):
        raise AssertionError("State machine is non-deterministic: duplicate (from,event)")
    used = {machine["initial_state"], *machine["terminal_states"]}
    for source, _, target in transitions:
        used.update((source, target))
    if used != allowed_states:
        raise AssertionError(f"State machine/Schema state mismatch: missing={allowed_states-used}, extra={used-allowed_states}")
    terminal = set(machine["terminal_states"])
    if any(source in terminal for source, _, _ in transitions):
        raise AssertionError("Terminal states must not have outgoing transitions")
    reachable = {machine["initial_state"]}
    changed = True
    while changed:
        changed = False
        for source, _, target in transitions:
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    if allowed_states - reachable:
        raise AssertionError(f"Unreachable states: {allowed_states-reachable}")


def validate_work_order_failure_paths(machine: dict[str, Any]) -> None:
    transitions = {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}
    required = {(state, "fail", "failed") for state in ("queued", "waiting", "paused")}
    if not required <= transitions:
        raise AssertionError("WorkOrder lacks a truthful failure path from queued, waiting or paused")
    mark_checks("work_order.failure_paths")


def status_enum(schema_path: str) -> set[str]:
    return set(load(schema_path)["properties"]["status"]["enum"])


work_order_machine = load("contracts/state-machines/work-order-v1.json")
validate_state_machine(work_order_machine, status_enum("contracts/schemas/work-order-state.schema.json"))
validate_work_order_failure_paths(work_order_machine)
validate_state_machine(load("contracts/state-machines/conversation-v1.json"), status_enum("contracts/schemas/conversation.schema.json"))
validate_state_machine(load("contracts/state-machines/agent-runtime-run-v1.json"), status_enum("contracts/schemas/agent-runtime-run-status.schema.json"))
validate_state_machine(load("contracts/state-machines/runtime-recording-v1.json"), status_enum("contracts/schemas/runtime-recording.schema.json"))
invocation_machine = load("contracts/state-machines/invocation-v2.json")
validate_state_machine(invocation_machine, status_enum("contracts/schemas/invocation-record.schema.json"))
if any(item["from"] in {"executing", "outcome_unknown", "reconciling", "manual_review"} and item["to"] == "cancelled" for item in invocation_machine["transitions"]):
    raise AssertionError("In-flight/unknown Invocation cannot transition directly to cancelled")
if any(item["event"] == "abandon" for item in invocation_machine["transitions"]):
    raise AssertionError("Invocation abandon must explicitly bind risk acceptance")
if any(item["event"] == "retryable_failure" for item in invocation_machine["transitions"]):
    raise AssertionError("Invocation retry transition must distinguish idempotent retry from approved non-idempotent retry")
sandbox_machine = load("contracts/state-machines/sandbox-operation-v2.json")
validate_state_machine(sandbox_machine, status_enum("contracts/schemas/sandbox-operation-record.schema.json"))
unsafe_direct_cancel = {"running", "reconciling", "manual_review_required"}
if any(item["from"] in unsafe_direct_cancel and item["to"] == "cancelled" for item in sandbox_machine["transitions"]):
    raise AssertionError("In-flight/unknown Sandbox operation cannot transition directly to cancelled")

nondeterministic = copy.deepcopy(invocation_machine)
nondeterministic["transitions"].append({"from": "prepared", "event": "dispatch", "to": "failed"})
try:
    validate_state_machine(nondeterministic, status_enum("contracts/schemas/invocation-record.schema.json"))
except AssertionError:
    pass
else:
    raise AssertionError("Expected non-deterministic state-machine fixture to fail")
orphaned = copy.deepcopy(invocation_machine)
orphaned["transitions"].append({"from": "orphaned", "event": "remain_orphaned", "to": "orphaned"})
try:
    validate_state_machine(orphaned, status_enum("contracts/schemas/invocation-record.schema.json") | {"orphaned"})
except AssertionError:
    pass
else:
    raise AssertionError("Expected unreachable non-terminal state fixture to fail")

work_order_failure_negative = load("contracts/tests/semantic-invalid/work-order-failure-path-cases.json")
for case in work_order_failure_negative["cases"]:
    candidate = copy.deepcopy(work_order_machine)
    candidate["transitions"] = [
        transition for transition in candidate["transitions"]
        if not (transition["from"] == case["remove_failure_from"] and transition["event"] == "fail")
    ]
    try:
        validate_work_order_failure_paths(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected WorkOrder failure-path fixture to fail: {case['id']}")

context = load("examples/contracts/run-admission-context.json")
manifest = load("examples/contracts/run-manifest-v2.json")
no_sandbox_manifest = load("examples/contracts/run-manifest-no-sandbox.json")
workflow_run = load("examples/contracts/workflow-run.json")
agent_run = load("examples/contracts/agent-run.json")
runtime_start = load("examples/contracts/agent-runtime-start-request.json")
renewed_runtime_authorization = load("examples/contracts/runtime-authorization-renewed.json")
runtime_token = load("examples/contracts/agent-runtime-invocation-token-claims.json")
capability_request = load("examples/contracts/capability-invocation-request.json")
capability_token = load("examples/contracts/capability-invocation-token-claims.json")
capability_status_token = load("examples/contracts/capability-invocation-status-token-claims.json")
capability_cancel = load("examples/contracts/capability-cancellation-request.json")
capability_cancel_token = load("examples/contracts/capability-cancellation-token-claims.json")
capability_result = load("examples/contracts/capability-invocation-result.json")
artifact_staging_grant = load("examples/contracts/artifact-staging-grant.json")
artifact_staging_object = load("examples/contracts/artifact-staging-object-request.json")
artifact_stage_token = load("examples/contracts/artifact-gateway-stage-token-claims.json")
artifact_staging_commit = load("examples/contracts/artifact-staging-commit-request.json")
artifact_commit_token = load("examples/contracts/artifact-gateway-commit-token-claims.json")
artifact_read_token = load("examples/contracts/artifact-gateway-read-token-claims.json")
egress_request = load("examples/contracts/egress-http-request.json")
egress_response = load("examples/contracts/egress-http-response.json")
egress_token = load("examples/contracts/egress-invocation-token-claims.json")
workspace_content_manifest = load("examples/contracts/workspace-content-manifest.json")
canonical_event = load("examples/contracts/canonical-event-v2.json")
semantic_traceability = load("contracts/semantic-constraints-v1.json")
event_registry = load("contracts/event-types/agent-runtime-core-v1.json")
platform_event_registry = load("contracts/event-types/platform-core-v1.json")
meter = load("examples/contracts/meter-definition.json")
usage_entry = load("examples/contracts/technical-usage-entry.json")
usage_report = load("examples/contracts/usage-report.json")
settlement = load("examples/contracts/business-settlement-envelope.json")
policy_decision = load("examples/contracts/policy-decision.json")
execution_budget = load("examples/contracts/execution-budget.json")
gateway_connect = load("examples/contracts/runtime-gateway-frame.json")
gateway_control = load("examples/contracts/runtime-gateway-control-frame.json")
runtime_session_request = load("examples/contracts/runtime-session-request.json")
conformance_suites = [
    load("contracts/conformance/runtime/v1/suite.json"),
    load("contracts/conformance/sandbox/v1/suite.json"),
    load("contracts/conformance/runtime-gateway/v1/suite.json"),
    load("contracts/conformance/capability/v1/suite.json"),
    load("contracts/conformance/execution-gateway/v1/suite.json"),
]
validate_provider_architecture(context, conformance_suites)
validate_execution_topology(manifest, workflow_run, agent_run, runtime_start)
renewed_runtime_start = copy.deepcopy(runtime_start)
renewed_runtime_start["invocation_attempt_id"] = renewed_runtime_authorization[
    "artifact_grants"
][0]["execution_scope"]["invocation_attempt_id"]
renewed_runtime_start["runtime_authorization"] = renewed_runtime_authorization
validate_runtime_authorization(
    renewed_runtime_authorization,
    manifest,
    renewed_runtime_start,
    runtime_start["runtime_authorization"],
)
validate_runtime_token(runtime_token, manifest, agent_run, runtime_start)
capability_resolution = next(
    item for item in manifest["capability_resolutions"]
    if item["resolution_id"] == capability_request["provider_resolution_id"]
)
validate_capability_invocation(
    capability_request, capability_token, capability_resolution, manifest
)
capability_status_operation = {
    "operation": "status",
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "provider_operation_id": capability_status_token["provider_operation_id"],
}
validate_capability_invocation(
    capability_request, capability_status_token, capability_resolution, manifest,
    capability_status_operation, capability_token,
)
validate_capability_invocation(
    capability_request, capability_cancel_token, capability_resolution, manifest,
    capability_cancel, capability_status_token,
)
validate_artifact_gateway(
    artifact_staging_grant, artifact_staging_object, artifact_stage_token,
    artifact_staging_commit, artifact_commit_token,
    capability_request["input_artifact_grants"][0], artifact_read_token, capability_request,
)
validate_egress_gateway(
    egress_request, egress_token, egress_response,
    manifest["gateway_bindings"]["egress"]["port"], runtime_start["runtime_authorization"],
)
validate_workspace_content_manifest(workspace_content_manifest)
validate_canonical_event_source(canonical_event)
validate_platform_event_registry_binding(canonical_event, platform_event_registry)
validate_gateway_frames(gateway_connect, gateway_control)
validate_runtime_session_request(
    runtime_session_request, manifest, {"runtime:view", "runtime:control"}
)
validate_event_registry(event_registry)
validate_event_registry(platform_event_registry)
if manifest["event_registry"] != {
    "registry_id": event_registry["registry_id"],
    "registry_version": event_registry["registry_version"],
    "registry_digest": event_registry["registry_digest"],
}:
    raise AssertionError("RunManifest binds a different EventTypeRegistry revision")
validate_usage_contracts(meter, usage_entry, usage_report, settlement)
validate_usage_observations(capability_result, meter, usage_entry)
validate_policy_decision(policy_decision)
for conformance_suite in conformance_suites:
    validate_conformance_suite(conformance_suite)
validate_run_admission(manifest, context)
validate_run_admission(no_sandbox_manifest, context)
grant = load("examples/contracts/execution-grant-claims.json")
work_order_grant = load("examples/contracts/execution-grant-work-order-claims.json")
conversation_turn_request = load("examples/contracts/conversation-turn-request.json")
work_order_request = load("examples/contracts/work-order.json")
control_request = load("examples/contracts/work-order-control-request.json")
control_grant = load("examples/contracts/execution-grant-control-claims.json")
conversation = load("examples/contracts/conversation.json")
validate_execution_grant_request(
    grant,
    conversation_turn_request,
    authenticated_conversation_id=conversation["conversation_id"],
)
validate_run_manifest_request_binding(manifest, grant, conversation_turn_request)
validate_execution_grant_request(
    work_order_grant,
    work_order_request,
    authenticated_conversation_id=work_order_grant["conversation_id"],
)
validate_execution_grant_request(
    control_grant,
    control_request,
    authenticated_conversation_id=control_request["conversation_id"],
)
validate_work_order_control_contract(control_request)
bound_runtime_command = load("examples/contracts/agent-runtime-command.json")
control_runtime_input = load("examples/contracts/work-order-control-runtime-input.json")
if bound_runtime_command["authorized_control_request_id"] != control_request["control_request_id"]:
    raise AssertionError("Agent Runtime command references a different WorkOrderControlRequest")
if bound_runtime_command.get("input_id") != control_runtime_input["input_id"] or bound_runtime_command.get("input_content_digest") != control_runtime_input["content_digest"]:
    raise AssertionError("Agent Runtime command input does not match the authorized control input")
if control_runtime_input["content"] != control_request["content"]["content"]:
    raise AssertionError("Platform RuntimeInputEnvelope changes authorized control content")
commercial = grant["commercial_authorization"]
validate_self_digest(commercial, "commercial_authorization_digest")
validate_self_digest(execution_budget, "budget_digest")
if commercial != context["commercial_authorization"]:
    raise AssertionError("ExecutionGrant and Run admission bind different CommercialAuthorizationSnapshots")
if not set(grant["capabilities"]) <= set(commercial["authorized_capabilities"]):
    raise AssertionError("ExecutionGrant capabilities exceed commercial authorization")
if any(name not in commercial["authorized_limits"] or value > commercial["authorized_limits"][name] for name, value in grant["limits"].items()):
    raise AssertionError("ExecutionGrant limits exceed commercial authorization")
if policy_decision["commercial_authorization_id"] != commercial["commercial_authorization_id"] or policy_decision["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]:
    raise AssertionError("PolicyDecision binds a different CommercialAuthorizationSnapshot")
if policy_decision["execution_budget_id"] != execution_budget["budget_id"] or policy_decision["execution_budget_digest"] != execution_budget["budget_digest"]:
    raise AssertionError("PolicyDecision binds a different ExecutionBudget")
if manifest["policy_decision"] != policy_decision:
    raise AssertionError("RunManifest binds a different PolicyDecision")
if manifest["execution_budget"] != execution_budget:
    raise AssertionError("RunManifest binds a different ExecutionBudget")
if usage_report["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]:
    raise AssertionError("UsageReport binds a different CommercialAuthorizationSnapshot")
if settlement["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]:
    raise AssertionError("Settlement envelope binds a different CommercialAuthorizationSnapshot")
manual = load("examples/contracts/sandbox-manual-review-decision.json")
validate_self_digest(manual, "decision_digest")
invocation_manual = load("examples/contracts/invocation-manual-review-decision.json")
validate_self_digest(invocation_manual, "decision_digest")

grant_binding_negative = load("contracts/tests/semantic-invalid/execution-grant-request-binding-cases.json")
for case in grant_binding_negative["cases"]:
    candidate_grant = copy.deepcopy(grant)
    candidate_request = copy.deepcopy(conversation_turn_request)
    authenticated_conversation_id = conversation["conversation_id"]
    if case["mutation"] == "request_digest_mismatch":
        candidate_grant["request_digest"] = "sha256:" + "f" * 64
    elif case["mutation"] == "request_contract_mismatch":
        candidate_grant["request_contract_id"] = "urn:agent-platform:work-order-request:v1"
    elif case["mutation"] == "client_message_mismatch":
        candidate_request["client_message_id"] = "client-msg-other"
        candidate_grant["request_digest"] = canonical_digest({
            key: value for key, value in candidate_request.items() if key != "execution_grant"
        })
    else:
        raise AssertionError(f"Unknown ExecutionGrant binding mutation: {case['mutation']}")
    try:
        validate_execution_grant_request(
            candidate_grant,
            candidate_request,
            authenticated_conversation_id=authenticated_conversation_id,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected ExecutionGrant binding fixture to fail: {case['id']}")

architecture_negative = load("contracts/tests/semantic-invalid/architecture-closure-cases.json")
for case in architecture_negative["cases"]:
    mutation = case["mutation"]
    try:
        if mutation == "provider_runtime_wrong_port":
            candidate = copy.deepcopy(context)
            runtime_revision = next(item for item in candidate["provider_revisions"] if item["provider_kind"] == "agent_runtime")
            runtime_revision["port"]["protocol"] = "capability-provider"
            validate_provider_architecture(candidate, conformance_suites)
        elif mutation == "orchestration_digest_mismatch":
            candidate_manifest = copy.deepcopy(manifest)
            candidate_manifest["orchestration_binding"]["binding_digest"] = "sha256:" + "f" * 64
            validate_execution_topology(candidate_manifest, workflow_run, agent_run, runtime_start)
        elif mutation == "agent_run_manifest_mismatch":
            candidate_agent_run = copy.deepcopy(agent_run)
            candidate_agent_run["run_manifest_digest"] = "sha256:" + "f" * 64
            validate_execution_topology(manifest, workflow_run, candidate_agent_run, runtime_start)
        elif mutation == "event_registry_duplicate":
            candidate = copy.deepcopy(event_registry)
            candidate["definitions"].append(copy.deepcopy(candidate["definitions"][0]))
            candidate["registry_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "registry_digest"})
            validate_event_registry(candidate)
        elif mutation == "usage_final_partial":
            candidate = copy.deepcopy(usage_report)
            candidate["entries"][0]["measurement_status"] = "partial"
            candidate["usage_report_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "usage_report_digest"})
            validate_usage_contracts(meter, candidate["entries"][0], candidate, settlement)
        elif mutation == "policy_deny_overridden":
            candidate = copy.deepcopy(policy_decision)
            candidate["evaluations"].append({
                "subject_kind": "egress", "subject_id": "forbidden", "action": "deny",
                "source": "platform", "rule_digest": "sha256:" + "f" * 64,
            })
            candidate["decision_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "decision_digest"})
            validate_policy_decision(candidate)
        elif mutation == "conformance_unknown_dependency":
            candidate = copy.deepcopy(conformance_suites[0])
            candidate["profiles"][0]["depends_on"] = ["missing-profile"]
            candidate["suite_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "suite_digest"})
            validate_conformance_suite(candidate)
        elif mutation == "execution_topology_cross_tenant":
            candidate_start = copy.deepcopy(runtime_start)
            candidate_start["tenant_id"] = "ten_other"
            candidate_start["request_digest"] = canonical_digest({key: item for key, item in candidate_start.items() if key != "request_digest"})
            validate_execution_topology(manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "workflow_root_mismatch":
            candidate_workflow = copy.deepcopy(workflow_run)
            candidate_workflow["root_agent_run_id"] = "agr_other"
            validate_execution_topology(manifest, candidate_workflow, agent_run, runtime_start)
        elif mutation == "provider_suite_digest_mismatch":
            candidate = copy.deepcopy(context)
            candidate["provider_revisions"][0]["conformance"][0]["suite_digest"] = "sha256:" + "f" * 64
            validate_provider_architecture(candidate, conformance_suites)
        elif mutation == "settlement_usage_binding_mismatch":
            candidate = copy.deepcopy(settlement)
            candidate["usage_report"]["tenant_id"] = "ten_other"
            candidate["settlement_envelope_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "settlement_envelope_digest"})
            validate_usage_contracts(meter, usage_entry, usage_report, candidate)
        elif mutation == "gateway_duplicate_resume_channel":
            candidate = copy.deepcopy(gateway_connect)
            candidate["resume_cursors"].append({"channel": "terminal", "sequence": 40})
            validate_gateway_frames(candidate, gateway_control)
        elif mutation == "runtime_token_request_digest_mismatch":
            candidate = copy.deepcopy(runtime_token)
            candidate["request_digest"] = "sha256:" + "f" * 64
            validate_runtime_token(candidate, manifest, agent_run, runtime_start)
        elif mutation == "provider_resolution_decision_digest_mismatch":
            candidate = copy.deepcopy(manifest["capability_resolutions"][0])
            candidate["decision_digest"] = "sha256:" + "f" * 64
            validate_provider_resolution(candidate)
        elif mutation == "provider_resolution_multiple_selected":
            candidate = copy.deepcopy(manifest["capability_resolutions"][0])
            duplicate = copy.deepcopy(candidate["candidate_evaluations"][0])
            duplicate["provider_instance_id"] = "provider-other"
            duplicate["provider_revision_id"] = "revision-other"
            duplicate["evidence_digest"] = "sha256:" + "e" * 64
            candidate["candidate_evaluations"].append(duplicate)
            candidate["decision_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "decision_digest"
            })
            validate_provider_resolution(candidate)
        else:
            raise AssertionError(f"Unknown architecture closure mutation: {mutation}")
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected architecture closure fixture to fail: {case['id']}")

negative = load("contracts/tests/semantic-invalid/run-manifest-cases.json")
for case in negative["cases"]:
    value = copy.deepcopy(manifest)
    registry = copy.deepcopy(context)
    mutation = case["mutation"]
    if mutation == "duplicate_sandbox_slot":
        duplicate = copy.deepcopy(value["sandboxes"][0]); duplicate["sandbox_id"] = "sbx_duplicate"; value["sandboxes"].append(duplicate)
    elif mutation == "missing_primary_slot":
        value["primary_sandbox_slot_key"] = "missing-slot"
    elif mutation == "wrong_run_manifest_digest":
        value["run_manifest_digest"] = "sha256:" + "0" * 64
    elif mutation == "conflicting_revision_snapshot":
        sandbox_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["sandboxes"][0]["resolution_id"]
        )
        sandbox_resolution["selected_provider_revision"]["configuration_digest"] = "sha256:" + "f" * 64
    elif mutation == "unadmitted_experience":
        value["selected_experiences"] = [{
            "selection": {
                "kind": "template",
                "catalog_entry_id": "unadmitted/template",
                "revision_id": "unadmitted-revision",
                "revision_digest": "sha256:" + "9" * 64,
                "capability_id": "template.html.generate",
            },
            "provider_instance_id": value["capability_resolutions"][0]["selected_provider_instance_id"],
            "provider_revision": copy.deepcopy(value["capability_resolutions"][0]["selected_provider_revision"]),
        }]
    elif mutation == "unauthorized_experience_entitlement":
        registry["commercial_authorization"]["authorized_entitlements"] = []
        registry["commercial_authorization"]["commercial_authorization_digest"] = canonical_digest({key: item for key, item in registry["commercial_authorization"].items() if key != "commercial_authorization_digest"})
        value["commercial_authorization"]["commercial_authorization_digest"] = registry["commercial_authorization"]["commercial_authorization_digest"]
    elif mutation == "missing_required_experience_tag":
        registry["experience_requirements"][0]["required_tags"] = ["nonexistent-tag"]
    elif mutation == "commercial_authorization_digest_mismatch":
        value["commercial_authorization"]["commercial_authorization_digest"] = "sha256:" + "7" * 64
    elif mutation == "scenario_definition_mismatch":
        registry["scenario_definition"]["id"] = "other-scenario"
        registry["scenario_definition"]["definition_digest"] = canonical_digest({key: item for key, item in registry["scenario_definition"].items() if key != "definition_digest"})
    else:
        raise AssertionError(f"Unknown mutation: {mutation}")
    if mutation != "wrong_run_manifest_digest":
        for resolution in value["capability_resolutions"]:
            resolution["decision_digest"] = canonical_digest({
                key: item for key, item in resolution.items() if key != "decision_digest"
            })
        value["run_manifest_digest"] = canonical_digest({key: item for key, item in value.items() if key != "run_manifest_digest"})
    try:
        validate_run_admission(value, registry)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected semantic fixture to fail: {case['id']}")

admission_negative = load("contracts/tests/semantic-invalid/run-admission-cases.json")
for case in admission_negative["cases"]:
    value = copy.deepcopy(manifest)
    registry = copy.deepcopy(context)
    mutation = case["mutation"]
    if mutation == "forged_provider_revision_digest":
        runtime_resolution = next(item for item in value["capability_resolutions"] if item["resolution_id"] == value["agent_runtime"]["resolution_id"])
        runtime_resolution["selected_provider_revision"]["provider_revision_digest"] = "sha256:" + "f" * 64
    elif mutation == "extraneous_capability_resolution":
        extra = copy.deepcopy(value["capability_resolutions"][0]); extra["resolution_id"] = "res_extra"; extra["capability"] = {"id": "scenario.unrequested", "version": "1.0", "profile": None}; value["capability_resolutions"].append(extra)
    elif mutation == "forged_admission_decision_digest":
        sandbox_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["sandboxes"][0]["resolution_id"]
        )
        sandbox_resolution["selected_provider_revision"]["admission_decision_digest"] = "sha256:" + "e" * 64
    elif mutation == "stale_admission_decision":
        previous = registry["admission_decisions"][0]
        revoked = {"decision_id": "pad_revoked_later", "provider_revision_id": previous["provider_revision_id"], "provider_revision_digest": previous["provider_revision_digest"], "decision_sequence": 2, "decision": "revoked", "reason": "Test revocation", "evidence_digest": "sha256:" + "9" * 64, "decided_by": "principal:test", "decided_at": "2026-07-16T09:30:00Z", "supersedes_decision_id": previous["decision_id"], "decision_digest": "sha256:" + "0" * 64}
        revoked["decision_digest"] = canonical_digest({key: item for key, item in revoked.items() if key != "decision_digest"}); registry["admission_decisions"].append(revoked)
    elif mutation == "forged_capability_definition_digest":
        value["capability_resolutions"][0]["capability_definition_digest"] = "sha256:" + "a" * 64
    elif mutation == "sandbox_unsupported_capability":
        value["sandboxes"][0]["required_capabilities"] = [{"id": "tool.echo", "version": "1.0", "profile": "default"}]
    elif mutation == "agent_runtime_resolution_missing":
        value["agent_runtime"]["resolution_id"] = "res_missing_runtime"
    elif mutation == "capability_incompatible_provider_kind":
        value["capability_resolutions"][1]["selected_provider_revision"] = copy.deepcopy(value["capability_resolutions"][0]["selected_provider_revision"])
        value["capability_resolutions"][1]["selected_provider_instance_id"] = value["capability_resolutions"][0]["selected_provider_instance_id"]
    elif mutation == "missing_admission_predecessor":
        previous = registry["admission_decisions"][0]
        forged = copy.deepcopy(previous)
        forged.update({"decision_id": "pad_sequence_gap", "decision_sequence": 3, "supersedes_decision_id": "pad_missing", "decided_at": "2026-07-16T09:30:00Z"})
        forged["decision_digest"] = canonical_digest({key: item for key, item in forged.items() if key != "decision_digest"})
        registry["admission_decisions"].append(forged)
    elif mutation == "sandbox_resolution_wrong_kind":
        sandbox_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["sandboxes"][0]["resolution_id"]
        )
        runtime_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["agent_runtime"]["resolution_id"]
        )
        sandbox_resolution["selected_provider_instance_id"] = runtime_resolution["selected_provider_instance_id"]
        sandbox_resolution["selected_provider_revision"] = copy.deepcopy(runtime_resolution["selected_provider_revision"])
        sandbox_resolution["candidate_evaluations"] = copy.deepcopy(runtime_resolution["candidate_evaluations"])
        sandbox_resolution["decision_digest"] = canonical_digest({
            key: item for key, item in sandbox_resolution.items() if key != "decision_digest"
        })
    else:
        raise AssertionError(f"Unknown admission mutation: {mutation}")
    for resolution in value["capability_resolutions"]:
        resolution["decision_digest"] = canonical_digest({
            key: item for key, item in resolution.items() if key != "decision_digest"
        })
    value["run_manifest_digest"] = canonical_digest({key: item for key, item in value.items() if key != "run_manifest_digest"})
    try:
        validate_run_admission(value, registry)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected admission fixture to fail: {case['id']}")

def validate_case_decision_binding(
    record: dict[str, Any], case: dict[str, Any], decision: dict[str, Any],
    *, record_id_field: str, case_record_id_field: str,
) -> None:
    status_bindings = {
        "succeeded": ("resolve_success", "succeeded"),
        "failed": ("resolve_failure", "failed"),
        "cancelled": ("resolve_cancelled", "cancelled"),
        "abandoned": ("abandon", "abandoned"),
        "retry_scheduled": ("retry", "retry_approved"),
    }
    binding = status_bindings.get(record.get("status"))
    if binding is None:
        raise AssertionError("Aggregate status cannot carry a terminal/retry ManualReviewDecision binding")
    expected_decision, expected_outcome = binding
    validate_self_digest(case, "case_digest")
    validate_self_digest(decision, "decision_digest")
    if record[record_id_field] != case[case_record_id_field] or record[record_id_field] != decision[case_record_id_field]:
        raise AssertionError("Manual-review aggregate, case and decision bind different records")
    if record.get("reconciliation_case_id") != case["case_id"] or decision["case_id"] != case["case_id"]:
        raise AssertionError("Manual-review case_id reference is not closed")
    if record.get("manual_review_decision_id") != decision["decision_id"]:
        raise AssertionError("Manual-review decision_id reference is not closed")
    if record.get("current_attempt_id") != case["attempt_id"]:
        raise AssertionError("ReconciliationCase does not bind the aggregate's current attempt")
    if decision["case_version"] != case["case_version"] or decision["case_digest"] != case["case_digest"]:
        raise AssertionError("ManualReviewDecision does not bind the exact ReconciliationCase version")
    if case["status"] != "resolved" or case.get("resolved_outcome") != expected_outcome:
        raise AssertionError("ReconciliationCase outcome conflicts with the aggregate terminal/retry status")
    if decision["decision"] != expected_decision:
        raise AssertionError("ManualReviewDecision conflicts with the aggregate terminal/retry status")
    case_evidence, decision_evidence = set(case["evidence_references"]), set(decision["evidence_references"])
    if not case_evidence or not decision_evidence or not decision_evidence.issubset(case_evidence):
        raise AssertionError("Manual review must cite non-empty evidence recorded on the resolved case")
    if expected_decision == "abandon" and decision["risk_accepted"] is not True:
        raise AssertionError("Abandon requires explicit risk acceptance")
    parse_time = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    opened_at = parse_time(case["opened_at"])
    resolved_at = parse_time(case["resolved_at"])
    decided_at = parse_time(decision["occurred_at"])
    if not opened_at <= resolved_at <= decided_at:
        raise AssertionError("Adjudication timestamps must satisfy opened_at <= resolved_at <= decision.occurred_at")
    for aggregate_field in ("updated_at", "completed_at"):
        if aggregate_field in record and decided_at > parse_time(record[aggregate_field]):
            raise AssertionError(f"Decision occurred after aggregate {aggregate_field}")


operation_schema = load("contracts/schemas/sandbox-operation-record.schema.json")
manual_schema = load("contracts/schemas/sandbox-manual-review-decision.schema.json")
operation_validator = Draft202012Validator(operation_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
manual_validator = Draft202012Validator(manual_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
operation = load("examples/contracts/sandbox-operation.json")
reconciliation = load("examples/contracts/sandbox-reconciliation-case.json")
validate_case_decision_binding(operation, reconciliation, manual, record_id_field="operation_id", case_record_id_field="operation_id")
if operation["current_attempt_number"] > operation["max_attempts"]:
    raise AssertionError("current_attempt_number exceeds max_attempts")
sandbox_negative = load("contracts/tests/semantic-invalid/sandbox-operation-cases.json")
for case in sandbox_negative["cases"]:
    candidate_operation = copy.deepcopy(operation)
    candidate_manual = copy.deepcopy(manual)
    if case["mutation"] == "attempt_number_exceeds_max":
        candidate_operation["current_attempt_number"] = candidate_operation["max_attempts"] + 1
        failed = candidate_operation["current_attempt_number"] > candidate_operation["max_attempts"]
    elif case["mutation"] == "running_without_current_attempt":
        candidate_operation["status"] = "running"; candidate_operation.pop("current_attempt_id", None)
        failed = bool(list(operation_validator.iter_errors(candidate_operation)))
    elif case["mutation"] == "abandon_without_risk_acceptance":
        candidate_manual["decision"] = "abandon"; candidate_manual["risk_accepted"] = False
        failed = bool(list(manual_validator.iter_errors(candidate_manual)))
    elif case["mutation"] == "cancelled_effect_completed":
        candidate_operation.update({
            "status": "cancelled", "terminal_reason": "cancelled", "completed_at": "2026-07-16T10:07:00Z",
            "cancellation_confirmation": {"confirmed_by": "provider", "evidence_reference": "evidence://provider/1", "external_effect_status": "effect_completed", "confirmed_at": "2026-07-16T10:07:00Z"},
        })
        failed = bool(list(operation_validator.iter_errors(candidate_operation)))
    elif case["mutation"] == "abandoned_without_manual_decision":
        candidate_operation.pop("manual_review_decision_id", None)
        failed = bool(list(operation_validator.iter_errors(candidate_operation)))
    elif case["mutation"] in {"forged_case_reference", "case_digest_mismatch", "empty_resolved_evidence"}:
        candidate_case = copy.deepcopy(reconciliation)
        if case["mutation"] == "forged_case_reference":
            candidate_operation["reconciliation_case_id"] = "src_forged"
        elif case["mutation"] == "case_digest_mismatch":
            candidate_manual["case_digest"] = "sha256:" + "f" * 64
            candidate_manual["decision_digest"] = canonical_digest({key: item for key, item in candidate_manual.items() if key != "decision_digest"})
        else:
            candidate_case["evidence_references"] = []
            candidate_case["case_digest"] = canonical_digest({key: item for key, item in candidate_case.items() if key != "case_digest"})
        try:
            validate_case_decision_binding(candidate_operation, candidate_case, candidate_manual, record_id_field="operation_id", case_record_id_field="operation_id")
        except AssertionError:
            failed = True
        else:
            failed = False
    else:
        raise AssertionError(f"Unknown Sandbox mutation: {case['mutation']}")
    if not failed:
        raise AssertionError(f"Expected Sandbox semantic fixture to fail: {case['id']}")

invocation_schema = load("contracts/schemas/invocation-record.schema.json")
invocation_manual_schema = load("contracts/schemas/invocation-manual-review-decision.schema.json")
invocation_validator = Draft202012Validator(invocation_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
invocation_manual_validator = Draft202012Validator(invocation_manual_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
invocation = load("examples/contracts/invocation-record.json")
invocation_reconciliation = load("examples/contracts/invocation-reconciliation-case.json")
validate_case_decision_binding(invocation, invocation_reconciliation, invocation_manual, record_id_field="invocation_id", case_record_id_field="invocation_id")
retry_invocation = load("examples/contracts/invocation-non-idempotent-retry.json")
retry_case = load("examples/contracts/invocation-retry-reconciliation-case.json")
retry_decision = load("examples/contracts/invocation-retry-manual-review-decision.json")
validate_case_decision_binding(retry_invocation, retry_case, retry_decision, record_id_field="invocation_id", case_record_id_field="invocation_id")
invocation_negative = load("contracts/tests/semantic-invalid/invocation-cases.json")
for case in invocation_negative["cases"]:
    candidate = copy.deepcopy(invocation)
    decision = copy.deepcopy(invocation_manual)
    if case["mutation"] == "attempt_count_exceeds_max":
        candidate["attempt_count"] = candidate["max_attempts"] + 1
        failed = candidate["attempt_count"] > candidate["max_attempts"]
    elif case["mutation"] == "executing_without_current_attempt":
        candidate["status"] = "executing"; candidate.pop("current_attempt_id", None)
        failed = bool(list(invocation_validator.iter_errors(candidate)))
    elif case["mutation"] == "abandoned_without_manual_decision":
        candidate.update({"status": "abandoned", "completed_at": "2026-07-16T10:45:00Z", "terminal_reason": "unknown external outcome"})
        candidate.pop("manual_review_decision_id", None)
        failed = bool(list(invocation_validator.iter_errors(candidate)))
    elif case["mutation"] == "abandon_without_risk_acceptance":
        decision["risk_accepted"] = False
        failed = bool(list(invocation_manual_validator.iter_errors(decision)))
    elif case["mutation"] in {"forged_case_reference", "forged_decision_reference", "case_digest_mismatch", "outcome_mismatch", "empty_resolved_evidence", "aggregate_status_mismatch", "decision_before_case_opened"}:
        candidate_case = copy.deepcopy(invocation_reconciliation)
        if case["mutation"] == "forged_case_reference":
            candidate["reconciliation_case_id"] = "irc_forged"
        elif case["mutation"] == "forged_decision_reference":
            candidate["manual_review_decision_id"] = "imd_forged"
        elif case["mutation"] == "case_digest_mismatch":
            decision["case_digest"] = "sha256:" + "e" * 64
            decision["decision_digest"] = canonical_digest({key: item for key, item in decision.items() if key != "decision_digest"})
        elif case["mutation"] == "outcome_mismatch":
            candidate_case["resolved_outcome"] = "failed"
            candidate_case["case_digest"] = canonical_digest({key: item for key, item in candidate_case.items() if key != "case_digest"})
        elif case["mutation"] == "aggregate_status_mismatch":
            candidate["status"] = "succeeded"
            candidate["result_reference"] = "artifact://result/contradictory"
        elif case["mutation"] == "decision_before_case_opened":
            decision["occurred_at"] = "2026-07-16T09:00:00Z"
            decision["decision_digest"] = canonical_digest({key: item for key, item in decision.items() if key != "decision_digest"})
        else:
            candidate_case["evidence_references"] = []
            candidate_case["case_digest"] = canonical_digest({key: item for key, item in candidate_case.items() if key != "case_digest"})
        try:
            validate_case_decision_binding(candidate, candidate_case, decision, record_id_field="invocation_id", case_record_id_field="invocation_id")
        except AssertionError:
            failed = True
        else:
            failed = False
    elif case["mutation"] == "non_idempotent_retry_without_approval":
        candidate = copy.deepcopy(retry_invocation)
        candidate.pop("reconciliation_case_id", None)
        candidate.pop("manual_review_decision_id", None)
        failed = bool(list(invocation_validator.iter_errors(candidate)))
    else:
        raise AssertionError(f"Unknown Invocation mutation: {case['mutation']}")
    if not failed:
        raise AssertionError(f"Expected Invocation semantic fixture to fail: {case['id']}")


def validate_invocation_attempt_sequence(aggregate: dict[str, Any], attempts: list[dict[str, Any]]) -> None:
    if aggregate["attempt_count"] > aggregate["max_attempts"] or len(attempts) != aggregate["attempt_count"]:
        raise AssertionError("Invocation aggregate attempt_count/max_attempts conflicts with Attempt history")
    if any(item["invocation_id"] != aggregate["invocation_id"] for item in attempts):
        raise AssertionError("InvocationAttempt belongs to a different Invocation")
    if any(item["request_digest"] != aggregate["request_digest"] for item in attempts):
        raise AssertionError("InvocationAttempt request_digest differs from the immutable aggregate request")
    attempt_ids = [item["invocation_attempt_id"] for item in attempts]
    attempt_numbers = [item["attempt_number"] for item in attempts]
    fencing_tokens = [item["fencing_token"] for item in attempts]
    if len(attempt_ids) != len(set(attempt_ids)):
        raise AssertionError("InvocationAttempt IDs must be unique")
    if attempt_numbers != list(range(1, len(attempts) + 1)):
        raise AssertionError("Invocation attempt numbers must be contiguous and start at one")
    if any(current <= previous for previous, current in zip(fencing_tokens, fencing_tokens[1:])):
        raise AssertionError("Invocation fencing tokens must be unique and strictly increasing")
    if aggregate.get("current_attempt_id") != attempt_ids[-1]:
        raise AssertionError("Invocation current_attempt_id must reference the latest Attempt")


invocation_attempt_fixture = load("contracts/tests/semantic-invalid/invocation-attempt-sequence.json")
invocation_attempt_aggregate = load(invocation_attempt_fixture["aggregate"])
invocation_attempts = [load(path) for path in invocation_attempt_fixture["attempts"]]
validate_invocation_attempt_sequence(invocation_attempt_aggregate, invocation_attempts)
for case in invocation_attempt_fixture["cases"]:
    candidate_aggregate = copy.deepcopy(invocation_attempt_aggregate)
    candidate_attempts = copy.deepcopy(invocation_attempts)
    if case["mutation"] == "duplicate_fencing_token":
        candidate_attempts[1]["fencing_token"] = candidate_attempts[0]["fencing_token"]
    elif case["mutation"] == "attempt_number_gap":
        candidate_attempts[1]["attempt_number"] = 3
    elif case["mutation"] == "current_attempt_mismatch":
        candidate_aggregate["current_attempt_id"] = candidate_attempts[0]["invocation_attempt_id"]
    else:
        raise AssertionError(f"Unknown InvocationAttempt mutation: {case['mutation']}")
    try:
        validate_invocation_attempt_sequence(candidate_aggregate, candidate_attempts)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected InvocationAttempt sequence fixture to fail: {case['id']}")

attempt_sequence = load("contracts/tests/semantic-invalid/sandbox-attempt-sequence.json")
attempts = attempt_sequence["attempts"]
attempt_numbers = [item["attempt_number"] for item in attempts]
fencing_tokens = [item["fencing_token"] for item in attempts]
if attempt_numbers != list(range(1, len(attempts) + 1)):
    raise AssertionError("Sandbox attempt numbers must be contiguous and start at one")
if any(current <= previous for previous, current in zip(fencing_tokens, fencing_tokens[1:])):
    pass
else:
    raise AssertionError("Expected Sandbox fencing-token negative fixture to fail")


def validate_conversation_message_sequence(messages: list[dict[str, Any]]) -> None:
    if not messages:
        return
    conversation_id = messages[0]["conversation_id"]
    identifiers = [item["message_id"] for item in messages]
    if len(identifiers) != len(set(identifiers)):
        raise AssertionError("Conversation message IDs must be unique")
    if [item["message_sequence"] for item in messages] != list(range(1, len(messages) + 1)):
        raise AssertionError("Conversation message_sequence must be contiguous from one")
    if any(item["conversation_id"] != conversation_id for item in messages):
        raise AssertionError("Conversation message history contains a cross-Conversation record")
    prior: set[str] = set()
    for item in messages:
        parent = item.get("parent_message_id")
        if parent is not None and parent not in prior:
            raise AssertionError("Conversation parent_message_id must reference a prior immutable message")
        prior.add(item["message_id"])


conversation_fixture = load("contracts/tests/semantic-invalid/conversation-message-sequence.json")
validate_conversation_message_sequence(conversation_fixture["messages"])
for case in conversation_fixture["cases"]:
    candidate = copy.deepcopy(conversation_fixture["messages"])
    if case["mutation"] == "sequence_gap":
        candidate[1]["message_sequence"] = 3
    elif case["mutation"] == "duplicate_message_id":
        candidate[1]["message_id"] = candidate[0]["message_id"]
    elif case["mutation"] == "parent_not_prior":
        candidate[1]["parent_message_id"] = "msg_future"
    elif case["mutation"] == "cross_conversation":
        candidate[1]["conversation_id"] = "conv_other"
    else:
        raise AssertionError(f"Unknown Conversation mutation: {case['mutation']}")
    try:
        validate_conversation_message_sequence(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Conversation semantic fixture to fail: {case['id']}")


def validate_runtime_recording_sequence(recording: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
    if recording["chunk_count"] != len(chunks):
        raise AssertionError("RuntimeRecording chunk_count conflicts with persisted chunk history")
    if any(item["recording_id"] != recording["recording_id"] for item in chunks):
        raise AssertionError("RuntimeRecording contains a chunk from another recording")
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for item in chunks:
        by_channel.setdefault(item["channel"], []).append(item)
        start = datetime.fromisoformat(item["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(item["ended_at"].replace("Z", "+00:00"))
        if start > end or item["start_work_sequence"] > item["end_work_sequence"]:
            raise AssertionError("RuntimeRecording chunk chronology is reversed")
    for channel_chunks in by_channel.values():
        if [item["chunk_sequence"] for item in channel_chunks] != list(range(1, len(channel_chunks) + 1)):
            raise AssertionError("RuntimeRecording chunk_sequence must be contiguous per channel")
        for previous, current in zip(channel_chunks, channel_chunks[1:]):
            if current["start_work_sequence"] < previous["end_work_sequence"]:
                raise AssertionError("RuntimeRecording work_sequence ranges overlap or reverse")


recording_fixture = load("contracts/tests/semantic-invalid/runtime-recording-sequence.json")
validate_runtime_recording_sequence(recording_fixture["recording"], recording_fixture["chunks"])
for case in recording_fixture["cases"]:
    candidate = copy.deepcopy(recording_fixture["chunks"])
    if case["mutation"] == "sequence_gap":
        candidate[1]["chunk_sequence"] = 3
    elif case["mutation"] == "cross_recording":
        candidate[1]["recording_id"] = "rec_other"
    elif case["mutation"] == "work_sequence_reversal":
        candidate[1]["start_work_sequence"] = 1
    elif case["mutation"] == "time_reversal":
        candidate[1]["ended_at"] = "2026-07-15T10:04:00Z"
        candidate[1]["started_at"] = "2026-07-15T10:05:00Z"
    else:
        raise AssertionError(f"Unknown RuntimeRecording mutation: {case['mutation']}")
    try:
        validate_runtime_recording_sequence(recording_fixture["recording"], candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected RuntimeRecording semantic fixture to fail: {case['id']}")


def validate_runtime_command_sequence(commands: list[dict[str, Any]]) -> None:
    if not commands:
        return
    runtime_run_id = commands[0]["runtime_run_id"]
    identifiers = [item["command_id"] for item in commands]
    if len(identifiers) != len(set(identifiers)):
        raise AssertionError("Agent Runtime command IDs must be unique")
    if [item["command_sequence"] for item in commands] != list(range(1, len(commands) + 1)):
        raise AssertionError("Agent Runtime command_sequence must be contiguous from one")
    if any(item["runtime_run_id"] != runtime_run_id for item in commands):
        raise AssertionError("Agent Runtime command history contains another run")
    fencing = [item["fencing_token"] for item in commands]
    if any(current <= previous for previous, current in zip(fencing, fencing[1:])):
        raise AssertionError("Agent Runtime command fencing_token must strictly increase")


runtime_command_fixture = load("contracts/tests/semantic-invalid/agent-runtime-command-sequence.json")
validate_runtime_command_sequence(runtime_command_fixture["commands"])
for case in runtime_command_fixture["cases"]:
    candidate = copy.deepcopy(runtime_command_fixture["commands"])
    if case["mutation"] == "sequence_gap":
        candidate[1]["command_sequence"] = 3
    elif case["mutation"] == "stale_fencing":
        candidate[1]["fencing_token"] = candidate[0]["fencing_token"]
    elif case["mutation"] == "duplicate_id":
        candidate[1]["command_id"] = candidate[0]["command_id"]
    elif case["mutation"] == "cross_run":
        candidate[1]["runtime_run_id"] = "runtime_other"
    else:
        raise AssertionError(f"Unknown Agent Runtime command mutation: {case['mutation']}")
    try:
        validate_runtime_command_sequence(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Agent Runtime command semantic fixture to fail: {case['id']}")


def validate_workspace_revision(workspace_revision: dict[str, Any]) -> None:
    validate_self_digest(workspace_revision, "revision_digest")
    if workspace_revision["revision_number"] == 1 and workspace_revision["parent_revision_id"] is not None:
        raise AssertionError("Initial WorkspaceRevision cannot have a parent")
    if workspace_revision["revision_number"] > 1 and workspace_revision["parent_revision_id"] is None:
        raise AssertionError("Later WorkspaceRevision must reference its immediate predecessor")


def validate_conversation_branch(
    branch: dict[str, Any], message: dict[str, Any], work_order: dict[str, Any],
    workspace_revision: dict[str, Any],
) -> None:
    if (branch["head_message_id"] is None) != (branch["head_message_sequence"] == 0):
        raise AssertionError("ConversationBranch head ID and sequence do not represent the same head")
    if branch["head_message_id"] is not None:
        if message["message_id"] != branch["head_message_id"] or message["message_sequence"] != branch["head_message_sequence"]:
            raise AssertionError("ConversationBranch head does not bind the projected ConversationMessage")
        if message["conversation_id"] != branch["conversation_id"] or message["branch_id"] != branch["branch_id"]:
            raise AssertionError("ConversationBranch head belongs to another Conversation or branch")
    if branch["active_work_order_id"] is not None:
        work = work_order["work"]
        if work["conversation_id"] != branch["conversation_id"] or work["branch_id"] != branch["branch_id"]:
            raise AssertionError("ConversationBranch active WorkOrder belongs to another Conversation or branch")
    validate_workspace_revision(workspace_revision)
    if workspace_revision["workspace_revision_id"] != branch["workspace_head_revision_id"]:
        raise AssertionError("ConversationBranch references a different WorkspaceRevision")
    if workspace_revision["revision_digest"] != branch["workspace_head_revision_digest"]:
        raise AssertionError("ConversationBranch Workspace head digest is stale or forged")
    if workspace_revision["branch_id"] != branch["branch_id"]:
        raise AssertionError("ConversationBranch WorkspaceRevision belongs to another branch")
    mark_checks("conversation_branch.head_consistency", "conversation_branch.workspace_binding")


branch_fixture = load("contracts/tests/semantic-invalid/conversation-branch-cases.json")
branch = load(branch_fixture["branch"])
branch_message = load(branch_fixture["message"])
branch_work_order = load(branch_fixture["work_order"])
branch_workspace_revision = load("examples/contracts/workspace-revision.json")
validate_conversation_branch(branch, branch_message, branch_work_order, branch_workspace_revision)
for case in branch_fixture["cases"]:
    candidate_branch = copy.deepcopy(branch)
    candidate_message = copy.deepcopy(branch_message)
    candidate_work_order = copy.deepcopy(branch_work_order)
    candidate_workspace_revision = copy.deepcopy(branch_workspace_revision)
    if case["mutation"] == "zero_sequence_with_head":
        candidate_branch["head_message_sequence"] = 0
    elif case["mutation"] == "positive_sequence_without_head":
        candidate_branch["head_message_id"] = None
    elif case["mutation"] == "cross_conversation_message":
        candidate_message["conversation_id"] = "conv_other"
    elif case["mutation"] == "active_work_order_branch_mismatch":
        candidate_work_order["work"]["branch_id"] = "other-branch"
    elif case["mutation"] == "workspace_head_digest_mismatch":
        candidate_branch["workspace_head_revision_digest"] = "sha256:" + "f" * 64
    elif case["mutation"] == "workspace_revision_cross_branch":
        candidate_workspace_revision["branch_id"] = "other-branch"
        candidate_workspace_revision["revision_digest"] = canonical_digest({
            key: item for key, item in candidate_workspace_revision.items() if key != "revision_digest"
        })
        candidate_branch["workspace_head_revision_digest"] = candidate_workspace_revision["revision_digest"]
    elif case["mutation"] == "workspace_first_revision_has_parent":
        candidate_workspace_revision["parent_revision_id"] = "wsr_parent"
        candidate_workspace_revision["revision_digest"] = canonical_digest({
            key: item for key, item in candidate_workspace_revision.items() if key != "revision_digest"
        })
        candidate_branch["workspace_head_revision_digest"] = candidate_workspace_revision["revision_digest"]
    elif case["mutation"] == "workspace_later_revision_missing_parent":
        candidate_workspace_revision["revision_number"] = 2
        candidate_workspace_revision["parent_revision_id"] = None
        candidate_workspace_revision["revision_digest"] = canonical_digest({
            key: item for key, item in candidate_workspace_revision.items() if key != "revision_digest"
        })
        candidate_branch["workspace_head_revision_digest"] = candidate_workspace_revision["revision_digest"]
    else:
        raise AssertionError(f"Unknown ConversationBranch mutation: {case['mutation']}")
    try:
        validate_conversation_branch(
            candidate_branch,
            candidate_message,
            candidate_work_order,
            candidate_workspace_revision,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected ConversationBranch semantic fixture to fail: {case['id']}")


validate_semantic_traceability(semantic_traceability)

phase0_closure_negative = load("contracts/tests/semantic-invalid/phase0-closure-cases.json")
for case in phase0_closure_negative["cases"]:
    mutation = case["mutation"]
    try:
        if mutation == "runtime_input_digest_mismatch":
            candidate_manifest = copy.deepcopy(manifest)
            candidate_start = copy.deepcopy(runtime_start)
            candidate_manifest["input"]["content_digest"] = "sha256:" + "f" * 64
            candidate_start["input"] = copy.deepcopy(candidate_manifest["input"])
            candidate_start["request_digest"] = canonical_digest({
                key: value for key, value in candidate_start.items() if key != "request_digest"
            })
            validate_execution_topology(candidate_manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "runtime_context_mismatch":
            candidate_start = copy.deepcopy(runtime_start)
            candidate_start["context_package"]["context_package_id"] = "ctx_other"
            candidate_start["request_digest"] = canonical_digest({
                key: value for key, value in candidate_start.items() if key != "request_digest"
            })
            validate_execution_topology(manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "artifact_grant_tenant_mismatch":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["artifact_grants"][0]["tenant_id"] = "ten_other"
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            candidate_start["request_digest"] = canonical_digest({
                key: value for key, value in candidate_start.items() if key != "request_digest"
            })
            validate_execution_topology(manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "capability_token_tenant_mismatch":
            candidate = copy.deepcopy(capability_token)
            candidate["tenant_id"] = "ten_other"
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "capability_token_request_digest_mismatch":
            candidate = copy.deepcopy(capability_token)
            candidate["invocation_request_digest"] = "sha256:" + "f" * 64
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "provider_resolution_work_order_mismatch":
            candidate_manifest = copy.deepcopy(manifest)
            candidate = candidate_manifest["capability_resolutions"][0]
            candidate["work_order_id"] = "wrk_other"
            candidate["decision_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "decision_digest"
            })
            validate_execution_topology(candidate_manifest, workflow_run, agent_run, runtime_start)
        elif mutation == "workspace_manifest_count_mismatch":
            candidate = copy.deepcopy(workspace_content_manifest)
            candidate["entry_count"] += 1
            candidate["manifest_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "manifest_digest"
            })
            validate_workspace_content_manifest(candidate)
        elif mutation == "workspace_manifest_bytes_mismatch":
            candidate = copy.deepcopy(workspace_content_manifest)
            candidate["total_file_bytes"] += 1
            candidate["manifest_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "manifest_digest"
            })
            validate_workspace_content_manifest(candidate)
        elif mutation == "workspace_manifest_symlink_escape":
            candidate = copy.deepcopy(workspace_content_manifest)
            candidate["symlink_policy"] = "allow_relative_within_root"
            candidate["entries"].append({
                "path": "escape-link", "entry_type": "symlink", "mode": "0777", "symlink_target": "../outside",
            })
            candidate["entry_count"] += 1
            candidate["manifest_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "manifest_digest"
            })
            validate_workspace_content_manifest(candidate)
        elif mutation == "canonical_event_dedupe_mismatch":
            candidate = copy.deepcopy(canonical_event)
            candidate["dedupe_key"] = "sha256:" + "f" * 64
            validate_canonical_event_source(candidate)
        elif mutation == "canonical_event_provider_revision_missing":
            candidate = copy.deepcopy(canonical_event)
            candidate["producer_kind"] = "provider"
            candidate["metadata"]["provider_instance_id"] = "provider-instance"
            validate_canonical_event_source(candidate)
        elif mutation == "control_grant_work_order_mismatch":
            candidate = copy.deepcopy(control_grant)
            candidate["work_order_id"] = "wrk_other"
            validate_execution_grant_request(
                candidate, control_request, authenticated_conversation_id=control_request["conversation_id"]
            )
        elif mutation == "traceability_missing_constraint":
            candidate = copy.deepcopy(semantic_traceability)
            candidate["constraints"].pop()
            validate_semantic_traceability(candidate)
        elif mutation == "traceability_unknown_check_id":
            candidate = copy.deepcopy(semantic_traceability)
            enforcement = next(
                enforcement
                for entry in candidate["constraints"]
                for enforcement in entry["enforcements"]
                if enforcement["status"] == "contract_gate"
            )
            enforcement["check_id"] = "semantic.unknown"
            validate_semantic_traceability(candidate)
        elif mutation == "traceability_unexecuted_check_id":
            candidate = copy.deepcopy(semantic_traceability)
            enforcement = next(
                enforcement
                for entry in candidate["constraints"]
                for enforcement in entry["enforcements"]
                if enforcement["status"] == "contract_gate"
            )
            enforcement["check_id"] = "semantic_traceability.known_but_unexecuted"
            validate_semantic_traceability(candidate)
        elif mutation == "control_grant_stale_turn_binding":
            candidate = copy.deepcopy(control_grant)
            candidate["turn_id"] = "turn_stale"
            validate_execution_grant_request(
                candidate, control_request, authenticated_conversation_id=control_request["conversation_id"]
            )
        elif mutation == "principal_context_digest_mismatch":
            candidate = copy.deepcopy(grant)
            candidate["principal_context_digest"] = "sha256:" + "f" * 64
            validate_execution_grant_request(
                candidate, conversation_turn_request, authenticated_conversation_id=conversation["conversation_id"]
            )
        elif mutation == "execution_grant_snapshot_expired":
            candidate = copy.deepcopy(grant)
            candidate["principal_context"]["expires_at"] = "2026-07-16T08:59:59Z"
            candidate["principal_context"]["principal_context_digest"] = canonical_digest({
                key: value for key, value in candidate["principal_context"].items()
                if key != "principal_context_digest"
            })
            candidate["principal_context_digest"] = candidate["principal_context"]["principal_context_digest"]
            validate_execution_grant_request(
                candidate, conversation_turn_request, authenticated_conversation_id=conversation["conversation_id"]
            )
        elif mutation == "runtime_authorization_widens_permissions":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["authorization_sequence"] = 2
            authorization["predecessor_authorization_digest"] = runtime_start["runtime_authorization"]["authorization_digest"]
            authorization["renewal_reason"] = "adapter_restart"
            authorization["effective_permissions"]["model"]["allowed_model_profiles"].append("forbidden-model")
            authorization["effective_permissions"]["permissions_digest"] = canonical_digest({
                key: value for key, value in authorization["effective_permissions"].items()
                if key != "permissions_digest"
            })
            authorization["policy_decision"]["effective_permissions_digest"] = authorization[
                "effective_permissions"
            ]["permissions_digest"]
            authorization["policy_decision"]["decision_digest"] = canonical_digest({
                key: value for key, value in authorization["policy_decision"].items()
                if key != "decision_digest"
            })
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(
                authorization, manifest, candidate_start, runtime_start["runtime_authorization"]
            )
        elif mutation == "runtime_authorization_component_scope_mismatch":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["execution_budget"]["tenant_id"] = "ten_other"
            authorization["execution_budget"]["budget_digest"] = canonical_digest({
                key: value for key, value in authorization["execution_budget"].items()
                if key != "budget_digest"
            })
            authorization["policy_decision"]["execution_budget_digest"] = authorization[
                "execution_budget"
            ]["budget_digest"]
            authorization["policy_decision"]["decision_digest"] = canonical_digest({
                key: value for key, value in authorization["policy_decision"].items()
                if key != "decision_digest"
            })
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(authorization, manifest, candidate_start)
        elif mutation == "runtime_authorization_commercial_expiry_exceeded":
            candidate_manifest = copy.deepcopy(manifest)
            candidate_start = copy.deepcopy(runtime_start)
            candidate_manifest["commercial_authorization"]["expires_at"] = "2026-07-16T09:10:00Z"
            candidate_manifest["run_manifest_digest"] = canonical_digest({
                key: value for key, value in candidate_manifest.items() if key != "run_manifest_digest"
            })
            authorization = candidate_start["runtime_authorization"]
            authorization["commercial_authorization"] = copy.deepcopy(
                candidate_manifest["commercial_authorization"]
            )
            authorization["run_manifest_digest"] = candidate_manifest["run_manifest_digest"]
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(authorization, candidate_manifest, candidate_start)
        elif mutation == "runtime_artifact_grant_predates_authorization":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["artifact_grants"][0]["issued_at"] = "2026-07-16T09:00:59Z"
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(authorization, manifest, candidate_start)
        elif mutation == "capability_artifact_grant_outlives_deadline":
            candidate_request = copy.deepcopy(capability_request)
            candidate_token = copy.deepcopy(capability_token)
            candidate_request["input_artifact_grants"][0]["expires_at"] = "2026-07-16T09:20:01Z"
            candidate_request["input_artifact_grants"][0]["grant_digest"] = canonical_digest({
                key: value for key, value in candidate_request["input_artifact_grants"][0].items()
                if key != "grant_digest"
            })
            candidate_request["request_digest"] = canonical_digest({
                key: value for key, value in candidate_request.items() if key != "request_digest"
            })
            candidate_token["invocation_request_digest"] = candidate_request["request_digest"]
            candidate_token["operation_request_digest"] = candidate_request["request_digest"]
            candidate_token["exp"] = 1784193060
            validate_capability_invocation(
                candidate_request, candidate_token, capability_resolution, manifest
            )
        elif mutation == "required_gateway_disabled":
            candidate_start = copy.deepcopy(runtime_start)
            candidate_start["gateway_bindings"]["model"] = {
                "kind": "model", "mode": "disabled", "reason": "policy_denied",
            }
            validate_gateway_bindings(
                candidate_start["gateway_bindings"],
                candidate_start["runtime_authorization"]["execution_budget"],
                candidate_start["runtime_authorization"]["effective_permissions"],
            )
        elif mutation == "provider_usage_contains_platform_entry":
            candidate = copy.deepcopy(capability_result)
            candidate["usage"][0]["entry_id"] = "platform-owned"
            validate_usage_observations(candidate, meter, usage_entry)
        elif mutation == "capability_request_resolution_mismatch":
            candidate_request = copy.deepcopy(capability_request)
            candidate_request["provider_resolution_id"] = "res_other"
            candidate_request["request_digest"] = canonical_digest({
                key: value for key, value in candidate_request.items() if key != "request_digest"
            })
            validate_capability_invocation(
                candidate_request, capability_token, capability_resolution, manifest
            )
        elif mutation == "capability_token_audience_mismatch":
            candidate = copy.deepcopy(capability_token)
            candidate["aud"] = "urn:agent-platform:provider-instance:other"
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "capability_token_operation_replay":
            candidate = copy.deepcopy(capability_token)
            candidate["operation"] = "cancel"
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "capability_token_lineage_gap":
            candidate = copy.deepcopy(capability_status_token)
            candidate["authorization_sequence"] += 1
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest,
                capability_status_operation, capability_token,
            )
        elif mutation == "run_manifest_request_binding_mismatch":
            candidate = copy.deepcopy(manifest)
            candidate["request_binding"]["request_digest"] = "sha256:" + "f" * 64
            validate_run_manifest_request_binding(candidate, grant, conversation_turn_request)
        elif mutation == "staging_grant_gateway_mismatch":
            candidate_request = copy.deepcopy(capability_request)
            candidate_token = copy.deepcopy(capability_token)
            staging = candidate_request["output_staging_grant"]
            staging["gateway_binding"]["route_id"] = "artifact-route-other"
            staging["grant_digest"] = canonical_digest({
                key: value for key, value in staging.items() if key != "grant_digest"
            })
            candidate_request["request_digest"] = canonical_digest({
                key: value for key, value in candidate_request.items() if key != "request_digest"
            })
            candidate_token["staging_grant_digest"] = staging["grant_digest"]
            candidate_token["invocation_request_digest"] = candidate_request["request_digest"]
            candidate_token["operation_request_digest"] = candidate_request["request_digest"]
            validate_capability_invocation(
                candidate_request, candidate_token, capability_resolution, manifest
            )
        elif mutation == "gateway_contract_digest_mismatch":
            candidate = copy.deepcopy(manifest["gateway_bindings"])
            candidate["artifact"]["port"]["contract_digest"] = "sha256:" + "f" * 64
            validate_gateway_bindings(candidate, execution_budget, manifest["effective_permissions"])
        elif mutation == "artifact_gateway_request_digest_mismatch":
            candidate = copy.deepcopy(artifact_stage_token)
            candidate["request_digest"] = "sha256:" + "f" * 64
            validate_artifact_gateway(
                artifact_staging_grant, artifact_staging_object, candidate,
                artifact_staging_commit, artifact_commit_token,
                capability_request["input_artifact_grants"][0], artifact_read_token,
                capability_request,
            )
        elif mutation == "artifact_gateway_read_fencing_mismatch":
            candidate = copy.deepcopy(artifact_read_token)
            candidate["fencing_token"] += 1
            descriptor = {
                "operation": "read_content",
                "tenant_id": candidate["tenant_id"],
                "work_order_id": candidate["work_order_id"],
                "invocation_id": candidate["invocation_id"],
                "invocation_attempt_id": candidate["invocation_attempt_id"],
                "fencing_token": candidate["fencing_token"],
                "artifact_id": capability_request["input_artifact_grants"][0]["artifact_id"],
                "version_id": capability_request["input_artifact_grants"][0]["version_id"],
            }
            candidate["request_digest"] = canonical_digest(descriptor)
            validate_artifact_gateway(
                artifact_staging_grant, artifact_staging_object, artifact_stage_token,
                artifact_staging_commit, artifact_commit_token,
                capability_request["input_artifact_grants"][0], candidate,
                capability_request,
            )
        elif mutation == "egress_token_destination_mismatch":
            candidate = copy.deepcopy(egress_token)
            candidate["destination_id"] = "other-destination"
            validate_egress_gateway(
                egress_request, candidate, egress_response,
                manifest["gateway_bindings"]["egress"]["port"], runtime_start["runtime_authorization"],
            )
        else:
            raise AssertionError(f"Unknown Phase 0 closure mutation: {mutation}")
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Phase 0 closure fixture to fail: {case['id']}")


negative_fixture_count = sum(
    len(json.loads(path.read_text(encoding="utf-8")).get("cases", []))
    for path in (ROOT / "contracts/tests/semantic-invalid").glob("*.json")
)
print(f"Semantic validation passed with deterministic state-machine/safety checks and {negative_fixture_count} negative invariant fixtures.")
