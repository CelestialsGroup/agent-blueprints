from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cryptography.hazmat.primitives.asymmetric import ed25519
from process_test_support import INSTALLED_BIN, InstalledProcessTestCase

from agent_native_runtime.admission import SecureAdmissionCore
from agent_native_runtime.errors import (
    AuthorizationBindingError,
    CursorExpiredError,
    RuntimeRunNotFoundError,
    StaleFencingError,
    TokenValidationError,
)
from agent_native_runtime.http_process import (
    _event_page_document,
    _parse_exact_read_request_line,
    _read_error_response,
    _ReadRequestTarget,
)
from agent_native_runtime.model import (
    EventPage,
    RunStartedEventData,
    RuntimeEvent,
)
from agent_native_runtime.process_config import load_process_configuration
from agent_native_runtime.security import RuntimeContractProjection


class ReadTransportAdmissionTest(unittest.TestCase):
    def test_exact_status_and_event_targets_apply_openapi_defaults(self) -> None:
        self.assertEqual(
            _parse_exact_read_request_line(b"GET /v1/runs/runtime-run-1 HTTP/1.1\r\n"),
            _ReadRequestTarget("read_status", "runtime-run-1"),
        )
        self.assertEqual(
            _parse_exact_read_request_line(
                b"GET /v1/runs/runtime-run-1/events HTTP/1.1\r\n"
            ),
            _ReadRequestTarget(
                "read_events",
                "runtime-run-1",
                after_event_sequence=0,
                limit=1000,
            ),
        )
        for query in (
            b"after_event_sequence=7&limit=25",
            b"limit=25&after_event_sequence=7",
        ):
            with self.subTest(query=query):
                self.assertEqual(
                    _parse_exact_read_request_line(
                        b"GET /v1/runs/runtime-run-1/events?" + query + b" HTTP/1.1\r\n"
                    ),
                    _ReadRequestTarget(
                        "read_events",
                        "runtime-run-1",
                        after_event_sequence=7,
                        limit=25,
                    ),
                )
        self.assertEqual(
            _parse_exact_read_request_line(
                b"GET /v1/runs/runtime-run-1/events?limit=1 HTTP/1.1\r\n"
            ),
            _ReadRequestTarget(
                "read_events",
                "runtime-run-1",
                after_event_sequence=0,
                limit=1,
            ),
        )

    def test_malformed_read_targets_remain_outside_the_admitted_handler(self) -> None:
        for request_line in (
            b"GET /v1/runs/ HTTP/1.1\r\n",
            b"GET /v1/runs/a/ HTTP/1.1\r\n",
            b"GET /v1/runs/a%2Fb HTTP/1.1\r\n",
            b"GET /v1/runs/a\\b HTTP/1.1\r\n",
            b"GET /v1/runs/a?limit=1 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events/ HTTP/1.1\r\n",
            b"GET /v1/runs/a/events? HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?limit=0 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?limit=1001 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?limit=01 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?limit=1&limit=2 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?after_event_sequence=-1 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?after_event_sequence=9007199254740992 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?unknown=1 HTTP/1.1\r\n",
            b"GET /v1/runs/a/events?limit=1#fragment HTTP/1.1\r\n",
            b"GET /v1/runs/" + (b"a" * 201) + b" HTTP/1.1\r\n",
            b"GET /v1/runs/" + (b"a" * 201) + b"/events HTTP/1.1\r\n",
            b"GET https://localhost/v1/runs/a/events HTTP/1.1\r\n",
            b"GET /v1/runs/a/events HTTP/1.0\r\n",
            b"POST /v1/runs/a/events HTTP/1.1\r\n",
        ):
            with self.subTest(request_line=request_line):
                self.assertIsNone(_parse_exact_read_request_line(request_line))

    def test_read_error_mapping_uses_only_declared_statuses_and_safe_details(
        self,
    ) -> None:
        busy = sqlite3.OperationalError("secret database path is locked")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        cursor = CursorExpiredError(
            work_order_id="work-order-1",
            requested_after=0,
            earliest_available=2,
            latest_available=4,
        )
        cases: tuple[tuple[Exception, int, str, bool, int | None], ...] = (
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
                StaleFencingError("secret fencing"),
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
            (cursor, 410, "EVENT_CURSOR_EXPIRED", False, None),
            (busy, 503, "PROVIDER_TEMPORARILY_UNAVAILABLE", True, 1),
            (RuntimeError("secret traceback"), 500, "INTERNAL_ERROR", False, None),
        )
        for error, status, code, retryable, retry_after in cases:
            with self.subTest(error=type(error).__name__):
                response = _read_error_response(error)
                self.assertEqual(response.status.value, status)
                self.assertEqual(response.code, code)
                self.assertEqual(response.retryable, retryable)
                self.assertEqual(response.retry_after, retry_after)
                self.assertNotIn("secret", response.message)
        response = _read_error_response(cursor)
        self.assertEqual(
            response.details,
            {
                "work_order_id": "work-order-1",
                "requested_after_event_sequence": 0,
                "earliest_available_event_sequence": 2,
                "latest_available_event_sequence": 4,
                "recovery": (
                    "latest_compatible_checkpoint_or_platform_canonical_event_history"
                ),
            },
        )

    def test_event_page_document_preserves_order_and_next_cursor(self) -> None:
        occurred_at = datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
        event = RuntimeEvent(
            event_id="event-1",
            runtime_run_id="runtime-run-1",
            event_sequence=1,
            type="runtime.run.started",
            occurred_at=occurred_at,
            data_version=1,
            data=RunStartedEventData(
                agent_run_id="agent-run-1",
                run_manifest_digest="sha256:" + "1" * 64,
                provider_revision_id="provider-revision-1",
            ),
            source_cursor="native-event-1",
        )
        self.assertEqual(
            _event_page_document(EventPage(events=(event,), next_event_sequence=1)),
            {
                "events": [
                    {
                        "event_id": "event-1",
                        "runtime_run_id": "runtime-run-1",
                        "event_sequence": 1,
                        "type": "runtime.run.started",
                        "occurred_at": "2026-07-30T08:00:00.000000Z",
                        "data_version": 1,
                        "data": {
                            "agent_run_id": "agent-run-1",
                            "run_manifest_digest": "sha256:" + "1" * 64,
                            "provider_revision_id": "provider-revision-1",
                        },
                        "source_cursor": "native-event-1",
                    }
                ],
                "next_event_sequence": 1,
            },
        )


