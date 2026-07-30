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
import subprocess
import tempfile
import time
import unittest
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, Literal, cast

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from agent_native_runtime.contract_projection import canonicalize_json
from agent_native_runtime.model import format_timestamp

INSTALLED_BIN = os.environ.get("AGENT_NATIVE_RUNTIME_INSTALLED_BIN")
APPLICATION_ROOT = Path(
    os.environ.get("AGENT_TEST_APPLICATION_ROOT", Path(__file__).resolve().parents[3])
).resolve()
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", APPLICATION_ROOT.parent / "contract")
).resolve()
CALLER_SUBJECT = "spn_agent_runtime_controller"
CALLER_URI = "spiffe://agent.test/runtime-controller"


def document_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonicalize_json(value)).hexdigest()


def refresh_self_digest(document: dict[str, Any], field: str) -> None:
    unsigned = dict(document)
    unsigned.pop(field, None)
    document[field] = document_digest(unsigned)


@dataclass(frozen=True, slots=True)
class CertificateFiles:
    certificate: Path
    private_key: Path


class TestPKI:
    __test__ = False

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
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
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
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()
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

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: bytes = b"",
        body: bytes = b"",
        host: bytes = b"localhost",
        version: bytes = b"HTTP/1.1",
    ) -> None:
        self.connection.sendall(
            method.encode("ascii")
            + b" "
            + path.encode("ascii")
            + b" "
            + version
            + b"\r\nHost: "
            + host
            + b"\r\n"
            + headers
            + b"\r\n"
            + body
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


class InstalledProcessTestCase(unittest.TestCase):
    __test__ = False

    def setUp(self) -> None:
        if INSTALLED_BIN is None:
            self.skipTest("installed wheel process test")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = datetime.now(UTC)
        self.pki = TestPKI(self.root)
        self.eddsa_private = ed25519.Ed25519PrivateKey.generate()
        self.es256_private = ec.generate_private_key(ec.SECP256R1())
        self.eddsa_verification_key = self._write_public_key(
            "runtime-token-eddsa-public.pem", self.eddsa_private
        )
        self.es256_verification_key = self._write_public_key(
            "runtime-token-es256-public.pem", self.es256_private
        )
        installed_bin = Path(INSTALLED_BIN)
        self.migrate_bin = installed_bin / "agent-native-runtime-migrate"
        self.serve_bin = installed_bin / "agent-native-runtime-serve"
        self.assertTrue(self.migrate_bin.is_file())
        self.assertTrue(self.serve_bin.is_file())
        self.base = self.configuration(self.root / "state")
        self.config_path = self.write_configuration("process.json", self.base)

    def _write_public_key(
        self,
        name: str,
        private_key: ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey,
    ) -> Path:
        path = self.root / name
        path.write_bytes(
            private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        path.chmod(0o644)
        return path

    def timestamp(self, *, minutes: int = 0, seconds: int = 0) -> str:
        return format_timestamp(self.now + timedelta(minutes=minutes, seconds=seconds))

    def start_document(
        self, example_name: str = "agent-runtime-start-no-sandbox.json"
    ) -> dict[str, Any]:
        document = cast(
            dict[str, Any],
            json.loads(
                (CONTRACT_ROOT / "examples/contracts" / example_name).read_text(
                    encoding="utf-8"
                )
            ),
        )
        authorization = cast(dict[str, Any], document["runtime_authorization"])
        budget = cast(dict[str, Any], authorization["execution_budget"])
        allocation = cast(dict[str, Any], authorization["agent_run_budget_allocation"])
        policy = cast(dict[str, Any], authorization["policy_decision"])
        permissions = cast(dict[str, Any], authorization["effective_permissions"])
        commercial = cast(dict[str, Any], authorization["commercial_authorization"])
        grants = cast(list[dict[str, Any]], authorization["artifact_grants"])

        document["deadline_at"] = self.timestamp(minutes=10)
        budget["created_at"] = self.timestamp(minutes=-5)
        budget["expires_at"] = self.timestamp(minutes=30)
        refresh_self_digest(budget, "budget_digest")
        allocation["work_order_budget_digest"] = budget["budget_digest"]
        allocation["issued_at"] = self.timestamp(minutes=-3)
        allocation["expires_at"] = self.timestamp(minutes=30)
        refresh_self_digest(allocation, "allocation_digest")
        refresh_self_digest(permissions, "permissions_digest")
        commercial["expires_at"] = self.timestamp(minutes=30)
        policy["execution_budget_digest"] = budget["budget_digest"]
        policy["effective_permissions_digest"] = permissions["permissions_digest"]
        policy["decided_at"] = self.timestamp(minutes=-4)
        policy["expires_at"] = self.timestamp(minutes=30)
        refresh_self_digest(policy, "decision_digest")
        for grant in grants:
            grant["issued_at"] = self.timestamp(minutes=-3)
            grant["expires_at"] = self.timestamp(minutes=10)
            refresh_self_digest(grant, "grant_digest")
        authorization["issued_at"] = self.timestamp(minutes=-3)
        authorization["expires_at"] = self.timestamp(minutes=10)
        refresh_self_digest(authorization, "authorization_digest")
        refresh_self_digest(document, "request_digest")
        return document

    def start_claims(self, document: dict[str, Any], jti: str) -> dict[str, Any]:
        authorization = cast(dict[str, Any], document["runtime_authorization"])
        policy = cast(dict[str, Any], authorization["policy_decision"])
        budget = cast(dict[str, Any], authorization["execution_budget"])
        permissions = cast(dict[str, Any], authorization["effective_permissions"])
        now = int(self.now.timestamp())
        return {
            "iss": "agent-platform",
            "sub": CALLER_SUBJECT,
            "aud": self.base["runtime"]["provider_audience"],
            "jti": jti,
            "iat": now,
            "nbf": now,
            "exp": now + 240,
            "tenant_id": document["tenant_id"],
            "provider_revision_id": self.base["runtime"]["provider_revision_id"],
            "runtime_run_id": document["runtime_run_id"],
            "agent_run_id": document["agent_run_id"],
            "workflow_run_id": document["workflow_run_id"],
            "work_order_id": document["work_order_id"],
            "run_manifest_digest": document["run_manifest_digest"],
            "runtime_authorization_digest": authorization["authorization_digest"],
            "authority_mode": "execution",
            "operation": "start",
            "operation_contract_id": (
                "urn:agent-platform:agent-runtime-start-request:v1"
            ),
            "operation_digest_profile": ("rfc8785-request-excluding-request-digest-v1"),
            "operation_request_digest": document["request_digest"],
            "invocation_id": document["invocation_id"],
            "invocation_attempt_id": document["invocation_attempt_id"],
            "fencing_token": document["fencing_token"],
            "policy_decision_digest": policy["decision_digest"],
            "execution_budget_digest": budget["budget_digest"],
            "effective_permissions_digest": permissions["permissions_digest"],
        }

    @staticmethod
    def refresh_start_digests(document: dict[str, Any]) -> None:
        authorization = cast(dict[str, Any], document["runtime_authorization"])
        budget = cast(dict[str, Any], authorization["execution_budget"])
        allocation = cast(dict[str, Any], authorization["agent_run_budget_allocation"])
        policy = cast(dict[str, Any], authorization["policy_decision"])
        permissions = cast(dict[str, Any], authorization["effective_permissions"])
        grants = cast(list[dict[str, Any]], authorization["artifact_grants"])
        refresh_self_digest(budget, "budget_digest")
        allocation["work_order_budget_digest"] = budget["budget_digest"]
        refresh_self_digest(allocation, "allocation_digest")
        refresh_self_digest(permissions, "permissions_digest")
        policy["execution_budget_digest"] = budget["budget_digest"]
        policy["effective_permissions_digest"] = permissions["permissions_digest"]
        refresh_self_digest(policy, "decision_digest")
        for grant in grants:
            refresh_self_digest(grant, "grant_digest")
        refresh_self_digest(authorization, "authorization_digest")
        refresh_self_digest(document, "request_digest")

    def sign_start(
        self,
        claims: dict[str, Any],
        *,
        algorithm: Literal["EdDSA", "ES256"] = "EdDSA",
        private_key: ed25519.Ed25519PrivateKey
        | ec.EllipticCurvePrivateKey
        | None = None,
        kid: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> str:
        selected_key = private_key or (
            self.eddsa_private if algorithm == "EdDSA" else self.es256_private
        )
        selected_headers = {
            "kid": kid
            or ("process-eddsa-test" if algorithm == "EdDSA" else "process-es256-test"),
            "typ": "agent-runtime-invocation+jwt",
        }
        if headers:
            selected_headers.update(headers)
        return jwt.encode(
            claims,
            selected_key,
            algorithm=algorithm,
            headers=selected_headers,
        )

    @staticmethod
    def encode(document: object) -> bytes:
        return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()

    def start_request(
        self,
        document: dict[str, Any],
        *,
        jti: str,
        algorithm: Literal["EdDSA", "ES256"] = "EdDSA",
        claims: dict[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        body = self.encode(document)
        token = self.sign_start(
            claims or self.start_claims(document, jti), algorithm=algorithm
        )
        return body, token

    def command_document(
        self,
        start: dict[str, Any],
        *,
        command_type: str = "cancel",
        command_sequence: int = 1,
        fencing_token: int = 2,
        safety_control: bool = False,
    ) -> dict[str, Any]:
        document = cast(
            dict[str, Any],
            json.loads(
                (
                    CONTRACT_ROOT
                    / "examples/contracts/agent-runtime-system-safety-command.json"
                ).read_text(encoding="utf-8")
            ),
        )
        document.update(
            {
                "command_id": f"runtime-http-command-{command_sequence:04d}",
                "runtime_run_id": start["runtime_run_id"],
                "command_sequence": command_sequence,
                "type": command_type,
                "invocation_id": start["invocation_id"],
                "invocation_attempt_id": start["invocation_attempt_id"],
                "fencing_token": fencing_token,
                "idempotency_key": f"runtime-http-command-key-{command_sequence:04d}",
                "deadline_at": self.timestamp(minutes=5),
            }
        )
        document.pop("authorized_control_request_id", None)
        document.pop("system_safety_control_id", None)
        document.pop("system_safety_control_digest", None)
        if command_type in {"pause", "resume", "cancel"}:
            if safety_control and command_type in {"pause", "cancel"}:
                document["system_safety_control_id"] = (
                    f"runtime-http-safety-control-{command_sequence:04d}"
                )
                document["system_safety_control_digest"] = "sha256:" + "3" * 64
            else:
                document["authorized_control_request_id"] = (
                    f"runtime-http-control-request-{command_sequence:04d}"
                )
        elif command_type in {"append_input", "interrupt"}:
            document.update(
                {
                    "authorized_control_request_id": (
                        f"runtime-http-control-request-{command_sequence:04d}"
                    ),
                    "input_id": f"runtime-http-input-{command_sequence:04d}",
                    "input_content_digest": "sha256:" + "4" * 64,
                }
            )
        elif command_type == "approval_decision":
            document.update(
                {
                    "authorized_control_request_id": (
                        f"runtime-http-control-request-{command_sequence:04d}"
                    ),
                    "approval_id": f"runtime-http-approval-{command_sequence:04d}",
                    "decision": {"decision": "approve"},
                }
            )
        elif command_type == "subagent_spawn_decision":
            document.update(
                {
                    "spawn_request_id": f"runtime-http-spawn-{command_sequence:04d}",
                    "child_agent_run_admission_decision_id": (
                        f"runtime-http-child-admission-{command_sequence:04d}"
                    ),
                    "child_agent_run_admission_decision_digest": ("sha256:" + "5" * 64),
                    "spawn_outcome": "accepted",
                    "spawn_reason_codes": ["admitted"],
                    "child_agent_run_id": (
                        f"runtime-http-child-agent-run-{command_sequence:04d}"
                    ),
                }
            )
        elif command_type != "checkpoint":
            raise AssertionError(f"unsupported test Command type: {command_type}")
        refresh_self_digest(document, "command_digest")
        return document

    def command_claims(
        self,
        start: dict[str, Any],
        command: dict[str, Any],
        *,
        jti: str,
    ) -> dict[str, Any]:
        authorization = cast(dict[str, Any], start["runtime_authorization"])
        policy = cast(dict[str, Any], authorization["policy_decision"])
        budget = cast(dict[str, Any], authorization["execution_budget"])
        permissions = cast(dict[str, Any], authorization["effective_permissions"])
        safety_control = "system_safety_control_id" in command
        now = int(self.now.timestamp())
        claims: dict[str, Any] = {
            "iss": "agent-platform",
            "sub": CALLER_SUBJECT,
            "aud": self.base["runtime"]["provider_audience"],
            "jti": jti,
            "iat": now,
            "nbf": now,
            "exp": now + 240,
            "tenant_id": start["tenant_id"],
            "provider_revision_id": self.base["runtime"]["provider_revision_id"],
            "runtime_run_id": command["runtime_run_id"],
            "agent_run_id": start["agent_run_id"],
            "workflow_run_id": start["workflow_run_id"],
            "work_order_id": start["work_order_id"],
            "run_manifest_digest": start["run_manifest_digest"],
            "runtime_authorization_digest": authorization["authorization_digest"],
            "authority_mode": "safety_control" if safety_control else "execution",
            "operation": "submit_command",
            "operation_contract_id": "urn:agent-platform:agent-runtime-command:v1",
            "operation_digest_profile": ("rfc8785-command-excluding-command-digest-v1"),
            "operation_request_digest": command["command_digest"],
            "invocation_id": command["invocation_id"],
            "invocation_attempt_id": command["invocation_attempt_id"],
            "fencing_token": command["fencing_token"],
            "policy_decision_digest": policy["decision_digest"],
            "execution_budget_digest": budget["budget_digest"],
            "effective_permissions_digest": permissions["permissions_digest"],
        }
        if safety_control:
            claims["system_safety_control_id"] = command["system_safety_control_id"]
            claims["system_safety_control_digest"] = command[
                "system_safety_control_digest"
            ]
        return claims

    def command_request(
        self,
        start: dict[str, Any],
        command: dict[str, Any],
        *,
        jti: str,
        algorithm: Literal["EdDSA", "ES256"] = "EdDSA",
        claims: dict[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        body = self.encode(command)
        token = self.sign_start(
            claims or self.command_claims(start, command, jti=jti),
            algorithm=algorithm,
        )
        return body, token

    @staticmethod
    def clone(document: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(document)

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
                        "kid": "process-eddsa-test",
                        "algorithm": "EdDSA",
                        "public_key_file": str(self.eddsa_verification_key),
                    },
                    {
                        "kid": "process-es256-test",
                        "algorithm": "ES256",
                        "public_key_file": str(self.es256_verification_key),
                    },
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

    def migrate(self, configuration: Path, *, environment_only: bool = False) -> None:
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

    def start_server(
        self,
        configuration: Path,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> RunningServer:
        process_environment = dict(os.environ)
        process_environment.update(environment or {})
        process = subprocess.Popen(
            [str(self.serve_bin), "--config", str(configuration)],
            env=process_environment,
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
                process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
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
    def serving(
        self,
        configuration: Path,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> Iterator[RunningServer]:
        server = self.start_server(configuration, environment=environment)
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
        return self.client_context(client).wrap_socket(raw, server_hostname="localhost")

    def request(
        self,
        port: int,
        client: CertificateFiles | None,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPSConnection(
            "127.0.0.1",
            port,
            timeout=2,
            context=self.client_context(client),
        )
        try:
            connection.request(method, path, body=body, headers=dict(headers or {}))
            response = connection.getresponse()
            encoded = response.read()
            return (
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                encoded,
            )
        finally:
            connection.close()

    def post_command(
        self,
        port: int,
        runtime_run_id: str,
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
            f"/v1/runs/{runtime_run_id}/commands",
            method="POST",
            body=body,
            headers=request_headers,
        )

    def state_snapshot(self, state_root: Path) -> dict[str, object]:
        database = state_root / "runtime.sqlite3"
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            logical_database = tuple(connection.iterdump())
        finally:
            connection.close()
        checkpoint_files = tuple(
            (path.relative_to(state_root).as_posix(), path.read_bytes())
            for path in sorted(state_root.rglob("*"))
            if path.is_file() and not path.name.startswith("runtime.sqlite3")
        )
        return {
            "logical_database": logical_database,
            "checkpoint_files": checkpoint_files,
        }

    def database_counts(self, state_root: Path) -> dict[str, int]:
        connection = sqlite3.connect(state_root / "runtime.sqlite3")
        try:
            return {
                table: cast(
                    int,
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                )
                for table in (
                    "consumed_mutation_jtis",
                    "runtime_runs",
                    "runtime_security_bindings",
                    "start_idempotency",
                    "runtime_events",
                    "execution_work",
                )
            }
        finally:
            connection.close()

    def command_database_counts(self, state_root: Path) -> dict[str, int]:
        counts = self.database_counts(state_root)
        connection = sqlite3.connect(state_root / "runtime.sqlite3")
        try:
            counts.update(
                {
                    table: cast(
                        int,
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
                            0
                        ],
                    )
                    for table in ("runtime_commands", "checkpoint_manifests")
                }
            )
        finally:
            connection.close()
        return counts
