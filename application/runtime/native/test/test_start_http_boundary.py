from __future__ import annotations

import http.client
import io
import json
import signal
import socket
import sqlite3
import time
import unittest
from copy import deepcopy
from datetime import UTC, datetime
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

from process_test_support import (
    CONTRACT_ROOT,
    INSTALLED_BIN,
    InstalledProcessTestCase,
    RawHTTPConnection,
    refresh_self_digest,
)

from agent_native_runtime.errors import (
    AuthorizationBindingError,
    CheckpointCompatibilityError,
    ContractSchemaError,
    DigestMismatchError,
    EncodedBodyTooLargeError,
    IdempotencyConflictError,
    InvalidMutationError,
    MutationReplayError,
    RuntimeRunConflictError,
    StrictJsonError,
    TokenValidationError,
    UnsupportedOperationError,
)
from agent_native_runtime.http_process import (
    RUN_STATUS_SCHEMA_ID,
    STANDARD_ERROR_SCHEMA_ID,
    START_ENCODED_BODY_LIMIT,
    ProviderRequestHandler,
    _HTTPErrorResponse,
    _is_exact_start_request_line,
    _parse_bearer_authorization,
    _parse_content_length,
    _runtime_status_document,
    _standard_error_document,
    _start_error_response,
    _targets_start_boundary,
)
from agent_native_runtime.model import RuntimeStatus
from agent_native_runtime.process_config import load_process_configuration
from agent_native_runtime.security import RuntimeContractProjection
from agent_native_runtime.tls import AuthenticatedCaller


class FakeConnection:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def settimeout(self, timeout: float) -> None:
        self.timeouts.append(timeout)


class FakeMetrics:
    def __init__(self) -> None:
        self.increments: list[str] = []

    def increment(self, name: str) -> None:
        self.increments.append(name)


