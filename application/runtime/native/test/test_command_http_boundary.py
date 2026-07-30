from __future__ import annotations

import json
import socket
import sqlite3
import time
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from cryptography.hazmat.primitives.asymmetric import ed25519
from process_test_support import (
    INSTALLED_BIN,
    InstalledProcessTestCase,
    RawHTTPConnection,
    refresh_self_digest,
)

from agent_native_runtime.errors import (
    AuthorizationBindingError,
    CheckpointCompatibilityError,
    CommandSequenceError,
    ContractSchemaError,
    DigestMismatchError,
    EncodedBodyTooLargeError,
    IdempotencyConflictError,
    InvalidMutationError,
    MutationReplayError,
    RuntimeRunConflictError,
    RuntimeRunNotFoundError,
    StaleFencingError,
    StateConflictError,
    StrictJsonError,
    TokenValidationError,
    UnsupportedOperationError,
)
from agent_native_runtime.http_process import (
    COMMAND_ENCODED_BODY_LIMIT,
    RUN_STATUS_SCHEMA_ID,
    STANDARD_ERROR_SCHEMA_ID,
    _command_error_response,
    _HTTPErrorResponse,
    _parse_exact_command_request_line,
    _targets_command_boundary,
)
from agent_native_runtime.process_config import load_process_configuration
from agent_native_runtime.security import RuntimeContractProjection


class CommandTransportAdmissionTest(unittest.TestCase):
    def test_command_request_line_is_exact_dynamic_origin_form(self) -> None:
        self.assertEqual(
            _parse_exact_command_request_line(
                b"POST /v1/runs/runtime-run-1/commands HTTP/1.1\r\n"
            ),
            "runtime-run-1",
        )
        for request_line in (
            b"POST /v1/runs//commands HTTP/1.1\r\n",
            b"POST /v1/runs/a/b/commands HTTP/1.1\r\n",
            b"POST /v1/runs/a%2Fb/commands HTTP/1.1\r\n",
            b"POST /v1/runs/a\\b/commands HTTP/1.1\r\n",
            b"POST /v1/runs/a/commands?cursor=1 HTTP/1.1\r\n",
            b"POST /v1/runs/a/commands#fragment HTTP/1.1\r\n",
            b"POST /v1/runs/a/commands/ HTTP/1.1\r\n",
            b"POST https://localhost/v1/runs/a/commands HTTP/1.1\r\n",
            b"POST /v1/runs/a/commands HTTP/1.0\r\n",
            b"GET /v1/runs/a/commands HTTP/1.1\r\n",
        ):
            with self.subTest(request_line=request_line):
                self.assertIsNone(_parse_exact_command_request_line(request_line))

        for command, path in (
            ("GET", "/v1/runs/a/commands"),
            ("POST", "/v1/runs/a/commands/"),
            ("POST", "/v1/runs/a/commands?cursor=1"),
            ("POST", "https://localhost/v1/runs/a/commands"),
        ):
            with self.subTest(command=command, path=path):
                self.assertTrue(_targets_command_boundary(command, path))
        self.assertFalse(_targets_command_boundary("GET", "/v1/runs/a"))

    def test_command_error_mapping_is_closed_and_safe(self) -> None:
        busy = sqlite3.OperationalError("secret database path is locked")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        cases: tuple[tuple[Exception, int, str, bool, int | None], ...] = (
            (
                EncodedBodyTooLargeError("secret body"),
                413,
                "COMMAND_BODY_TOO_LARGE",
                False,
                None,
            ),
            (
                TokenValidationError("secret token"),
                401,
                "RUNTIME_TOKEN_REJECTED",
                False,
                None,
            ),
            (
                AuthorizationBindingError("secret binding"),
                403,
                "RUNTIME_AUTHORIZATION_REJECTED",
                False,
                None,
            ),
            (
                RuntimeRunNotFoundError("secret run"),
                404,
                "RUNTIME_RUN_NOT_FOUND",
                False,
                None,
            ),
            (
                UnsupportedOperationError("secret operation"),
                422,
                "RUNTIME_COMMAND_UNSUPPORTED",
                False,
                None,
            ),
            (
                CheckpointCompatibilityError("secret checkpoint"),
                422,
                "RUNTIME_COMMAND_UNSUPPORTED",
                False,
                None,
            ),
            (busy, 503, "PROVIDER_TEMPORARILY_UNAVAILABLE", True, 1),
        )
        cases += tuple(
            (error, 400, "RUNTIME_COMMAND_REJECTED", False, None)
            for error in (
                StrictJsonError("secret JSON"),
                ContractSchemaError("secret schema"),
                DigestMismatchError("secret digest"),
                InvalidMutationError("secret mutation"),
            )
        )
        cases += tuple(
            (error, 409, "RUNTIME_COMMAND_CONFLICT", False, None)
            for error in (
                CommandSequenceError("secret sequence"),
                IdempotencyConflictError("secret idempotency"),
                MutationReplayError("secret JTI"),
                RuntimeRunConflictError("secret run conflict"),
                StaleFencingError("secret fencing"),
                StateConflictError("secret state"),
            )
        )
        cases += (
            (
                RuntimeError("secret traceback"),
                500,
                "INTERNAL_ERROR",
                False,
                None,
            ),
        )
        for error, status, code, retryable, retry_after in cases:
            with self.subTest(error=type(error).__name__):
                response = _command_error_response(error)
                self.assertIsInstance(response, _HTTPErrorResponse)
                self.assertEqual(response.status.value, status)
                self.assertEqual(response.code, code)
                self.assertEqual(response.retryable, retryable)
                self.assertEqual(response.retry_after, retry_after)
                self.assertNotIn("secret", response.message)


