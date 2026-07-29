from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from agent_native_runtime.contract_projection import build_draft202012_validator
from agent_native_runtime.errors import (
    CheckpointCompatibilityError,
    CheckpointContentError,
    CommandSequenceError,
    ConfigurationDriftError,
    CursorExpiredError,
    IdempotencyConflictError,
    InvalidMutationError,
    MutationReplayError,
    StaleFencingError,
    StateConflictError,
    WorkLeaseLostError,
)
from agent_native_runtime.kernel import NativeRuntimeKernel
from agent_native_runtime.model import (
    CommandMutation,
    MutationAdmission,
    RuntimeConfiguration,
    RuntimeEvent,
    RuntimeSecurityBinding,
    RuntimeStatus,
    StartMutation,
    event_data_to_document,
    format_timestamp,
)
from agent_native_runtime.store import SQLiteRuntimeStore

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()


def digest(character: str) -> str:
    return "sha256:" + character * 64


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


class BoundedTestExecutor:
    def __init__(self, *, max_runs: int = 8) -> None:
        self.max_runs = max_runs
        self.states: dict[str, bytes] = {}
        self.start_calls: list[str] = []
        self.restored: dict[str, bytes | None] = {}
        self.cancel_calls: list[str] = []

    def start(self, runtime_run_id: str, restored_state: bytes | None) -> None:
        self.start_calls.append(runtime_run_id)
        if runtime_run_id in self.states:
            if self.restored[runtime_run_id] != restored_state:
                raise AssertionError("idempotent start changed restored state")
            return
        if len(self.states) >= self.max_runs:
            raise RuntimeError("bounded executor capacity exhausted")
        self.restored[runtime_run_id] = restored_state
        self.states[runtime_run_id] = (
            restored_state
            or json.dumps(
                {"runtime_run_id": runtime_run_id, "step": 0},
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )

    def cancel(self, runtime_run_id: str) -> str:
        self.cancel_calls.append(runtime_run_id)
        if runtime_run_id not in self.states:
            raise RuntimeError("run is not active")
        return f"test-executor://cancellation/{runtime_run_id}"

    def checkpoint(self, runtime_run_id: str) -> bytes:
        return self.states[runtime_run_id]


class DurableKernelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.clock = FakeClock()
        self.configuration = RuntimeConfiguration(
            provider_revision_id="provider-revision-native-test-v1",
            runtime_revision="native-runtime-test-v1",
            provider_audience="urn:agent-platform:provider-instance:native-test",
            event_registry_id="agent-runtime-core",
            event_registry_version=1,
            event_registry_digest=(
                "sha256:d60c4b90063af5d3b889b10d3847fc431a3eee2f7fa3ba27ffe49ccbba251b43"
            ),
            state_root=Path(self.temporary.name) / "state",
            work_lease_seconds=5,
        )
        self.kernel = NativeRuntimeKernel.open(self.configuration, clock=self.clock)
        self.executor = BoundedTestExecutor()

    def start_mutation(self, runtime_run_id: str = "runtime-run-1") -> StartMutation:
        return StartMutation(
            runtime_run_id=runtime_run_id,
            tenant_id="tenant-1",
            conversation_id="conversation-1",
            work_order_id="work-order-1",
            workflow_run_id="workflow-run-1",
            agent_run_id=f"agent-{runtime_run_id}",
            invocation_id=f"invocation-{runtime_run_id}",
            invocation_attempt_id=f"attempt-{runtime_run_id}",
            fencing_token=1,
            idempotency_key=f"start-idempotency-{runtime_run_id}",
            request_digest=digest("1"),
            deadline_at=self.clock() + timedelta(minutes=5),
            run_manifest_digest=digest("2"),
            runtime_authorization_digest=digest("3"),
            workspace_revision_id="workspace-revision-1",
            workspace_revision_digest=digest("4"),
            sandbox_bindings=(),
        )

    def admission(
        self,
        jti: str,
        *,
        mutation: StartMutation | CommandMutation,
        authority_mode: str = "execution",
    ) -> MutationAdmission:
        operation: Literal["start", "submit_command"]
        if isinstance(mutation, StartMutation):
            operation = "start"
            tenant_id = mutation.tenant_id
            provider_revision_id = self.configuration.provider_revision_id
            runtime_run_id = mutation.runtime_run_id
            agent_run_id = mutation.agent_run_id
            workflow_run_id = mutation.workflow_run_id
            work_order_id = mutation.work_order_id
            run_manifest_digest = mutation.run_manifest_digest
            runtime_authorization_digest = mutation.runtime_authorization_digest
            invocation_id = mutation.invocation_id
            invocation_attempt_id = mutation.invocation_attempt_id
            fencing_token = mutation.fencing_token
            operation_contract_id = "urn:agent-platform:agent-runtime-start-request:v1"
            operation_digest_profile = "rfc8785-request-excluding-request-digest-v1"
            operation_request_digest = mutation.request_digest
        else:
            operation = "submit_command"
            binding = self.kernel.store.get_security_binding(mutation.runtime_run_id)
            tenant_id = binding.tenant_id
            provider_revision_id = binding.provider_revision_id
            runtime_run_id = binding.runtime_run_id
            agent_run_id = binding.agent_run_id
            workflow_run_id = binding.workflow_run_id
            work_order_id = binding.work_order_id
            run_manifest_digest = binding.run_manifest_digest
            runtime_authorization_digest = binding.runtime_authorization_digest
            invocation_id = mutation.invocation_id
            invocation_attempt_id = mutation.invocation_attempt_id
            fencing_token = mutation.fencing_token
            operation_contract_id = "urn:agent-platform:agent-runtime-command:v1"
            operation_digest_profile = "rfc8785-command-excluding-command-digest-v1"
            operation_request_digest = mutation.command_digest
        return MutationAdmission(
            issuer="agent-platform",
            subject="runtime-controller",
            jti=jti,
            operation=operation,
            authority_mode=authority_mode,  # type: ignore[arg-type]
            issued_at=self.clock(),
            not_before=self.clock(),
            expires_at=self.clock() + timedelta(minutes=2),
            tenant_id=tenant_id,
            provider_revision_id=provider_revision_id,
            runtime_run_id=runtime_run_id,
            agent_run_id=agent_run_id,
            workflow_run_id=workflow_run_id,
            work_order_id=work_order_id,
            run_manifest_digest=run_manifest_digest,
            runtime_authorization_digest=runtime_authorization_digest,
            invocation_id=invocation_id,
            invocation_attempt_id=invocation_attempt_id,
            fencing_token=fencing_token,
            policy_decision_digest=digest("5"),
            execution_budget_digest=digest("6"),
            effective_permissions_digest=digest("7"),
            operation_contract_id=operation_contract_id,
            operation_digest_profile=operation_digest_profile,
            operation_request_digest=operation_request_digest,
        )

    def security_binding(self, mutation: StartMutation) -> RuntimeSecurityBinding:
        return RuntimeSecurityBinding(
            tenant_id=mutation.tenant_id,
            provider_revision_id=self.configuration.provider_revision_id,
            runtime_run_id=mutation.runtime_run_id,
            agent_run_id=mutation.agent_run_id,
            workflow_run_id=mutation.workflow_run_id,
            work_order_id=mutation.work_order_id,
            run_manifest_digest=mutation.run_manifest_digest,
            runtime_authorization_digest=mutation.runtime_authorization_digest,
            policy_decision_digest=digest("5"),
            execution_budget_digest=digest("6"),
            effective_permissions_digest=digest("7"),
            authorization_issued_at=self.clock() - timedelta(minutes=1),
            authorization_expires_at=self.clock() + timedelta(minutes=5),
            policy_decided_at=self.clock() - timedelta(minutes=2),
            policy_expires_at=self.clock() + timedelta(minutes=10),
            budget_created_at=self.clock() - timedelta(minutes=3),
            budget_expires_at=self.clock() + timedelta(minutes=10),
            commercial_authorization_expires_at=self.clock() + timedelta(minutes=10),
            artifact_grants_not_before=None,
            artifact_grants_expire_at=None,
        )

    def start(self, mutation: StartMutation, jti: str) -> RuntimeStatus:
        return self.kernel.start(
            mutation,
            self.admission(jti, mutation=mutation),
            self.security_binding(mutation),
        )

    def submit(
        self,
        mutation: CommandMutation,
        jti: str,
        *,
        authority_mode: str = "execution",
    ) -> RuntimeStatus:
        return self.kernel.submit_command(
            mutation,
            self.admission(jti, mutation=mutation, authority_mode=authority_mode),
        )

    def command(
        self,
        command_id: str,
        sequence: int,
        fencing_token: int,
        command_type: str,
        *,
        runtime_run_id: str = "runtime-run-1",
        system: bool = False,
    ) -> CommandMutation:
        return CommandMutation(
            command_id=command_id,
            command_digest=digest(str(sequence + 4)),
            runtime_run_id=runtime_run_id,
            command_sequence=sequence,
            type=command_type,
            invocation_id=f"invocation-{command_id}",
            invocation_attempt_id=f"attempt-{command_id}",
            fencing_token=fencing_token,
            idempotency_key=f"command-idempotency-{command_id}",
            deadline_at=self.clock() + timedelta(minutes=1),
            authorized_control_request_id=(
                None
                if system or command_type == "checkpoint"
                else f"control-{command_id}"
            ),
            system_safety_control_id=f"safety-{command_id}" if system else None,
            system_safety_control_digest=digest("f") if system else None,
        )

    def start_and_run(self, runtime_run_id: str = "runtime-run-1") -> StartMutation:
        mutation = self.start_mutation(runtime_run_id)
        self.start(mutation, f"start-jti-{runtime_run_id}-0001")
        self.assertTrue(self.kernel.process_one(self.executor, owner="worker-1"))
        self.assertEqual(self.kernel.status(runtime_run_id).status, "running")
        return mutation

    def test_configuration_is_immutable_for_state_root(self) -> None:
        reopened = NativeRuntimeKernel.open(self.configuration, clock=self.clock)
        self.assertEqual(reopened.configuration, self.configuration)
        with self.assertRaises(ConfigurationDriftError):
            NativeRuntimeKernel.open(
                replace(self.configuration, runtime_revision="native-runtime-test-v2"),
                clock=self.clock,
            )

    def test_concurrent_first_open_serializes_migration_and_configuration(self) -> None:
        configuration = replace(
            self.configuration,
            state_root=Path(self.temporary.name) / "concurrent-first-open",
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            kernels = list(
                pool.map(
                    lambda _: NativeRuntimeKernel.open(configuration, clock=self.clock),
                    range(2),
                )
            )
        self.assertEqual(kernels[0].configuration, kernels[1].configuration)
        connection = kernels[0].store._connect()
        try:
            migrations = connection.execute(
                "SELECT version, migration_digest FROM schema_migrations"
            ).fetchall()
            self.assertEqual([row["version"] for row in migrations], [1, 2])
            self.assertTrue(
                all(len(row["migration_digest"]) == 64 for row in migrations)
            )
        finally:
            connection.close()

    def test_sqlite_durability_pragmas_and_strict_schema_are_active(self) -> None:
        connection = self.kernel.store._connect()
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("PRAGMA journal_mode").fetchone()[0], "wal"
            )
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)
            self.assertEqual(
                connection.execute("PRAGMA busy_timeout").fetchone()[0],
                self.configuration.sqlite_busy_timeout_ms,
            )
            tables = {
                row["name"]: row["strict"]
                for row in connection.execute("PRAGMA table_list")
                if not row["name"].startswith("sqlite_")
            }
            self.assertTrue(tables)
            self.assertTrue(all(value == 1 for value in tables.values()))
        finally:
            connection.close()
        self.assertEqual(
            stat.S_IMODE(self.configuration.state_root.stat().st_mode),
            0o700,
        )

    def test_empty_schema_rolls_back_but_data_bearing_schema_is_forward_only(
        self,
    ) -> None:
        self.kernel.store.rollback_empty()
        self.kernel = NativeRuntimeKernel.open(self.configuration, clock=self.clock)
        mutation = self.start_mutation()
        self.start(mutation, "start-jti-rollback-0001")
        with self.assertRaises(StateConflictError):
            self.kernel.store.rollback_empty()

    def test_data_bearing_v1_store_cannot_invent_security_bindings(self) -> None:
        configuration = replace(
            self.configuration,
            state_root=Path(self.temporary.name) / "data-bearing-v1",
        )
        store = SQLiteRuntimeStore(configuration)
        migration = (
            files("agent_native_runtime.migrations")
            .joinpath("0001_runtime_durable_kernel.up.sql")
            .read_text(encoding="utf-8")
        )
        connection = store._connect()
        try:
            store._enable_wal(connection)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    migration_digest TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                ) STRICT
                """
            )
            store._execute_sql_script(connection, migration)
            connection.execute(
                """
                INSERT INTO schema_migrations(
                    version, name, migration_digest, applied_at
                ) VALUES (1, 'runtime_durable_kernel', ?, ?)
                """,
                (
                    hashlib.sha256(migration.encode()).hexdigest(),
                    format_timestamp(self.clock()),
                ),
            )
            connection.execute(
                """
                INSERT INTO runtime_runs(
                    runtime_run_id, tenant_id, conversation_id, work_order_id,
                    workflow_run_id, agent_run_id, start_request_digest,
                    run_manifest_digest, runtime_authorization_digest,
                    workspace_revision_id, workspace_revision_digest, status,
                    observed_fencing_token, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', 1, ?, ?)
                """,
                (
                    "unbound-runtime-run",
                    "tenant-1",
                    "conversation-1",
                    "work-order-1",
                    "workflow-run-1",
                    "agent-run-1",
                    digest("1"),
                    digest("2"),
                    digest("3"),
                    "workspace-revision-1",
                    digest("4"),
                    format_timestamp(self.clock()),
                    format_timestamp(self.clock()),
                ),
            )
            connection.execute("COMMIT")
        finally:
            connection.close()

        with self.assertRaisesRegex(
            ConfigurationDriftError,
            "cannot be authoritatively upgraded",
        ):
            store.migrate()
        connection = store._connect()
        try:
            self.assertEqual(
                [
                    row["version"]
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )
                ],
                [1],
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'runtime_security_bindings'"
                ).fetchone()
            )
        finally:
            connection.close()

    def test_start_idempotency_conflict_and_jti_consumption_are_atomic(self) -> None:
        mutation = self.start_mutation()
        first = self.start(mutation, "start-jti-idempotent-0001")
        replay = self.start(mutation, "start-jti-idempotent-0002")
        self.assertEqual(first, replay)
        self.assertEqual(
            len(self.kernel.events("runtime-run-1", after_event_sequence=0).events), 1
        )

        conflict_jti = "start-jti-conflict-0001"
        conflict = replace(mutation, request_digest=digest("9"))
        with self.assertRaises(IdempotencyConflictError):
            self.start(conflict, conflict_jti)
        self.assertEqual(self.kernel.store.count_jti("agent-platform", conflict_jti), 0)

        with self.assertRaises(MutationReplayError):
            self.start(mutation, "start-jti-idempotent-0001")
        self.assertEqual(self.kernel.status("runtime-run-1").status, "accepted")

    def test_concurrent_start_serializes_to_one_run_and_one_event(self) -> None:
        mutation = self.start_mutation()

        def start(jti: str) -> object:
            return self.start(mutation, jti)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    start,
                    ("start-jti-concurrent-0001", "start-jti-concurrent-0002"),
                )
            )
        self.assertEqual(results[0], results[1])
        self.assertEqual(
            len(self.kernel.events("runtime-run-1", after_event_sequence=0).events), 1
        )
        self.assertEqual(
            self.kernel.store.count_jti("agent-platform", "start-jti-concurrent-0001"),
            1,
        )
        self.assertEqual(
            self.kernel.store.count_jti("agent-platform", "start-jti-concurrent-0002"),
            1,
        )

    def test_start_rejects_non_empty_sandbox_bindings_without_side_effects(
        self,
    ) -> None:
        mutation = replace(
            self.start_mutation(), sandbox_bindings=(("default", "sandbox-1"),)
        )
        jti = "start-jti-sandbox-0001"
        with self.assertRaises(InvalidMutationError):
            self.start(mutation, jti)
        self.assertEqual(self.kernel.store.count_jti("agent-platform", jti), 0)

    def test_command_sequence_fencing_replay_and_authority(self) -> None:
        self.start_and_run()
        pause = self.command("pause-1", 1, 2, "pause")
        paused = self.submit(pause, "command-jti-pause-0001")
        self.assertEqual(paused.status, "paused")
        replay = self.submit(pause, "command-jti-pause-0002")
        self.assertEqual(replay.last_command_sequence, 1)
        with self.assertRaises(MutationReplayError):
            self.submit(pause, "command-jti-pause-0001")

        sequence_jti = "command-jti-sequence-0001"
        sequence = self.command("resume-3", 3, 4, "resume")
        with self.assertRaises(CommandSequenceError):
            self.submit(sequence, sequence_jti)
        self.assertEqual(self.kernel.store.count_jti("agent-platform", sequence_jti), 0)

        stale_jti = "command-jti-stale-0001"
        stale = self.command("resume-2", 2, 2, "resume")
        with self.assertRaises(StaleFencingError):
            self.submit(stale, stale_jti)
        self.assertEqual(self.kernel.store.count_jti("agent-platform", stale_jti), 0)

        safety_jti = "command-jti-safety-0001"
        safety = self.command("resume-safety", 2, 3, "resume", system=True)
        with self.assertRaises(InvalidMutationError):
            self.submit(safety, safety_jti, authority_mode="safety_control")
        self.assertEqual(self.kernel.store.count_jti("agent-platform", safety_jti), 0)

        resume = self.command("resume-2", 2, 3, "resume")
        resumed = self.submit(resume, "command-jti-resume-0001")
        self.assertEqual(resumed.status, "running")
        self.assertEqual(resumed.observed_fencing_token, 3)

    def test_cancel_is_terminal_only_after_executor_evidence(self) -> None:
        self.start_and_run()
        cancel = self.command("cancel-1", 1, 2, "cancel", system=True)
        accepted = self.submit(
            cancel,
            "command-jti-cancel-0001",
            authority_mode="safety_control",
        )
        self.assertEqual(accepted.status, "cancel_requested")
        self.assertIsNone(accepted.completed_at)
        self.assertEqual(accepted.last_event_sequence, 1)

        self.assertTrue(self.kernel.process_one(self.executor, owner="worker-1"))
        terminal = self.kernel.status("runtime-run-1")
        self.assertEqual(terminal.status, "cancelled")
        self.assertIsNotNone(terminal.completed_at)
        self.assertEqual(
            terminal.cancellation_evidence_reference,
            "test-executor://cancellation/runtime-run-1",
        )
        events = self.kernel.events("runtime-run-1", after_event_sequence=1).events
        self.assertEqual([event.type for event in events], ["runtime.run.cancelled"])

    def test_checkpoint_is_content_addressed_and_restores_same_revision(self) -> None:
        self.start_and_run()
        checkpoint_command = self.command("checkpoint-1", 1, 2, "checkpoint")
        self.submit(checkpoint_command, "command-jti-checkpoint-0001")
        self.assertTrue(self.kernel.process_one(self.executor, owner="worker-1"))
        source = self.kernel.status("runtime-run-1")
        self.assertIsNotNone(source.checkpoint)
        checkpoint = source.checkpoint
        assert checkpoint is not None
        self.assertEqual(checkpoint.portability, "same_revision")
        self.assertEqual(checkpoint.event_sequence, 1)
        self.assertEqual(source.last_event_sequence, 2)
        self.assertEqual(len(self.kernel.checkpoints.object_paths()), 1)
        self.assertEqual(
            stat.S_IMODE(self.kernel.checkpoints.object_paths()[0].stat().st_mode),
            0o600,
        )

        restore = replace(
            self.start_mutation("runtime-run-2"),
            request_digest=digest("a"),
            checkpoint=checkpoint,
        )
        self.start(restore, "start-jti-restore-0001")
        self.assertTrue(self.kernel.process_one(self.executor, owner="worker-1"))
        self.assertEqual(
            self.executor.restored["runtime-run-2"],
            self.executor.states["runtime-run-1"],
        )

        rejected = replace(
            self.start_mutation("runtime-run-3"),
            request_digest=digest("b"),
            checkpoint=replace(checkpoint, portability="compatible_revision"),
        )
        rejected_jti = "start-jti-restore-rejected-0001"
        with self.assertRaises(CheckpointCompatibilityError):
            self.start(rejected, rejected_jti)
        self.assertEqual(self.kernel.store.count_jti("agent-platform", rejected_jti), 0)

    def test_cursor_resume_and_expiry_are_explicit(self) -> None:
        self.start_and_run()
        checkpoint_command = self.command("checkpoint-1", 1, 2, "checkpoint")
        self.submit(checkpoint_command, "command-jti-checkpoint-0001")
        self.kernel.process_one(self.executor, owner="worker-1")
        resumed = self.kernel.events("runtime-run-1", after_event_sequence=1)
        self.assertEqual([event.event_sequence for event in resumed.events], [2])
        self.assertEqual(resumed.next_event_sequence, 2)

        self.assertEqual(
            self.kernel.prune_events("runtime-run-1", through_sequence=1), 1
        )
        with self.assertRaises(CursorExpiredError) as raised:
            self.kernel.events("runtime-run-1", after_event_sequence=0)
        self.assertEqual(raised.exception.earliest_available, 2)
        self.assertEqual(raised.exception.latest_available, 2)
        self.assertEqual(
            [
                event.event_sequence
                for event in self.kernel.events(
                    "runtime-run-1", after_event_sequence=1
                ).events
            ],
            [2],
        )

    def test_retention_rejects_a_checkpoint_with_missing_content(self) -> None:
        self.start_and_run()
        checkpoint_command = self.command("checkpoint-1", 1, 2, "checkpoint")
        self.submit(checkpoint_command, "command-jti-checkpoint-0001")
        self.kernel.process_one(self.executor, owner="worker-1")
        checkpoint_path = self.kernel.checkpoints.object_paths()[0]
        checkpoint_path.unlink()
        with self.assertRaises(CheckpointContentError):
            self.kernel.prune_events("runtime-run-1", through_sequence=1)
        self.assertEqual(
            [
                event.event_sequence
                for event in self.kernel.events(
                    "runtime-run-1", after_event_sequence=0
                ).events
            ],
            [1, 2],
        )

    def test_expired_work_lease_recovers_without_duplicate_run_or_event(self) -> None:
        mutation = self.start_mutation()
        self.start(mutation, "start-jti-crash-recovery-0001")
        abandoned = self.kernel.store.claim_work("dead-worker", self.clock())
        self.assertIsNotNone(abandoned)
        assert abandoned is not None
        self.executor.start(abandoned.runtime_run_id, None)

        self.clock.advance(seconds=6)
        restarted = NativeRuntimeKernel.open(self.configuration, clock=self.clock)
        self.assertTrue(
            restarted.process_one(self.executor, owner="replacement-worker")
        )
        self.assertEqual(restarted.status("runtime-run-1").status, "running")
        self.assertEqual(self.executor.start_calls, ["runtime-run-1", "runtime-run-1"])
        self.assertEqual(
            len(restarted.events("runtime-run-1", after_event_sequence=0).events), 1
        )

    def test_expired_worker_cannot_complete_after_lease_loss(self) -> None:
        mutation = self.start_mutation()
        self.start(mutation, "start-jti-lease-fencing-0001")
        abandoned = self.kernel.store.claim_work("dead-worker", self.clock())
        self.assertIsNotNone(abandoned)
        assert abandoned is not None
        self.clock.advance(seconds=6)
        with self.assertRaises(WorkLeaseLostError):
            self.kernel.store.complete_start(abandoned, self.clock())
        self.assertTrue(
            self.kernel.process_one(self.executor, owner="replacement-worker")
        )
        self.assertEqual(self.kernel.status("runtime-run-1").status, "running")

    def test_checkpoint_object_may_be_orphaned_but_manifest_never_is(self) -> None:
        self.start_and_run()
        checkpoint_command = self.command("checkpoint-1", 1, 2, "checkpoint")
        self.submit(checkpoint_command, "command-jti-checkpoint-0001")
        with (
            patch.object(
                self.kernel.store,
                "complete_checkpoint",
                side_effect=RuntimeError("injected commit failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "injected commit failure"),
        ):
            self.kernel.process_one(self.executor, owner="worker-1")
        self.assertEqual(len(self.kernel.checkpoints.object_paths()), 1)
        self.assertIsNone(self.kernel.status("runtime-run-1").checkpoint)

        self.assertTrue(self.kernel.process_one(self.executor, owner="worker-1"))
        self.assertIsNotNone(self.kernel.status("runtime-run-1").checkpoint)
        self.assertEqual(len(self.kernel.checkpoints.object_paths()), 1)

    def test_emitted_events_validate_against_locked_contract(self) -> None:
        self.start_and_run()
        checkpoint_command = self.command("checkpoint-1", 1, 2, "checkpoint")
        self.submit(checkpoint_command, "command-jti-checkpoint-0001")
        self.kernel.process_one(self.executor, owner="worker-1")
        projection = json.loads(
            (ROOT / "internal/generated/runtimeapi/projection-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        documents = [
            json.loads((CONTRACT_ROOT / item["path"]).read_text(encoding="utf-8"))
            for item in projection["schemas"]
        ]
        validator = build_draft202012_validator(
            "urn:agent-platform:agent-runtime-event:v1", documents
        )
        for event in self.kernel.events("runtime-run-1", after_event_sequence=0).events:
            with self.subTest(event_type=event.type):
                validator.validate(self.event_document(event))

        connection = self.kernel.store._connect()
        try:
            connection.execute(
                """
                UPDATE runtime_events
                SET data_json = json_set(data_json, '$.unadmitted', 'value')
                WHERE runtime_run_id = ? AND event_sequence = 1
                """,
                ("runtime-run-1",),
            )
        finally:
            connection.close()
        with self.assertRaisesRegex(
            InvalidMutationError, "fields do not match its event type"
        ):
            self.kernel.events("runtime-run-1", after_event_sequence=0)

    @staticmethod
    def event_document(event: RuntimeEvent) -> dict[str, object]:
        return {
            "event_id": event.event_id,
            "runtime_run_id": event.runtime_run_id,
            "event_sequence": event.event_sequence,
            "type": event.type,
            "occurred_at": format_timestamp(event.occurred_at),
            "data_version": event.data_version,
            "data": event_data_to_document(event.data),
            "source_cursor": event.source_cursor,
        }


if __name__ == "__main__":
    unittest.main()
