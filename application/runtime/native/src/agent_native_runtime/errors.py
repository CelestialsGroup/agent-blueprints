from __future__ import annotations

from dataclasses import dataclass


class RuntimeKernelError(Exception):
    code = "runtime_kernel_error"


class ConfigurationError(RuntimeKernelError):
    code = "configuration_error"


class ConfigurationDriftError(ConfigurationError):
    code = "configuration_drift"


class InvalidMutationError(RuntimeKernelError):
    code = "invalid_mutation"


class MutationExpiredError(InvalidMutationError):
    code = "mutation_expired"


class IdempotencyConflictError(RuntimeKernelError):
    code = "idempotency_conflict"


class MutationReplayError(RuntimeKernelError):
    code = "mutation_jti_replayed"


class RuntimeRunNotFoundError(RuntimeKernelError):
    code = "runtime_run_not_found"


class RuntimeRunConflictError(RuntimeKernelError):
    code = "runtime_run_conflict"


class CommandSequenceError(RuntimeKernelError):
    code = "command_sequence_conflict"


class StaleFencingError(RuntimeKernelError):
    code = "stale_fencing_token"


class StateConflictError(RuntimeKernelError):
    code = "runtime_state_conflict"


class UnsupportedOperationError(InvalidMutationError):
    code = "unsupported_operation"


class CheckpointError(RuntimeKernelError):
    code = "checkpoint_error"


class CheckpointCompatibilityError(CheckpointError):
    code = "checkpoint_compatibility_rejected"


class CheckpointContentError(CheckpointError):
    code = "checkpoint_content_invalid"


class CheckpointTooLargeError(CheckpointError):
    code = "checkpoint_too_large"


class WorkLeaseLostError(RuntimeKernelError):
    code = "work_lease_lost"


class AdmissionError(RuntimeKernelError):
    code = "runtime_admission_rejected"


class StrictJsonError(AdmissionError):
    code = "strict_ijson_rejected"


class EncodedBodyTooLargeError(AdmissionError):
    code = "encoded_body_too_large"


class ContractSchemaError(AdmissionError):
    code = "runtime_contract_schema_rejected"


class DigestMismatchError(AdmissionError):
    code = "runtime_digest_mismatch"


class TokenValidationError(AdmissionError):
    code = "runtime_token_rejected"


class AuthorizationBindingError(AdmissionError):
    code = "runtime_authorization_binding_rejected"


@dataclass(slots=True)
class CursorExpiredError(RuntimeKernelError):
    work_order_id: str
    requested_after: int
    earliest_available: int
    latest_available: int

    code = "event_cursor_expired"

    def __str__(self) -> str:
        return (
            f"event cursor {self.requested_after} precedes earliest available "
            f"sequence {self.earliest_available}"
        )
