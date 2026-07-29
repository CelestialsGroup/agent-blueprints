from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import selectors
import signal
import socket
import sqlite3
import ssl
import stat
import subprocess
import tempfile
import time
import unittest
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, cast

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from agent_native_runtime.process_config import load_process_configuration
from agent_native_runtime.tls import (
    PeerIdentityNotAllowedError,
    authenticate_peer_certificate,
)

INSTALLED_BIN = os.environ.get("AGENT_NATIVE_RUNTIME_INSTALLED_BIN")
APPLICATION_ROOT = Path(
    os.environ.get("AGENT_TEST_APPLICATION_ROOT", Path(__file__).resolve().parents[3])
).resolve()
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", APPLICATION_ROOT.parent / "contract")
).resolve()
CALLER_SUBJECT = "spn_agent_runtime_controller"
CALLER_URI = "spiffe://agent.test/runtime-controller"


@dataclass(frozen=True, slots=True)
class CertificateFiles:
    certificate: Path
    private_key: Path


class TestPKI:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.now = datetime.now(UTC)
        self.ca_key = ec.generate_private_key(ec.SECP256R1())
        self.ca_certificate = self._ca(
            self.ca_key,
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Runtime Test CA")]),
        )
        self.ca_file = self._write_certificate("ca", self.ca_certificate)
        self.server = self._leaf(
            "server",
            self.ca_key,
            self.ca_certificate,
            eku=ExtendedKeyUsageOID.SERVER_AUTH,
            san=(
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ),
        )
        self.client = self._leaf(
            "client",
            self.ca_key,
            self.ca_certificate,
            eku=ExtendedKeyUsageOID.CLIENT_AUTH,
            san=(x509.UniformResourceIdentifier(CALLER_URI),),
        )
        self.unmapped = self._leaf(
            "unmapped",
            self.ca_key,
            self.ca_certificate,
            eku=ExtendedKeyUsageOID.CLIENT_AUTH,
            san=(x509.UniformResourceIdentifier("spiffe://agent.test/unmapped"),),
        )
        self.wrong_eku = self._leaf(
            "wrong-eku",
            self.ca_key,
            self.ca_certificate,
            eku=ExtendedKeyUsageOID.SERVER_AUTH,
            san=(x509.UniformResourceIdentifier(CALLER_URI),),
        )
        self.expired = self._leaf(
            "expired",
            self.ca_key,
            self.ca_certificate,
            eku=ExtendedKeyUsageOID.CLIENT_AUTH,
            san=(x509.UniformResourceIdentifier(CALLER_URI),),
            not_before=self.now - timedelta(days=10),
            not_after=self.now - timedelta(days=1),
        )
        other_key = ec.generate_private_key(ec.SECP256R1())
        other_ca = self._ca(
            other_key,
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Unknown Test CA")]),
        )
        self.unknown_ca = self._leaf(
            "unknown-ca",
            other_key,
            other_ca,
            eku=ExtendedKeyUsageOID.CLIENT_AUTH,
            san=(x509.UniformResourceIdentifier(CALLER_URI),),
        )

    def _ca(
        self, key: ec.EllipticCurvePrivateKey, subject: x509.Name
    ) -> x509.Certificate:
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(self.now - timedelta(days=1))
            .not_valid_after(self.now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

    def _leaf(
        self,
        name: str,
        issuer_key: ec.EllipticCurvePrivateKey,
        issuer: x509.Certificate,
        *,
        eku: x509.ObjectIdentifier,
        san: tuple[x509.GeneralName, ...],
        not_before: datetime | None = None,
        not_after: datetime | None = None,
    ) -> CertificateFiles:
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before or self.now - timedelta(hours=1))
            .not_valid_after(not_after or self.now + timedelta(days=1))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
            .add_extension(x509.SubjectAlternativeName(list(san)), critical=False)
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    issuer_key.public_key()
                ),
                critical=False,
            )
            .sign(issuer_key, hashes.SHA256())
        )
        certificate_path = self._write_certificate(name, certificate)
        private_path = self.root / f"{name}.key"
        private_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        private_path.chmod(0o600)
        return CertificateFiles(certificate_path, private_path)

    def _write_certificate(self, name: str, certificate: x509.Certificate) -> Path:
        path = self.root / f"{name}.crt"
        path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        path.chmod(0o644)
        return path


@dataclass(slots=True)
class RunningServer:
    process: subprocess.Popen[str]
    port: int

    def stop(self) -> dict[str, Any]:
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
        stdout, stderr = self.process.communicate(timeout=5)
        if self.process.returncode != 0:
            raise AssertionError(f"serve failed: {stderr}")
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        stopped = next(
            item for item in events if item.get("event") == "listener_stopped"
        )
        return cast(dict[str, Any], stopped)


