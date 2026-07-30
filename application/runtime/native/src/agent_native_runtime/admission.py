from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from .contract_projection import canonicalize_json, decode_strict_ijson
from .errors import (
    AuthorizationBindingError,
    DigestMismatchError,
    EncodedBodyTooLargeError,
    StrictJsonError,
    TokenValidationError,
    UnsupportedOperationError,
)
from .kernel import Clock, NativeRuntimeKernel, system_clock
from .model import (
    CheckpointManifest,
    CommandMutation,
    EventPage,
    MutationAdmission,
    RuntimeConfiguration,
    RuntimeSecurityBinding,
    RuntimeStatus,
    StartMutation,
    parse_timestamp,
)
from .security import (
    InvocationContext,
    RuntimeContractProjection,
    RuntimeTokenVerifier,
    SecurityConfiguration,
)

START_SCHEMA_ID = "urn:agent-platform:agent-runtime-start-request:v1"
COMMAND_SCHEMA_ID = "urn:agent-platform:agent-runtime-command:v1"
STATUS_DESCRIPTOR_SCHEMA_ID = (
    "urn:agent-platform:agent-runtime-status-operation-descriptor:v1"
)
EVENT_DESCRIPTOR_SCHEMA_ID = (
    "urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1"
)
START_BODY_LIMIT = 8 * 1024 * 1024
COMMAND_BODY_LIMIT = 256 * 1024
GATEWAY_CONTRACT_IDS = {
    "model": "urn:agent-platform:openapi:capability-provider:v1",
    "tool": "urn:agent-platform:openapi:capability-provider:v1",
    "artifact": "urn:agent-platform:openapi:artifact-gateway:v1",
    "egress": "urn:agent-platform:openapi:egress-gateway:v1",
}