class _ReadBoundaryExecutor:
    def start(self, runtime_run_id: str, restored_state: bytes | None) -> None:
        del runtime_run_id, restored_state

    def cancel(self, runtime_run_id: str) -> str:
        return "test-cancellation-evidence:" + runtime_run_id

    def checkpoint(self, runtime_run_id: str) -> bytes:
        return ("read-boundary-state:" + runtime_run_id).encode()


if INSTALLED_BIN is not None:

    class InstalledReadHTTPBoundaryTest(InstalledProcessTestCase):
        def setUp(self) -> None:
            super().setUp()
            self.process_configuration = load_process_configuration(self.config_path)
            self.projection = RuntimeContractProjection.load(
                self.process_configuration.security
            )

        def assert_json_document(
            self,
            response: tuple[int, dict[str, str], bytes],
            *,
            expected_status: int,
            schema_id: str,
        ) -> dict[str, Any]:
            status, headers, body = response
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
            expected_status: int,
            code: str,
            secrets: tuple[str, ...] = (),
        ) -> dict[str, Any]:
            document = self.assert_json_document(
                response,
                expected_status=expected_status,
                schema_id="urn:agent-platform:standard-error:v1",
            )
            self.assertEqual(document["code"], code)
            encoded = response[2].decode("ascii")
            for secret in secrets:
                self.assertNotIn(secret, encoded)
            return document

        def admit_start(self, port: int, *, jti: str) -> dict[str, Any]:
            document = self.start_document()
            body, token = self.start_request(document, jti=jti)
            status = self.assert_json_document(
                self.request(
                    port,
                    self.pki.client,
                    "/v1/runs",
                    method="POST",
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                ),
                expected_status=202,
                schema_id="urn:agent-platform:agent-runtime-run-status:v1",
            )
            self.assertEqual(status["runtime_run_id"], document["runtime_run_id"])
            return document

        def test_valid_status_and_default_events_are_read_only(self) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            with self.serving(self.config_path) as server:
                start = self.admit_start(server.port, jti="runtime-read-start-jti-0001")
                baseline = self.state_snapshot(state_root)
                runtime_run_id = cast(str, start["runtime_run_id"])

                status_token = self.read_token(
                    start,
                    operation="read_status",
                    jti="runtime-read-status-jti-0001",
                )
                status = self.assert_json_document(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}",
                        status_token,
                    ),
                    expected_status=200,
                    schema_id="urn:agent-platform:agent-runtime-run-status:v1",
                )
                self.assertEqual(status["runtime_run_id"], runtime_run_id)
                self.assertEqual(status["status"], "accepted")
                repeated_status = self.assert_json_document(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}",
                        status_token,
                    ),
                    expected_status=200,
                    schema_id="urn:agent-platform:agent-runtime-run-status:v1",
                )
                self.assertEqual(repeated_status, status)

                default_token = self.read_token(
                    start,
                    operation="read_events",
                    jti="runtime-read-events-jti-0001",
                    algorithm="ES256",
                )
                default_page = self.assert_json_document(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}/events",
                        default_token,
                    ),
                    expected_status=200,
                    schema_id="urn:agent-platform:agent-runtime-event-page:v1",
                )
                repeated_default_page = self.assert_json_document(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}/events",
                        default_token,
                    ),
                    expected_status=200,
                    schema_id="urn:agent-platform:agent-runtime-event-page:v1",
                )
                self.assertEqual(repeated_default_page, default_page)
                explicit_token = self.read_token(
                    start,
                    operation="read_events",
                    jti="runtime-read-events-jti-0002",
                )
                explicit_page = self.assert_json_document(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}/events?limit=1000&after_event_sequence=0",
                        explicit_token,
                    ),
                    expected_status=200,
                    schema_id="urn:agent-platform:agent-runtime-event-page:v1",
                )
                self.assertEqual(default_page, explicit_page)
                self.assertEqual(
                    [event["event_sequence"] for event in default_page["events"]],
                    [1],
                )
                self.assertEqual(default_page["next_event_sequence"], 1)
                self.assertEqual(self.state_snapshot(state_root), baseline)
            print("read-boundary-case:status_default_events_read_only:passed")

        def test_cursor_resume_empty_page_and_expiry_are_explicit(self) -> None:
            self.migrate(self.config_path)
            with self.serving(self.config_path) as server:
                start = self.admit_start(
                    server.port, jti="runtime-read-cursor-start-jti-0001"
                )
            core = SecureAdmissionCore.open_current(
                self.process_configuration.runtime,
                self.process_configuration.security,
            )
            executor = _ReadBoundaryExecutor()
            self.assertTrue(
                core.kernel.process_one(executor, owner="read-worker-start")
            )
            with self.serving(self.config_path) as server:
                command = self.command_document(
                    start,
                    command_type="checkpoint",
                    command_sequence=1,
                    fencing_token=2,
                )
                body, token = self.command_request(
                    start, command, jti="runtime-read-checkpoint-jti-0001"
                )
                self.assert_json_document(
                    self.post_command(
                        server.port,
                        cast(str, start["runtime_run_id"]),
                        body,
                        token,
                    ),
                    expected_status=202,
                    schema_id="urn:agent-platform:agent-runtime-run-status:v1",
                )
            self.assertTrue(
                core.kernel.process_one(executor, owner="read-worker-checkpoint")
            )
            runtime_run_id = cast(str, start["runtime_run_id"])
            self.assertEqual(
                core.kernel.prune_events(runtime_run_id, through_sequence=1), 1
            )

            with self.serving(self.config_path) as server:
                resume_token = self.read_token(
                    start,
                    operation="read_events",
                    jti="runtime-read-resume-jti-0001",
                    fencing_token=2,
                    after_event_sequence=1,
                    limit=1,
                )
                resumed = self.assert_json_document(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}/events?after_event_sequence=1&limit=1",
                        resume_token,
                    ),
                    expected_status=200,
                    schema_id="urn:agent-platform:agent-runtime-event-page:v1",
                )
                self.assertEqual(
                    [event["event_sequence"] for event in resumed["events"]], [2]
                )
                self.assertEqual(resumed["next_event_sequence"], 2)

                empty_token = self.read_token(
                    start,
                    operation="read_events",
                    jti="runtime-read-empty-jti-0001",
                    fencing_token=2,
                    after_event_sequence=2,
                    limit=1,
                )
                empty = self.assert_json_document(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}/events?limit=1&after_event_sequence=2",
                        empty_token,
                    ),
                    expected_status=200,
                    schema_id="urn:agent-platform:agent-runtime-event-page:v1",
                )
                self.assertEqual(empty, {"events": [], "next_event_sequence": 2})

                expired_token = self.read_token(
                    start,
                    operation="read_events",
                    jti="runtime-read-expired-jti-0001",
                    fencing_token=2,
                    after_event_sequence=0,
                    limit=1,
                )
                expired = self.assert_error(
                    self.get_read(
                        server.port,
                        f"/v1/runs/{runtime_run_id}/events?after_event_sequence=0&limit=1",
                        expired_token,
                    ),
                    expected_status=410,
                    code="EVENT_CURSOR_EXPIRED",
                    secrets=(expired_token,),
                )
                details = cast(dict[str, Any], expired["details"])
                self.assertEqual(details["earliest_available_event_sequence"], 2)
                self.assertEqual(details["latest_available_event_sequence"], 2)
            print("read-boundary-case:cursor_resume_empty_expiry:passed")

        def test_crypto_oracle_binding_and_admitted_not_found(self) -> None:
            self.migrate(self.config_path)
            state_root = Path(self.base["runtime"]["state_root"])
            with self.serving(self.config_path) as server:
                start = self.admit_start(
                    server.port, jti="runtime-read-oracle-start-jti-0001"
                )
                baseline = self.state_snapshot(state_root)
                runtime_run_id = cast(str, start["runtime_run_id"])
                wrong_key = ed25519.Ed25519PrivateKey.generate()
                outcomes: list[tuple[int, str]] = []
                for index, target in enumerate(
                    (runtime_run_id, "runtime-run-does-not-exist"), start=1
                ):
                    token = self.read_token(
                        start,
                        operation="read_status",
                        jti=f"runtime-read-oracle-jti-{index:04d}",
                        runtime_run_id=target,
                        private_key=wrong_key,
                    )
                    response = self.get_read(server.port, f"/v1/runs/{target}", token)
                    error = self.assert_error(
                        response,
                        expected_status=401,
                        code="RUNTIME_TOKEN_REJECTED",
                        secrets=(token,),
                    )
                    outcomes.append((response[0], cast(str, error["code"])))
                    self.assertEqual(self.state_snapshot(state_root), baseline)
                self.assertEqual(outcomes[0], outcomes[1])

                path_token = self.read_token(
                    start,
                    operation="read_status",
                    jti="runtime-read-path-jti-0001",
                )
                self.assert_error(
                    self.get_read(
                        server.port,
                        "/v1/runs/runtime-run-path-replacement",
                        path_token,
                    ),
                    expected_status=403,
                    code="RUNTIME_AUTHORIZATION_REJECTED",
                    secrets=(path_token,),
                )

                missing = "runtime-run-cryptographically-admitted"
                missing_token = self.read_token(
                    start,
                    operation="read_status",
                    jti="runtime-read-missing-jti-0001",
                    runtime_run_id=missing,
                )
                self.assert_error(
                    self.get_read(server.port, f"/v1/runs/{missing}", missing_token),
                    expected_status=404,
                    code="RUNTIME_RUN_NOT_FOUND",
                    secrets=(missing_token,),
                )
                self.assertEqual(self.state_snapshot(state_root), baseline)
            print("read-boundary-case:crypto_oracle_binding_not_found:passed")


if __name__ == "__main__":
    unittest.main()
