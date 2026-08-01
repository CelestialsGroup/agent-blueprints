from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from process_test_support import (
    APPLICATION_ROOT,
    CALLER_SUBJECT,
    CALLER_URI,
    CONTRACT_ROOT,
    CertificateFiles,
    InstalledProcessTestCase,
)

import agent_native_runtime


class Ed25519TestPKI:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.now = datetime.now(UTC)
        self.ca_key = ed25519.Ed25519PrivateKey.generate()
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "Runtime Cross-Language CA")]
        )
        self.ca_certificate = self._ca(self.ca_key, subject)
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

    def _ca(
        self, key: ed25519.Ed25519PrivateKey, subject: x509.Name
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
            .sign(key, None)
        )

    def _leaf(
        self,
        name: str,
        issuer_key: ed25519.Ed25519PrivateKey,
        issuer: x509.Certificate,
        *,
        eku: x509.ObjectIdentifier,
        san: tuple[x509.GeneralName, ...],
    ) -> CertificateFiles:
        key = ed25519.Ed25519PrivateKey.generate()
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .issuer_name(issuer.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(self.now - timedelta(hours=1))
            .not_valid_after(self.now + timedelta(days=1))
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
            .sign(issuer_key, None)
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


class FixtureBuilder(InstalledProcessTestCase):
    def __init__(self, root: Path) -> None:
        unittest.TestCase.__init__(self, methodName="runTest")
        self.root = root
        self.now = datetime.now(UTC)
        self.pki = cast(Any, Ed25519TestPKI(root))
        self.eddsa_private = ed25519.Ed25519PrivateKey.generate()
        self.eddsa_verification_key = self._write_public_key(
            "runtime-token-eddsa-public.pem", self.eddsa_private
        )
        self.es256_private = None  # type: ignore[assignment]
        self.es256_verification_key = self.eddsa_verification_key
        self.base = self.configuration(root / "state")
        self.base["security"]["verification_keys"] = [
            {
                "kid": "process-eddsa-test",
                "algorithm": "EdDSA",
                "public_key_file": str(self.eddsa_verification_key),
            }
        ]
        registry = json.loads(
            (CONTRACT_ROOT / "event-types/agent-runtime-core-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.registry_digest = cast(str, registry["registry_digest"])
        self.base["runtime"]["event_registry_digest"] = self.registry_digest
        self.base["process"]["limits"].update(
            {
                "tls_handshake_timeout_ms": 2_000,
                "idle_timeout_ms": 2_000,
                "read_timeout_ms": 2_000,
                "write_timeout_ms": 2_000,
                "drain_timeout_ms": 2_000,
            }
        )


def _write_bytes(root: Path, name: str, value: bytes) -> str:
    path = root / name
    path.write_bytes(value)
    path.chmod(0o600)
    return str(path)


def _invocation(
    root: Path,
    name: str,
    *,
    operation: str,
    token: str,
    runtime_run_id: str,
    invocation_id: str,
    invocation_attempt_id: str,
    fencing_token: int,
    request_digest: str,
    body: bytes | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "operation": operation,
        "token_path": _write_bytes(root, f"{name}.token", token.encode("ascii")),
        "runtime_run_id": runtime_run_id,
        "invocation_id": invocation_id,
        "invocation_attempt_id": invocation_attempt_id,
        "fencing_token": fencing_token,
        "request_digest": request_digest,
    }
    if body is not None:
        value["body_path"] = _write_bytes(root, f"{name}.json", body)
    return value


def _module_path() -> Path:
    module_file = agent_native_runtime.__file__
    if module_file is None:
        raise AssertionError("installed runtime module has no file")
    path = Path(module_file).resolve()
    source_root = (APPLICATION_ROOT / "runtime/native/src").resolve()
    if path == source_root or source_root in path.parents:
        raise AssertionError(
            "Native Runtime resolved from source instead of installed wheel"
        )
    return path


def build_fixture(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=False)
    builder = FixtureBuilder(root)
    config_path = builder.write_configuration("process.json", builder.base)
    start = builder.start_document()
    start_body, start_token = builder.start_request(
        start, jti="cross-language-start-jti-0001"
    )
    status_claims = builder.read_claims(
        start,
        operation="read_status",
        jti="cross-language-status-jti-0001",
        fencing_token=1,
    )
    status_token = builder.sign_start(status_claims)
    command = builder.command_document(
        start, command_type="cancel", command_sequence=1, fencing_token=2
    )
    command_body, command_token = builder.command_request(
        start, command, jti="cross-language-command-jti-0001"
    )
    events_claims = builder.read_claims(
        start,
        operation="read_events",
        jti="cross-language-events-jti-0001",
        fencing_token=2,
        after_event_sequence=0,
        limit=1000,
    )
    events_token = builder.sign_start(events_claims)
    missing_runtime_run_id = "rtr_01J00000000000000000000099"
    missing_claims = builder.read_claims(
        start,
        operation="read_status",
        jti="cross-language-missing-status-jti-0001",
        runtime_run_id=missing_runtime_run_id,
        fencing_token=1,
    )
    missing_token = builder.sign_start(missing_claims)
    stale_command = builder.command_document(
        start, command_type="cancel", command_sequence=2, fencing_token=2
    )
    stale_body, stale_token = builder.command_request(
        start, stale_command, jti="cross-language-command-jti-0002"
    )
    registry_path = CONTRACT_ROOT / "event-types/agent-runtime-core-v1.json"
    ca_fingerprint = builder.pki.ca_certificate.fingerprint(hashes.SHA256()).hex()
    return {
        "schema_version": 1,
        "installed_module_path": str(_module_path()),
        "config_path": str(config_path),
        "state_root": str(root / "state"),
        "provider_revision_id": builder.base["runtime"]["provider_revision_id"],
        "registry": {
            "resource_sha256": "sha256:"
            + hashlib.sha256(registry_path.read_bytes()).hexdigest(),
            "registry_digest": builder.registry_digest,
        },
        "tls": {
            "algorithm": "Ed25519",
            "ca_certificate_path": str(builder.pki.ca_file),
            "client_certificate_path": str(builder.pki.client.certificate),
            "client_private_key_path": str(builder.pki.client.private_key),
            "ca_sha256_fingerprint": "sha256:" + ca_fingerprint,
            "client_uri_san": CALLER_URI,
            "client_token_subject": CALLER_SUBJECT,
        },
        "start": _invocation(
            root,
            "start",
            operation="start",
            token=start_token,
            runtime_run_id=cast(str, start["runtime_run_id"]),
            invocation_id=cast(str, start["invocation_id"]),
            invocation_attempt_id=cast(str, start["invocation_attempt_id"]),
            fencing_token=cast(int, start["fencing_token"]),
            request_digest=cast(str, start["request_digest"]),
            body=start_body,
        ),
        "status": _invocation(
            root,
            "status",
            operation="read_status",
            token=status_token,
            runtime_run_id=cast(str, start["runtime_run_id"]),
            invocation_id=cast(str, start["invocation_id"]),
            invocation_attempt_id=cast(str, start["invocation_attempt_id"]),
            fencing_token=1,
            request_digest=cast(str, status_claims["operation_request_digest"]),
        ),
        "command": _invocation(
            root,
            "command",
            operation="submit_command",
            token=command_token,
            runtime_run_id=cast(str, command["runtime_run_id"]),
            invocation_id=cast(str, command["invocation_id"]),
            invocation_attempt_id=cast(str, command["invocation_attempt_id"]),
            fencing_token=cast(int, command["fencing_token"]),
            request_digest=cast(str, command["command_digest"]),
            body=command_body,
        ),
        "events": {
            **_invocation(
                root,
                "events",
                operation="read_events",
                token=events_token,
                runtime_run_id=cast(str, start["runtime_run_id"]),
                invocation_id=cast(str, start["invocation_id"]),
                invocation_attempt_id=cast(str, start["invocation_attempt_id"]),
                fencing_token=2,
                request_digest=cast(str, events_claims["operation_request_digest"]),
            ),
            "after_event_sequence": 0,
            "limit": 1000,
        },
        "missing_status": _invocation(
            root,
            "missing-status",
            operation="read_status",
            token=missing_token,
            runtime_run_id=missing_runtime_run_id,
            invocation_id=cast(str, start["invocation_id"]),
            invocation_attempt_id=cast(str, start["invocation_attempt_id"]),
            fencing_token=1,
            request_digest=cast(str, missing_claims["operation_request_digest"]),
        ),
        "stale_command": _invocation(
            root,
            "stale-command",
            operation="submit_command",
            token=stale_token,
            runtime_run_id=cast(str, stale_command["runtime_run_id"]),
            invocation_id=cast(str, stale_command["invocation_id"]),
            invocation_attempt_id=cast(str, stale_command["invocation_attempt_id"]),
            fencing_token=cast(int, stale_command["fencing_token"]),
            request_digest=cast(str, stale_command["command_digest"]),
            body=stale_body,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    arguments = parser.parse_args()
    fixture = build_fixture(arguments.output_root.resolve())
    arguments.manifest.write_text(
        json.dumps(fixture, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    arguments.manifest.chmod(0o600)


if __name__ == "__main__":
    main()