class SecureAdmissionCore:
    """Authenticated Contract admission with no HTTP, TLS, or token issuance."""

    def __init__(
        self,
        kernel: NativeRuntimeKernel,
        security: SecurityConfiguration,
        projection: RuntimeContractProjection,
    ) -> None:
        self.kernel = kernel
        self.security = security
        self.projection = projection
        self.tokens = RuntimeTokenVerifier(security, projection)

    @classmethod
    def migrate(
        cls,
        runtime: RuntimeConfiguration,
        security: SecurityConfiguration,
        *,
        clock: Clock = system_clock,
    ) -> None:
        cls._validate_configuration_binding(runtime, security)
        projection = RuntimeContractProjection.load(security)
        NativeRuntimeKernel.migrate(runtime, clock=clock)
        store = NativeRuntimeKernel(runtime, clock=clock).store
        store.bind_security_configuration(
            configuration_digest=security.digest(),
            contract_source_revision=projection.contract_source_revision,
            contract_manifest_digest=projection.contract_manifest_digest,
            runtime_suite_digest=projection.runtime_suite_digest,
            schema_closure_digest=projection.schema_closure_digest,
            now=clock(),
        )

    @classmethod
    def open_current(
        cls,
        runtime: RuntimeConfiguration,
        security: SecurityConfiguration,
        *,
        clock: Clock = system_clock,
    ) -> SecureAdmissionCore:
        cls._validate_configuration_binding(runtime, security)
        projection = RuntimeContractProjection.load(security)
        kernel = NativeRuntimeKernel.open_current(runtime, clock=clock)
        kernel.store.check_security_configuration(
            configuration_digest=security.digest(),
            contract_source_revision=projection.contract_source_revision,
            contract_manifest_digest=projection.contract_manifest_digest,
            runtime_suite_digest=projection.runtime_suite_digest,
            schema_closure_digest=projection.schema_closure_digest,
        )
        return cls(kernel, security, projection)

    @staticmethod
    def _validate_configuration_binding(
        runtime: RuntimeConfiguration, security: SecurityConfiguration
    ) -> None:
        if (
            runtime.provider_revision_id != security.provider_revision_id
            or runtime.runtime_revision != security.runtime_revision
            or runtime.provider_audience != security.provider_audience
        ):
            raise AuthorizationBindingError(
                "Runtime and security configuration bindings differ"
            )

    def start(
        self,
        encoded_body: bytes,
        compact_jws: str,
        *,
        authenticated_caller: str,
    ) -> RuntimeStatus:
        document = self._document(
            encoded_body, schema_id=START_SCHEMA_ID, encoded_limit=START_BODY_LIMIT
        )
        now = self.kernel.clock()
        mutation, binding, context, deadline = self._start_values(document, now)
        admission = self.tokens.verify(
            compact_jws,
            authenticated_caller=authenticated_caller,
            operation="start",
            now=now,
        )
        self._validate_admission_context(admission, context)
        self._validate_execution_window(admission, binding, deadline)
        return self.kernel.start(mutation, admission, binding)

    def submit_command(
        self,
        runtime_run_id: str,
        encoded_body: bytes,
        compact_jws: str,
        *,
        authenticated_caller: str,
    ) -> RuntimeStatus:
        mutation, admission, admitted_at = self.admit_command(
            runtime_run_id,
            encoded_body,
            compact_jws,
            authenticated_caller=authenticated_caller,
        )
        return self.kernel.submit_admitted_command(mutation, admission, admitted_at)

    def admit_command(
        self,
        runtime_run_id: str,
        encoded_body: bytes,
        compact_jws: str,
        *,
        authenticated_caller: str,
    ) -> tuple[CommandMutation, MutationAdmission, datetime]:
        document = self._document(
            encoded_body, schema_id=COMMAND_SCHEMA_ID, encoded_limit=COMMAND_BODY_LIMIT
        )
        if document.get("runtime_run_id") != runtime_run_id:
            raise AuthorizationBindingError(
                "Command path and body runtime_run_id differ"
            )
        self._require_self_digest(document, "command_digest", "Runtime Command")
        now = self.kernel.clock()
        admission = self.tokens.verify(
            compact_jws,
            authenticated_caller=authenticated_caller,
            operation="submit_command",
            now=now,
        )
        deadline = self._validate_command_context(document, admission)
        if admission.expires_at > deadline:
            raise AuthorizationBindingError(
                "Runtime command token outlives the command deadline"
            )
        mutation = self._command_mutation(document)
        admitted_at = self.kernel.validate_command(mutation, admission)
        return mutation, admission, admitted_at

    def status(
        self,
        runtime_run_id: str,
        compact_jws: str,
        *,
        authenticated_caller: str,
    ) -> RuntimeStatus:
        admission = self.tokens.verify(
            compact_jws,
            authenticated_caller=authenticated_caller,
            operation="read_status",
            now=self.kernel.clock(),
        )
        if admission.runtime_run_id != runtime_run_id:
            raise AuthorizationBindingError(
                "Status path and token runtime_run_id differ"
            )
        descriptor = {
            "operation": "read_status",
            "runtime_run_id": runtime_run_id,
            "invocation_id": admission.invocation_id,
            "invocation_attempt_id": admission.invocation_attempt_id,
            "fencing_token": admission.fencing_token,
        }
        self.projection.validate(STATUS_DESCRIPTOR_SCHEMA_ID, descriptor)
        if admission.operation_request_digest != _document_digest(descriptor):
            raise AuthorizationBindingError("Status descriptor and token digest differ")
        return self.kernel.authorized_status(admission)

    def events(
        self,
        runtime_run_id: str,
        compact_jws: str,
        *,
        authenticated_caller: str,
        after_event_sequence: int = 0,
        limit: int = 1000,
    ) -> EventPage:
        admission = self.tokens.verify(
            compact_jws,
            authenticated_caller=authenticated_caller,
            operation="read_events",
            now=self.kernel.clock(),
        )
        if admission.runtime_run_id != runtime_run_id:
            raise AuthorizationBindingError(
                "Event path and token runtime_run_id differ"
            )
        descriptor = {
            "operation": "read_events",
            "runtime_run_id": runtime_run_id,
            "invocation_id": admission.invocation_id,
            "invocation_attempt_id": admission.invocation_attempt_id,
            "fencing_token": admission.fencing_token,
            "after_event_sequence": after_event_sequence,
            "limit": limit,
        }
        self.projection.validate(EVENT_DESCRIPTOR_SCHEMA_ID, descriptor)
        if admission.operation_request_digest != _document_digest(descriptor):
            raise AuthorizationBindingError("Event descriptor and token digest differ")
        return self.kernel.authorized_events(
            admission,
            after_event_sequence=after_event_sequence,
            limit=limit,
        )

    def _document(
        self, encoded: bytes, *, schema_id: str, encoded_limit: int
    ) -> dict[str, Any]:
        if len(encoded) > encoded_limit:
            raise EncodedBodyTooLargeError(
                f"encoded Runtime document exceeds {encoded_limit} bytes"
            )
        try:
            value = decode_strict_ijson(
                encoded,
                max_depth=self.security.max_json_depth,
                max_nodes=self.security.max_json_nodes,
                max_number_token_bytes=self.security.max_number_token_bytes,
                max_decimal_exponent=self.security.max_decimal_exponent,
            )
        except ValueError as error:
            raise StrictJsonError("Runtime document is not Strict I-JSON") from error
        if not isinstance(value, dict) or any(
            not isinstance(key, str) for key in value
        ):
            raise StrictJsonError("Runtime document must be a JSON object")
        document = cast(dict[str, Any], value)
        self.projection.validate(schema_id, document)
        return document

    def _start_values(
        self, document: Mapping[str, Any], now: datetime
    ) -> tuple[StartMutation, RuntimeSecurityBinding, InvocationContext, datetime]:
        self._require_self_digest(document, "request_digest", "Runtime Start")
        authorization = _object(document, "runtime_authorization")
        budget = _object(authorization, "execution_budget")
        allocation = _object(authorization, "agent_run_budget_allocation")
        policy = _object(authorization, "policy_decision")
        permissions = _object(authorization, "effective_permissions")
        commercial = _object(authorization, "commercial_authorization")
        grants = _objects(authorization, "artifact_grants")
        context_package = _object(document, "context_package")
        runtime_input = _object(document, "input")
        gateway_bindings = _object(document, "gateway_bindings")

        for value, field, name in (
            (context_package, "context_package_digest", "ContextPackage"),
            (budget, "budget_digest", "ExecutionBudget"),
            (allocation, "allocation_digest", "AgentRunBudgetAllocation"),
            (policy, "decision_digest", "PolicyDecision"),
            (permissions, "permissions_digest", "EffectivePermissions"),
            (authorization, "authorization_digest", "RuntimeAuthorization"),
        ):
            self._require_self_digest(value, field, name)
        for grant in grants:
            self._require_self_digest(grant, "grant_digest", "ArtifactGrant")
        content = runtime_input.get("content")
        if _document_digest(content) != _string(runtime_input, "content_digest"):
            raise DigestMismatchError("Runtime input content digest differs")

        tenant_id = _string(document, "tenant_id")
        runtime_run_id = _string(document, "runtime_run_id")
        agent_run_id = _string(document, "agent_run_id")
        workflow_run_id = _string(document, "workflow_run_id")
        work_order_id = _string(document, "work_order_id")
        invocation_id = _string(document, "invocation_id")
        invocation_attempt_id = _string(document, "invocation_attempt_id")
        run_manifest_digest = _string(document, "run_manifest_digest")
        request_digest = _string(document, "request_digest")
        fencing_token = _integer(document, "fencing_token")
        deadline = _timestamp(document, "deadline_at")
        authorization_digest = _string(authorization, "authorization_digest")
        policy_digest = _string(policy, "decision_digest")
        budget_digest = _string(budget, "budget_digest")
        permissions_digest = _string(permissions, "permissions_digest")
        expected_scope = {"kind": "work_order", "work_order_id": work_order_id}

        for value, field, expected in (
            (authorization, "tenant_id", tenant_id),
            (authorization, "work_order_id", work_order_id),
            (authorization, "runtime_run_id", runtime_run_id),
            (authorization, "run_manifest_digest", run_manifest_digest),
            (budget, "tenant_id", tenant_id),
            (allocation, "tenant_id", tenant_id),
            (allocation, "work_order_id", work_order_id),
            (allocation, "agent_run_id", agent_run_id),
            (policy, "tenant_id", tenant_id),
            (permissions, "tenant_id", tenant_id),
        ):
            if value.get(field) != expected:
                raise AuthorizationBindingError(
                    f"Runtime Start {field} binding differs"
                )
        for value in (budget, policy, permissions):
            if value.get("execution_scope") != expected_scope:
                raise AuthorizationBindingError(
                    "Runtime authorization execution scope is not this WorkOrder"
                )
        if (
            allocation.get("work_order_budget_id") != budget.get("budget_id")
            or allocation.get("work_order_budget_digest") != budget_digest
        ):
            raise AuthorizationBindingError(
                "AgentRun allocation does not bind the WorkOrder budget"
            )
        allocation_limits = _object(allocation, "limits")
        budget_limits = _object(budget, "limits")
        if any(
            budget_limits.get(name) != value
            for name, value in allocation_limits.items()
        ):
            raise AuthorizationBindingError(
                "AgentRun allocation exceeds or differs from the WorkOrder budget"
            )
        if (
            policy.get("commercial_authorization_id")
            != commercial.get("commercial_authorization_id")
            or policy.get("commercial_authorization_digest")
            != commercial.get("commercial_authorization_digest")
            or policy.get("execution_budget_id") != budget.get("budget_id")
            or policy.get("execution_budget_digest") != budget_digest
            or policy.get("effective_permissions_digest") != permissions_digest
            or policy.get("decision_point") != "run_admission"
            or policy.get("outcome") != "allow"
        ):
            raise AuthorizationBindingError(
                "PolicyDecision does not authorize the presented Runtime Start"
            )

        topology = _object(document, "run_topology")
        if (
            topology.get("run_kind") != "root"
            or topology.get("root_agent_run_id") != agent_run_id
            or topology.get("run_depth") != 0
        ):
            raise UnsupportedOperationError("B03.2a1.0 admits only root Runtime Starts")
        if runtime_input.get(
            "source_kind"
        ) != "conversation_message" or runtime_input.get(
            "input_message_id"
        ) != document.get("input_message_id"):
            raise AuthorizationBindingError(
                "root Runtime input does not match input_message_id"
            )
        workspace = _object(document, "workspace_binding")
        if workspace.get("base_workspace_revision_id") != document.get(
            "workspace_revision_id"
        ) or workspace.get("base_workspace_revision_digest") != document.get(
            "workspace_revision_digest"
        ):
            raise AuthorizationBindingError(
                "Runtime workspace binding differs from the Start revision"
            )
        if (
            document.get("sandbox_bindings") != []
            or permissions.get("sandbox_slots") != []
        ):
            raise UnsupportedOperationError(
                "this Runtime revision requires no Sandbox bindings or permissions"
            )
        admission_limits = _object(document, "admission_limits")
        if len(canonicalize_json(content)) > _integer(
            admission_limits, "max_inline_input_bytes"
        ):
            raise AuthorizationBindingError("inline Runtime input exceeds its limit")

        gateway_ports = self._validate_gateway_bindings(
            gateway_bindings,
            budget=budget,
            permissions=permissions,
            has_artifact_grants=bool(grants),
        )

        grant_issued: list[datetime] = []
        grant_expires: list[datetime] = []
        artifact_port = gateway_ports.get("artifact")
        granted_digests: set[str] = set()
        for grant in grants:
            if (
                grant.get("tenant_id") != tenant_id
                or grant.get("execution_scope") != expected_scope
                or grant.get("runtime_run_id") != runtime_run_id
                or grant.get("invocation_id") != invocation_id
                or grant.get("invocation_attempt_id") != invocation_attempt_id
                or grant.get("gateway_binding") != artifact_port
            ):
                raise AuthorizationBindingError(
                    "ArtifactGrant scope differs from the Runtime Start"
                )
            grant_issued.append(_timestamp(grant, "issued_at"))
            grant_expires.append(_timestamp(grant, "expires_at"))
            granted_digests.add(_string(grant, "artifact_digest"))
        for item in _objects(context_package, "items"):
            if (
                item.get("kind") in {"artifact", "workspace_manifest"}
                and item.get("digest") not in granted_digests
            ):
                raise AuthorizationBindingError(
                    "ContextPackage artifact lacks a presented ArtifactGrant"
                )

        authorization_issued = _timestamp(authorization, "issued_at")
        authorization_expires = _timestamp(authorization, "expires_at")
        policy_decided = _timestamp(policy, "decided_at")
        policy_expires = _timestamp(policy, "expires_at")
        budget_created = _timestamp(budget, "created_at")
        budget_expires = _timestamp(budget, "expires_at")
        commercial_expires = _timestamp(commercial, "expires_at")
        if not (
            budget_created
            <= policy_decided
            <= authorization_issued
            < authorization_expires
        ):
            raise AuthorizationBindingError(
                "RuntimeAuthorization lower time bounds are inconsistent"
            )
        if authorization_expires > min(
            policy_expires, budget_expires, commercial_expires, deadline
        ):
            raise AuthorizationBindingError(
                "RuntimeAuthorization exceeds an admission upper bound"
            )
        if authorization_expires <= now.astimezone(UTC):
            raise AuthorizationBindingError("RuntimeAuthorization has expired")
        if grant_issued:
            if min(grant_issued) < authorization_issued:
                raise AuthorizationBindingError(
                    "ArtifactGrant predates RuntimeAuthorization"
                )
            if max(grant_expires) > authorization_expires or any(
                authorization_expires > expires for expires in grant_expires
            ):
                raise AuthorizationBindingError(
                    "ArtifactGrant and RuntimeAuthorization expiry differ"
                )

        checkpoint = (
            CheckpointManifest.from_document(
                cast(dict[str, Any], document["checkpoint"])
            )
            if "checkpoint" in document
            else None
        )
        mutation = StartMutation(
            runtime_run_id=runtime_run_id,
            tenant_id=tenant_id,
            conversation_id=_string(document, "conversation_id"),
            work_order_id=work_order_id,
            workflow_run_id=workflow_run_id,
            agent_run_id=agent_run_id,
            invocation_id=invocation_id,
            invocation_attempt_id=invocation_attempt_id,
            fencing_token=fencing_token,
            idempotency_key=_string(document, "idempotency_key"),
            request_digest=request_digest,
            deadline_at=deadline,
            run_manifest_digest=run_manifest_digest,
            runtime_authorization_digest=authorization_digest,
            workspace_revision_id=_string(document, "workspace_revision_id"),
            workspace_revision_digest=_string(document, "workspace_revision_digest"),
            sandbox_bindings=tuple(
                (
                    _string(item, "sandbox_slot_key"),
                    _string(item, "sandbox_id"),
                )
                for item in _objects(document, "sandbox_bindings")
            ),
            checkpoint=checkpoint,
        )
        binding = RuntimeSecurityBinding(
            tenant_id=tenant_id,
            provider_revision_id=self.security.provider_revision_id,
            runtime_run_id=runtime_run_id,
            agent_run_id=agent_run_id,
            workflow_run_id=workflow_run_id,
            work_order_id=work_order_id,
            run_manifest_digest=run_manifest_digest,
            runtime_authorization_digest=authorization_digest,
            policy_decision_digest=policy_digest,
            execution_budget_digest=budget_digest,
            effective_permissions_digest=permissions_digest,
            authorization_issued_at=authorization_issued,
            authorization_expires_at=authorization_expires,
            policy_decided_at=policy_decided,
            policy_expires_at=policy_expires,
            budget_created_at=budget_created,
            budget_expires_at=budget_expires,
            commercial_authorization_expires_at=commercial_expires,
            artifact_grants_not_before=max(grant_issued) if grant_issued else None,
            artifact_grants_expire_at=min(grant_expires) if grant_expires else None,
        )
        context = self._context(
            binding,
            invocation_id=invocation_id,
            invocation_attempt_id=invocation_attempt_id,
            fencing_token=fencing_token,
            operation_request_digest=request_digest,
        )
        return mutation, binding, context, deadline

    @staticmethod
    def _validate_gateway_bindings(
        gateway_bindings: Mapping[str, Any],
        *,
        budget: Mapping[str, Any],
        permissions: Mapping[str, Any],
        has_artifact_grants: bool,
    ) -> dict[str, Mapping[str, Any]]:
        ports: dict[str, Mapping[str, Any]] = {}
        for kind, contract_id in GATEWAY_CONTRACT_IDS.items():
            binding = _object(gateway_bindings, kind)
            if binding.get("kind") != kind:
                raise AuthorizationBindingError(
                    f"Runtime {kind} Gateway binding kind differs"
                )
            if binding.get("mode") == "enabled":
                port = _object(binding, "port")
                if (
                    port.get("gateway_kind") != kind
                    or port.get("contract_id") != contract_id
                ):
                    raise AuthorizationBindingError(
                        f"Runtime {kind} Gateway Port binding differs"
                    )
                ports[kind] = port

        policies = _object(budget, "policies")
        model = _object(permissions, "model")
        tool = _object(permissions, "tool")
        artifact = _object(permissions, "artifact")
        egress = _object(permissions, "egress")
        required = {
            "model": bool(policies.get("model_gateway_required"))
            or bool(model.get("allowed_model_profiles")),
            "tool": bool(policies.get("tool_gateway_required"))
            or bool(tool.get("allowed_capabilities")),
            "artifact": has_artifact_grants
            or artifact.get("read") is True
            or artifact.get("stage_new_version") is True,
            "egress": bool(policies.get("egress_gateway_required"))
            or egress.get("mode") != "none",
        }
        missing = sorted(
            kind for kind, needed in required.items() if needed and kind not in ports
        )
        if missing:
            raise AuthorizationBindingError(
                "required Runtime Gateway binding is disabled or incomplete: "
                + ",".join(missing)
            )
        return ports

    @staticmethod
    def _validate_command_context(
        document: Mapping[str, Any], admission: MutationAdmission
    ) -> datetime:
        expected = (
            _string(document, "runtime_run_id"),
            _string(document, "invocation_id"),
            _string(document, "invocation_attempt_id"),
            _integer(document, "fencing_token"),
            _string(document, "command_digest"),
            _optional_string(document, "system_safety_control_id"),
            _optional_string(document, "system_safety_control_digest"),
        )
        actual = (
            admission.runtime_run_id,
            admission.invocation_id,
            admission.invocation_attempt_id,
            admission.fencing_token,
            admission.operation_request_digest,
            admission.system_safety_control_id,
            admission.system_safety_control_digest,
        )
        if actual != expected:
            raise AuthorizationBindingError(
                "Command body and Runtime invocation token differ"
            )
        return _timestamp(document, "deadline_at")

    @staticmethod
    def _command_mutation(document: Mapping[str, Any]) -> CommandMutation:
        command_type = _string(document, "type")
        if command_type not in {"pause", "resume", "cancel", "checkpoint"}:
            raise UnsupportedOperationError(
                f"Runtime command {command_type!r} is outside B03.2a1.0"
            )
        return CommandMutation(
            command_id=_string(document, "command_id"),
            command_digest=_string(document, "command_digest"),
            runtime_run_id=_string(document, "runtime_run_id"),
            command_sequence=_integer(document, "command_sequence"),
            type=command_type,
            invocation_id=_string(document, "invocation_id"),
            invocation_attempt_id=_string(document, "invocation_attempt_id"),
            fencing_token=_integer(document, "fencing_token"),
            idempotency_key=_string(document, "idempotency_key"),
            deadline_at=_timestamp(document, "deadline_at"),
            authorized_control_request_id=_optional_string(
                document, "authorized_control_request_id"
            ),
            system_safety_control_id=_optional_string(
                document, "system_safety_control_id"
            ),
            system_safety_control_digest=_optional_string(
                document, "system_safety_control_digest"
            ),
            reason=_optional_string(document, "reason"),
        )

    @staticmethod
    def _context(
        binding: RuntimeSecurityBinding,
        *,
        invocation_id: str,
        invocation_attempt_id: str,
        fencing_token: int,
        operation_request_digest: str,
        command_type: str | None = None,
        system_safety_control_id: str | None = None,
        system_safety_control_digest: str | None = None,
    ) -> InvocationContext:
        return InvocationContext(
            tenant_id=binding.tenant_id,
            runtime_run_id=binding.runtime_run_id,
            agent_run_id=binding.agent_run_id,
            workflow_run_id=binding.workflow_run_id,
            work_order_id=binding.work_order_id,
            run_manifest_digest=binding.run_manifest_digest,
            runtime_authorization_digest=binding.runtime_authorization_digest,
            invocation_id=invocation_id,
            invocation_attempt_id=invocation_attempt_id,
            fencing_token=fencing_token,
            policy_decision_digest=binding.policy_decision_digest,
            execution_budget_digest=binding.execution_budget_digest,
            effective_permissions_digest=binding.effective_permissions_digest,
            operation_request_digest=operation_request_digest,
            command_type=command_type,
            system_safety_control_id=system_safety_control_id,
            system_safety_control_digest=system_safety_control_digest,
        )

    @staticmethod
    def _validate_execution_window(
        admission: MutationAdmission,
        binding: RuntimeSecurityBinding,
        operation_deadline: datetime,
    ) -> None:
        if admission.authority_mode != "execution":
            raise AuthorizationBindingError(
                "Runtime Start requires execution authority"
            )
        lower_bounds = [
            binding.authorization_issued_at,
            binding.policy_decided_at,
            binding.budget_created_at,
        ]
        upper_bounds = [
            binding.authorization_expires_at,
            binding.policy_expires_at,
            binding.budget_expires_at,
            binding.commercial_authorization_expires_at,
            operation_deadline,
        ]
        if binding.artifact_grants_not_before is not None:
            lower_bounds.append(binding.artifact_grants_not_before)
            assert binding.artifact_grants_expire_at is not None
            upper_bounds.append(binding.artifact_grants_expire_at)
        if admission.not_before < max(lower_bounds):
            raise AuthorizationBindingError(
                "Runtime token predates its presented authorization facts"
            )
        if admission.expires_at > min(upper_bounds):
            raise AuthorizationBindingError(
                "Runtime token outlives its presented authorization facts"
            )

    @staticmethod
    def _validate_admission_context(
        admission: MutationAdmission, context: InvocationContext
    ) -> None:
        expected = (
            context.tenant_id,
            context.runtime_run_id,
            context.agent_run_id,
            context.workflow_run_id,
            context.work_order_id,
            context.run_manifest_digest,
            context.runtime_authorization_digest,
            context.invocation_id,
            context.invocation_attempt_id,
            context.fencing_token,
            context.policy_decision_digest,
            context.execution_budget_digest,
            context.effective_permissions_digest,
            context.operation_request_digest,
            context.system_safety_control_id,
            context.system_safety_control_digest,
        )
        actual = (
            admission.tenant_id,
            admission.runtime_run_id,
            admission.agent_run_id,
            admission.workflow_run_id,
            admission.work_order_id,
            admission.run_manifest_digest,
            admission.runtime_authorization_digest,
            admission.invocation_id,
            admission.invocation_attempt_id,
            admission.fencing_token,
            admission.policy_decision_digest,
            admission.execution_budget_digest,
            admission.effective_permissions_digest,
            admission.operation_request_digest,
            admission.system_safety_control_id,
            admission.system_safety_control_digest,
        )
        if actual != expected:
            raise TokenValidationError(
                "Runtime token does not match the presented execution context"
            )

    @staticmethod
    def _require_self_digest(
        document: Mapping[str, Any], field: str, name: str
    ) -> None:
        expected = _string(document, field)
        unsigned = dict(document)
        del unsigned[field]
        if _document_digest(unsigned) != expected:
            raise DigestMismatchError(f"{name} {field} differs")