class RawHTTPConnection:
    def __init__(self, connection: ssl.SSLSocket) -> None:
        self.connection = connection
        self.buffer = b""

    def request(self, method: str, path: str, *, headers: bytes = b"") -> None:
        self.connection.sendall(
            method.encode("ascii")
            + b" "
            + path.encode("ascii")
            + b" HTTP/1.1\r\nHost: localhost\r\n"
            + headers
            + b"\r\n"
        )

    def response(self) -> tuple[int, dict[str, str], bytes]:
        while b"\r\n\r\n" not in self.buffer:
            chunk = self.connection.recv(65_536)
            if not chunk:
                raise ConnectionError("connection closed before HTTP headers")
            self.buffer += chunk
        encoded_headers, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        lines = encoded_headers.decode("ascii").split("\r\n")
        status = int(lines[0].split(" ", 2)[1])
        headers = {
            name.lower(): value.strip()
            for name, value in (line.split(":", 1) for line in lines[1:])
        }
        length = int(headers["content-length"])
        while len(self.buffer) < length:
            chunk = self.connection.recv(65_536)
            if not chunk:
                raise ConnectionError("connection closed before HTTP body")
            self.buffer += chunk
        body, self.buffer = self.buffer[:length], self.buffer[length:]
        return status, headers, body


if INSTALLED_BIN is None:

    class ProcessFoundationSourceBoundaryTest(unittest.TestCase):
        def test_installed_cli_entrypoints_are_declared(self) -> None:
            pyproject = (APPLICATION_ROOT / "runtime/native/pyproject.toml").read_text(
                encoding="utf-8"
            )
            self.assertIn("agent-native-runtime-migrate", pyproject)
            self.assertIn("agent-native-runtime-serve", pyproject)