if INSTALLED_BIN is not None:

    class InstalledCommandHTTPBoundaryTest(InstalledProcessTestCase):
        def setUp(self) -> None:
            super().setUp()
            configuration = load_process_configuration(self.config_path)
            self.projection = RuntimeContractProjection.load(configuration.security)

        def assert_json_document(
            self,
            status: int,
            headers: dict[str, str],
            body: bytes,
            *,
            expected_status: int,
            schema_id: str,
        ) -> dict[str, Any]:
            self.assertEqual(status, expected_status, body)
            self.assertEqual(headers["content-type"], "application/json")
            self.assertEqual(int(headers["content-length"]), len(body))
            document = cast(dict[str, Any], json.loads(body))
            self.projection.validate(schema_id, document)
            return document

        def assert_error(
            self,
            response: tuple[int, dict[str, str], bytes],
            *,
            status: int,
            code: str,
            retry_after: int | None = None,
            secrets: tuple[str, ...] = (),
        ) -> dict[str, Any]:
            response_status, headers, body = response
            document = self.assert_json_document(
                response_status,
                headers,
                body,
                expected_status=status,
                schema_id=STANDARD_ERROR_SCHEMA_ID,
            )
            self.assertEqual(document["code"], code, document)
            if retry_after is None:
                self.assertNotIn("retry-after", headers)
            else:
                self.assertEqual(headers["retry-after"], str(retry_after))
            encoded = body.decode("ascii")
            for secret in secrets:
                self.assertNotIn(secret, encoded)
            return document

        def admit_start(
            self,
            port: int,
            *,
            jti: str = "runtime-command-start-jti-0001",
            document: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            document = document or self.start_document()
            body, token = self.start_request(document, jti=jti)
            response = self.request(
                port,
                self.pki.client,
                "/v1/runs",
                method="POST",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
            status = self.assert_json_document(
                *response,
                expected_status=202,
                schema_id=RUN_STATUS_SCHEMA_ID,
            )
            self.last_start_response_bytes = len(response[2])
            self.assertEqual(status["status"], "accepted")
            return document

        def test_valid_cancel_replay_conflicts_and_cancel_requested_boundary(
            self,
        ) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            with self.serving(self.config_path) as server:
                start = self.admit_start(server.port)
                command = self.command_document(start)
                body, first_token = self.command_request(
                    start, command, jti="runtime-command-jti-accepted-0001"
                )
                accepted = self.assert_json_document(
                    *self.post_command(
                        server.port,
                        cast(str, start["runtime_run_id"]),
                        body,
                        first_token,
                    ),
                    expected_status=202,
                    schema_id=RUN_STATUS_SCHEMA_ID,
                )
                self.assertEqual(accepted["status"], "cancel_requested")
                self.assertEqual(accepted["last_command_sequence"], 1)
                self.assertEqual(accepted["last_event_sequence"], 1)
                self.assertNotIn("completed_at", accepted)

                _, replay_token = self.command_request(
                    start,
                    command,
                    jti="runtime-command-jti-replay-0002",
                    algorithm="ES256",
                )
                replay = self.assert_json_document(
                    *self.post_command(
                        server.port,
                        cast(str, start["runtime_run_id"]),
                        body,
                        replay_token,
                    ),
                    expected_status=202,
                    schema_id=RUN_STATUS_SCHEMA_ID,
                )
                self.assertEqual(replay, accepted)

                self.assert_error(
                    self.post_command(
                        server.port,
                        cast(str, start["runtime_run_id"]),
                        body,
                        first_token,
                    ),
                    status=409,
                    code="RUNTIME_COMMAND_CONFLICT",
                    secrets=(first_token,),
                )

                conflict = deepcopy(command)
                conflict["reason"] = "replacement command content"
                refresh_self_digest(conflict, "command_digest")
                conflict_body, conflict_token = self.command_request(
                    start, conflict, jti="runtime-command-jti-conflict-0003"
                )
                self.assert_error(
                    self.post_command(
                        server.port,
                        cast(str, start["runtime_run_id"]),
                        conflict_body,
                        conflict_token,
                    ),
                    status=409,
                    code="RUNTIME_COMMAND_CONFLICT",
                    secrets=(conflict_token,),
                )

            counts = self.command_database_counts(state_root)
            self.assertEqual(counts["consumed_mutation_jtis"], 3)
            self.assertEqual(counts["runtime_commands"], 1)
            self.assertEqual(counts["execution_work"], 2)
            self.assertEqual(counts["runtime_events"], 1)
            connection = sqlite3.connect(state_root / "runtime.sqlite3")
            try:
                durable = connection.execute(
                    "SELECT status, cancellation_evidence_reference FROM runtime_runs"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(durable, ("cancel_requested", None))

        def test_crypto_oracle_durable_binding_and_unsupported_variants(self) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            with self.serving(self.config_path) as server:
                start = self.admit_start(
                    server.port, jti="runtime-command-start-jti-crypto-0001"
                )
                runtime_run_id = cast(str, start["runtime_run_id"])
                baseline = self.command_database_counts(state_root)

                path_command = self.command_document(start)
                path_body, path_token = self.command_request(
                    start,
                    path_command,
                    jti="runtime-command-path-binding-jti-0001",
                )
                self.assert_error(
                    self.post_command(
                        server.port,
                        "runtime-run-path-replacement",
                        path_body,
                        path_token,
                    ),
                    status=403,
                    code="RUNTIME_AUTHORIZATION_REJECTED",
                    secrets=(path_token,),
                )
                self.assertEqual(self.command_database_counts(state_root), baseline)

                wrong_key = ed25519.Ed25519PrivateKey.generate()
                outcomes: list[tuple[int, str]] = []
                for index, target in enumerate(
                    (runtime_run_id, "runtime-run-does-not-exist"), start=1
                ):
                    target_start = deepcopy(start)
                    target_start["runtime_run_id"] = target
                    command = self.command_document(target_start)
                    claims = self.command_claims(
                        target_start,
                        command,
                        jti=f"runtime-command-oracle-jti-{index:04d}",
                    )
                    token = self.sign_start(claims, private_key=wrong_key)
                    response = self.post_command(
                        server.port, target, self.encode(command), token
                    )
                    error = self.assert_error(
                        response,
                        status=401,
                        code="RUNTIME_TOKEN_REJECTED",
                        secrets=(token,),
                    )
                    outcomes.append((response[0], cast(str, error["code"])))
                    self.assertEqual(self.command_database_counts(state_root), baseline)
                self.assertEqual(outcomes[0], outcomes[1])

                missing_start = deepcopy(start)
                missing_start["runtime_run_id"] = (
                    "runtime-run-cryptographically-admitted"
                )
                missing = self.command_document(missing_start)
                missing_body, missing_token = self.command_request(
                    missing_start,
                    missing,
                    jti="runtime-command-missing-jti-0001",
                )
                self.assert_error(
                    self.post_command(
                        server.port,
                        cast(str, missing["runtime_run_id"]),
                        missing_body,
                        missing_token,
                    ),
                    status=404,
                    code="RUNTIME_RUN_NOT_FOUND",
                    secrets=(missing_token,),
                )
                self.assertEqual(self.command_database_counts(state_root), baseline)

                durable_command = self.command_document(start)
                durable_claims = self.command_claims(
                    start,
                    durable_command,
                    jti="runtime-command-durable-binding-jti-0001",
                )
                durable_claims["tenant_id"] = "tenant-durable-replacement"
                durable_token = self.sign_start(durable_claims)
                self.assert_error(
                    self.post_command(
                        server.port,
                        runtime_run_id,
                        self.encode(durable_command),
                        durable_token,
                    ),
                    status=403,
                    code="RUNTIME_AUTHORIZATION_REJECTED",
                    secrets=(durable_token,),
                )
                self.assertEqual(self.command_database_counts(state_root), baseline)

                for index, command_type in enumerate(
                    (
                        "append_input",
                        "interrupt",
                        "approval_decision",
                        "subagent_spawn_decision",
                    ),
                    start=1,
                ):
                    command = self.command_document(
                        start,
                        command_type=command_type,
                        command_sequence=index,
                        fencing_token=index + 1,
                    )
                    body, token = self.command_request(
                        start,
                        command,
                        jti=f"runtime-command-unsupported-jti-{index:04d}",
                    )
                    self.assert_error(
                        self.post_command(server.port, runtime_run_id, body, token),
                        status=422,
                        code="RUNTIME_COMMAND_UNSUPPORTED",
                        secrets=(token,),
                    )
                    self.assertEqual(self.command_database_counts(state_root), baseline)

        def test_target_host_content_type_and_framing_are_strict(self) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            target_rejections = (
                b"GET /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs/run-1/commands/ HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs/run%2F1/commands HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs/run/1/commands HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs/run-1/commands?x=1 HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST https://localhost/v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs/run-1/commands HTTP/1.0\r\nHost: localhost\r\n\r\n",
            )
            framing_rejections = (
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 0\r\n\r\n",
                    "HTTP_HOST_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n"
                    b"Host: localhost\r\nContent-Type: application/json\r\n"
                    b"Content-Length: 0\r\n\r\n",
                    "HTTP_HOST_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: remote.invalid\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 0\r\n\r\n",
                    "HTTP_HOST_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: text/plain\r\nContent-Length: 0\r\n\r\n",
                    "HTTP_CONTENT_TYPE_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 0\r\n"
                    b"Content-Length: 0\r\n\r\n",
                    "HTTP_FRAMING_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 00\r\n\r\n",
                    "HTTP_FRAMING_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 0, 0\r\n\r\n",
                    "HTTP_FRAMING_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nTransfer-Encoding: chunked\r\n"
                    b"Content-Length: 0\r\n\r\n",
                    "HTTP_FRAMING_REJECTED",
                ),
                (
                    b"POST /v1/runs/run-1/commands HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nExpect: 100-continue\r\n"
                    b"Content-Length: 0\r\n\r\n",
                    "HTTP_FRAMING_REJECTED",
                ),
            )
            with self.serving(self.config_path) as server:
                for index, request in enumerate(target_rejections):
                    with self.subTest(kind="target", index=index):
                        raw = RawHTTPConnection(
                            self.tls_socket(server.port, self.pki.client)
                        )
                        try:
                            raw.connection.sendall(request)
                            self.assert_error(
                                raw.response(),
                                status=400,
                                code=(
                                    "HTTP_VERSION_REJECTED"
                                    if index == len(target_rejections) - 1
                                    else "HTTP_COMMAND_TARGET_REJECTED"
                                ),
                            )
                        finally:
                            raw.connection.close()
                for index, (request, code) in enumerate(framing_rejections):
                    with self.subTest(kind="framing", index=index):
                        raw = RawHTTPConnection(
                            self.tls_socket(server.port, self.pki.client)
                        )
                        try:
                            raw.connection.sendall(request)
                            self.assert_error(raw.response(), status=400, code=code)
                        finally:
                            raw.connection.close()
            counts = self.command_database_counts(state_root)
            self.assertTrue(all(value == 0 for value in counts.values()))

        def test_body_limit_short_read_slow_body_and_exact_limit(self) -> None:
            bounded = deepcopy(self.base)
            state_root = self.root / "state-command-body-boundary"
            bounded["runtime"]["state_root"] = str(state_root)
            bounded["process"]["limits"]["read_timeout_ms"] = 300
            path = self.write_configuration("command-body-boundary.json", bounded)
            self.migrate(path)
            with self.serving(path) as server:
                start = self.admit_start(
                    server.port, jti="runtime-command-body-start-jti-0001"
                )
                command = self.command_document(start)
                body, token = self.command_request(
                    start, command, jti="runtime-command-body-jti-0001"
                )
                authorization = f"Authorization: Bearer {token}\r\n".encode("ascii")
                route = f"/v1/runs/{start['runtime_run_id']}/commands"

                over_limit = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                over_limit.request(
                    "POST",
                    route,
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + authorization
                        + f"Content-Length: {COMMAND_ENCODED_BODY_LIMIT + 1}\r\n".encode(
                            "ascii"
                        )
                    ),
                )
                self.assert_error(
                    over_limit.response(),
                    status=413,
                    code="COMMAND_BODY_TOO_LARGE",
                    secrets=(token,),
                )
                over_limit.connection.close()

                short = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
                short.request(
                    "POST",
                    route,
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + authorization
                        + f"Content-Length: {len(body) + 1}\r\n".encode("ascii")
                    ),
                    body=body,
                )
                try:
                    short.connection.shutdown(socket.SHUT_WR)
                    with self.assertRaises(ConnectionError):
                        short.response()
                finally:
                    short.connection.close()

                slow = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
                slow.request(
                    "POST",
                    route,
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + authorization
                        + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    ),
                    body=body[:1],
                )
                time.sleep(0.4)
                self.assert_error(
                    slow.response(),
                    status=400,
                    code="HTTP_BODY_READ_REJECTED",
                    secrets=(token,),
                )
                slow.connection.close()

                exact = body + b" " * (COMMAND_ENCODED_BODY_LIMIT - len(body))
                self.assertEqual(len(exact), COMMAND_ENCODED_BODY_LIMIT)
                accepted = self.post_command(
                    server.port,
                    cast(str, start["runtime_run_id"]),
                    exact,
                    token,
                )
                status = self.assert_json_document(
                    *accepted,
                    expected_status=202,
                    schema_id=RUN_STATUS_SCHEMA_ID,
                )
                self.assertEqual(status["status"], "cancel_requested")

            counts = self.command_database_counts(state_root)
            self.assertEqual(counts["consumed_mutation_jtis"], 2)
            self.assertEqual(counts["runtime_commands"], 1)

        def test_concurrency_sqlite_busy_and_response_limit_are_closed(self) -> None:
            concurrent = deepcopy(self.base)
            concurrent_state = self.root / "state-command-concurrency"
            concurrent["runtime"]["state_root"] = str(concurrent_state)
            concurrent["process"]["limits"]["max_connections"] = 2
            concurrent["process"]["limits"]["max_concurrent_requests"] = 1
            concurrent["process"]["limits"]["read_timeout_ms"] = 2_000
            concurrent_path = self.write_configuration(
                "command-concurrency.json", concurrent
            )
            self.migrate(concurrent_path)
            with self.serving(concurrent_path) as server:
                start = self.admit_start(
                    server.port, jti="runtime-command-concurrency-start-jti-0001"
                )
                command = self.command_document(start)
                body, token = self.command_request(
                    start, command, jti="runtime-command-concurrency-jti-0001"
                )
                route = f"/v1/runs/{start['runtime_run_id']}/commands"
                authorization = f"Authorization: Bearer {token}\r\n".encode("ascii")
                held = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
                held.request(
                    "POST",
                    route,
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + authorization
                        + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    ),
                    body=body[:1],
                )
                rejected = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                rejected.request(
                    "POST",
                    route,
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + authorization
                        + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    ),
                    body=body,
                )
                self.assert_error(
                    rejected.response(),
                    status=429,
                    code="PROVIDER_COMMAND_CONCURRENCY_LIMIT",
                    retry_after=1,
                    secrets=(token,),
                )
                held.connection.close()
                rejected.connection.close()

            locked = deepcopy(self.base)
            locked_state = self.root / "state-command-sqlite-busy"
            locked["runtime"]["state_root"] = str(locked_state)
            locked["runtime"]["sqlite_busy_timeout_ms"] = 100
            locked_path = self.write_configuration("command-sqlite-busy.json", locked)
            self.migrate(locked_path)
            with self.serving(locked_path) as server:
                start = self.admit_start(
                    server.port, jti="runtime-command-busy-start-jti-0001"
                )
            command = self.command_document(start)
            body, token = self.command_request(
                start, command, jti="runtime-command-busy-jti-0001"
            )
            lock_connection = sqlite3.connect(locked_state / "runtime.sqlite3")
            lock_connection.execute("BEGIN IMMEDIATE")
            try:
                with self.serving(locked_path) as server:
                    self.assert_error(
                        self.post_command(
                            server.port,
                            cast(str, start["runtime_run_id"]),
                            body,
                            token,
                        ),
                        status=503,
                        code="PROVIDER_TEMPORARILY_UNAVAILABLE",
                        retry_after=1,
                        secrets=(token,),
                    )
            finally:
                lock_connection.rollback()
                lock_connection.close()

            long_start = self.start_document()
            replacements = {
                cast(str, long_start[field]): character * 200
                for field, character in (
                    ("runtime_run_id", "r"),
                    ("tenant_id", "t"),
                    ("conversation_id", "c"),
                    ("work_order_id", "w"),
                    ("workflow_run_id", "f"),
                    ("agent_run_id", "a"),
                )
            }
            encoded = json.dumps(long_start, separators=(",", ":"))
            for original, replacement in replacements.items():
                encoded = encoded.replace(original, replacement)
            long_start = cast(dict[str, Any], json.loads(encoded))
            self.refresh_start_digests(long_start)

            probe = deepcopy(self.base)
            probe_state = self.root / "state-command-response-probe"
            probe["runtime"]["state_root"] = str(probe_state)
            probe_path = self.write_configuration("command-response-probe.json", probe)
            self.migrate(probe_path)
            with self.serving(probe_path) as server:
                self.admit_start(
                    server.port,
                    jti="runtime-command-limit-probe-jti-0001",
                    document=deepcopy(long_start),
                )
            response_limit = self.last_start_response_bytes + 4
            self.assertGreater(response_limit, 256)

            limited = deepcopy(self.base)
            limited_state = self.root / "state-command-response-limit"
            limited["runtime"]["state_root"] = str(limited_state)
            limited["process"]["limits"]["max_response_bytes"] = response_limit
            limited_path = self.write_configuration(
                "command-response-base.json", limited
            )
            self.migrate(limited_path)
            with self.serving(limited_path) as server:
                start = self.admit_start(
                    server.port,
                    jti="runtime-command-limit-start-jti-0001",
                    document=deepcopy(long_start),
                )
                command = self.command_document(start)
                body, token = self.command_request(
                    start, command, jti="runtime-command-limit-jti-0001"
                )
                self.assert_error(
                    self.post_command(
                        server.port,
                        cast(str, start["runtime_run_id"]),
                        body,
                        token,
                    ),
                    status=500,
                    code="RESPONSE_LIMIT_EXCEEDED",
                    secrets=(token,),
                )
            counts = self.command_database_counts(limited_state)
            self.assertEqual(counts["runtime_commands"], 1)
            self.assertEqual(counts["consumed_mutation_jtis"], 2)


if __name__ == "__main__":
    unittest.main()