def _document_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonicalize_json(value)).hexdigest()


def _object(document: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = document.get(field)
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise AuthorizationBindingError(f"{field} must be an object")
    return cast(Mapping[str, Any], value)


def _objects(document: Mapping[str, Any], field: str) -> tuple[Mapping[str, Any], ...]:
    value = document.get(field)
    if not isinstance(value, list):
        raise AuthorizationBindingError(f"{field} must be an array")
    admitted: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or any(not isinstance(key, str) for key in item):
            raise AuthorizationBindingError(f"{field} must contain objects")
        admitted.append(cast(Mapping[str, Any], item))
    return tuple(admitted)


def _string(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise AuthorizationBindingError(f"{field} must be a non-empty string")
    return value


def _optional_string(document: Mapping[str, Any], field: str) -> str | None:
    value = document.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise AuthorizationBindingError(f"{field} must be a non-empty string")
    return value


def _integer(document: Mapping[str, Any], field: str) -> int:
    value = document.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise AuthorizationBindingError(f"{field} must be an integer")
    return value


def _timestamp(document: Mapping[str, Any], field: str) -> datetime:
    value = _string(document, field)
    try:
        return parse_timestamp(value)
    except ValueError as error:
        raise AuthorizationBindingError(f"{field} is not a timestamp") from error
