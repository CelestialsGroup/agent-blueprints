from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from importlib.resources import files
from typing import Any, cast

from .contract_projection import canonicalize_json
from .errors import (
    AuthorizationBindingError,
    CommandSequenceError,
    ConfigurationDriftError,
    CursorExpiredError,
    IdempotencyConflictError,
    InvalidMutationError,
    MutationReplayError,
    RuntimeRunConflictError,
    RuntimeRunNotFoundError,
    StaleFencingError,
    StateConflictError,
    WorkLeaseLostError,
)
from .model import (
    TERMINAL_STATES,
    CheckpointCreatedEventData,
    CheckpointManifest,
    CommandMutation,
    EventPage,
    MutationAdmission,
    RunCancelledEventData,
    RunStartedEventData,
    RuntimeConfiguration,
    RuntimeEvent,
    RuntimeEventData,
    RuntimeEventType,
    RuntimeSecurityBinding,
    RuntimeStatus,
    StartMutation,
    WorkItem,
    event_data_from_document,
    event_data_to_document,
    event_type_for_data,
    format_timestamp,
    parse_timestamp,
)

SCHEMA_VERSION = 2
MIGRATIONS = (
    (1, "runtime_durable_kernel"),
    (2, "secure_admission_core"),
)


def _sha256_document(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonicalize_json(value)).hexdigest()