class TimeoutReader(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        del size
        raise TimeoutError


class StartTransportAdmissionTest(unittest.TestCase):
    def handler(self, body: bytes = b"") -> ProviderRequestHandler:
        handler = ProviderRequestHandler.__new__(ProviderRequestHandler)
        limits = SimpleNamespace(read_timeout_ms=200, max_response_bytes=65_536)
        security = SimpleNamespace(max_token_bytes=16 * 1024)
        process_state = SimpleNamespace(metrics=FakeMetrics(), readiness=Mock())
        process_state.readiness.is_set.return_value = True
        handler.server = cast(
            Any,
            SimpleNamespace(
                configuration=SimpleNamespace(limits=limits, security=security),
                process_state=process_state,
                core=Mock(side_effect=AssertionError("core must not be accessed")),
                server_address=("127.0.0.1", 8443),
            ),
        )
        handler.connection = cast(Any, FakeConnection())
        handler.rfile = io.BytesIO(body)
        handler.close_connection = False
        return handler

    @staticmethod
    def headers(*values: tuple[str, str]) -> Message:
        headers = Message()
        for name, value in values:
            headers[name] = value
        return headers

    def test_content_length_is_single_ascii_canonical_decimal(self) -> None:
        self.assertIsNone(_parse_content_length([]))
        self.assertEqual(_parse_content_length(["0"]), 0)
        self.assertEqual(
            _parse_content_length([str(START_ENCODED_BODY_LIMIT)]),
            START_ENCODED_BODY_LIMIT,
        )
        for values in (
            ["1", "1"],
            ["1, 1"],
            [""],
            ["+1"],
            ["-1"],
            ["01"],
            [" 1"],
            ["1 "],
            ["\N{ARABIC-INDIC DIGIT ONE}"],
            ["9" * 21],
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                _parse_content_length(values)

    def test_start_request_line_is_exact_origin_form_http_1_1(self) -> None:
        self.assertTrue(_is_exact_start_request_line(b"POST /v1/runs HTTP/1.1\r\n"))
        for request_line in (
            b"POST /v1/runs HTTP/1.1\n",
            b"POST /v1/runs/ HTTP/1.1\r\n",
            b"POST /v1/runs?x=1 HTTP/1.1\r\n",
            b"POST https://localhost/v1/runs HTTP/1.1\r\n",
            b"POST /v1/runs HTTP/1.0\r\n",
            b"GET /v1/runs HTTP/1.1\r\n",
        ):
            with self.subTest(request_line=request_line):
                self.assertFalse(_is_exact_start_request_line(request_line))

        for command, path in (
            ("GET", "/v1/runs"),
            ("POST", "/v1/runs/"),
            ("POST", "/v1/runs?x=1"),
            ("POST", "https://localhost/v1/runs"),
        ):
            with self.subTest(command=command, path=path):
                self.assertTrue(_targets_start_boundary(command, path))
        self.assertFalse(_targets_start_boundary("GET", "/v1/runs/runtime-run-1"))

    def test_bearer_authorization_is_one_bounded_compact_jws(self) -> None:
        token = "abc.def.ghi"
        self.assertEqual(
            _parse_bearer_authorization(
                [f"Bearer {token}"], max_token_bytes=len(token)
            ),
            token,
        )
        for values, maximum in (
            ([], 100),
            ([f"Bearer {token}", f"Bearer {token}"], 100),
            ([f"bearer {token}"], 100),
            ([f"Bearer  {token}"], 100),
            (["Bearer abc.def"], 100),
            (["Bearer abc..ghi"], 100),
            (["Bearer abc.def.ghi="], 100),
            (["Bearer abc.def.ghi extra"], 100),
            ([f"Bearer {token}"], len(token) - 1),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                _parse_bearer_authorization(values, max_token_bytes=maximum)

    def test_exact_body_reader_rejects_short_read_before_core(self) -> None:
        handler = self.handler(b"a")
        with patch.object(handler, "_send_standard_error") as send_error:
            self.assertIsNone(handler._read_exact_body(2))
        self.assertTrue(handler.close_connection)
        self.assertEqual(send_error.call_args.args[0].value, 400)
        self.assertEqual(send_error.call_args.args[1], "HTTP_BODY_READ_REJECTED")

    def test_exact_body_reader_enforces_one_total_deadline(self) -> None:
        handler = self.handler(b"ab")
        with (
            patch.object(handler, "_send_standard_error") as send_error,
            patch(
                "agent_native_runtime.http_process.time.monotonic",
                side_effect=(10.0, 10.05, 10.25),
            ),
            patch("agent_native_runtime.http_process._BODY_READ_CHUNK_BYTES", 1),
        ):
            self.assertIsNone(handler._read_exact_body(2))
        self.assertEqual(send_error.call_args.args[0].value, 400)
        metrics = cast(Any, handler.server).process_state.metrics
        self.assertEqual(metrics.increments, ["read_timeouts"])

    def test_exact_body_reader_normalizes_socket_timeout(self) -> None:
        handler = self.handler()
        handler.rfile = TimeoutReader()
        with patch.object(handler, "_send_standard_error") as send_error:
            self.assertIsNone(handler._read_exact_body(1))
        self.assertEqual(send_error.call_args.args[1], "HTTP_BODY_READ_REJECTED")
        metrics = cast(Any, handler.server).process_state.metrics
        self.assertEqual(metrics.increments, ["read_timeouts"])

    def test_over_limit_start_rejects_before_body_reader_and_core(self) -> None:
        handler = self.handler()
        handler.path = "/v1/runs"
        handler._content_length = START_ENCODED_BODY_LIMIT + 1
        handler.headers = cast(Any, self.headers(("Content-Type", "application/json")))
        with (
            patch.object(handler, "_send_standard_error") as send_error,
            patch.object(
                handler,
                "_read_exact_body",
                side_effect=AssertionError("body reader must not be called"),
            ),
        ):
            handler.do_POST()
        self.assertTrue(handler.close_connection)
        self.assertEqual(send_error.call_args.args[0].value, 413)
        self.assertEqual(send_error.call_args.args[1], "START_BODY_TOO_LARGE")

    def test_common_framing_rejects_ambiguous_headers_before_core(self) -> None:
        cases = {
            "duplicate_host": self.headers(
                ("Host", "localhost"), ("Host", "localhost")
            ),
            "non_local_host": self.headers(("Host", "runtime.example")),
            "transfer_encoding": self.headers(
                ("Host", "localhost"),
                ("Transfer-Encoding", "chunked"),
                ("Content-Length", "1"),
            ),
            "expect": self.headers(
                ("Host", "localhost"),
                ("Expect", "something"),
                ("Content-Length", "1"),
            ),
            "duplicate_length": self.headers(
                ("Host", "localhost"),
                ("Content-Length", "1"),
                ("Content-Length", "1"),
            ),
        }
        for name, headers in cases.items():
            with self.subTest(name=name):
                handler = self.handler()
                handler.command = "POST"
                handler.path = "/v1/runs"
                handler.request_version = "HTTP/1.1"
                handler.headers = cast(Any, headers)
                with patch.object(handler, "_send_standard_error") as send_error:
                    self.assertFalse(handler._validate_host_and_framing())
                self.assertTrue(handler.close_connection)
                self.assertEqual(send_error.call_args.args[0].value, 400)

    def test_start_requires_exact_content_type_and_content_length(self) -> None:
        for name, content_type, content_length in (
            ("missing_type", None, "2"),
            ("parameterized_type", "application/json; charset=utf-8", "2"),
            ("missing_length", "application/json", None),
        ):
            with self.subTest(name=name):
                values = []
                if content_type is not None:
                    values.append(("Content-Type", content_type))
                handler = self.handler(b"{}")
                handler.path = "/v1/runs"
                handler._content_length = (
                    int(content_length) if content_length is not None else None
                )
                handler.headers = cast(Any, self.headers(*values))
                with (
                    patch.object(handler, "_send_standard_error") as send_error,
                    patch.object(
                        handler,
                        "_read_exact_body",
                        side_effect=AssertionError("body reader must not be called"),
                    ),
                ):
                    handler.do_POST()
                self.assertTrue(handler.close_connection)
                self.assertEqual(send_error.call_args.args[0].value, 400)

    def test_valid_start_transport_reads_exact_body_without_core(self) -> None:
        handler = self.handler(b"{}")
        handler.path = "/v1/runs"
        handler._content_length = 2
        handler.headers = cast(Any, self.headers(("Content-Type", "application/json")))
        with (
            patch.object(handler, "_route_not_enabled") as route_not_enabled,
            patch.object(handler, "_send_standard_error") as send_error,
        ):
            handler.do_POST()
        route_not_enabled.assert_not_called()
        self.assertEqual(send_error.call_args.args[0].value, 401)

    def test_start_calls_core_with_mtls_subject_and_validates_202(self) -> None:
        handler = self.handler(b"{}")
        handler.path = "/v1/runs"
        handler._content_length = 2
        token = "abc.def.ghi"
        handler.headers = cast(
            Any,
            self.headers(
                ("Content-Type", "application/json"),
                ("Authorization", f"Bearer {token}"),
            ),
        )
        handler.authenticated_caller = AuthenticatedCaller(
            certificate_uri="spiffe://agent.test/runtime-controller",
            token_subject="spn_agent_runtime_controller",
            certificate_fingerprint="sha256:" + "1" * 64,
            _comparison_subject=b"spn_agent_runtime_controller",
        )
        status = RuntimeStatus(
            runtime_run_id="runtime-run-1",
            tenant_id="tenant-1",
            conversation_id="conversation-1",
            work_order_id="work-order-1",
            workflow_run_id="workflow-run-1",
            agent_run_id="agent-run-1",
            status="accepted",
            last_command_sequence=0,
            last_event_sequence=1,
            observed_fencing_token=1,
            updated_at=datetime(2026, 7, 30, tzinfo=UTC),
        )
        core = Mock()
        core.start.return_value = status
        cast(Any, handler.server).core = core
        with patch.object(handler, "_send_json") as send_json:
            handler.do_POST()
        core.start.assert_called_once_with(
            b"{}",
            token,
            authenticated_caller="spn_agent_runtime_controller",
        )
        document = _runtime_status_document(status)
        core.projection.validate.assert_called_once_with(RUN_STATUS_SCHEMA_ID, document)
        self.assertEqual(send_json.call_args.args[0].value, 202)
        self.assertEqual(send_json.call_args.args[1], document)

    def test_runtime_status_mapping_excludes_provider_private_fields(self) -> None:
        status = RuntimeStatus(
            runtime_run_id="runtime-run-1",
            tenant_id="tenant-1",
            conversation_id="conversation-1",
            work_order_id="work-order-1",
            workflow_run_id="workflow-run-1",
            agent_run_id="agent-run-1",
            status="cancelled",
            last_command_sequence=1,
            last_event_sequence=2,
            observed_fencing_token=2,
            updated_at=datetime(2026, 7, 30, tzinfo=UTC),
            completed_at=datetime(2026, 7, 30, tzinfo=UTC),
            cancellation_evidence_reference="provider-private://evidence",
        )
        document = _runtime_status_document(status)
        self.assertNotIn("cancellation_evidence_reference", document)
        self.assertEqual(document["completed_at"], "2026-07-30T00:00:00.000000Z")

    def test_start_error_mapping_is_closed_and_safe(self) -> None:
        busy = sqlite3.OperationalError("secret database path is locked")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        locked = sqlite3.OperationalError("secret table is locked")
        locked.sqlite_errorcode = sqlite3.SQLITE_LOCKED
        cases: tuple[tuple[Exception, int, str, bool, int | None], ...] = (
            (
                StrictJsonError("secret body"),
                400,
                "RUNTIME_START_REJECTED",
                False,
                None,
            ),
            (
                ContractSchemaError("secret schema"),
                400,
                "RUNTIME_START_REJECTED",
                False,
                None,
            ),
            (
                DigestMismatchError("secret digest"),
                400,
                "RUNTIME_START_REJECTED",
                False,
                None,
            ),
            (
                InvalidMutationError("secret input"),
                400,
                "RUNTIME_START_REJECTED",
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
                MutationReplayError("secret jti"),
                409,
                "RUNTIME_START_CONFLICT",
                False,
                None,
            ),
            (
                IdempotencyConflictError("secret key"),
                409,
                "RUNTIME_START_CONFLICT",
                False,
                None,
            ),
            (
                RuntimeRunConflictError("secret run"),
                409,
                "RUNTIME_START_CONFLICT",
                False,
                None,
            ),
            (
                EncodedBodyTooLargeError("secret body"),
                413,
                "START_BODY_TOO_LARGE",
                False,
                None,
            ),
            (
                UnsupportedOperationError("secret sandbox"),
                422,
                "RUNTIME_START_UNSUPPORTED",
                False,
                None,
            ),
            (
                CheckpointCompatibilityError("secret checkpoint"),
                422,
                "RUNTIME_START_UNSUPPORTED",
                False,
                None,
            ),
            (busy, 503, "PROVIDER_TEMPORARILY_UNAVAILABLE", True, 1),
            (locked, 503, "PROVIDER_TEMPORARILY_UNAVAILABLE", True, 1),
            (
                sqlite3.OperationalError("secret corruption"),
                500,
                "INTERNAL_ERROR",
                False,
                None,
            ),
            (
                RuntimeError("secret traceback"),
                500,
                "INTERNAL_ERROR",
                False,
                None,
            ),
        )
        for error, status, code, retryable, retry_after in cases:
            with self.subTest(error=type(error).__name__, status=status):
                response = _start_error_response(error)
                self.assertIsInstance(response, _HTTPErrorResponse)
                self.assertEqual(response.status.value, status)
                self.assertEqual(response.code, code)
                self.assertEqual(response.retryable, retryable)
                self.assertEqual(response.retry_after, retry_after)
                self.assertNotIn("secret", response.message)

    def test_standard_error_uses_fresh_trace_id_and_closed_fields(self) -> None:
        first = _standard_error_document(
            "INTERNAL_ERROR",
            "Runtime Provider encountered an internal error.",
            retryable=False,
        )
        second = _standard_error_document(
            "INTERNAL_ERROR",
            "Runtime Provider encountered an internal error.",
            retryable=False,
        )
        self.assertNotEqual(first["trace_id"], second["trace_id"])
        self.assertEqual(set(first), {"code", "message", "retryable", "trace_id"})

    def test_standard_error_is_schema_validated_before_socket_write(self) -> None:
        handler = self.handler()
        core = Mock()
        cast(Any, handler.server).core = core
        with patch.object(handler, "_write_json_response") as write_response:
            handler._send_standard_error(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="INTERNAL_ERROR",
                message="Runtime Provider encountered an internal error.",
                retryable=False,
            )
        document = core.projection.validate.call_args.args[1]
        self.assertEqual(
            core.projection.validate.call_args.args[0],
            "urn:agent-platform:standard-error:v1",
        )
        encoded = write_response.call_args.args[1]
        self.assertEqual(json.loads(encoded), document)
        self.assertEqual(set(document), {"code", "message", "retryable", "trace_id"})

    def test_response_schema_failure_is_internal_not_bad_request(self) -> None:
        handler = self.handler(b"{}")
        handler.path = "/v1/runs"
        handler._content_length = 2
        token = "abc.def.ghi"
        handler.headers = cast(
            Any,
            self.headers(
                ("Content-Type", "application/json"),
                ("Authorization", f"Bearer {token}"),
            ),
        )
        handler.authenticated_caller = AuthenticatedCaller(
            certificate_uri="spiffe://agent.test/runtime-controller",
            token_subject="spn_agent_runtime_controller",
            certificate_fingerprint="sha256:" + "1" * 64,
            _comparison_subject=b"spn_agent_runtime_controller",
        )
        core = Mock()
        core.start.return_value = RuntimeStatus(
            runtime_run_id="runtime-run-1",
            tenant_id="tenant-1",
            conversation_id="conversation-1",
            work_order_id="work-order-1",
            workflow_run_id="workflow-run-1",
            agent_run_id="agent-run-1",
            status="accepted",
            last_command_sequence=0,
            last_event_sequence=1,
            observed_fencing_token=1,
            updated_at=datetime(2026, 7, 30, tzinfo=UTC),
        )
        core.projection.validate.side_effect = ContractSchemaError("secret response")
        cast(Any, handler.server).core = core
        with patch.object(handler, "_send_standard_error") as send_error:
            handler.do_POST()
        self.assertEqual(send_error.call_args.args[0].value, 500)
        self.assertEqual(send_error.call_args.args[1], "RESPONSE_VALIDATION_FAILED")


if INSTALLED_BIN is not None:

    class InstalledStartHTTPBoundaryTest(InstalledProcessTestCase):
        def setUp(self) -> None:
            super().setUp()
            configuration = load_process_configuration(self.config_path)
            self.projection = RuntimeContractProjection.load(configuration.security)
            self.zero_facts = {
                "consumed_mutation_jtis": 0,
                "runtime_runs": 0,
                "runtime_security_bindings": 0,
                "start_idempotency": 0,
                "runtime_events": 0,
                "execution_work": 0,
            }

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
            self.assertLessEqual(
                len(body), self.base["process"]["limits"]["max_response_bytes"]
            )
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

        def post_start(
            self,
            port: int,
            body: bytes,
            token: str | None,
            *,
            headers: dict[str, str] | None = None,
        ) -> tuple[int, dict[str, str], bytes]:
            request_headers = {"Content-Type": "application/json"}
            if token is not None:
                request_headers["Authorization"] = f"Bearer {token}"
            if headers:
                request_headers.update(headers)
            return self.request(
                port,
                self.pki.client,
                "/v1/runs",
                method="POST",
                body=body,
                headers=request_headers,
            )

        def fault_environment(self, name: str, source: str) -> dict[str, str]:
            fault_root = self.root / f"fault-{name}"
            fault_root.mkdir()
            (fault_root / "sitecustomize.py").write_text(source, encoding="utf-8")
            return {"PYTHONPATH": str(fault_root)}

        def test_valid_algorithms_replay_and_conflicts(self) -> None:
            for algorithm in ("EdDSA", "ES256"):
                with self.subTest(algorithm=algorithm):
                    value = deepcopy(self.base)
                    state_root = self.root / f"state-{algorithm.lower()}"
                    value["runtime"]["state_root"] = str(state_root)
                    path = self.write_configuration(
                        f"process-{algorithm.lower()}.json", value
                    )
                    self.migrate(path)
                    document = self.start_document()
                    body, token = self.start_request(
                        document,
                        jti=f"runtime-http-{algorithm.lower()}-jti-0001",
                        algorithm=algorithm,
                    )
                    with self.serving(path) as server:
                        accepted = self.post_start(server.port, body, token)
                        first = self.assert_json_document(
                            *accepted,
                            expected_status=202,
                            schema_id=RUN_STATUS_SCHEMA_ID,
                        )
                        self.assertEqual(first["status"], "accepted")

                        _, replay_token = self.start_request(
                            document,
                            jti=f"runtime-http-{algorithm.lower()}-jti-0002",
                            algorithm=algorithm,
                        )
                        replay = self.post_start(server.port, body, replay_token)
                        second = self.assert_json_document(
                            *replay,
                            expected_status=202,
                            schema_id=RUN_STATUS_SCHEMA_ID,
                        )
                        self.assertEqual(second, first)

                        reused = self.post_start(server.port, body, token)
                        self.assert_error(
                            reused,
                            status=409,
                            code="RUNTIME_START_CONFLICT",
                            secrets=(token,),
                        )

                        conflict = deepcopy(document)
                        conflict["branch_id"] = "conflicting-branch"
                        refresh_self_digest(conflict, "request_digest")
                        conflict_body, conflict_token = self.start_request(
                            conflict,
                            jti=f"runtime-http-{algorithm.lower()}-jti-0003",
                            algorithm=algorithm,
                        )
                        self.assert_error(
                            self.post_start(server.port, conflict_body, conflict_token),
                            status=409,
                            code="RUNTIME_START_CONFLICT",
                            secrets=(conflict_token,),
                        )

                    self.assertEqual(
                        self.database_counts(state_root),
                        {
                            "consumed_mutation_jtis": 2,
                            "runtime_runs": 1,
                            "runtime_security_bindings": 1,
                            "start_idempotency": 1,
                            "runtime_events": 1,
                            "execution_work": 1,
                        },
                    )

        def test_token_binding_failures_are_401_and_precommit(self) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            document = self.start_document()
            body = self.encode(document)
            with self.serving(self.config_path) as server:
                _, valid_token = self.start_request(
                    document, jti="runtime-http-mtls-jti-0001"
                )
                self.assert_error(
                    self.request(
                        server.port,
                        self.pki.unmapped,
                        "/v1/runs",
                        method="POST",
                        body=body,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {valid_token}",
                        },
                    ),
                    status=403,
                    code="WORKLOAD_IDENTITY_REJECTED",
                    secrets=(valid_token,),
                )
                self.assert_error(
                    self.post_start(server.port, body, None),
                    status=401,
                    code="RUNTIME_TOKEN_REJECTED",
                )
                malformed = "sensitiveMalformed.token.value"
                self.assert_error(
                    self.post_start(server.port, body, malformed),
                    status=401,
                    code="RUNTIME_TOKEN_REJECTED",
                    secrets=(malformed,),
                )
                duplicate = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                duplicate_token = "sensitive.duplicate.token"
                duplicate.request(
                    "POST",
                    "/v1/runs",
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + f"Authorization: Bearer {duplicate_token}\r\n".encode("ascii")
                        + f"Authorization: Bearer {duplicate_token}\r\n".encode("ascii")
                        + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    ),
                    body=body,
                )
                try:
                    self.assert_error(
                        duplicate.response(),
                        status=401,
                        code="RUNTIME_TOKEN_REJECTED",
                        secrets=(duplicate_token,),
                    )
                finally:
                    duplicate.connection.close()

                replacements: tuple[tuple[str, str, object], ...] = (
                    ("subject", "sub", "spn_other_runtime_controller"),
                    (
                        "audience",
                        "aud",
                        "urn:agent-platform:provider-instance:replacement",
                    ),
                    ("operation", "operation", "read_status"),
                    (
                        "request_digest",
                        "operation_request_digest",
                        "sha256:" + "0" * 64,
                    ),
                    ("issuer", "iss", "replacement-issuer"),
                    ("expired", "exp", int(time.time()) - 60),
                )
                for index, (name, field, replacement) in enumerate(replacements):
                    with self.subTest(name=name):
                        claims = self.start_claims(
                            document, f"runtime-http-auth-jti-{index:04d}"
                        )
                        claims[field] = replacement
                        token = self.sign_start(claims)
                        self.assert_error(
                            self.post_start(server.port, body, token),
                            status=401,
                            code="RUNTIME_TOKEN_REJECTED",
                            secrets=(token,),
                        )
                        self.assertEqual(
                            self.database_counts(state_root), self.zero_facts
                        )

        def test_request_schema_authorization_and_unsupported_fail_precommit(
            self,
        ) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            document = self.start_document()
            _, token = self.start_request(document, jti="runtime-http-input-jti-0001")
            sensitive_body = b'{"sensitive-body-marker":'
            with self.serving(self.config_path) as server:
                self.assert_error(
                    self.post_start(server.port, sensitive_body, token),
                    status=400,
                    code="RUNTIME_START_REJECTED",
                    secrets=("sensitive-body-marker", token),
                )

                empty_body = b"{}"
                self.assert_error(
                    self.post_start(server.port, empty_body, token),
                    status=400,
                    code="RUNTIME_START_REJECTED",
                    secrets=(token,),
                )

                digest_mismatch = deepcopy(document)
                digest_mismatch["branch_id"] = "replacement-branch"
                self.assert_error(
                    self.post_start(server.port, self.encode(digest_mismatch), token),
                    status=400,
                    code="RUNTIME_START_REJECTED",
                    secrets=(token,),
                )

                unauthorized = deepcopy(document)
                authorization = cast(
                    dict[str, Any], unauthorized["runtime_authorization"]
                )
                authorization["tenant_id"] = "ten_replacement"
                refresh_self_digest(authorization, "authorization_digest")
                refresh_self_digest(unauthorized, "request_digest")
                unauthorized_body, unauthorized_token = self.start_request(
                    unauthorized, jti="runtime-http-forbidden-jti-0001"
                )
                self.assert_error(
                    self.post_start(server.port, unauthorized_body, unauthorized_token),
                    status=403,
                    code="RUNTIME_AUTHORIZATION_REJECTED",
                    secrets=(unauthorized_token,),
                )

                sandbox = self.start_document("agent-runtime-start-request.json")
                sandbox_body, sandbox_token = self.start_request(
                    sandbox, jti="runtime-http-sandbox-jti-0001"
                )
                self.assert_error(
                    self.post_start(server.port, sandbox_body, sandbox_token),
                    status=422,
                    code="RUNTIME_START_UNSUPPORTED",
                    secrets=(sandbox_token,),
                )

                checkpoint = deepcopy(document)
                checkpoint["checkpoint"] = json.loads(
                    (
                        CONTRACT_ROOT
                        / "examples/contracts/agent-runtime-checkpoint-manifest.json"
                    ).read_text(encoding="utf-8")
                )
                refresh_self_digest(checkpoint, "request_digest")
                checkpoint_body, checkpoint_token = self.start_request(
                    checkpoint, jti="runtime-http-checkpoint-jti-0001"
                )
                self.assert_error(
                    self.post_start(server.port, checkpoint_body, checkpoint_token),
                    status=422,
                    code="RUNTIME_START_UNSUPPORTED",
                    secrets=(checkpoint_token,),
                )

                self.assertEqual(self.database_counts(state_root), self.zero_facts)

        def test_request_target_host_content_type_and_framing_are_strict(
            self,
        ) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            requests = (
                b"GET /v1/runs HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs/ HTTP/1.1\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs?x=1 HTTP/1.1\r\nHost: localhost\r\n\r\n",
                (b"POST https://localhost/v1/runs HTTP/1.1\r\nHost: localhost\r\n\r\n"),
                b"POST /v1/runs HTTP/1.0\r\nHost: localhost\r\n\r\n",
                b"POST /v1/runs HTTP/1.1\nHost: localhost\r\n\r\n",
                b"POST /v1/runs HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Host: localhost\r\nContent-Length: 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: runtime.example\r\n"
                    b"Content-Length: 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Length: 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: text/plain\r\nContent-Length: 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 0\r\n"
                    b"Content-Length: 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 00\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Content-Type: application/json\r\nContent-Length: 0, 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Transfer-Encoding: identity\r\nContent-Length: 0\r\n\r\n"
                ),
                (
                    b"POST /v1/runs HTTP/1.1\r\nHost: localhost\r\n"
                    b"Expect: 100-continue\r\nContent-Length: 0\r\n\r\n"
                ),
            )
            with self.serving(self.config_path) as server:
                for index, request in enumerate(requests):
                    with self.subTest(index=index):
                        raw = RawHTTPConnection(
                            self.tls_socket(server.port, self.pki.client)
                        )
                        try:
                            raw.connection.sendall(request)
                            self.assert_error(
                                raw.response(),
                                status=400,
                                code=(
                                    "HTTP_CONTENT_TYPE_REJECTED"
                                    if index in {9, 10, 11}
                                    else "HTTP_FRAMING_REJECTED"
                                    if index >= 12
                                    else "HTTP_HOST_REJECTED"
                                    if index in {6, 7, 8}
                                    else "HTTP_VERSION_REJECTED"
                                    if index == 4
                                    else "HTTP_START_TARGET_REJECTED"
                                ),
                            )
                        finally:
                            raw.connection.close()
                        self.assertEqual(
                            self.database_counts(state_root), self.zero_facts
                        )

                status_response = self.request(
                    server.port,
                    self.pki.client,
                    "/v1/runs/runtime-run-not-enabled",
                )
                self.assert_error(
                    status_response,
                    status=401,
                    code="RUNTIME_TOKEN_REJECTED",
                )
                command_response = self.request(
                    server.port,
                    self.pki.client,
                    "/v1/runs/runtime-run-not-enabled/commands",
                    method="POST",
                    body=b"",
                )
                self.assert_error(
                    command_response,
                    status=400,
                    code="HTTP_CONTENT_TYPE_REJECTED",
                )

        def test_body_limit_short_read_and_total_deadline_are_precommit(self) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            document = self.start_document()
            body, token = self.start_request(document, jti="runtime-http-body-jti-0001")
            authorization = f"Authorization: Bearer {token}\r\n".encode("ascii")
            with self.serving(self.config_path) as server:
                over_limit = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                over_limit.request(
                    "POST",
                    "/v1/runs",
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + authorization
                        + b"Content-Length: 8388609\r\n"
                    ),
                )
                self.assert_error(
                    over_limit.response(),
                    status=413,
                    code="START_BODY_TOO_LARGE",
                    secrets=(token,),
                )
                over_limit.connection.close()

                self.assert_error(
                    self.post_start(server.port, b"", token),
                    status=400,
                    code="RUNTIME_START_REJECTED",
                    secrets=(token,),
                )

                short = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
                short.request(
                    "POST",
                    "/v1/runs",
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
                    "/v1/runs",
                    headers=(
                        b"Content-Type: application/json\r\n"
                        + authorization
                        + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    ),
                    body=body[:1],
                )
                time.sleep(0.3)
                self.assert_error(
                    slow.response(),
                    status=400,
                    code="HTTP_BODY_READ_REJECTED",
                    secrets=(token,),
                )
                slow.connection.close()
                self.assertEqual(self.database_counts(state_root), self.zero_facts)

            boundary = deepcopy(self.base)
            boundary_state = self.root / "state-body-boundary"
            boundary["runtime"]["state_root"] = str(boundary_state)
            boundary["process"]["limits"]["read_timeout_ms"] = 5_000
            boundary_path = self.write_configuration("body-boundary.json", boundary)
            self.migrate(boundary_path)
            boundary_document = self.start_document()
            encoded, boundary_token = self.start_request(
                boundary_document, jti="runtime-http-body-jti-0002"
            )
            exact_body = encoded + b" " * (START_ENCODED_BODY_LIMIT - len(encoded))
            self.assertEqual(len(exact_body), START_ENCODED_BODY_LIMIT)
            with self.serving(boundary_path) as server:
                accepted = self.post_start(server.port, exact_body, boundary_token)
                self.assert_json_document(
                    *accepted,
                    expected_status=202,
                    schema_id=RUN_STATUS_SCHEMA_ID,
                )
            self.assertEqual(self.database_counts(boundary_state)["runtime_runs"], 1)

        def test_committed_run_status_response_respects_byte_limit(self) -> None:
            limited = deepcopy(self.base)
            state_root = self.root / "state-start-response-limit"
            limited["runtime"]["state_root"] = str(state_root)
            limited["process"]["limits"]["max_response_bytes"] = 1_024
            limited_path = self.write_configuration(
                "start-response-limit.json", limited
            )
            self.migrate(limited_path)

            document = self.start_document()
            replacements = {
                cast(str, document[field]): character * 200
                for field, character in (
                    ("runtime_run_id", "r"),
                    ("tenant_id", "t"),
                    ("conversation_id", "c"),
                    ("work_order_id", "w"),
                    ("workflow_run_id", "f"),
                    ("agent_run_id", "a"),
                )
            }
            encoded = json.dumps(document, separators=(",", ":"))
            for original, replacement in replacements.items():
                encoded = encoded.replace(original, replacement)
            long_document = cast(dict[str, Any], json.loads(encoded))
            self.refresh_start_digests(long_document)
            body, token = self.start_request(
                long_document, jti="runtime-http-response-limit-jti-0001"
            )
            with self.serving(limited_path) as server:
                self.assert_error(
                    self.post_start(server.port, body, token),
                    status=500,
                    code="RESPONSE_LIMIT_EXCEEDED",
                    secrets=(token,),
                )
            self.assertEqual(
                self.database_counts(state_root),
                {
                    "consumed_mutation_jtis": 1,
                    "runtime_runs": 1,
                    "runtime_security_bindings": 1,
                    "start_idempotency": 1,
                    "runtime_events": 1,
                    "execution_work": 1,
                },
            )

        def test_concurrency_and_sqlite_lock_use_retryable_closed_mappings(
            self,
        ) -> None:
            concurrent = deepcopy(self.base)
            concurrent_state = self.root / "state-start-concurrency"
            concurrent["runtime"]["state_root"] = str(concurrent_state)
            concurrent["process"]["limits"]["max_connections"] = 2
            concurrent["process"]["limits"]["max_concurrent_requests"] = 1
            concurrent["process"]["limits"]["read_timeout_ms"] = 2_000
            concurrent_path = self.write_configuration(
                "start-concurrency.json", concurrent
            )
            self.migrate(concurrent_path)
            document = self.start_document()
            body, token = self.start_request(
                document, jti="runtime-http-concurrency-jti-0001"
            )
            authorization = f"Authorization: Bearer {token}\r\n".encode("ascii")
            with self.serving(concurrent_path) as server:
                held = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
                held.request(
                    "POST",
                    "/v1/runs",
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
                    "/v1/runs",
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
                    code="PROVIDER_START_CONCURRENCY_LIMIT",
                    retry_after=1,
                    secrets=(token,),
                )
                held.connection.close()
                rejected.connection.close()
            self.assertEqual(self.database_counts(concurrent_state), self.zero_facts)

            locked = deepcopy(self.base)
            locked_state = self.root / "state-sqlite-locked"
            locked["runtime"]["state_root"] = str(locked_state)
            locked["runtime"]["sqlite_busy_timeout_ms"] = 100
            locked_path = self.write_configuration("sqlite-locked.json", locked)
            self.migrate(locked_path)
            lock_connection = sqlite3.connect(locked_state / "runtime.sqlite3")
            lock_connection.execute("BEGIN IMMEDIATE")
            lock_document = self.start_document()
            lock_body, lock_token = self.start_request(
                lock_document, jti="runtime-http-sqlite-jti-0001"
            )
            try:
                with self.serving(locked_path) as server:
                    self.assert_error(
                        self.post_start(server.port, lock_body, lock_token),
                        status=503,
                        code="PROVIDER_TEMPORARILY_UNAVAILABLE",
                        retry_after=1,
                        secrets=(lock_token,),
                    )
            finally:
                lock_connection.rollback()
                lock_connection.close()
            self.assertEqual(self.database_counts(locked_state), self.zero_facts)

        def test_draining_start_is_retryable_503_without_facts(self) -> None:
            draining = deepcopy(self.base)
            state_root = self.root / "state-start-draining"
            draining["runtime"]["state_root"] = str(state_root)
            draining["process"]["limits"]["idle_timeout_ms"] = 2_000
            draining["process"]["limits"]["read_timeout_ms"] = 2_000
            draining_path = self.write_configuration("start-draining.json", draining)
            self.migrate(draining_path)
            document = self.start_document()
            body, token = self.start_request(
                document, jti="runtime-http-draining-jti-0001"
            )
            server = self.start_server(draining_path)
            keepalive = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
            keepalive.request("GET", "/health/live")
            self.assertEqual(keepalive.response()[0], 200)
            server.process.send_signal(signal.SIGTERM)
            time.sleep(0.05)
            keepalive.request(
                "POST",
                "/v1/runs",
                headers=(
                    b"Content-Type: application/json\r\n"
                    + f"Authorization: Bearer {token}\r\n".encode("ascii")
                    + f"Content-Length: {len(body)}\r\n".encode("ascii")
                ),
                body=body,
            )
            self.assert_error(
                keepalive.response(),
                status=503,
                code="PROVIDER_NOT_READY",
                retry_after=1,
                secrets=(token,),
            )
            keepalive.connection.close()
            stdout, stderr = server.process.communicate(timeout=3)
            self.assertEqual(server.process.returncode, 0, stderr)
            self.assertIn('"event":"listener_stopped"', stdout)
            self.assertEqual(self.database_counts(state_root), self.zero_facts)

        def test_controlled_post_validation_precommit_failure_has_zero_facts(
            self,
        ) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            document = self.start_document()
            body, token = self.start_request(
                document, jti="runtime-http-controlled-failure-jti-0001"
            )
            environment = self.fault_environment(
                "precommit",
                """from agent_native_runtime.kernel import NativeRuntimeKernel

def controlled_failure(self, mutation, admission, security_binding):
    raise RuntimeError("sensitive-controlled-precommit-marker")

NativeRuntimeKernel.start = controlled_failure
""",
            )
            with self.serving(self.config_path, environment=environment) as server:
                self.assert_error(
                    self.post_start(server.port, body, token),
                    status=500,
                    code="INTERNAL_ERROR",
                    secrets=(token, "sensitive-controlled-precommit-marker"),
                )
            self.assertEqual(self.database_counts(state_root), self.zero_facts)

        def test_postcommit_response_loss_retries_same_runtime_run(self) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            document = self.start_document()
            body, first_token = self.start_request(
                document, jti="runtime-http-response-loss-jti-0001"
            )
            environment = self.fault_environment(
                "response-loss",
                """import socket
from http import HTTPStatus
from agent_native_runtime.http_process import ProviderRequestHandler

original_send_json = ProviderRequestHandler._send_json

def drop_accepted_response(self, status, document, *, retry_after=None):
    if status == HTTPStatus.ACCEPTED:
        self.close_connection = True
        self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()
        return
    original_send_json(self, status, document, retry_after=retry_after)

ProviderRequestHandler._send_json = drop_accepted_response
""",
            )
            with (
                self.serving(self.config_path, environment=environment) as server,
                self.assertRaises(
                    (http.client.RemoteDisconnected, ConnectionError, OSError)
                ),
            ):
                self.post_start(server.port, body, first_token)

            first_counts = self.database_counts(state_root)
            self.assertEqual(
                first_counts,
                {
                    "consumed_mutation_jtis": 1,
                    "runtime_runs": 1,
                    "runtime_security_bindings": 1,
                    "start_idempotency": 1,
                    "runtime_events": 1,
                    "execution_work": 1,
                },
            )
            connection = sqlite3.connect(state_root / "runtime.sqlite3")
            try:
                durable = connection.execute(
                    "SELECT runtime_run_id, status FROM runtime_runs"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(durable, (document["runtime_run_id"], "accepted"))

            _, retry_token = self.start_request(
                document, jti="runtime-http-response-loss-jti-0002"
            )
            with self.serving(self.config_path) as server:
                response = self.post_start(server.port, body, retry_token)
                replay = self.assert_json_document(
                    *response,
                    expected_status=202,
                    schema_id=RUN_STATUS_SCHEMA_ID,
                )
            self.assertEqual(replay["runtime_run_id"], durable[0])
            self.assertEqual(replay["status"], durable[1])
            self.assertEqual(
                self.database_counts(state_root),
                {
                    "consumed_mutation_jtis": 2,
                    "runtime_runs": 1,
                    "runtime_security_bindings": 1,
                    "start_idempotency": 1,
                    "runtime_events": 1,
                    "execution_work": 1,
                },
            )


if __name__ == "__main__":
    unittest.main()
