from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from .build_identity import BUILD_IDENTITY
from .contract_projection import canonicalize_json, decode_strict_ijson
from .errors import ConfigurationDriftError, ConfigurationError
from .model import RuntimeConfiguration
from .security import SecurityConfiguration, VerificationKey

CONFIG_ENVIRONMENT_VARIABLE = "AGENT_NATIVE_RUNTIME_CONFIG_FILE"
PROCESS_BINDING_FILE = "process-configuration-v1.json"
CAPABILITY_FEATURES = frozenset(
    {
        "runtime.start",
        "runtime.pause",
        "runtime.resume",
        "runtime.cancel",
        "runtime.events.cursor",
        "runtime.checkpoint.export",
        "runtime.checkpoint.restore",
    }
)


@dataclass(frozen=True, slots=True)
class ClientIdentityBinding:
    certificate_uri: str
    token_subject: str

    def __post_init__(self) -> None:
        if not self.certificate_uri.startswith("spiffe://"):
            raise ConfigurationError("client certificate identity must be a SPIFFE URI")
        if not 1 <= len(self.certificate_uri) <= 2_048:
            raise ConfigurationError("client certificate identity length is invalid")
        if not 1 <= len(self.token_subject) <= 500:
            raise ConfigurationError("client token subject length is invalid")


@dataclass(frozen=True, slots=True)
class HTTPProcessLimits:
    max_connections: int
    max_concurrent_requests: int
    max_requests_per_connection: int
    max_request_line_bytes: int
    max_header_bytes: int
    max_header_count: int
    max_response_bytes: int
    listen_backlog: int
    socket_send_buffer_bytes: int
    tls_handshake_timeout_ms: int
    idle_timeout_ms: int
    read_timeout_ms: int
    write_timeout_ms: int
    drain_timeout_ms: int

    def __post_init__(self) -> None:
        ranges = (
            ("max_connections", self.max_connections, 1, 128),
            ("max_concurrent_requests", self.max_concurrent_requests, 1, 128),
            ("max_requests_per_connection", self.max_requests_per_connection, 1, 1_000),
            ("max_request_line_bytes", self.max_request_line_bytes, 256, 16_384),
            ("max_header_bytes", self.max_header_bytes, 1_024, 65_536),
            ("max_header_count", self.max_header_count, 1, 100),
            ("max_response_bytes", self.max_response_bytes, 256, 1_048_576),
            ("listen_backlog", self.listen_backlog, 1, 128),
            (
                "socket_send_buffer_bytes",
                self.socket_send_buffer_bytes,
                1_024,
                1_048_576,
            ),
            ("tls_handshake_timeout_ms", self.tls_handshake_timeout_ms, 50, 60_000),
            ("idle_timeout_ms", self.idle_timeout_ms, 50, 60_000),
            ("read_timeout_ms", self.read_timeout_ms, 50, 60_000),
            ("write_timeout_ms", self.write_timeout_ms, 50, 60_000),
            ("drain_timeout_ms", self.drain_timeout_ms, 100, 60_000),
        )
        for name, value, minimum, maximum in ranges:
            if not minimum <= value <= maximum:
                raise ConfigurationError(
                    f"{name} must be between {minimum} and {maximum}"
                )
        if self.max_concurrent_requests > self.max_connections:
            raise ConfigurationError(
                "max_concurrent_requests cannot exceed max_connections"
            )


