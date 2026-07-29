from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime

from .checkpoint import CheckpointObjectStore
from .errors import (
    CheckpointCompatibilityError,
    InvalidMutationError,
    RuntimeKernelError,
    WorkLeaseLostError,
)
from .execution import ExecutionLoop
from .model import (
    CheckpointManifest,
    CommandMutation,
    EventPage,
    MutationAdmission,
    RuntimeConfiguration,
    RuntimeStatus,
    StartMutation,
)
from .store import SQLiteRuntimeStore

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


class NativeRuntimeKernel:
    """Provider-local durable lifecycle component with no HTTP or Platform storage."""

    def __init__(
        self,
        configuration: RuntimeConfiguration,
        *,
        clock: Clock = system_clock,
    ) -> None:
        self.configuration = configuration
        self.clock = clock
        self.store = SQLiteRuntimeStore(configuration)
        self.checkpoints = CheckpointObjectStore(configuration)

    @classmethod
    def open(
        cls,
        configuration: RuntimeConfiguration,
        *,
        clock: Clock = system_clock,
    ) -> NativeRuntimeKernel:
        kernel = cls(configuration, clock=clock)
        kernel.store.migrate()
        kernel.store.bind_configuration(kernel.clock())
        return kernel

    def start(
        self, mutation: StartMutation, admission: MutationAdmission
    ) -> RuntimeStatus:
        now = self.clock()
        mutation.validate(now)
        admission.validate(operation="start", now=now)
        if admission.authority_mode != "execution":
            raise InvalidMutationError(
                "Start requires execution authority; safety-control authority is reduction-only"
            )
        if mutation.checkpoint is not None:
            self._validate_restore(mutation.checkpoint)
            self.checkpoints.read_verified(mutation.checkpoint)
        return self.store.start(mutation, admission, now)

    def status(self, runtime_run_id: str) -> RuntimeStatus:
        return self.store.get_status(runtime_run_id)

    def submit_command(
        self, mutation: CommandMutation, admission: MutationAdmission
    ) -> RuntimeStatus:
        now = self.clock()
        mutation.validate(now)
        admission.validate(operation="submit_command", now=now)
        return self.store.submit_command(mutation, admission, now)

    def events(
        self, runtime_run_id: str, *, after_event_sequence: int, limit: int = 100
    ) -> EventPage:
        return self.store.read_events(runtime_run_id, after_event_sequence, limit)

    def prune_events(self, runtime_run_id: str, *, through_sequence: int) -> int:
        checkpoint = self.store.get_status(runtime_run_id).checkpoint
        if checkpoint is not None:
            self.checkpoints.read_verified(checkpoint)
        return self.store.prune_events(runtime_run_id, through_sequence, self.clock())

    def process_one(self, executor: ExecutionLoop, *, owner: str) -> bool:
        if not owner:
            raise ValueError("work owner must not be empty")
        work = self.store.claim_work(owner, self.clock())
        if work is None:
            return False
        try:
            if work.kind == "start":
                restored_state = (
                    self.checkpoints.read_verified(work.restore_checkpoint)
                    if work.restore_checkpoint is not None
                    else None
                )
                executor.start(work.runtime_run_id, restored_state)
                self.store.complete_start(work, self.clock())
            elif work.kind == "cancel":
                evidence_reference = executor.cancel(work.runtime_run_id)
                self.store.complete_cancel(work, evidence_reference, self.clock())
            elif work.kind == "checkpoint":
                payload = executor.checkpoint(work.runtime_run_id)
                checkpoint_object = self.checkpoints.write(payload)
                status = self.store.get_status(work.runtime_run_id)
                command_identity = work.command_id or work.work_id
                checkpoint_id = (
                    "native-checkpoint-"
                    + hashlib.sha256(
                        f"{work.runtime_run_id}:{command_identity}".encode()
                    ).hexdigest()[:32]
                )
                created_at = self.clock()
                manifest = CheckpointManifest(
                    checkpoint_id=checkpoint_id,
                    runtime_run_id=work.runtime_run_id,
                    provider_revision_id=self.configuration.provider_revision_id,
                    source_runtime_revision=self.configuration.runtime_revision,
                    event_sequence=status.last_event_sequence,
                    content_reference=checkpoint_object.content_reference,
                    digest=checkpoint_object.digest,
                    size_bytes=checkpoint_object.size_bytes,
                    portability="same_revision",
                    compatibility_profile=self.configuration.checkpoint_profile,
                    created_at=created_at,
                )
                self.store.complete_checkpoint(
                    work,
                    manifest,
                    self.store.checkpoint_manifest_digest(manifest),
                    self.clock(),
                )
            else:
                raise AssertionError(f"unknown durable work kind: {work.kind}")
            return True
        except BaseException as error:
            error_code = (
                error.code
                if isinstance(error, RuntimeKernelError)
                else "execution_loop_error"
            )
            with suppress(WorkLeaseLostError):
                self.store.release_work(work, error_code, self.clock())
            raise

    def _validate_restore(self, manifest: CheckpointManifest) -> None:
        manifest.validate()
        if manifest.portability != "same_revision":
            raise CheckpointCompatibilityError(
                "B03.2a0 rejects compatible_revision and portable restore"
            )
        if manifest.provider_revision_id != self.configuration.provider_revision_id:
            raise CheckpointCompatibilityError(
                "checkpoint ProviderRevision does not match"
            )
        if manifest.source_runtime_revision != self.configuration.runtime_revision:
            raise CheckpointCompatibilityError(
                "checkpoint Runtime revision does not match"
            )
        if manifest.compatibility_profile != self.configuration.checkpoint_profile:
            raise CheckpointCompatibilityError(
                "checkpoint compatibility profile does not match"
            )
        if manifest.event_sequence < 0:
            raise CheckpointCompatibilityError(
                "checkpoint event sequence must not be negative"
            )
        if not 0 <= manifest.size_bytes <= self.configuration.max_checkpoint_bytes:
            raise CheckpointCompatibilityError(
                "checkpoint size exceeds the configured limit"
            )