else:

    class InstalledProcessFoundationTest(unittest.TestCase):
        def setUp(self) -> None:
            self.temporary = tempfile.TemporaryDirectory()
            self.addCleanup(self.temporary.cleanup)
            self.root = Path(self.temporary.name)
            self.pki = TestPKI(self.root)
            signing_key = ed25519.Ed25519PrivateKey.generate()
            self.verification_key = self.root / "runtime-token-public.pem"
            self.verification_key.write_bytes(
                signing_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            installed_bin = Path(cast(str, INSTALLED_BIN))
            self.migrate_bin = installed_bin / "agent-native-runtime-migrate"
            self.serve_bin = installed_bin / "agent-native-runtime-serve"
            self.assertTrue(self.migrate_bin.is_file())
            self.assertTrue(self.serve_bin.is_file())
            self.base = self.configuration(self.root / "state")
            self.config_path = self.write_configuration("process.json", self.base)

        def configuration(self, state_root: Path) -> dict[str, Any]:
            return {
                "schema_version": 1,
                "runtime": {
                    "provider_revision_id": "apr_01J00000000000000000000000",
                    "runtime_revision": "native-runtime-process-test-v1",
                    "provider_audience": "urn:agent-platform:provider-instance:api_native_runtime",
                    "event_registry_id": "agent-runtime-core",
                    "event_registry_version": 1,
                    "event_registry_digest": "sha256:d60c4b90063af5d3b889b10d3847fc431a3eee2f7fa3ba27ffe49ccbba251b43",
                    "state_root": str(state_root),
                    "checkpoint_profile": "runtime-core-v1",
                    "max_checkpoint_bytes": 16 * 1024 * 1024,
                    "sqlite_busy_timeout_ms": 1_000,
                    "work_lease_seconds": 5,
                },
                "security": {
                    "trusted_callers": [CALLER_SUBJECT],
                    "verification_keys": [
                        {
                            "kid": "process-test",
                            "algorithm": "EdDSA",
                            "public_key_file": str(self.verification_key),
                        }
                    ],
                    "application_root": str(APPLICATION_ROOT),
                    "contract_root": str(CONTRACT_ROOT),
                    "max_token_bytes": 16 * 1024,
                    "clock_skew_seconds": 5,
                    "max_json_depth": 64,
                    "max_json_nodes": 100_000,
                    "max_number_token_bytes": 1_024,
                    "max_decimal_exponent": 400,
                },
                "process": {
                    "bind_host": "127.0.0.1",
                    "bind_port": 0,
                    "server_certificate_file": str(self.pki.server.certificate),
                    "server_private_key_file": str(self.pki.server.private_key),
                    "client_ca_file": str(self.pki.ca_file),
                    "client_identities": [
                        {"certificate_uri": CALLER_URI, "token_subject": CALLER_SUBJECT}
                    ],
                    "limits": {
                        "max_connections": 4,
                        "max_concurrent_requests": 2,
                        "max_requests_per_connection": 8,
                        "max_request_line_bytes": 1_024,
                        "max_header_bytes": 4_096,
                        "max_header_count": 16,
                        "max_response_bytes": 65_536,
                        "listen_backlog": 4,
                        "socket_send_buffer_bytes": 4_096,
                        "tls_handshake_timeout_ms": 200,
                        "idle_timeout_ms": 300,
                        "read_timeout_ms": 200,
                        "write_timeout_ms": 100,
                        "drain_timeout_ms": 400,
                    },
                },
                "capabilities": {
                    "runtime_name": "native-runtime",
                    "runtime_version": "process-test-v1",
                    "features": [
                        "runtime.start",
                        "runtime.pause",
                        "runtime.resume",
                        "runtime.cancel",
                        "runtime.events.cursor",
                        "runtime.checkpoint.export",
                        "runtime.checkpoint.restore",
                    ],
                },
            }

        def write_configuration(self, name: str, value: dict[str, Any]) -> Path:
            path = self.root / name
            path.write_text(
                json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            return path

        def migrate(
            self, configuration: Path, *, environment_only: bool = False
        ) -> None:
            environment = dict(os.environ)
            command = [str(self.migrate_bin)]
            if environment_only:
                environment["AGENT_NATIVE_RUNTIME_CONFIG_FILE"] = str(configuration)
            else:
                command.extend(("--config", str(configuration)))
            result = subprocess.run(
                command,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"event":"migration_complete"', result.stdout)

        def failed_serve(self, configuration: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [str(self.serve_bin), "--config", str(configuration)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )

        def start_server(self, configuration: Path) -> RunningServer:
            process = subprocess.Popen(
                [str(self.serve_bin), "--config", str(configuration)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(cast(BinaryIO, process.stdout), selectors.EVENT_READ)
            deadline = time.monotonic() + 10
            line = ""
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    stderr = process.stderr.read() if process.stderr else ""
                    raise AssertionError(f"serve exited before readiness: {stderr}")
                if selector.select(timeout=0.1):
                    line = process.stdout.readline()
                    if line:
                        break
            selector.close()
            if not line:
                process.kill()
                process.wait(timeout=5)
                raise AssertionError("serve did not emit bounded listener readiness")
            event = json.loads(line)
            self.assertEqual(event["event"], "listener_ready")
            self.assertTrue(event["readiness"])
            self.assertEqual(event["tls_minimum"], "1.2")
            return RunningServer(process=process, port=cast(int, event["port"]))

        @contextmanager
        def serving(self, configuration: Path) -> Iterator[RunningServer]:
            server = self.start_server(configuration)
            try:
                yield server
            finally:
                if server.process.poll() is None:
                    server.stop()

        def client_context(
            self,
            client: CertificateFiles | None = None,
            *,
            maximum_version: ssl.TLSVersion | None = None,
        ) -> ssl.SSLContext:
            context = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH, cafile=str(self.pki.ca_file)
            )
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if maximum_version is not None:
                context.maximum_version = maximum_version
            if client is not None:
                context.load_cert_chain(client.certificate, client.private_key)
            return context

        def tls_socket(
            self, port: int, client: CertificateFiles | None = None
        ) -> ssl.SSLSocket:
            raw = socket.create_connection(("127.0.0.1", port), timeout=2)
            return self.client_context(client).wrap_socket(
                raw, server_hostname="localhost"
            )

        def request(
            self,
            port: int,
            client: CertificateFiles | None,
            path: str,
            *,
            method: str = "GET",
        ) -> tuple[int, dict[str, str], bytes]:
            connection = http.client.HTTPSConnection(
                "127.0.0.1",
                port,
                timeout=2,
                context=self.client_context(client),
            )
            try:
                connection.request(method, path)
                response = connection.getresponse()
                body = response.read()
                return (
                    response.status,
                    {key.lower(): value for key, value in response.headers.items()},
                    body,
                )
            finally:
                connection.close()

        def state_snapshot(self, state_root: Path) -> dict[str, object]:
            database = state_root / "runtime.sqlite3"
            connection = sqlite3.connect(
                database.resolve().as_uri() + "?mode=ro", uri=True
            )
            try:
                logical_database = tuple(connection.iterdump())
            finally:
                connection.close()
            checkpoint_files = tuple(
                (
                    path.relative_to(state_root).as_posix(),
                    path.read_bytes(),
                )
                for path in sorted(state_root.rglob("*"))
                if path.is_file() and not path.name.startswith("runtime.sqlite3")
            )
            return {
                "logical_database": logical_database,
                "checkpoint_files": checkpoint_files,
            }

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

                status, _, _ = self.request(
                    server.port, self.pki.client, "/v1/runs", method="POST"
                )
                self.assertEqual(status, 404)
                connection = sqlite3.connect(
                    Path(self.base["runtime"]["state_root"]) / "runtime.sqlite3"
                )
                try:
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM runtime_runs"
                        ).fetchone()[0],
                        0,
                    )
                finally:
                    connection.close()

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
                self.assertEqual(oversized.response()[0], 414)
                oversized.connection.close()

                headers = RawHTTPConnection(
                    self.tls_socket(server.port, self.pki.client)
                )
                headers.connection.sendall(
                    b"GET /health/live HTTP/1.1\r\nHost: localhost\r\nX-Large: "
                    + b"a" * 4_200
                    + b"\r\n\r\n"
                )
                self.assertEqual(headers.response()[0], 431)
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
