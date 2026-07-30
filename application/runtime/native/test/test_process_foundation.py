from __future__ import annotations

import hashlib
import json
import signal
import socket
import sqlite3
import ssl
import stat
import time
import unittest
import warnings
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from process_test_support import (
    APPLICATION_ROOT,
    CALLER_SUBJECT,
    INSTALLED_BIN,
    InstalledProcessTestCase,
    RawHTTPConnection,
)

from agent_native_runtime.process_config import load_process_configuration
from agent_native_runtime.tls import (
    PeerIdentityNotAllowedError,
    authenticate_peer_certificate,
)

if INSTALLED_BIN is None:

    class ProcessFoundationSourceBoundaryTest(unittest.TestCase):
        def test_installed_cli_entrypoints_are_declared(self) -> None:
            pyproject = (APPLICATION_ROOT / "runtime/native/pyproject.toml").read_text(
                encoding="utf-8"
            )
            self.assertIn("agent-native-runtime-migrate", pyproject)
            self.assertIn("agent-native-runtime-serve", pyproject)

else:

    class InstalledProcessFoundationTest(InstalledProcessTestCase):
        def test_installed_migrate_serve_separation_and_schema_fail_closed(
            self,
        ) -> None:
            missing = self.failed_serve(self.config_path)
            self.assertEqual(missing.returncode, 2)
            self.assertFalse(Path(self.base["runtime"]["state_root"]).exists())

            self.migrate(self.config_path, environment_only=True)
            self.migrate(self.config_path)
            with self.serving(self.config_path):
                pass

            for name, statement in (
                ("old", "DELETE FROM schema_migrations WHERE version = 2"),
                (
                    "drift",
                    "UPDATE schema_migrations SET migration_digest = '"
                    + "0" * 64
                    + "' WHERE version = 2",
                ),
            ):
                with self.subTest(name=name):
                    value = deepcopy(self.base)
                    state_root = self.root / f"state-{name}"
                    value["runtime"]["state_root"] = str(state_root)
                    path = self.write_configuration(f"{name}.json", value)
                    self.migrate(path)
                    connection = sqlite3.connect(state_root / "runtime.sqlite3")
                    try:
                        connection.execute(statement)
                        connection.commit()
                    finally:
                        connection.close()
                    before = self.state_snapshot(state_root)
                    result = self.failed_serve(path)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(self.state_snapshot(state_root), before)

            drifted = deepcopy(self.base)
            drifted["runtime"]["runtime_revision"] = "native-runtime-process-drift"
            drifted_path = self.write_configuration("configuration-drift.json", drifted)
            state_root = Path(self.base["runtime"]["state_root"])
            before = self.state_snapshot(state_root)
            result = self.failed_serve(drifted_path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.state_snapshot(state_root), before)

            process_drift = deepcopy(self.base)
            process_drift["capabilities"]["runtime_name"] = "changed-runtime"
            process_drift_path = self.write_configuration(
                "process-configuration-drift.json", process_drift
            )
            before = self.state_snapshot(state_root)
            result = self.failed_serve(process_drift_path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.state_snapshot(state_root), before)

        def test_real_mtls_certificate_identity_and_route_boundary(self) -> None:
            self.migrate(self.config_path)
            with self.serving(self.config_path) as server:
                status, headers, body = self.request(
                    server.port, self.pki.client, "/v1/capabilities"
                )
                self.assertEqual(status, 200)
                self.assertEqual(headers["content-type"], "application/json")
                capabilities = json.loads(body)
                self.assertEqual(
                    capabilities["provider_revision_id"],
                    self.base["runtime"]["provider_revision_id"],
                )
                self.assertLessEqual(
                    len(body), self.base["process"]["limits"]["max_response_bytes"]
                )
                status, _, _ = self.request(
                    server.port, self.pki.unmapped, "/v1/capabilities"
                )
                self.assertEqual(status, 403)

                for name, certificate in (
                    ("missing", None),
                    ("unknown_ca", self.pki.unknown_ca),
                    ("expired", self.pki.expired),
                    ("wrong_eku", self.pki.wrong_eku),
                ):
                    with (
                        self.subTest(name=name),
                        self.assertRaises((ssl.SSLError, ConnectionError, OSError)),
                    ):
                        self.request(server.port, certificate, "/v1/capabilities")

                status, start_headers, start_body = self.request(
                    server.port, self.pki.client, "/v1/runs", method="POST"
                )
                self.assertEqual(status, 400)
                self.assertEqual(start_headers["content-type"], "application/json")
                self.assertEqual(int(start_headers["content-length"]), len(start_body))
                standard_error = json.loads(start_body)
                self.assertEqual(standard_error["code"], "HTTP_CONTENT_TYPE_REJECTED")
                self.assertEqual(
                    set(standard_error),
                    {"code", "message", "retryable", "trace_id"},
                )
                state_root = Path(self.base["runtime"]["state_root"])
                self.assertEqual(
                    self.database_counts(state_root),
                    {
                        "consumed_mutation_jtis": 0,
                        "runtime_runs": 0,
                        "runtime_security_bindings": 0,
                        "start_idempotency": 0,
                        "runtime_events": 0,
                        "execution_work": 0,
                    },
                )

            with self.serving(self.config_path) as restarted:
                restarted_status, _, restarted_body = self.request(
                    restarted.port, self.pki.client, "/v1/capabilities"
                )
                self.assertEqual(restarted_status, 200)
                self.assertEqual(json.loads(restarted_body), capabilities)

            configuration = load_process_configuration(self.config_path)
            self.assertEqual(
                configuration.client_identities[0].token_subject, CALLER_SUBJECT
            )
            parsed_client_certificate = x509.load_pem_x509_certificate(
                self.pki.client.certificate.read_bytes()
            )
            caller = authenticate_peer_certificate(
                parsed_client_certificate.public_bytes(serialization.Encoding.DER),
                configuration,
            )
            caller.require_token_subject(CALLER_SUBJECT)
            with self.assertRaises(PeerIdentityNotAllowedError):
                caller.require_token_subject("spn_other_runtime_controller")
            print(
                "process-foundation-test-pki:"
                + ",".join(
                    (
                        "ca=sha256:"
                        + hashlib.sha256(
                            self.pki.ca_certificate.public_bytes(
                                serialization.Encoding.DER
                            )
                        ).hexdigest(),
                        "client=sha256:"
                        + hashlib.sha256(
                            parsed_client_certificate.public_bytes(
                                serialization.Encoding.DER
                            )
                        ).hexdigest(),
                    )
                )
            )
            self.assertEqual(
                stat.S_IMODE(self.pki.server.private_key.stat().st_mode), 0o600
            )

        def test_bounded_connection_request_header_body_and_read_timeouts(self) -> None:
            self.migrate(self.config_path)
            with self.serving(self.config_path) as server:
                raw = socket.create_connection(("127.0.0.1", server.port), timeout=2)
                time.sleep(0.3)
                self.assertEqual(raw.recv(1), b"")
                raw.close()

                idle = self.tls_socket(server.port, self.pki.client)
                time.sleep(0.4)
                self.assertEqual(idle.recv(1), b"")
                idle.close()

                slow = self.tls_socket(server.port, self.pki.client)
                slow.sendall(b"GET /health/live HTTP/1.1\r\nHost: localhost\r\nX-Slow:")
                time.sleep(0.3)
                self.assertEqual(slow.recv(1), b"")
                slow.close()

                oversized = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                oversized.connection.sendall(
                    b"GET /" + b"a" * 1_100 + b" HTTP/1.1\r\nHost: localhost\r\n\r\n"
                )
                try:
                    status, _, payload = oversized.response()
                    self.assertEqual(status, 400)
                    self.assertEqual(
                        json.loads(payload)["code"], "HTTP_REQUEST_LINE_REJECTED"
                    )
                finally:
                    oversized.connection.close()

                headers = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                headers.connection.sendall(
                    b"GET /health/live HTTP/1.1\r\nHost: localhost\r\nX-Large: "
                    + b"a" * 4_200
                    + b"\r\n\r\n"
                )
                try:
                    status, _, payload = headers.response()
                    self.assertEqual(status, 400)
                    self.assertEqual(
                        json.loads(payload)["code"], "HTTP_REQUEST_REJECTED"
                    )
                finally:
                    headers.connection.close()

                body = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
                body.request(
                    "GET", "/v1/capabilities", headers=b"Content-Length: 1\r\n"
                )
                self.assertEqual(body.response()[0], 413)
                body.connection.close()

            limited = deepcopy(self.base)
            limited["runtime"]["state_root"] = str(self.root / "state-connection-limit")
            limited["process"]["limits"]["max_connections"] = 1
            limited["process"]["limits"]["max_concurrent_requests"] = 1
            limited_path = self.write_configuration("connection-limit.json", limited)
            self.migrate(limited_path)
            with self.serving(limited_path) as server:
                first = self.tls_socket(server.port, self.pki.client)
                second = self.tls_socket(server.port, self.pki.client)
                second.sendall(b"GET /health/live HTTP/1.1\r\nHost: localhost\r\n\r\n")
                self.assertIn(b" 503 ", second.recv(4_096))
                first.close()
                second.close()

            concurrent = deepcopy(self.base)
            concurrent["runtime"]["state_root"] = str(self.root / "state-request-limit")
            concurrent["process"]["limits"]["max_connections"] = 2
            concurrent["process"]["limits"]["max_concurrent_requests"] = 1
            concurrent_path = self.write_configuration("request-limit.json", concurrent)
            self.migrate(concurrent_path)
            with self.serving(concurrent_path) as server:
                first = self.tls_socket(server.port, self.pki.client)
                first.sendall(
                    b"GET /health/live HTTP/1.1\r\nHost: localhost\r\nX-Slow:"
                )
                concurrent_second = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                concurrent_second.request("GET", "/health/live")
                self.assertEqual(concurrent_second.response()[0], 503)
                first.close()
                concurrent_second.connection.close()

        def test_response_write_limit_and_tls_version_are_enforced(self) -> None:
            self.migrate(self.config_path)
            too_small = deepcopy(self.base)
            too_small["runtime"]["state_root"] = str(
                self.root / "state-response-too-small"
            )
            too_small["process"]["limits"]["max_response_bytes"] = 256
            too_small_path = self.write_configuration(
                "response-too-small.json", too_small
            )
            self.migrate(too_small_path)
            too_small_state = Path(too_small["runtime"]["state_root"])
            before = self.state_snapshot(too_small_state)
            result = self.failed_serve(too_small_path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.state_snapshot(too_small_state), before)

            with self.serving(self.config_path) as server:
                legacy = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                legacy.check_hostname = False
                legacy.verify_mode = ssl.CERT_NONE
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    legacy.maximum_version = ssl.TLSVersion.TLSv1_1
                with self.assertRaises((ssl.SSLError, OSError)):
                    raw = socket.create_connection(
                        ("127.0.0.1", server.port), timeout=2
                    )
                    legacy.wrap_socket(raw, server_hostname="localhost")

            large = deepcopy(self.base)
            large["runtime"]["state_root"] = str(self.root / "state-write-timeout")
            large["capabilities"]["runtime_name"] = "n" * 32_000
            large["process"]["limits"]["max_requests_per_connection"] = 1_000
            large_path = self.write_configuration("write-timeout.json", large)
            self.migrate(large_path)
            server = self.start_server(large_path)
            client = self.tls_socket(server.port, self.pki.client)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1_024)
            request = b"GET /v1/capabilities HTTP/1.1\r\nHost: localhost\r\n\r\n"
            client.sendall(request * 32)
            time.sleep(0.5)
            stopped = server.stop()
            client.close()
            self.assertGreaterEqual(stopped["metrics"]["write_timeouts"], 1)

        def test_sigterm_readiness_bounded_drain_preserves_durable_work(self) -> None:
            drain = deepcopy(self.base)
            drain["runtime"]["state_root"] = str(self.root / "state-drain")
            drain["process"]["limits"]["max_connections"] = 3
            drain["process"]["limits"]["max_concurrent_requests"] = 2
            drain["process"]["limits"]["idle_timeout_ms"] = 2_000
            drain["process"]["limits"]["read_timeout_ms"] = 2_000
            drain_path = self.write_configuration("drain.json", drain)
            self.migrate(drain_path)
            state_root = Path(drain["runtime"]["state_root"])
            database = state_root / "runtime.sqlite3"
            timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            digest = "sha256:" + "1" * 64
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
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
                        "drain-runtime-run",
                        "tenant-1",
                        "conversation-1",
                        "work-order-1",
                        "workflow-run-1",
                        "agent-run-1",
                        digest,
                        digest,
                        digest,
                        "workspace-revision-1",
                        digest,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO execution_work(
                        work_id, runtime_run_id, kind, state, created_at, updated_at
                    ) VALUES ('drain-work', 'drain-runtime-run', 'start', 'pending', ?, ?)
                    """,
                    (timestamp, timestamp),
                )
                connection.commit()
            finally:
                connection.close()

            server = self.start_server(drain_path)
            keepalive = RawHTTPConnection(self.tls_socket(server.port, self.pki.client))
            keepalive.request("GET", "/health/live")
            self.assertEqual(keepalive.response()[0], 200)
            held = self.tls_socket(server.port, self.pki.client)
            held.sendall(b"GET /health/live HTTP/1.1\r\nHost: localhost\r\nX-Held:")

            started = time.monotonic()
            server.process.send_signal(signal.SIGTERM)
            time.sleep(0.05)
            keepalive.request("GET", "/health/ready")
            self.assertEqual(keepalive.response()[0], 503)
            with self.assertRaises(OSError):
                socket.create_connection(("127.0.0.1", server.port), timeout=0.2)
            keepalive.connection.close()
            stdout, stderr = server.process.communicate(timeout=3)
            elapsed = time.monotonic() - started
            held.close()
            self.assertEqual(server.process.returncode, 0, stderr)
            self.assertLess(elapsed, 2)
            stopped = next(
                json.loads(line)
                for line in stdout.splitlines()
                if '"event":"listener_stopped"' in line
            )
            self.assertFalse(stopped["readiness"])
            self.assertFalse(stopped["bounded_drain_complete"])
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(
                    connection.execute(
                        "SELECT state FROM execution_work WHERE work_id = 'drain-work'"
                    ).fetchone()[0],
                    "pending",
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
