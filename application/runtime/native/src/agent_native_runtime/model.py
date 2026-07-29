from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from .errors import (
    ConfigurationError,
    InvalidMutationError,
    MutationExpiredError,
    UnsupportedOperationError,
)

SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})
SUPPORTED_COMMANDS = frozenset({"pause", "resume", "cancel", "checkpoint"})
RUNTIME_OPERATIONS = frozenset(
    {"start", "read_status", "submit_command", "read_events"}
)
RUNTIME_EVENT_TYPES = frozenset(
    {
        "runtime.run.started",
        "runtime.checkpoint.created",
        "runtime.run.cancelled",
    }
)

type RuntimeEventType = Literal[
    "runtime.run.started",
    "runtime.checkpoint.created",
    "runtime.run.cancelled",
]


def require_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidMutationError(f"{field} must include a timezone")
    return value.astimezone(UTC)


def format_timestamp(value: datetime) -> str:
    return (
        require_utc(value, "timestamp")
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def require_identifier(
    value: str, field: str, *, minimum: int = 1, maximum: int = 200
) -> None:
    if not minimum <= len(value) <= maximum:
        raise InvalidMutationError(
            f"{field} length must be between {minimum} and {maximum} bytes"
        )


def require_digest(value: str, field: str) -> None:
    if not SHA256_DIGEST.fullmatch(value):
        raise InvalidMutationError(f"{field} must be a sha256 digest")


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    provider_revision_id: str
    runtime_revision: str
    provider_audience: str
    event_registry_id: str
    event_registry_version: int
    event_registry_digest: str
    state_root: Path
    checkpoint_profile: str = "runtime-core-v1"
    max_checkpoint_bytes: int = 16 * 1024 * 1024
    sqlite_busy_timeout_ms: int = 5_000
    work_lease_seconds: int = 30

    def __post_init__(self) -> None:
        for field, value in (
            ("provider_revision_id", self.provider_revision_id),
            ("runtime_revision", self.runtime_revision),
            ("provider_audience", self.provider_audience),
            ("event_registry_id", self.event_registry_id),
            ("checkpoint_profile", self.checkpoint_profile),
        ):
            if not value:
                raise ConfigurationError(f"{field} must not be empty")
        if self.event_registry_version < 1:
            raise ConfigurationError("event_registry_version must be positive")
        if not SHA256_DIGEST.fullmatch(self.event_registry_digest):
            raise ConfigurationError("event_registry_digest must be a sha256 digest")
        if self.max_checkpoint_bytes < 1:
            raise ConfigurationError("max_checkpoint_bytes must be positive")
        if not 1 <= self.sqlite_busy_timeout_ms <= 60_000:
            raise ConfigurationError(
                "sqlite_busy_timeout_ms must be between 1 and 60000"
            )
        if not 1 <= self.work_lease_seconds <= 300:
            raise ConfigurationError("work_lease_seconds must be between 1 and 300")
        root = self.state_root.expanduser().resolve()
        if root == Path(root.anchor):
            raise ConfigurationError("state_root must not be a filesystem root")
        object.__setattr__(self, "state_root", root)

    def digest_document(self) -> dict[str, Any]:
        return {
            "checkpoint_profile": self.checkpoint_profile,
            "event_registry_digest": self.event_registry_digest,
            "event_registry_id": self.event_registry_id,
            "event_registry_version": self.event_registry_version,
            "max_checkpoint_bytes": self.max_checkpoint_bytes,
            "provider_audience": self.provider_audience,
            "provider_revision_id": self.provider_revision_id,
            "runtime_revision": self.runtime_revision,
            "sqlite_busy_timeout_ms": self.sqlite_busy_timeout_ms,
            "state_root": str(self.state_root),
            "work_lease_seconds": self.work_lease_seconds,
        }


@dataclass(frozen=True, slots=True)
class MutationAdmission:
    issuer: str
    subject: str
    jti: str
    operation: Literal["start", "read_status", "submit_command", "read_events"]
    authority_mode: Literal["execution", "safety_control"]
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    tenant_id: str
    provider_revision_id: str
    runtime_run_id: str
    agent_run_id: str
    workflow_run_id: str
    work_order_id: str
    invocation_id: str
    invocation_attempt_id: str
    run_manifest_digest: str
    runtime_authorization_digest: str
    fencing_token: int
    policy_decision_digest: str
    execution_budget_digest: str
    effective_permissions_digest: str
    operation_contract_id: str
    operation_digest_profile: str
    operation_request_digest: str
    system_safety_control_id: str | None = None
    system_safety_control_digest: str | None = None
    clock_skew_seconds: int = 0

    def validate(self, *, operation: str, now: datetime) -> None:
        for field, value in (
            ("issuer", self.issuer),
            ("subject", self.subject),
            ("tenant_id", self.tenant_id),
            ("provider_revision_id", self.provider_revision_id),
            ("runtime_run_id", self.runtime_run_id),
            ("agent_run_id", self.agent_run_id),
            ("workflow_run_id", self.workflow_run_id),
            ("work_order_id", self.work_order_id),
            ("invocation_id", self.invocation_id),
            ("invocation_attempt_id", self.invocation_attempt_id),
            ("operation_contract_id", self.operation_contract_id),
            ("operation_digest_profile", self.operation_digest_profile),
        ):
            require_identifier(value, field, maximum=500)
        require_identifier(self.jti, "jti", minimum=16, maximum=500)
        for field, value in (
            ("run_manifest_digest", self.run_manifest_digest),
            ("runtime_authorization_digest", self.runtime_authorization_digest),
            ("policy_decision_digest", self.policy_decision_digest),
            ("execution_budget_digest", self.execution_budget_digest),
            ("effective_permissions_digest", self.effective_permissions_digest),
            ("operation_request_digest", self.operation_request_digest),
        ):
            require_digest(value, field)
        if (self.system_safety_control_id is None) != (
            self.system_safety_control_digest is None
        ):
            raise InvalidMutationError(
                "mutation admission safety-control binding is incomplete"
            )
        if self.system_safety_control_id is not None:
            require_identifier(
                self.system_safety_control_id,
                "system_safety_control_id",
                maximum=500,
            )
            require_digest(
                cast(str, self.system_safety_control_digest),
                "system_safety_control_digest",
            )
        if self.operation != operation:
            raise InvalidMutationError("mutation admission operation does not match")
        if self.operation not in RUNTIME_OPERATIONS:
            raise InvalidMutationError("mutation admission operation is invalid")
        if self.authority_mode not in {"execution", "safety_control"}:
            raise InvalidMutationError("mutation admission authority mode is invalid")
        if self.fencing_token < 1:
            raise InvalidMutationError(
                "mutation admission fencing token must be positive"
            )
        if not 0 <= self.clock_skew_seconds <= 30:
            raise InvalidMutationError("mutation admission clock skew is invalid")
        issued_at = require_utc(self.issued_at, "issued_at")
        not_before = require_utc(self.not_before, "not_before")
        expires_at = require_utc(self.expires_at, "expires_at")
        if not issued_at <= not_before < expires_at:
            raise InvalidMutationError("mutation admission time window is invalid")
        if expires_at - issued_at > timedelta(seconds=300):
            raise InvalidMutationError("mutation admission exceeds the 300 second TTL")
        now_utc = require_utc(now, "now")
        skew = timedelta(seconds=self.clock_skew_seconds)
        if issued_at > now_utc + skew or not_before > now_utc + skew:
            raise InvalidMutationError("mutation admission is not yet valid")
        if expires_at + skew <= now_utc:
            raise MutationExpiredError("mutation admission has expired")


@dataclass(frozen=True, slots=True)
class RuntimeSecurityBinding:
    tenant_id: str
    provider_revision_id: str
    runtime_run_id: str
    agent_run_id: str
    workflow_run_id: str
    work_order_id: str
    run_manifest_digest: str
    runtime_authorization_digest: str
    policy_decision_digest: str
    execution_budget_digest: str
    effective_permissions_digest: str
    authorization_issued_at: datetime
    authorization_expires_at: datetime
    policy_decided_at: datetime
    policy_expires_at: datetime
    budget_created_at: datetime
    budget_expires_at: datetime
    commercial_authorization_expires_at: datetime
    artifact_grants_not_before: datetime | None
    artifact_grants_expire_at: datetime | None

    def validate(self) -> None:
        for field, value in (
            ("tenant_id", self.tenant_id),
            ("provider_revision_id", self.provider_revision_id),
            ("runtime_run_id", self.runtime_run_id),
            ("agent_run_id", self.agent_run_id),
            ("workflow_run_id", self.workflow_run_id),
            ("work_order_id", self.work_order_id),
        ):
            require_identifier(value, field)
        for field, value in (
            ("run_manifest_digest", self.run_manifest_digest),
            ("runtime_authorization_digest", self.runtime_authorization_digest),
            ("policy_decision_digest", self.policy_decision_digest),
            ("execution_budget_digest", self.execution_budget_digest),
            ("effective_permissions_digest", self.effective_permissions_digest),
        ):
            require_digest(value, field)
        lower_bounds = (
            require_utc(self.authorization_issued_at, "authorization_issued_at"),
            require_utc(self.policy_decided_at, "policy_decided_at"),
            require_utc(self.budget_created_at, "budget_created_at"),
        )
        upper_bounds = (
            require_utc(self.authorization_expires_at, "authorization_expires_at"),
            require_utc(self.policy_expires_at, "policy_expires_at"),
            require_utc(self.budget_expires_at, "budget_expires_at"),
            require_utc(
                self.commercial_authorization_expires_at,
                "commercial_authorization_expires_at",
            ),
        )
        if max(lower_bounds) >= min(upper_bounds):
            raise InvalidMutationError("Runtime security binding time window is empty")
        if (self.artifact_grants_not_before is None) != (
            self.artifact_grants_expire_at is None
        ):
            raise InvalidMutationError("Artifact Grant time bounds are incomplete")
        if self.artifact_grants_not_before is not None:
            grant_lower = require_utc(
                self.artifact_grants_not_before, "artifact_grants_not_before"
            )
            grant_upper = require_utc(
                cast(datetime, self.artifact_grants_expire_at),
                "artifact_grants_expire_at",
            )
            if grant_lower < self.authorization_issued_at:
                raise InvalidMutationError(
                    "Artifact Grant predates RuntimeAuthorization"
                )
            if grant_lower >= grant_upper or grant_upper > min(upper_bounds):
                raise InvalidMutationError(
                    "Artifact Grant exceeds the Runtime security window"
                )


@dataclass(frozen=True, slots=True)
class CheckpointManifest:
    checkpoint_id: str
    runtime_run_id: str
    provider_revision_id: str
    source_runtime_revision: str
    event_sequence: int
    content_reference: str
    digest: str
    size_bytes: int
    portability: Literal["same_revision", "compatible_revision", "portable"]
    compatibility_profile: str
    created_at: datetime

    def validate(self) -> None:
        for field, value in (
            ("checkpoint_id", self.checkpoint_id),
            ("runtime_run_id", self.runtime_run_id),
            ("provider_revision_id", self.provider_revision_id),
            ("source_runtime_revision", self.source_runtime_revision),
            ("compatibility_profile", self.compatibility_profile),
        ):
            require_identifier(value, field)
        require_identifier(self.content_reference, "content_reference", maximum=2000)
        require_digest(self.digest, "digest")
        if self.event_sequence < 0:
            raise InvalidMutationError("checkpoint event_sequence must not be negative")
        if self.size_bytes < 0:
            raise InvalidMutationError("checkpoint size_bytes must not be negative")
        if self.portability not in {"same_revision", "compatible_revision", "portable"}:
            raise InvalidMutationError("checkpoint portability is invalid")
        require_utc(self.created_at, "created_at")

    def to_document(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "runtime_run_id": self.runtime_run_id,
            "provider_revision_id": self.provider_revision_id,
            "source_runtime_revision": self.source_runtime_revision,
            "event_sequence": self.event_sequence,
            "content_reference": self.content_reference,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "portability": self.portability,
            "compatibility_profile": self.compatibility_profile,
            "created_at": format_timestamp(self.created_at),
        }

    @classmethod
    def from_document(cls, value: dict[str, Any]) -> CheckpointManifest:
        return cls(
            checkpoint_id=value["checkpoint_id"],
            runtime_run_id=value["runtime_run_id"],
            provider_revision_id=value["provider_revision_id"],
            source_runtime_revision=value["source_runtime_revision"],
            event_sequence=value["event_sequence"],
            content_reference=value["content_reference"],
            digest=value["digest"],
            size_bytes=value["size_bytes"],
            portability=value["portability"],
            compatibility_profile=value["compatibility_profile"],
            created_at=parse_timestamp(value["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class StartMutation:
    runtime_run_id: str
    tenant_id: str
    conversation_id: str
    work_order_id: str
    workflow_run_id: str
    agent_run_id: str
    invocation_id: str
    invocation_attempt_id: str
    fencing_token: int
    idempotency_key: str
    request_digest: str
    deadline_at: datetime
    run_manifest_digest: str
    runtime_authorization_digest: str
    workspace_revision_id: str
    workspace_revision_digest: str
    sandbox_bindings: tuple[tuple[str, str], ...] = ()
    checkpoint: CheckpointManifest | None = None

    def validate(self, now: datetime) -> None:
        for field, value in (
            ("runtime_run_id", self.runtime_run_id),
            ("tenant_id", self.tenant_id),
            ("conversation_id", self.conversation_id),
            ("work_order_id", self.work_order_id),
            ("workflow_run_id", self.workflow_run_id),
            ("agent_run_id", self.agent_run_id),
            ("invocation_id", self.invocation_id),
            ("invocation_attempt_id", self.invocation_attempt_id),
            ("workspace_revision_id", self.workspace_revision_id),
        ):
            require_identifier(value, field)
        require_identifier(
            self.idempotency_key, "idempotency_key", minimum=16, maximum=500
        )
        for field, value in (
            ("request_digest", self.request_digest),
            ("run_manifest_digest", self.run_manifest_digest),
            ("runtime_authorization_digest", self.runtime_authorization_digest),
            ("workspace_revision_digest", self.workspace_revision_digest),
        ):
            require_digest(value, field)
        if self.fencing_token < 1:
            raise InvalidMutationError("fencing_token must be positive")
        if require_utc(self.deadline_at, "deadline_at") <= require_utc(now, "now"):
            raise InvalidMutationError("start deadline has expired")
        if self.sandbox_bindings:
            raise UnsupportedOperationError(
                "this Runtime revision requires sandboxes=[]"
            )


@dataclass(frozen=True, slots=True)
class CommandMutation:
    command_id: str
    command_digest: str
    runtime_run_id: str
    command_sequence: int
    type: str
    invocation_id: str
    invocation_attempt_id: str
    fencing_token: int
    idempotency_key: str
    deadline_at: datetime
    authorized_control_request_id: str | None = None
    system_safety_control_id: str | None = None
    system_safety_control_digest: str | None = None
    reason: str | None = None

    def validate(self, now: datetime) -> None:
        for field, value in (
            ("command_id", self.command_id),
            ("runtime_run_id", self.runtime_run_id),
            ("invocation_id", self.invocation_id),
            ("invocation_attempt_id", self.invocation_attempt_id),
        ):
            require_identifier(value, field)
        require_identifier(
            self.idempotency_key, "idempotency_key", minimum=16, maximum=500
        )
        require_digest(self.command_digest, "command_digest")
        if self.command_sequence < 1:
            raise InvalidMutationError("command_sequence must be positive")
        if self.fencing_token < 1:
            raise InvalidMutationError("fencing_token must be positive")
        if require_utc(self.deadline_at, "deadline_at") <= require_utc(now, "now"):
            raise InvalidMutationError("command deadline has expired")
        if self.type not in SUPPORTED_COMMANDS:
            raise UnsupportedOperationError(
                f"command type {self.type!r} is outside B03.2a0"
            )
        for field, optional_value in (
            ("authorized_control_request_id", self.authorized_control_request_id),
            ("system_safety_control_id", self.system_safety_control_id),
        ):
            if optional_value is not None:
                require_identifier(optional_value, field)
        if self.system_safety_control_digest is not None:
            require_digest(
                self.system_safety_control_digest, "system_safety_control_digest"
            )
        if self.reason is not None and not 1 <= len(self.reason) <= 1000:
            raise InvalidMutationError("reason length must be between 1 and 1000 bytes")


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    runtime_run_id: str
    tenant_id: str
    conversation_id: str
    work_order_id: str
    workflow_run_id: str
    agent_run_id: str
    status: str
    last_command_sequence: int
    last_event_sequence: int
    observed_fencing_token: int
    updated_at: datetime
    completed_at: datetime | None = None
    checkpoint: CheckpointManifest | None = None
    cancellation_evidence_reference: str | None = None


@dataclass(frozen=True, slots=True)
class RunStartedEventData:
    agent_run_id: str
    run_manifest_digest: str
    provider_revision_id: str


@dataclass(frozen=True, slots=True)
class CheckpointCreatedEventData:
    checkpoint_id: str
    checkpoint_manifest_digest: str
    content_reference: str


@dataclass(frozen=True, slots=True)
class RunCancelledEventData:
    cancellation_evidence_reference: str
    completed_at: str


type RuntimeEventData = (
    RunStartedEventData | CheckpointCreatedEventData | RunCancelledEventData
)


def event_data_to_document(data: RuntimeEventData) -> dict[str, object]:
    if isinstance(data, RunStartedEventData):
        return {
            "agent_run_id": data.agent_run_id,
            "run_manifest_digest": data.run_manifest_digest,
            "provider_revision_id": data.provider_revision_id,
        }
    if isinstance(data, CheckpointCreatedEventData):
        return {
            "checkpoint_id": data.checkpoint_id,
            "checkpoint_manifest_digest": data.checkpoint_manifest_digest,
            "content_reference": data.content_reference,
        }
    return {
        "cancellation_evidence_reference": data.cancellation_evidence_reference,
        "completed_at": data.completed_at,
    }


def event_type_for_data(data: RuntimeEventData) -> RuntimeEventType:
    if isinstance(data, RunStartedEventData):
        return "runtime.run.started"
    if isinstance(data, CheckpointCreatedEventData):
        return "runtime.checkpoint.created"
    return "runtime.run.cancelled"


def event_data_from_document(
    event_type: RuntimeEventType, document: object
) -> RuntimeEventData:
    if not isinstance(document, dict):
        raise InvalidMutationError("Runtime event data must be an object")
    if any(not isinstance(key, str) for key in document):
        raise InvalidMutationError("Runtime event data keys must be strings")
    values = cast(Mapping[str, object], document)
    if event_type == "runtime.run.started":
        admitted = _closed_string_values(
            values,
            ("agent_run_id", "run_manifest_digest", "provider_revision_id"),
        )
        return RunStartedEventData(
            agent_run_id=admitted["agent_run_id"],
            run_manifest_digest=admitted["run_manifest_digest"],
            provider_revision_id=admitted["provider_revision_id"],
        )
    if event_type == "runtime.checkpoint.created":
        admitted = _closed_string_values(
            values,
            ("checkpoint_id", "checkpoint_manifest_digest", "content_reference"),
        )
        return CheckpointCreatedEventData(
            checkpoint_id=admitted["checkpoint_id"],
            checkpoint_manifest_digest=admitted["checkpoint_manifest_digest"],
            content_reference=admitted["content_reference"],
        )
    admitted = _closed_string_values(
        values,
        ("cancellation_evidence_reference", "completed_at"),
    )
    return RunCancelledEventData(
        cancellation_evidence_reference=admitted["cancellation_evidence_reference"],
        completed_at=admitted["completed_at"],
    )


def _closed_string_values(
    values: Mapping[str, object], required: tuple[str, ...]
) -> dict[str, str]:
    if set(values) != set(required):
        raise InvalidMutationError(
            "Runtime event data fields do not match its event type"
        )
    admitted: dict[str, str] = {}
    for field in required:
        value = values[field]
        if not isinstance(value, str) or not value:
            raise InvalidMutationError(
                f"Runtime event data field {field} must be a string"
            )
        admitted[field] = value
    return admitted


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_id: str
    runtime_run_id: str
    event_sequence: int
    type: RuntimeEventType
    occurred_at: datetime
    data_version: Literal[1]
    data: RuntimeEventData
    source_cursor: str

    def __post_init__(self) -> None:
        if self.type != event_type_for_data(self.data):
            raise InvalidMutationError("Runtime event type and data do not match")


@dataclass(frozen=True, slots=True)
class EventPage:
    events: tuple[RuntimeEvent, ...]
    next_event_sequence: int


@dataclass(frozen=True, slots=True)
class WorkItem:
    work_id: str
    runtime_run_id: str
    kind: Literal["start", "cancel", "checkpoint"]
    command_id: str | None
    lease_owner: str
    lease_token: int
    attempt_count: int
    restore_checkpoint: CheckpointManifest | None