@dataclass(frozen=True, slots=True)
class ProviderProcessConfiguration:
    runtime: RuntimeConfiguration
    security: SecurityConfiguration
    bind_host: str
    bind_port: int
    server_certificate_file: Path
    server_private_key_file: Path
    client_ca_file: Path
    client_identities: tuple[ClientIdentityBinding, ...]
    limits: HTTPProcessLimits
    runtime_name: str
    runtime_version: str
    features: tuple[str, ...]
    source_file: Path
    source_sha256: str

    def __post_init__(self) -> None:
        if self.bind_host != "127.0.0.1":
            raise ConfigurationError(
                "the component-only Provider process must bind to 127.0.0.1"
            )
        if not 0 <= self.bind_port <= 65_535:
            raise ConfigurationError("bind_port is outside the TCP port range")
        if not 1 <= len(self.runtime_name) <= 32_768:
            raise ConfigurationError("runtime_name length is invalid")
        if not 1 <= len(self.runtime_version) <= 200:
            raise ConfigurationError("runtime_version length is invalid")
        if not self.features or len(set(self.features)) != len(self.features):
            raise ConfigurationError("capability features must be non-empty and unique")
        if not set(self.features).issubset(CAPABILITY_FEATURES):
            raise ConfigurationError(
                "capability features exceed the implemented subset"
            )
        checkpoint_features = {
            "runtime.checkpoint.export",
            "runtime.checkpoint.restore",
        }
        if bool(
            set(self.features) & checkpoint_features
        ) != checkpoint_features.issubset(self.features):
            raise ConfigurationError(
                "checkpoint export and restore capabilities must be advertised together"
            )
        uris = tuple(item.certificate_uri for item in self.client_identities)
        subjects = tuple(item.token_subject for item in self.client_identities)
        if not uris or len(set(uris)) != len(uris):
            raise ConfigurationError(
                "client certificate identities must be a non-empty exact allowlist"
            )
        if len(set(subjects)) != len(subjects):
            raise ConfigurationError(
                "client certificate identities must map one-to-one to token subjects"
            )
        if frozenset(subjects) != self.security.trusted_callers:
            raise ConfigurationError(
                "client identity token subjects must exactly match trusted_callers"
            )
        for name in (
            "server_certificate_file",
            "server_private_key_file",
            "client_ca_file",
            "source_file",
        ):
            path = cast(Path, getattr(self, name)).expanduser().resolve()
            if path == Path(path.anchor):
                raise ConfigurationError(f"{name} must not be a filesystem root")
            object.__setattr__(self, name, path)

    def capabilities_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "protocol_version": "v1",
            "provider_revision_id": self.runtime.provider_revision_id,
            "runtime_name": self.runtime_name,
            "runtime_version": self.runtime_version,
            "features": list(self.features),
            "limits": {
                "max_input_bytes": 8 * 1024 * 1024,
                "max_event_batch": 1_000,
                "max_checkpoint_bytes": self.runtime.max_checkpoint_bytes,
            },
            "event_registries": [
                {
                    "registry_id": self.runtime.event_registry_id,
                    "registry_version": self.runtime.event_registry_version,
                    "registry_digest": self.runtime.event_registry_digest,
                }
            ],
        }
        if "runtime.checkpoint.export" in self.features:
            document["checkpoint_profiles"] = [
                {
                    "profile_id": self.runtime.checkpoint_profile,
                    "suite_id": BUILD_IDENTITY.conformance_suite_id,
                    "suite_version": BUILD_IDENTITY.conformance_suite_version,
                    "suite_digest": BUILD_IDENTITY.conformance_suite_digest,
                }
            ]
        return document

    def binding_bytes(self) -> bytes:
        document = {
            "capabilities_digest": "sha256:"
            + hashlib.sha256(
                canonicalize_json(self.capabilities_document())
            ).hexdigest(),
            "configuration_sha256": self.source_sha256,
            "schema_version": 1,
        }
        return (
            json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("ascii")


def resolve_configuration_path(
    explicit_path: str | None, environment: Mapping[str, str] | None = None
) -> Path:
    values = dict(os.environ if environment is None else environment)
    environment_path = values.get(CONFIG_ENVIRONMENT_VARIABLE)
    if (
        explicit_path is not None
        and environment_path is not None
        and Path(explicit_path).expanduser().resolve()
        != Path(environment_path).expanduser().resolve()
    ):
        raise ConfigurationError(
            "CLI and environment configuration paths must not conflict"
        )
    selected = explicit_path or environment_path
    if selected is None:
        raise ConfigurationError(
            f"configuration requires --config or {CONFIG_ENVIRONMENT_VARIABLE}"
        )
    return Path(selected).expanduser().resolve()


def load_process_configuration(path: Path) -> ProviderProcessConfiguration:
    encoded = _read_regular_file(path, "process configuration")
    try:
        value = decode_strict_ijson(encoded)
    except ValueError as error:
        raise ConfigurationError(
            "process configuration is not bounded Strict I-JSON"
        ) from error
    root = _closed_mapping(
        value,
        "process configuration",
        required={"schema_version", "runtime", "security", "process", "capabilities"},
    )
    if _integer(root, "schema_version") != 1:
        raise ConfigurationError("process configuration schema_version is not admitted")
    base = path.parent.resolve()
    runtime_value = _closed_mapping(
        root["runtime"],
        "runtime configuration",
        required={
            "provider_revision_id",
            "runtime_revision",
            "provider_audience",
            "event_registry_id",
            "event_registry_version",
            "event_registry_digest",
            "state_root",
            "checkpoint_profile",
            "max_checkpoint_bytes",
            "sqlite_busy_timeout_ms",
            "work_lease_seconds",
        },
    )
    runtime = RuntimeConfiguration(
        provider_revision_id=_string(runtime_value, "provider_revision_id"),
        runtime_revision=_string(runtime_value, "runtime_revision"),
        provider_audience=_string(runtime_value, "provider_audience"),
        event_registry_id=_string(runtime_value, "event_registry_id"),
        event_registry_version=_integer(runtime_value, "event_registry_version"),
        event_registry_digest=_string(runtime_value, "event_registry_digest"),
        state_root=_path(runtime_value, "state_root", base),
        checkpoint_profile=_string(runtime_value, "checkpoint_profile"),
        max_checkpoint_bytes=_integer(runtime_value, "max_checkpoint_bytes"),
        sqlite_busy_timeout_ms=_integer(runtime_value, "sqlite_busy_timeout_ms"),
        work_lease_seconds=_integer(runtime_value, "work_lease_seconds"),
    )
    security_value = _closed_mapping(
        root["security"],
        "security configuration",
        required={
            "trusted_callers",
            "verification_keys",
            "application_root",
            "contract_root",
            "max_token_bytes",
            "clock_skew_seconds",
            "max_json_depth",
            "max_json_nodes",
            "max_number_token_bytes",
            "max_decimal_exponent",
        },
    )
    callers = _string_tuple(security_value, "trusted_callers")
    key_values = _mapping_tuple(security_value, "verification_keys")
    keys: list[VerificationKey] = []
    for index, key_value in enumerate(key_values):
        admitted = _closed_mapping(
            key_value,
            f"verification key {index}",
            required={"kid", "algorithm", "public_key_file"},
        )
        algorithm = _string(admitted, "algorithm")
        if algorithm not in {"EdDSA", "ES256"}:
            raise ConfigurationError("verification key algorithm is not admitted")
        keys.append(
            VerificationKey(
                kid=_string(admitted, "kid"),
                algorithm=cast(Literal["EdDSA", "ES256"], algorithm),
                public_key_pem=_read_regular_file(
                    _path(admitted, "public_key_file", base),
                    f"verification key {index}",
                ),
            )
        )
    security = SecurityConfiguration(
        provider_revision_id=runtime.provider_revision_id,
        runtime_revision=runtime.runtime_revision,
        provider_audience=runtime.provider_audience,
        trusted_callers=frozenset(callers),
        verification_keys=tuple(keys),
        application_root=_path(security_value, "application_root", base),
        contract_root=_path(security_value, "contract_root", base),
        max_token_bytes=_integer(security_value, "max_token_bytes"),
        clock_skew_seconds=_integer(security_value, "clock_skew_seconds"),
        max_json_depth=_integer(security_value, "max_json_depth"),
        max_json_nodes=_integer(security_value, "max_json_nodes"),
        max_number_token_bytes=_integer(security_value, "max_number_token_bytes"),
        max_decimal_exponent=_integer(security_value, "max_decimal_exponent"),
    )
    process_value = _closed_mapping(
        root["process"],
        "Provider process configuration",
        required={
            "bind_host",
            "bind_port",
            "server_certificate_file",
            "server_private_key_file",
            "client_ca_file",
            "client_identities",
            "limits",
        },
    )
    identity_values = _mapping_tuple(process_value, "client_identities")
    identities = tuple(
        ClientIdentityBinding(
            certificate_uri=_string(
                _closed_mapping(
                    item,
                    f"client identity {index}",
                    required={"certificate_uri", "token_subject"},
                ),
                "certificate_uri",
            ),
            token_subject=_string(
                _closed_mapping(
                    item,
                    f"client identity {index}",
                    required={"certificate_uri", "token_subject"},
                ),
                "token_subject",
            ),
        )
        for index, item in enumerate(identity_values)
    )
    limits_value = _closed_mapping(
        process_value["limits"],
        "HTTP process limits",
        required={
            "max_connections",
            "max_concurrent_requests",
            "max_requests_per_connection",
            "max_request_line_bytes",
            "max_header_bytes",
            "max_header_count",
            "max_response_bytes",
            "listen_backlog",
            "socket_send_buffer_bytes",
            "tls_handshake_timeout_ms",
            "idle_timeout_ms",
            "read_timeout_ms",
            "write_timeout_ms",
            "drain_timeout_ms",
        },
    )
    limits = HTTPProcessLimits(
        **{
            name: _integer(limits_value, name)
            for name in (
                "max_connections",
                "max_concurrent_requests",
                "max_requests_per_connection",
                "max_request_line_bytes",
                "max_header_bytes",
                "max_header_count",
                "max_response_bytes",
                "listen_backlog",
                "socket_send_buffer_bytes",
                "tls_handshake_timeout_ms",
                "idle_timeout_ms",
                "read_timeout_ms",
                "write_timeout_ms",
                "drain_timeout_ms",
            )
        }
    )
    capabilities_value = _closed_mapping(
        root["capabilities"],
        "capabilities configuration",
        required={"runtime_name", "runtime_version", "features"},
    )
    configuration = ProviderProcessConfiguration(
        runtime=runtime,
        security=security,
        bind_host=_string(process_value, "bind_host"),
        bind_port=_integer(process_value, "bind_port"),
        server_certificate_file=_path(process_value, "server_certificate_file", base),
        server_private_key_file=_path(process_value, "server_private_key_file", base),
        client_ca_file=_path(process_value, "client_ca_file", base),
        client_identities=identities,
        limits=limits,
        runtime_name=_string(capabilities_value, "runtime_name"),
        runtime_version=_string(capabilities_value, "runtime_version"),
        features=_string_tuple(capabilities_value, "features"),
        source_file=path,
        source_sha256="sha256:" + hashlib.sha256(encoded).hexdigest(),
    )
    if path.is_symlink():
        raise ConfigurationError("process configuration must not be a symlink")
    return configuration


def migrate_process_configuration(
    configuration: ProviderProcessConfiguration,
) -> None:
    target = configuration.runtime.state_root / PROCESS_BINDING_FILE
    expected = configuration.binding_bytes()
    if target.exists() or target.is_symlink():
        _check_process_binding(target, expected)
        return
    temporary = configuration.runtime.state_root / (
        f".{PROCESS_BINDING_FILE}.{uuid.uuid4().hex}.partial"
    )
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(expected)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            _check_process_binding(target, expected)
        else:
            _fsync_directory(configuration.runtime.state_root)
    finally:
        temporary.unlink(missing_ok=True)


def check_process_configuration_current(
    configuration: ProviderProcessConfiguration,
) -> None:
    _check_process_binding(
        configuration.runtime.state_root / PROCESS_BINDING_FILE,
        configuration.binding_bytes(),
    )


def _check_process_binding(path: Path, expected: bytes) -> None:
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise ConfigurationDriftError(
            "immutable process configuration binding is unavailable"
        ) from error
    if (
        not stat.S_ISREG(file_stat.st_mode)
        or stat.S_ISLNK(file_stat.st_mode)
        or stat.S_IMODE(file_stat.st_mode) != 0o600
    ):
        raise ConfigurationDriftError(
            "immutable process configuration binding has drifted"
        )
    try:
        actual = path.read_bytes()
    except OSError as error:
        raise ConfigurationDriftError(
            "immutable process configuration binding is unreadable"
        ) from error
    if actual != expected:
        raise ConfigurationDriftError(
            "immutable process configuration differs from the state root binding"
        )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_regular_file(path: Path, name: str) -> bytes:
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise ConfigurationError(f"{name} is unavailable") from error
    if not stat.S_ISREG(file_stat.st_mode) or stat.S_ISLNK(file_stat.st_mode):
        raise ConfigurationError(f"{name} must be a regular non-symlink file")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ConfigurationError(f"{name} is unreadable") from error


def _closed_mapping(
    value: object, name: str, *, required: set[str]
) -> Mapping[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ConfigurationError(f"{name} must be an object")
    admitted = cast(Mapping[str, Any], value)
    if set(admitted) != required:
        raise ConfigurationError(f"{name} fields do not match the closed configuration")
    return admitted


def _mapping_tuple(document: Mapping[str, Any], field: str) -> tuple[object, ...]:
    value = document.get(field)
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{field} must be a non-empty array")
    return tuple(value)


def _string_tuple(document: Mapping[str, Any], field: str) -> tuple[str, ...]:
    values = _mapping_tuple(document, field)
    if any(not isinstance(value, str) or not value for value in values):
        raise ConfigurationError(f"{field} must contain non-empty strings")
    return cast(tuple[str, ...], values)


def _string(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{field} must be a non-empty string")
    return value


def _integer(document: Mapping[str, Any], field: str) -> int:
    value = document.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{field} must be an integer")
    return value


def _path(document: Mapping[str, Any], field: str, base: Path) -> Path:
    raw = Path(_string(document, field)).expanduser()
    return (raw if raw.is_absolute() else base / raw).resolve()
