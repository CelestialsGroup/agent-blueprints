from __future__ import annotations

import hashlib
import hmac
import ssl
import stat
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

from .errors import ConfigurationError
from .process_config import ProviderProcessConfiguration


class PeerCertificateError(Exception):
    pass


class PeerIdentityNotAllowedError(PeerCertificateError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedCaller:
    certificate_uri: str
    token_subject: str
    certificate_fingerprint: str
    _comparison_subject: bytes = field(repr=False)

    def require_token_subject(self, subject: str) -> None:
        try:
            encoded = subject.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise PeerIdentityNotAllowedError(
                "Runtime token subject is not valid UTF-8"
            ) from error
        if not hmac.compare_digest(encoded, self._comparison_subject):
            raise PeerIdentityNotAllowedError(
                "Runtime token subject does not match the mTLS identity"
            )


@dataclass(frozen=True, slots=True)
class TLSMaterialSnapshot:
    server_certificate: bytes = field(repr=False)
    server_private_key: bytes = field(repr=False)
    client_ca: bytes = field(repr=False)


def build_server_tls_context(
    configuration: ProviderProcessConfiguration,
) -> ssl.SSLContext:
    snapshot = _load_and_validate_tls_material(configuration)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = False
    context.options |= ssl.OP_NO_COMPRESSION
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        context.verify_flags |= ssl.VERIFY_X509_STRICT
    try:
        context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20")
        context.load_verify_locations(cafile=str(configuration.client_ca_file))
        context.load_cert_chain(
            certfile=str(configuration.server_certificate_file),
            keyfile=str(configuration.server_private_key_file),
        )
    except (OSError, ssl.SSLError) as error:
        raise ConfigurationError("TLS server material cannot be loaded") from error
    if snapshot != _load_tls_snapshot(configuration):
        raise ConfigurationError("TLS material changed while the context was loaded")
    return context


def authenticate_peer_certificate(
    encoded_certificate: bytes,
    configuration: ProviderProcessConfiguration,
    *,
    now: datetime | None = None,
) -> AuthenticatedCaller:
    if not encoded_certificate:
        raise PeerCertificateError("mTLS peer certificate is missing")
    try:
        certificate = x509.load_der_x509_certificate(encoded_certificate)
    except ValueError as error:
        raise PeerCertificateError("mTLS peer certificate is invalid") from error
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if (
        not certificate.not_valid_before_utc
        <= current
        < certificate.not_valid_after_utc
    ):
        raise PeerCertificateError(
            "mTLS peer certificate is outside its validity window"
        )
    try:
        extended_key_usage = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
    except x509.ExtensionNotFound as error:
        raise PeerCertificateError(
            "mTLS peer certificate lacks clientAuth EKU"
        ) from error
    if ExtendedKeyUsageOID.CLIENT_AUTH not in extended_key_usage:
        raise PeerCertificateError("mTLS peer certificate lacks clientAuth EKU")
    try:
        key_usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
    except x509.ExtensionNotFound:
        key_usage = None
    if key_usage is not None and not key_usage.digital_signature:
        raise PeerCertificateError(
            "mTLS peer certificate cannot authenticate a TLS signature"
        )
    try:
        subject_alternative_name = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as error:
        raise PeerCertificateError(
            "mTLS peer certificate lacks a URI identity"
        ) from error
    identities = subject_alternative_name.get_values_for_type(
        x509.UniformResourceIdentifier
    )
    if len(identities) != 1:
        raise PeerCertificateError(
            "mTLS peer certificate must contain exactly one URI identity"
        )
    certificate_uri = identities[0]
    binding = next(
        (
            item
            for item in configuration.client_identities
            if hmac.compare_digest(item.certificate_uri, certificate_uri)
        ),
        None,
    )
    if binding is None:
        raise PeerIdentityNotAllowedError(
            "mTLS peer identity is outside the exact allowlist"
        )
    fingerprint = "sha256:" + certificate.fingerprint(hashes.SHA256()).hex()
    return AuthenticatedCaller(
        certificate_uri=certificate_uri,
        token_subject=binding.token_subject,
        certificate_fingerprint=fingerprint,
        _comparison_subject=binding.token_subject.encode("utf-8"),
    )


def _load_and_validate_tls_material(
    configuration: ProviderProcessConfiguration,
) -> TLSMaterialSnapshot:
    snapshot = _load_tls_snapshot(configuration)
    now = datetime.now(UTC)
    try:
        server_certificates = x509.load_pem_x509_certificates(
            snapshot.server_certificate
        )
        ca_certificates = x509.load_pem_x509_certificates(snapshot.client_ca)
        private_key = serialization.load_pem_private_key(
            snapshot.server_private_key, password=None
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError("TLS material is not valid PEM") from error
    if not server_certificates:
        raise ConfigurationError("server certificate chain is empty")
    server = server_certificates[0]
    if not server.not_valid_before_utc <= now < server.not_valid_after_utc:
        raise ConfigurationError("server certificate is outside its validity window")
    try:
        server_eku = server.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
    except x509.ExtensionNotFound as error:
        raise ConfigurationError("server certificate lacks serverAuth EKU") from error
    if ExtendedKeyUsageOID.SERVER_AUTH not in server_eku:
        raise ConfigurationError("server certificate lacks serverAuth EKU")
    server_public = server.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_public = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if not hmac.compare_digest(server_public, private_public):
        raise ConfigurationError("server certificate and private key differ")
    if not ca_certificates:
        raise ConfigurationError("client CA bundle is empty")
    for certificate in ca_certificates:
        try:
            constraints = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
        except x509.ExtensionNotFound as error:
            raise ConfigurationError("client CA lacks BasicConstraints") from error
        if not constraints.ca:
            raise ConfigurationError("client CA bundle contains a non-CA certificate")
        if (
            not certificate.not_valid_before_utc
            <= now
            < certificate.not_valid_after_utc
        ):
            raise ConfigurationError("client CA is outside its validity window")
    return snapshot


def _load_tls_snapshot(
    configuration: ProviderProcessConfiguration,
) -> TLSMaterialSnapshot:
    return TLSMaterialSnapshot(
        server_certificate=_read_tls_file(
            configuration.server_certificate_file, "server certificate"
        ),
        server_private_key=_read_tls_file(
            configuration.server_private_key_file,
            "server private key",
            private=True,
        ),
        client_ca=_read_tls_file(configuration.client_ca_file, "client CA"),
    )


def _read_tls_file(path: Path, name: str, *, private: bool = False) -> bytes:
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise ConfigurationError(f"{name} is unavailable") from error
    if not stat.S_ISREG(file_stat.st_mode) or stat.S_ISLNK(file_stat.st_mode):
        raise ConfigurationError(f"{name} must be a regular non-symlink file")
    if private and stat.S_IMODE(file_stat.st_mode) != 0o600:
        raise ConfigurationError("server private key permissions must be 0600")
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise ConfigurationError(f"{name} is unreadable") from error
    if not encoded:
        raise ConfigurationError(f"{name} must not be empty")
    return encoded


def public_certificate_fingerprint(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