class SQLiteRuntimeStore:
    def __init__(self, configuration: RuntimeConfiguration) -> None:
        self.configuration = configuration
        self.configuration.state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.configuration.state_root.chmod(0o700)
        self.database_path = self.configuration.state_root / "runtime.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            isolation_level=None,
            timeout=self.configuration.sqlite_busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            f"PRAGMA busy_timeout = {self.configuration.sqlite_busy_timeout_ms}"
        )
        connection.execute("PRAGMA synchronous = FULL")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise RuntimeError("SQLite foreign key enforcement is unavailable")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @contextmanager
    def _read_transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        connection = self._connect()
        try:
            self._enable_wal(connection)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    migration_digest TEXT NOT NULL CHECK (length(migration_digest) = 64),
                    applied_at TEXT NOT NULL
                ) STRICT
                """
            )
            applied_rows = connection.execute(
                "SELECT version, name, migration_digest FROM schema_migrations ORDER BY version"
            ).fetchall()
            if any(row["version"] > SCHEMA_VERSION for row in applied_rows):
                raise ConfigurationDriftError(
                    "SQLite schema is newer than this Runtime"
                )
            applied = {row["version"]: row for row in applied_rows}
            if tuple(applied) != tuple(range(1, len(applied) + 1)):
                raise ConfigurationDriftError(
                    "SQLite migrations are not a contiguous prefix"
                )
            for version, name in MIGRATIONS:
                migration = (
                    files("agent_native_runtime.migrations")
                    .joinpath(f"{version:04d}_{name}.up.sql")
                    .read_text(encoding="utf-8")
                )
                migration_digest = hashlib.sha256(migration.encode("utf-8")).hexdigest()
                existing = applied.get(version)
                if existing is not None:
                    if (
                        existing["name"] != name
                        or existing["migration_digest"] != migration_digest
                    ):
                        raise ConfigurationDriftError(
                            f"applied SQLite migration {version} has drifted"
                        )
                    continue
                if version == 2 and any(
                    connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                    is not None
                    for table in (
                        "runtime_runs",
                        "start_idempotency",
                        "consumed_mutation_jtis",
                        "runtime_commands",
                        "runtime_events",
                        "checkpoint_manifests",
                        "execution_work",
                    )
                ):
                    raise ConfigurationDriftError(
                        "data-bearing a0 store cannot be authoritatively upgraded"
                    )
                self._execute_sql_script(connection, migration)
                applied_at = format_timestamp(datetime.now().astimezone())
                connection.execute(
                    """
                    INSERT INTO schema_migrations(
                        version, name, migration_digest, applied_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (version, name, migration_digest, applied_at),
                )
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _enable_wal(self, connection: sqlite3.Connection) -> None:
        deadline = time.monotonic() + self.configuration.sqlite_busy_timeout_ms / 1000
        while True:
            try:
                journal_mode = connection.execute(
                    "PRAGMA journal_mode = WAL"
                ).fetchone()[0]
            except sqlite3.OperationalError as error:
                if (
                    getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_BUSY
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
                continue
            if str(journal_mode).lower() != "wal":
                raise RuntimeError("SQLite WAL mode is required")
            return

    def bind_configuration(self, now: datetime) -> None:
        digest = _sha256_document(self.configuration.digest_document())
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM provider_metadata WHERE singleton = 1"
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO provider_metadata(
                        singleton, provider_revision_id, runtime_revision,
                        configuration_digest, configured_at
                    ) VALUES (1, ?, ?, ?, ?)
                    """,
                    (
                        self.configuration.provider_revision_id,
                        self.configuration.runtime_revision,
                        digest,
                        format_timestamp(now),
                    ),
                )
                return
            if (
                row["provider_revision_id"] != self.configuration.provider_revision_id
                or row["runtime_revision"] != self.configuration.runtime_revision
                or row["configuration_digest"] != digest
            ):
                raise ConfigurationDriftError(
                    "immutable Runtime configuration differs from the state root binding"
                )

    def bind_security_configuration(
        self,
        *,
        configuration_digest: str,
        contract_source_revision: str,
        contract_manifest_digest: str,
        runtime_suite_digest: str,
        schema_closure_digest: str,
        now: datetime,
    ) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM provider_security_metadata WHERE singleton = 1"
            ).fetchone()
            expected = (
                configuration_digest,
                contract_source_revision,
                contract_manifest_digest,
                runtime_suite_digest,
                schema_closure_digest,
            )
            if row is None:
                connection.execute(
                    """
                    INSERT INTO provider_security_metadata(
                        singleton, security_configuration_digest,
                        contract_source_revision, contract_manifest_digest,
                        runtime_suite_digest, schema_closure_digest, configured_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?)
                    """,
                    (*expected, format_timestamp(now)),
                )
                return
            actual = (
                row["security_configuration_digest"],
                row["contract_source_revision"],
                row["contract_manifest_digest"],
                row["runtime_suite_digest"],
                row["schema_closure_digest"],
            )
            if actual != expected:
                raise ConfigurationDriftError(
                    "immutable security configuration differs from the state root binding"
                )

    def rollback_empty(self) -> None:
        with self._transaction() as connection:
            for table in (
                "runtime_runs",
                "start_idempotency",
                "consumed_mutation_jtis",
                "runtime_commands",
                "runtime_events",
                "checkpoint_manifests",
                "execution_work",
            ):
                if (
                    connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                    is not None
                ):
                    raise StateConflictError(
                        "data-bearing Runtime schema is forward-only"
                    )
            connection.execute("DELETE FROM provider_security_metadata")
            migration = (
                files("agent_native_runtime.migrations")
                .joinpath("0002_secure_admission_core.down.sql")
                .read_text(encoding="utf-8")
            )
            self._execute_sql_script(connection, migration)
            connection.execute("DELETE FROM schema_migrations WHERE version = 2")
            connection.execute("DELETE FROM provider_metadata")
            migration = (
                files("agent_native_runtime.migrations")
                .joinpath("0001_runtime_durable_kernel.down.sql")
                .read_text(encoding="utf-8")
            )
            self._execute_sql_script(connection, migration)
            connection.execute("DELETE FROM schema_migrations WHERE version = 1")

    def start(
        self,
        mutation: StartMutation,
        admission: MutationAdmission,
        security_binding: RuntimeSecurityBinding,
        now: datetime,
    ) -> RuntimeStatus:
        security_binding.validate()
        self._validate_start_security_binding(mutation, admission, security_binding)
        timestamp = format_timestamp(now)
        checkpoint_json = (
            json.dumps(
                mutation.checkpoint.to_document(), separators=(",", ":"), sort_keys=True
            )
            if mutation.checkpoint
            else None
        )
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT request_digest, runtime_run_id FROM start_idempotency WHERE idempotency_key = ?",
                (mutation.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != mutation.request_digest:
                    raise IdempotencyConflictError(
                        "start idempotency key is already bound to another digest"
                    )
                if existing["runtime_run_id"] != mutation.runtime_run_id:
                    raise RuntimeRunConflictError(
                        "start replay changed the immutable runtime_run_id"
                    )
                self._require_security_binding(
                    connection, admission, minimum_fencing=False
                )
                self._consume_jti(
                    connection,
                    admission,
                    mutation.request_digest,
                    mutation.runtime_run_id,
                    now,
                )
                return self._status(connection, mutation.runtime_run_id)

            if connection.execute(
                "SELECT 1 FROM runtime_runs WHERE runtime_run_id = ?",
                (mutation.runtime_run_id,),
            ).fetchone():
                raise RuntimeRunConflictError(
                    "runtime_run_id already exists under another Start identity"
                )

            self._consume_jti(
                connection,
                admission,
                mutation.request_digest,
                mutation.runtime_run_id,
                now,
            )
            connection.execute(
                """
                INSERT INTO runtime_runs(
                    runtime_run_id, tenant_id, conversation_id, work_order_id,
                    workflow_run_id, agent_run_id, start_request_digest,
                    run_manifest_digest, runtime_authorization_digest,
                    workspace_revision_id, workspace_revision_digest, status,
                    observed_fencing_token, checkpoint_manifest_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?, ?)
                """,
                (
                    mutation.runtime_run_id,
                    mutation.tenant_id,
                    mutation.conversation_id,
                    mutation.work_order_id,
                    mutation.workflow_run_id,
                    mutation.agent_run_id,
                    mutation.request_digest,
                    mutation.run_manifest_digest,
                    mutation.runtime_authorization_digest,
                    mutation.workspace_revision_id,
                    mutation.workspace_revision_digest,
                    mutation.fencing_token,
                    checkpoint_json,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO runtime_security_bindings(
                    runtime_run_id, tenant_id, provider_revision_id, agent_run_id,
                    workflow_run_id, work_order_id, run_manifest_digest,
                    runtime_authorization_digest, policy_decision_digest,
                    execution_budget_digest, effective_permissions_digest,
                    authorization_issued_at, authorization_expires_at,
                    policy_decided_at, policy_expires_at, budget_created_at,
                    budget_expires_at, commercial_authorization_expires_at,
                    artifact_grants_not_before, artifact_grants_expire_at, bound_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    security_binding.runtime_run_id,
                    security_binding.tenant_id,
                    security_binding.provider_revision_id,
                    security_binding.agent_run_id,
                    security_binding.workflow_run_id,
                    security_binding.work_order_id,
                    security_binding.run_manifest_digest,
                    security_binding.runtime_authorization_digest,
                    security_binding.policy_decision_digest,
                    security_binding.execution_budget_digest,
                    security_binding.effective_permissions_digest,
                    format_timestamp(security_binding.authorization_issued_at),
                    format_timestamp(security_binding.authorization_expires_at),
                    format_timestamp(security_binding.policy_decided_at),
                    format_timestamp(security_binding.policy_expires_at),
                    format_timestamp(security_binding.budget_created_at),
                    format_timestamp(security_binding.budget_expires_at),
                    format_timestamp(
                        security_binding.commercial_authorization_expires_at
                    ),
                    format_timestamp(security_binding.artifact_grants_not_before)
                    if security_binding.artifact_grants_not_before
                    else None,
                    format_timestamp(security_binding.artifact_grants_expire_at)
                    if security_binding.artifact_grants_expire_at
                    else None,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO start_idempotency(idempotency_key, request_digest, runtime_run_id, accepted_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    mutation.idempotency_key,
                    mutation.request_digest,
                    mutation.runtime_run_id,
                    timestamp,
                ),
            )
            self._append_event(
                connection,
                mutation.runtime_run_id,
                RunStartedEventData(
                    agent_run_id=mutation.agent_run_id,
                    run_manifest_digest=mutation.run_manifest_digest,
                    provider_revision_id=self.configuration.provider_revision_id,
                ),
                now,
            )
            connection.execute(
                """
                INSERT INTO execution_work(
                    work_id, runtime_run_id, kind, state, restore_checkpoint_json,
                    created_at, updated_at
                ) VALUES (?, ?, 'start', 'pending', ?, ?, ?)
                """,
                (
                    f"{mutation.runtime_run_id}:start",
                    mutation.runtime_run_id,
                    checkpoint_json,
                    timestamp,
                    timestamp,
                ),
            )
            return self._status(connection, mutation.runtime_run_id)

    def submit_command(
        self,
        mutation: CommandMutation,
        admission: MutationAdmission,
        now: datetime,
    ) -> RuntimeStatus:
        timestamp = format_timestamp(now)
        with self._transaction() as connection:
            run = connection.execute(
                "SELECT * FROM runtime_runs WHERE runtime_run_id = ?",
                (mutation.runtime_run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeRunNotFoundError(mutation.runtime_run_id)
            self._require_security_binding(
                connection,
                admission,
                minimum_fencing=False,
                validate_execution_window=True,
            )
            self._validate_command_authority(mutation, admission)

            existing = connection.execute(
                """
                SELECT command_digest FROM runtime_commands
                WHERE runtime_run_id = ? AND command_id = ?
                """,
                (mutation.runtime_run_id, mutation.command_id),
            ).fetchone()
            if existing is not None:
                if existing["command_digest"] != mutation.command_digest:
                    raise IdempotencyConflictError(
                        "command_id is already bound to another digest"
                    )
                self._consume_jti(
                    connection,
                    admission,
                    mutation.command_digest,
                    mutation.runtime_run_id,
                    now,
                )
                return self._status(connection, mutation.runtime_run_id)

            key_row = connection.execute(
                """
                SELECT command_digest FROM runtime_commands
                WHERE runtime_run_id = ? AND idempotency_key = ?
                """,
                (mutation.runtime_run_id, mutation.idempotency_key),
            ).fetchone()
            if key_row is not None:
                raise IdempotencyConflictError(
                    "command idempotency key is already bound to another command"
                )
            expected_sequence = run["last_command_sequence"] + 1
            if mutation.command_sequence != expected_sequence:
                raise CommandSequenceError(
                    f"expected command sequence {expected_sequence}, got {mutation.command_sequence}"
                )
            if mutation.fencing_token <= run["observed_fencing_token"]:
                raise StaleFencingError(
                    "command fencing token must be strictly newer than the observed token"
                )
            next_state, work_kind = self._command_transition(
                run["status"], mutation.type
            )
            self._consume_jti(
                connection,
                admission,
                mutation.command_digest,
                mutation.runtime_run_id,
                now,
            )
            connection.execute(
                """
                INSERT INTO runtime_commands(
                    runtime_run_id, command_id, command_digest, command_sequence, type,
                    invocation_id, invocation_attempt_id, fencing_token, idempotency_key,
                    authority_mode, authorized_control_request_id, system_safety_control_id,
                    system_safety_control_digest, deadline_at, accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation.runtime_run_id,
                    mutation.command_id,
                    mutation.command_digest,
                    mutation.command_sequence,
                    mutation.type,
                    mutation.invocation_id,
                    mutation.invocation_attempt_id,
                    mutation.fencing_token,
                    mutation.idempotency_key,
                    admission.authority_mode,
                    mutation.authorized_control_request_id,
                    mutation.system_safety_control_id,
                    mutation.system_safety_control_digest,
                    format_timestamp(mutation.deadline_at),
                    timestamp,
                ),
            )
            connection.execute(
                """
                UPDATE runtime_runs
                SET status = ?, observed_fencing_token = ?, last_command_sequence = ?, updated_at = ?
                WHERE runtime_run_id = ?
                """,
                (
                    next_state,
                    mutation.fencing_token,
                    mutation.command_sequence,
                    timestamp,
                    mutation.runtime_run_id,
                ),
            )
            if work_kind is not None:
                connection.execute(
                    """
                    INSERT INTO execution_work(
                        work_id, runtime_run_id, kind, command_id, state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        f"{mutation.runtime_run_id}:command:{mutation.command_id}",
                        mutation.runtime_run_id,
                        work_kind,
                        mutation.command_id,
                        timestamp,
                        timestamp,
                    ),
                )
            return self._status(connection, mutation.runtime_run_id)

    def get_status(self, runtime_run_id: str) -> RuntimeStatus:
        connection = self._connect()
        try:
            return self._status(connection, runtime_run_id)
        finally:
            connection.close()

    def get_security_binding(self, runtime_run_id: str) -> RuntimeSecurityBinding:
        with self._read_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_security_bindings WHERE runtime_run_id = ?",
                (runtime_run_id,),
            ).fetchone()
            if row is None:
                raise RuntimeRunNotFoundError(runtime_run_id)
            return self._security_binding_from_row(row)

    def authorized_status(
        self, admission: MutationAdmission, now: datetime
    ) -> RuntimeStatus:
        admission.validate(operation="read_status", now=now)
        with self._read_transaction() as connection:
            self._require_security_binding(connection, admission, minimum_fencing=True)
            return self._status(connection, admission.runtime_run_id)

    def authorized_events(
        self,
        admission: MutationAdmission,
        *,
        after_sequence: int,
        limit: int,
        now: datetime,
    ) -> EventPage:
        admission.validate(operation="read_events", now=now)
        if after_sequence < 0:
            raise InvalidMutationError("after_sequence must not be negative")
        if not 1 <= limit <= 1000:
            raise InvalidMutationError("event limit must be between 1 and 1000")
        with self._read_transaction() as connection:
            self._require_security_binding(connection, admission, minimum_fencing=True)
            run = connection.execute(
                """
                SELECT work_order_id, earliest_event_sequence, last_event_sequence
                FROM runtime_runs WHERE runtime_run_id = ?
                """,
                (admission.runtime_run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeRunNotFoundError(admission.runtime_run_id)
            if after_sequence < run["earliest_event_sequence"] - 1:
                raise CursorExpiredError(
                    work_order_id=run["work_order_id"],
                    requested_after=after_sequence,
                    earliest_available=run["earliest_event_sequence"],
                    latest_available=run["last_event_sequence"],
                )
            rows = connection.execute(
                """
                SELECT * FROM runtime_events
                WHERE runtime_run_id = ? AND event_sequence > ?
                ORDER BY event_sequence ASC LIMIT ?
                """,
                (admission.runtime_run_id, after_sequence, limit),
            ).fetchall()
            events = tuple(self._event(row) for row in rows)
            next_sequence = events[-1].event_sequence if events else after_sequence
            return EventPage(events=events, next_event_sequence=next_sequence)

    def read_events(
        self, runtime_run_id: str, after_sequence: int, limit: int
    ) -> EventPage:
        if after_sequence < 0:
            raise InvalidMutationError("after_sequence must not be negative")
        if not 1 <= limit <= 1000:
            raise InvalidMutationError("event limit must be between 1 and 1000")
        with self._read_transaction() as connection:
            run = connection.execute(
                """
                SELECT work_order_id, earliest_event_sequence, last_event_sequence
                FROM runtime_runs WHERE runtime_run_id = ?
                """,
                (runtime_run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeRunNotFoundError(runtime_run_id)
            if after_sequence < run["earliest_event_sequence"] - 1:
                raise CursorExpiredError(
                    work_order_id=run["work_order_id"],
                    requested_after=after_sequence,
                    earliest_available=run["earliest_event_sequence"],
                    latest_available=run["last_event_sequence"],
                )
            rows = connection.execute(
                """
                SELECT * FROM runtime_events
                WHERE runtime_run_id = ? AND event_sequence > ?
                ORDER BY event_sequence ASC LIMIT ?
                """,
                (runtime_run_id, after_sequence, limit),
            ).fetchall()
            events = tuple(self._event(row) for row in rows)
            next_sequence = events[-1].event_sequence if events else after_sequence
            return EventPage(events=events, next_event_sequence=next_sequence)

    def prune_events(
        self, runtime_run_id: str, through_sequence: int, now: datetime
    ) -> int:
        with self._transaction() as connection:
            run = connection.execute(
                "SELECT checkpoint_manifest_json FROM runtime_runs WHERE runtime_run_id = ?",
                (runtime_run_id,),
            ).fetchone()
            if run is None:
                raise RuntimeRunNotFoundError(runtime_run_id)
            if run["checkpoint_manifest_json"] is None:
                raise StateConflictError("event retention requires a usable checkpoint")
            checkpoint = CheckpointManifest.from_document(
                json.loads(run["checkpoint_manifest_json"])
            )
            if through_sequence > checkpoint.event_sequence:
                raise StateConflictError(
                    "cannot prune beyond the checkpoint event sequence"
                )
            deleted = connection.execute(
                """
                DELETE FROM runtime_events
                WHERE runtime_run_id = ? AND event_sequence <= ?
                """,
                (runtime_run_id, through_sequence),
            ).rowcount
            earliest = connection.execute(
                "SELECT MIN(event_sequence) FROM runtime_events WHERE runtime_run_id = ?",
                (runtime_run_id,),
            ).fetchone()[0]
            if earliest is None:
                raise StateConflictError("retention cannot remove every recovery event")
            connection.execute(
                """
                UPDATE runtime_runs SET earliest_event_sequence = ?, updated_at = ?
                WHERE runtime_run_id = ?
                """,
                (earliest, format_timestamp(now), runtime_run_id),
            )
            return deleted

    def claim_work(self, owner: str, now: datetime) -> WorkItem | None:
        lease_expires = now + timedelta(seconds=self.configuration.work_lease_seconds)
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT work.* FROM execution_work AS work
                WHERE (
                    work.state = 'pending'
                    OR (work.state = 'processing' AND work.lease_expires_at <= ?)
                )
                AND NOT EXISTS (
                    SELECT 1 FROM execution_work AS active
                    WHERE active.runtime_run_id = work.runtime_run_id
                      AND active.state = 'processing'
                      AND active.lease_expires_at > ?
                )
                ORDER BY work.created_at ASC, work.work_id ASC
                LIMIT 1
                """,
                (format_timestamp(now), format_timestamp(now)),
            ).fetchone()
            if row is None:
                return None
            lease_token = row["lease_token"] + 1
            connection.execute(
                """
                UPDATE execution_work
                SET state = 'processing', lease_owner = ?, lease_token = ?,
                    lease_expires_at = ?, attempt_count = attempt_count + 1,
                    last_error_code = NULL, updated_at = ?
                WHERE work_id = ?
                """,
                (
                    owner,
                    lease_token,
                    format_timestamp(lease_expires),
                    format_timestamp(now),
                    row["work_id"],
                ),
            )
            checkpoint = (
                CheckpointManifest.from_document(
                    json.loads(row["restore_checkpoint_json"])
                )
                if row["restore_checkpoint_json"]
                else None
            )
            return WorkItem(
                work_id=row["work_id"],
                runtime_run_id=row["runtime_run_id"],
                kind=row["kind"],
                command_id=row["command_id"],
                lease_owner=owner,
                lease_token=lease_token,
                attempt_count=row["attempt_count"] + 1,
                restore_checkpoint=checkpoint,
            )

    def release_work(self, work: WorkItem, error_code: str, now: datetime) -> None:
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE execution_work
                SET state = 'pending', lease_owner = NULL, lease_expires_at = NULL,
                    last_error_code = ?, updated_at = ?
                WHERE work_id = ? AND state = 'processing'
                  AND lease_owner = ? AND lease_token = ? AND lease_expires_at > ?
                """,
                (
                    error_code,
                    format_timestamp(now),
                    work.work_id,
                    work.lease_owner,
                    work.lease_token,
                    format_timestamp(now),
                ),
            ).rowcount
            if updated != 1:
                raise WorkLeaseLostError(work.work_id)

    def complete_start(self, work: WorkItem, now: datetime) -> RuntimeStatus:
        with self._transaction() as connection:
            self._require_work_lease(connection, work, now)
            run = self._require_run(connection, work.runtime_run_id)
            next_state = "running" if run["status"] == "accepted" else run["status"]
            connection.execute(
                """
                UPDATE runtime_runs SET status = ?, updated_at = ? WHERE runtime_run_id = ?
                """,
                (next_state, format_timestamp(now), work.runtime_run_id),
            )
            self._complete_work(connection, work, now)
            return self._status(connection, work.runtime_run_id)

    def complete_cancel(
        self, work: WorkItem, evidence_reference: str, now: datetime
    ) -> RuntimeStatus:
        if not evidence_reference:
            raise InvalidMutationError(
                "cancellation evidence reference must not be empty"
            )
        with self._transaction() as connection:
            self._require_work_lease(connection, work, now)
            run = self._require_run(connection, work.runtime_run_id)
            if run["status"] != "cancel_requested":
                raise StateConflictError(
                    "terminal cancellation requires a durable cancel_requested state"
                )
            completed_at = format_timestamp(now)
            connection.execute(
                """
                UPDATE runtime_runs
                SET status = 'cancelled', cancellation_evidence_reference = ?,
                    updated_at = ?, completed_at = ?
                WHERE runtime_run_id = ?
                """,
                (evidence_reference, completed_at, completed_at, work.runtime_run_id),
            )
            self._append_event(
                connection,
                work.runtime_run_id,
                RunCancelledEventData(
                    cancellation_evidence_reference=evidence_reference,
                    completed_at=completed_at,
                ),
                now,
            )
            self._complete_work(connection, work, now)
            return self._status(connection, work.runtime_run_id)

    def complete_checkpoint(
        self,
        work: WorkItem,
        manifest: CheckpointManifest,
        manifest_digest: str,
        now: datetime,
    ) -> RuntimeStatus:
        manifest_json = json.dumps(
            manifest.to_document(), separators=(",", ":"), sort_keys=True
        )
        with self._transaction() as connection:
            self._require_work_lease(connection, work, now)
            run = self._require_run(connection, work.runtime_run_id)
            if manifest.runtime_run_id != work.runtime_run_id:
                raise StateConflictError("checkpoint manifest changed runtime_run_id")
            if manifest.event_sequence != run["last_event_sequence"]:
                raise StateConflictError("checkpoint event sequence is stale")
            connection.execute(
                """
                INSERT INTO checkpoint_manifests(
                    checkpoint_id, runtime_run_id, command_id, manifest_digest,
                    manifest_json, content_digest, content_reference, size_bytes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.checkpoint_id,
                    work.runtime_run_id,
                    work.command_id,
                    manifest_digest,
                    manifest_json,
                    manifest.digest,
                    manifest.content_reference,
                    manifest.size_bytes,
                    format_timestamp(manifest.created_at),
                ),
            )
            connection.execute(
                """
                UPDATE runtime_runs SET checkpoint_manifest_json = ?, updated_at = ?
                WHERE runtime_run_id = ?
                """,
                (manifest_json, format_timestamp(now), work.runtime_run_id),
            )
            self._append_event(
                connection,
                work.runtime_run_id,
                CheckpointCreatedEventData(
                    checkpoint_id=manifest.checkpoint_id,
                    checkpoint_manifest_digest=manifest_digest,
                    content_reference=manifest.content_reference,
                ),
                now,
            )
            self._complete_work(connection, work, now)
            return self._status(connection, work.runtime_run_id)

    def checkpoint_manifest_digest(self, manifest: CheckpointManifest) -> str:
        return _sha256_document(manifest.to_document())

    def count_jti(self, issuer: str, jti: str) -> int:
        connection = self._connect()
        try:
            return cast(
                int,
                connection.execute(
                    "SELECT COUNT(*) FROM consumed_mutation_jtis WHERE issuer = ? AND jti = ?",
                    (issuer, jti),
                ).fetchone()[0],
            )
        finally:
            connection.close()

    def _validate_start_security_binding(
        self,
        mutation: StartMutation,
        admission: MutationAdmission,
        binding: RuntimeSecurityBinding,
    ) -> None:
        expected = (
            mutation.tenant_id,
            self.configuration.provider_revision_id,
            mutation.runtime_run_id,
            mutation.agent_run_id,
            mutation.workflow_run_id,
            mutation.work_order_id,
            mutation.run_manifest_digest,
            mutation.runtime_authorization_digest,
        )
        bound = (
            binding.tenant_id,
            binding.provider_revision_id,
            binding.runtime_run_id,
            binding.agent_run_id,
            binding.workflow_run_id,
            binding.work_order_id,
            binding.run_manifest_digest,
            binding.runtime_authorization_digest,
        )
        admitted = (
            admission.tenant_id,
            admission.provider_revision_id,
            admission.runtime_run_id,
            admission.agent_run_id,
            admission.workflow_run_id,
            admission.work_order_id,
            admission.run_manifest_digest,
            admission.runtime_authorization_digest,
        )
        if bound != expected or admitted != expected:
            raise AuthorizationBindingError(
                "Start request, token and durable security scope differ"
            )
        if (
            admission.policy_decision_digest != binding.policy_decision_digest
            or admission.execution_budget_digest != binding.execution_budget_digest
            or admission.effective_permissions_digest
            != binding.effective_permissions_digest
            or admission.invocation_id != mutation.invocation_id
            or admission.invocation_attempt_id != mutation.invocation_attempt_id
            or admission.fencing_token != mutation.fencing_token
            or admission.operation_request_digest != mutation.request_digest
        ):
            raise AuthorizationBindingError(
                "Start token differs from the presented execution binding"
            )
        self._validate_admission_window(admission, binding)

    def _require_security_binding(
        self,
        connection: sqlite3.Connection,
        admission: MutationAdmission,
        *,
        minimum_fencing: bool,
        validate_execution_window: bool = False,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT binding.*, run.observed_fencing_token
            FROM runtime_security_bindings AS binding
            JOIN runtime_runs AS run USING (runtime_run_id)
            WHERE binding.runtime_run_id = ?
            """,
            (admission.runtime_run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeRunNotFoundError(admission.runtime_run_id)
        expected = (
            admission.tenant_id,
            admission.provider_revision_id,
            admission.agent_run_id,
            admission.workflow_run_id,
            admission.work_order_id,
            admission.run_manifest_digest,
            admission.runtime_authorization_digest,
            admission.policy_decision_digest,
            admission.execution_budget_digest,
            admission.effective_permissions_digest,
        )
        actual = (
            row["tenant_id"],
            row["provider_revision_id"],
            row["agent_run_id"],
            row["workflow_run_id"],
            row["work_order_id"],
            row["run_manifest_digest"],
            row["runtime_authorization_digest"],
            row["policy_decision_digest"],
            row["execution_budget_digest"],
            row["effective_permissions_digest"],
        )
        if actual != expected:
            raise AuthorizationBindingError(
                "Runtime token does not match the durable security binding"
            )
        if minimum_fencing and admission.fencing_token < row["observed_fencing_token"]:
            raise StaleFencingError(
                "read token fencing is older than the observed Runtime fencing"
            )
        if validate_execution_window and admission.authority_mode == "execution":
            self._validate_admission_window(
                admission, self._security_binding_from_row(row)
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _security_binding_from_row(row: sqlite3.Row) -> RuntimeSecurityBinding:
        return RuntimeSecurityBinding(
            tenant_id=row["tenant_id"],
            provider_revision_id=row["provider_revision_id"],
            runtime_run_id=row["runtime_run_id"],
            agent_run_id=row["agent_run_id"],
            workflow_run_id=row["workflow_run_id"],
            work_order_id=row["work_order_id"],
            run_manifest_digest=row["run_manifest_digest"],
            runtime_authorization_digest=row["runtime_authorization_digest"],
            policy_decision_digest=row["policy_decision_digest"],
            execution_budget_digest=row["execution_budget_digest"],
            effective_permissions_digest=row["effective_permissions_digest"],
            authorization_issued_at=parse_timestamp(row["authorization_issued_at"]),
            authorization_expires_at=parse_timestamp(row["authorization_expires_at"]),
            policy_decided_at=parse_timestamp(row["policy_decided_at"]),
            policy_expires_at=parse_timestamp(row["policy_expires_at"]),
            budget_created_at=parse_timestamp(row["budget_created_at"]),
            budget_expires_at=parse_timestamp(row["budget_expires_at"]),
            commercial_authorization_expires_at=parse_timestamp(
                row["commercial_authorization_expires_at"]
            ),
            artifact_grants_not_before=parse_timestamp(
                row["artifact_grants_not_before"]
            )
            if row["artifact_grants_not_before"]
            else None,
            artifact_grants_expire_at=parse_timestamp(row["artifact_grants_expire_at"])
            if row["artifact_grants_expire_at"]
            else None,
        )

    @staticmethod
    def _validate_admission_window(
        admission: MutationAdmission, binding: RuntimeSecurityBinding
    ) -> None:
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
        ]
        if binding.artifact_grants_not_before is not None:
            lower_bounds.append(binding.artifact_grants_not_before)
            assert binding.artifact_grants_expire_at is not None
            upper_bounds.append(binding.artifact_grants_expire_at)
        if admission.not_before < max(lower_bounds):
            raise AuthorizationBindingError(
                "execution token predates its durable authorization facts"
            )
        if admission.expires_at > min(upper_bounds):
            raise AuthorizationBindingError(
                "execution token outlives its durable authorization facts"
            )

    def _consume_jti(
        self,
        connection: sqlite3.Connection,
        admission: MutationAdmission,
        digest: str,
        runtime_run_id: str,
        now: datetime,
    ) -> None:
        try:
            connection.execute(
                """
                INSERT INTO consumed_mutation_jtis(
                    issuer, jti, operation, request_digest, runtime_run_id,
                    expires_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    admission.issuer,
                    admission.jti,
                    admission.operation,
                    digest,
                    runtime_run_id,
                    format_timestamp(admission.expires_at),
                    format_timestamp(now),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise MutationReplayError(
                "mutation JTI has already been consumed"
            ) from error

    @staticmethod
    def _execute_sql_script(connection: sqlite3.Connection, encoded: str) -> None:
        statement = ""
        for line in encoded.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
        if statement.strip():
            raise RuntimeError("SQLite migration ends with an incomplete statement")

    def _validate_command_authority(
        self, mutation: CommandMutation, admission: MutationAdmission
    ) -> None:
        has_safety_id = mutation.system_safety_control_id is not None
        has_safety_digest = mutation.system_safety_control_digest is not None
        if has_safety_id != has_safety_digest:
            raise InvalidMutationError(
                "system safety authority requires both ID and digest"
            )
        if admission.authority_mode == "safety_control":
            if mutation.type not in {"pause", "cancel"}:
                raise InvalidMutationError(
                    "safety-control authority permits only exact Pause or Cancel"
                )
            if not has_safety_id or mutation.authorized_control_request_id is not None:
                raise InvalidMutationError(
                    "safety-control command authority is incomplete"
                )
            return
        if has_safety_id:
            raise InvalidMutationError(
                "execution authority cannot present SystemSafetyControl"
            )
        if mutation.type in {"pause", "resume", "cancel"}:
            if mutation.authorized_control_request_id is None:
                raise InvalidMutationError(
                    "user control command lacks its authority binding"
                )
        elif mutation.authorized_control_request_id is not None:
            raise InvalidMutationError(
                "checkpoint command cannot use control authority"
            )

    def _command_transition(
        self, state: str, command_type: str
    ) -> tuple[str, str | None]:
        if state in TERMINAL_STATES:
            raise StateConflictError(f"runtime run is terminal in state {state}")
        if command_type == "cancel":
            if state not in {"accepted", "running", "waiting_input", "paused"}:
                raise StateConflictError(f"Cancel is not valid from state {state}")
            return "cancel_requested", "cancel"
        if command_type == "pause":
            if state != "running":
                raise StateConflictError(f"Pause is not valid from state {state}")
            return "paused", None
        if command_type == "resume":
            if state != "paused":
                raise StateConflictError(f"Resume is not valid from state {state}")
            return "running", None
        if command_type == "checkpoint":
            if state not in {"running", "waiting_input", "paused"}:
                raise StateConflictError(f"Checkpoint is not valid from state {state}")
            return state, "checkpoint"
        raise InvalidMutationError(f"unsupported command type {command_type}")

    def _append_event(
        self,
        connection: sqlite3.Connection,
        runtime_run_id: str,
        data: RuntimeEventData,
        now: datetime,
    ) -> None:
        row = self._require_run(connection, runtime_run_id)
        sequence = row["last_event_sequence"] + 1
        event_id = f"{runtime_run_id}:event:{sequence}"
        event_type = event_type_for_data(data)
        connection.execute(
            """
            INSERT INTO runtime_events(
                runtime_run_id, event_sequence, event_id, type, occurred_at,
                data_version, data_json, source_cursor
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                runtime_run_id,
                sequence,
                event_id,
                event_type,
                format_timestamp(now),
                json.dumps(
                    event_data_to_document(data), separators=(",", ":"), sort_keys=True
                ),
                f"native-event-{sequence}",
            ),
        )
        connection.execute(
            """
            UPDATE runtime_runs SET last_event_sequence = ?, updated_at = ?
            WHERE runtime_run_id = ?
            """,
            (sequence, format_timestamp(now), runtime_run_id),
        )

    def _status(
        self, connection: sqlite3.Connection, runtime_run_id: str
    ) -> RuntimeStatus:
        row = self._require_run(connection, runtime_run_id)
        checkpoint = (
            CheckpointManifest.from_document(
                json.loads(row["checkpoint_manifest_json"])
            )
            if row["checkpoint_manifest_json"]
            else None
        )
        return RuntimeStatus(
            runtime_run_id=row["runtime_run_id"],
            tenant_id=row["tenant_id"],
            conversation_id=row["conversation_id"],
            work_order_id=row["work_order_id"],
            workflow_run_id=row["workflow_run_id"],
            agent_run_id=row["agent_run_id"],
            status=row["status"],
            last_command_sequence=row["last_command_sequence"],
            last_event_sequence=row["last_event_sequence"],
            observed_fencing_token=row["observed_fencing_token"],
            updated_at=parse_timestamp(row["updated_at"]),
            completed_at=parse_timestamp(row["completed_at"])
            if row["completed_at"]
            else None,
            checkpoint=checkpoint,
            cancellation_evidence_reference=row["cancellation_evidence_reference"],
        )

    def _event(self, row: sqlite3.Row) -> RuntimeEvent:
        event_type_value = row["type"]
        if event_type_value not in {
            "runtime.run.started",
            "runtime.checkpoint.created",
            "runtime.run.cancelled",
        }:
            raise InvalidMutationError(
                "persisted Runtime event type is not admitted by a0"
            )
        event_type = cast(RuntimeEventType, event_type_value)
        data_version = row["data_version"]
        if data_version != 1:
            raise InvalidMutationError(
                "persisted Runtime event data version is not admitted"
            )
        return RuntimeEvent(
            event_id=row["event_id"],
            runtime_run_id=row["runtime_run_id"],
            event_sequence=row["event_sequence"],
            type=event_type,
            occurred_at=parse_timestamp(row["occurred_at"]),
            data_version=1,
            data=event_data_from_document(event_type, json.loads(row["data_json"])),
            source_cursor=row["source_cursor"],
        )

    def _require_run(
        self, connection: sqlite3.Connection, runtime_run_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM runtime_runs WHERE runtime_run_id = ?", (runtime_run_id,)
        ).fetchone()
        if row is None:
            raise RuntimeRunNotFoundError(runtime_run_id)
        return cast(sqlite3.Row, row)

    def _require_work_lease(
        self, connection: sqlite3.Connection, work: WorkItem, now: datetime
    ) -> None:
        row = connection.execute(
            """
            SELECT 1 FROM execution_work
            WHERE work_id = ? AND state = 'processing'
              AND lease_owner = ? AND lease_token = ? AND lease_expires_at > ?
            """,
            (work.work_id, work.lease_owner, work.lease_token, format_timestamp(now)),
        ).fetchone()
        if row is None:
            raise WorkLeaseLostError(work.work_id)

    def _complete_work(
        self, connection: sqlite3.Connection, work: WorkItem, now: datetime
    ) -> None:
        completed_at = format_timestamp(now)
        updated = connection.execute(
            """
            UPDATE execution_work
            SET state = 'completed', lease_expires_at = NULL,
                updated_at = ?, completed_at = ?
            WHERE work_id = ? AND state = 'processing'
              AND lease_owner = ? AND lease_token = ?
            """,
            (
                completed_at,
                completed_at,
                work.work_id,
                work.lease_owner,
                work.lease_token,
            ),
        ).rowcount
        if updated != 1:
            raise WorkLeaseLostError(work.work_id)
