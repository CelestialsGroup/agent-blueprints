from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jsonschema import ValidationError

from .build_identity import BUILD_IDENTITY
from .contract_projection import (
    DEFAULT_MAX_JSON_DEPTH,
    DEFAULT_MAX_JSON_NODES,
    DEFAULT_MAX_NUMBER_TOKEN_BYTES,
    build_draft202012_validator,
    canonicalize_json,
    decode_strict_ijson,
)
from .errors import (
    ConfigurationError,
    ContractSchemaError,
    StrictJsonError,
    TokenValidationError,
)
from .model import MutationAdmission

type JwsAlgorithm = Literal["EdDSA", "ES256"]
type RuntimeOperation = Literal["start", "read_status", "submit_command", "read_events"]
type PublicVerificationKey = ed25519.Ed25519PublicKey | ec.EllipticCurvePublicKey

EXPECTED_OPERATION_BINDINGS: dict[RuntimeOperation, tuple[str, str]] = {
    "start": (
        "urn:agent-platform:agent-runtime-start-request:v1",
        "rfc8785-request-excluding-request-digest-v1",
    ),
    "submit_command": (
        "urn:agent-platform:agent-runtime-command:v1",
        "rfc8785-command-excluding-command-digest-v1",
    ),
    "read_status": (
        "urn:agent-platform:agent-runtime-status-operation-descriptor:v1",
        "rfc8785-full-document-v1",
    ),
    "read_events": (
        "urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1",
        "rfc8785-full-document-v1",
    ),
}


@dataclass(frozen=True, slots=True)
class VerificationKey:
    kid: str
    algorithm: JwsAlgorithm
    public_key_pem: bytes = field(repr=False)
    _public_key: PublicVerificationKey = field(init=False, repr=False, compare=False)
    _fingerprint: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 1 <= len(self.kid) <= 200:
            raise ConfigurationError("verification key kid length is invalid")
        try:
            loaded = load_pem_public_key(self.public_key_pem)
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                "verification key is not a public PEM key"
            ) from error
        if self.algorithm == "EdDSA":
            if not isinstance(loaded, ed25519.Ed25519PublicKey):
                raise ConfigurationError("EdDSA requires an Ed25519 public key")
        elif self.algorithm == "ES256":
            if not isinstance(loaded, ec.EllipticCurvePublicKey) or not isinstance(
                loaded.curve, ec.SECP256R1
            ):
                raise ConfigurationError("ES256 requires a P-256 public key")
        else:
            raise ConfigurationError("verification key algorithm is not admitted")
        encoded = loaded.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        object.__setattr__(self, "_public_key", loaded)
        object.__setattr__(
            self, "_fingerprint", "sha256:" + hashlib.sha256(encoded).hexdigest()
        )

    @property
    def public_key(self) -> PublicVerificationKey:
        return self._public_key

    @property
    def fingerprint(self) -> str:
        return self._fingerprint


@dataclass(frozen=True, slots=True)
class SecurityConfiguration:
    provider_revision_id: str
    runtime_revision: str
    provider_audience: str
    trusted_callers: frozenset[str]
    verification_keys: tuple[VerificationKey, ...]
    application_root: Path
    contract_root: Path
    max_token_bytes: int = 16 * 1024
    clock_skew_seconds: int = 5
    max_json_depth: int = DEFAULT_MAX_JSON_DEPTH
    max_json_nodes: int = DEFAULT_MAX_JSON_NODES
    max_number_token_bytes: int = DEFAULT_MAX_NUMBER_TOKEN_BYTES
    max_decimal_exponent: int = 400

    def __post_init__(self) -> None:
        if not self.provider_revision_id:
            raise ConfigurationError("provider_revision_id must not be empty")
        if not self.runtime_revision:
            raise ConfigurationError("runtime_revision must not be empty")
        if not self.provider_audience.startswith(
            "urn:agent-platform:provider-instance:"
        ):
            raise ConfigurationError("provider_audience is not a Runtime audience")
        if not self.trusted_callers or any(
            not caller for caller in self.trusted_callers
        ):
            raise ConfigurationError("trusted_callers must be a non-empty closed set")
        if not self.verification_keys:
            raise ConfigurationError("at least one verification key is required")
        kids = tuple(key.kid for key in self.verification_keys)
        if len(set(kids)) != len(kids):
            raise ConfigurationError("verification key kid values must be unique")
        if not 256 <= self.max_token_bytes <= 64 * 1024:
            raise ConfigurationError("max_token_bytes is outside the admitted range")
        if not 0 <= self.clock_skew_seconds <= 30:
            raise ConfigurationError("clock_skew_seconds must be between 0 and 30")
        if not 1 <= self.max_json_depth <= 256:
            raise ConfigurationError("max_json_depth is outside the admitted range")
        if not 1 <= self.max_json_nodes <= 1_000_000:
            raise ConfigurationError("max_json_nodes is outside the admitted range")
        if not 1 <= self.max_number_token_bytes <= 1_024:
            raise ConfigurationError(
                "max_number_token_bytes is outside the admitted range"
            )
        if not 1 <= self.max_decimal_exponent <= 400:
            raise ConfigurationError(
                "max_decimal_exponent is outside the admitted range"
            )
        for name in ("application_root", "contract_root"):
            root = cast(Path, getattr(self, name)).expanduser().resolve()
            if root == Path(root.anchor):
                raise ConfigurationError(f"{name} must not be a filesystem root")
            object.__setattr__(self, name, root)

    def key(self, kid: str) -> VerificationKey:
        for key in self.verification_keys:
            if key.kid == kid:
                return key
        raise TokenValidationError("Runtime token uses an unknown kid")

    def digest(self) -> str:
        document = {
            "application_root": str(self.application_root),
            "clock_skew_seconds": self.clock_skew_seconds,
            "contract_root": str(self.contract_root),
            "keys": [
                {
                    "algorithm": key.algorithm,
                    "fingerprint": key.fingerprint,
                    "kid": key.kid,
                }
                for key in sorted(self.verification_keys, key=lambda item: item.kid)
            ],
            "max_decimal_exponent": self.max_decimal_exponent,
            "max_json_depth": self.max_json_depth,
            "max_json_nodes": self.max_json_nodes,
            "max_number_token_bytes": self.max_number_token_bytes,
            "max_token_bytes": self.max_token_bytes,
            "provider_audience": self.provider_audience,
            "provider_revision_id": self.provider_revision_id,
            "runtime_revision": self.runtime_revision,
            "trusted_callers": sorted(self.trusted_callers),
        }
        return "sha256:" + hashlib.sha256(canonicalize_json(document)).hexdigest()


@dataclass(frozen=True, slots=True)
class InvocationContext:
    tenant_id: str
    runtime_run_id: str
    agent_run_id: str
    workflow_run_id: str
    work_order_id: str
    run_manifest_digest: str
    runtime_authorization_digest: str
    invocation_id: str
    invocation_attempt_id: str
    fencing_token: int
    policy_decision_digest: str
    execution_budget_digest: str
    effective_permissions_digest: str
    operation_request_digest: str
    command_type: str | None = None
    system_safety_control_id: str | None = None
    system_safety_control_digest: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeContractProjection:
    validators: Mapping[str, Any] = field(repr=False)
    contract_source_revision: str
    contract_manifest_digest: str
    runtime_suite_digest: str
    schema_closure_digest: str

    @classmethod
    def load(cls, configuration: SecurityConfiguration) -> RuntimeContractProjection:
        lock_path = configuration.application_root / "dependency-lock.json"
        manifest_path = (
            configuration.application_root
            / "internal/generated/runtimeapi/projection-manifest.json"
        )
        try:
            lock_value = json.loads(lock_path.read_text(encoding="utf-8"))
            manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ConfigurationError(
                "Runtime Contract lock inputs are unreadable"
            ) from error
        if not isinstance(lock_value, dict) or not isinstance(manifest_value, dict):
            raise ConfigurationError("Runtime Contract lock inputs must be objects")
        lock = cast(dict[str, Any], lock_value)
        manifest = cast(dict[str, Any], manifest_value)
        if lock.get("schema_version") != 1 or manifest.get("schema_version") != 1:
            raise ConfigurationError("Runtime Contract lock version is not admitted")
        contract_lock = _mapping(lock.get("contract"), "contract dependency lock")
        source_revision = _string(
            contract_lock.get("source_revision"), "contract source revision"
        )
        manifest_digest = _string(
            contract_lock.get("manifest_digest"), "contract manifest digest"
        )
        if (
            source_revision != BUILD_IDENTITY.contract_source_revision
            or manifest_digest != BUILD_IDENTITY.contract_manifest_digest
        ):
            raise ConfigurationError("Contract lock differs from the built Runtime")
        suites = contract_lock.get("suites")
        if not isinstance(suites, list):
            raise ConfigurationError("contract suites lock is invalid")
        runtime_suite = next(
            (
                item
                for item in suites
                if isinstance(item, dict)
                and item.get("suite_id") == BUILD_IDENTITY.conformance_suite_id
                and item.get("suite_version")
                == BUILD_IDENTITY.conformance_suite_version
            ),
            None,
        )
        if (
            runtime_suite is None
            or runtime_suite.get("suite_digest")
            != BUILD_IDENTITY.conformance_suite_digest
        ):
            raise ConfigurationError("Runtime Suite differs from the built Runtime")

        schema_entries = manifest.get("schemas")
        if not isinstance(schema_entries, list) or len(schema_entries) != manifest.get(
            "schema_count"
        ):
            raise ConfigurationError("Runtime Schema projection manifest is invalid")
        documents: list[Mapping[str, Any]] = []
        closure_hasher = hashlib.sha256()
        seen_ids: set[str] = set()
        for item in schema_entries:
            entry = _mapping(item, "Runtime Schema projection entry")
            relative = Path(_string(entry.get("path"), "Runtime Schema path"))
            if relative.is_absolute() or ".." in relative.parts:
                raise ConfigurationError("Runtime Schema path escapes Contract root")
            path = (configuration.contract_root / relative).resolve()
            if not path.is_relative_to(configuration.contract_root):
                raise ConfigurationError("Runtime Schema path escapes Contract root")
            try:
                encoded = path.read_bytes()
            except OSError as error:
                raise ConfigurationError(
                    "Runtime Schema input is unavailable"
                ) from error
            if hashlib.sha256(encoded).hexdigest() != entry.get("sha256"):
                raise ConfigurationError("Runtime Schema input digest differs")
            encoded_path = relative.as_posix().encode("utf-8")
            closure_hasher.update(len(encoded_path).to_bytes(8, "big"))
            closure_hasher.update(encoded_path)
            closure_hasher.update(len(encoded).to_bytes(8, "big"))
            closure_hasher.update(encoded)
            try:
                document_value = json.loads(encoded.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ConfigurationError(
                    "Runtime Schema input is not valid JSON"
                ) from error
            if not isinstance(document_value, dict):
                raise ConfigurationError("Runtime Schema input must be an object")
            document = cast(Mapping[str, Any], document_value)
            identifier = document.get("$id")
            if identifier != entry.get("id") or not isinstance(identifier, str):
                raise ConfigurationError("Runtime Schema $id differs from projection")
            if identifier in seen_ids:
                raise ConfigurationError("Runtime Schema projection repeats a $id")
            seen_ids.add(identifier)
            documents.append(document)
        _validate_schema_reference_closure(documents, seen_ids)
        closure_digest = closure_hasher.hexdigest()
        if (
            closure_digest != manifest.get("schema_closure_sha256")
            or closure_digest != BUILD_IDENTITY.runtime_schema_closure_sha256
        ):
            raise ConfigurationError("Runtime Schema closure digest differs")
        openapi_path = Path(_string(manifest.get("openapi_path"), "OpenAPI path"))
        if openapi_path.is_absolute() or ".." in openapi_path.parts:
            raise ConfigurationError("Runtime OpenAPI path escapes Contract root")
        resolved_openapi = (configuration.contract_root / openapi_path).resolve()
        if not resolved_openapi.is_relative_to(configuration.contract_root):
            raise ConfigurationError("Runtime OpenAPI path escapes Contract root")
        try:
            openapi_bytes = resolved_openapi.read_bytes()
        except OSError as error:
            raise ConfigurationError("Runtime OpenAPI input is unavailable") from error
        openapi_digest = hashlib.sha256(openapi_bytes).hexdigest()
        if (
            openapi_digest != manifest.get("openapi_sha256")
            or openapi_digest != BUILD_IDENTITY.runtime_openapi_sha256
        ):
            raise ConfigurationError("Runtime OpenAPI digest differs")

        schema_ids = (
            *(
                EXPECTED_OPERATION_BINDINGS[operation][0]
                for operation in (
                    "start",
                    "submit_command",
                    "read_status",
                    "read_events",
                )
            ),
            "urn:agent-platform:agent-runtime-invocation-jws-header:v1",
            "urn:agent-platform:agent-runtime-invocation-token-claims:v1",
            "urn:agent-platform:agent-runtime-capabilities:v1",
            "urn:agent-platform:agent-runtime-run-status:v1",
            "urn:agent-platform:agent-runtime-event-page:v1",
            "urn:agent-platform:standard-error:v1",
        )
        try:
            validators = {
                schema_id: build_draft202012_validator(schema_id, documents)
                for schema_id in schema_ids
            }
        except (TypeError, ValueError, ValidationError) as error:
            raise ConfigurationError(
                "Runtime Schema projection cannot be compiled"
            ) from error
        return cls(
            validators=validators,
            contract_source_revision=source_revision,
            contract_manifest_digest=manifest_digest,
            runtime_suite_digest=BUILD_IDENTITY.conformance_suite_digest,
            schema_closure_digest="sha256:" + closure_digest,
        )

    def validate(self, schema_id: str, document: object) -> None:
        try:
            validator = self.validators[schema_id]
        except KeyError as error:
            raise ContractSchemaError(
                "Runtime document uses a Schema outside the admitted projection"
            ) from error
        try:
            validator.validate(document)
        except ValidationError as error:
            raise ContractSchemaError(f"Runtime document fails {schema_id}") from error


class RuntimeTokenVerifier:
    def __init__(
        self,
        configuration: SecurityConfiguration,
        projection: RuntimeContractProjection,
    ) -> None:
        self.configuration = configuration
        self.projection = projection

    def verify(
        self,
        compact_jws: str,
        *,
        authenticated_caller: str,
        operation: RuntimeOperation,
        now: datetime,
    ) -> MutationAdmission:
        if authenticated_caller not in self.configuration.trusted_callers:
            raise TokenValidationError("authenticated caller is not admitted")
        try:
            encoded_token = compact_jws.encode("ascii")
        except UnicodeEncodeError as error:
            raise TokenValidationError(
                "Runtime token must be ASCII compact JWS"
            ) from error
        if len(encoded_token) > self.configuration.max_token_bytes:
            raise TokenValidationError("Runtime token exceeds the configured limit")
        segments = encoded_token.split(b".")
        if len(segments) != 3 or any(not segment for segment in segments):
            raise TokenValidationError("Runtime token is not a compact JWS")
        header_bytes = _decode_base64url(segments[0])
        claims_bytes = _decode_base64url(segments[1])
        _decode_base64url(segments[2])
        header = self._token_document(
            header_bytes,
            "Runtime JWS header",
            "urn:agent-platform:agent-runtime-invocation-jws-header:v1",
        )
        algorithm = _string(header.get("alg"), "Runtime JWS alg")
        kid = _string(header.get("kid"), "Runtime JWS kid")
        key = self.configuration.key(kid)
        if algorithm != key.algorithm:
            raise TokenValidationError("Runtime token algorithm and key differ")
        try:
            decoded = jwt.decode(
                compact_jws,
                key.public_key,
                algorithms=[key.algorithm],
                options={
                    "verify_aud": False,
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_iss": False,
                    "verify_nbf": False,
                },
            )
        except jwt.PyJWTError as error:
            raise TokenValidationError("Runtime token signature is invalid") from error
        claims = self._token_document(
            claims_bytes,
            "Runtime token claims",
            "urn:agent-platform:agent-runtime-invocation-token-claims:v1",
        )
        if decoded != claims:
            raise TokenValidationError("Runtime token claims decode is ambiguous")
        self._validate_claim_bindings(
            claims,
            authenticated_caller=authenticated_caller,
            operation=operation,
        )
        issued_at = _numeric_date(claims.get("iat"), "iat")
        not_before = _numeric_date(claims.get("nbf"), "nbf")
        expires_at = _numeric_date(claims.get("exp"), "exp")
        if not issued_at <= not_before < expires_at:
            raise TokenValidationError("Runtime token time ordering is invalid")
        if (expires_at - issued_at).total_seconds() > 300:
            raise TokenValidationError("Runtime token exceeds the 300 second TTL")
        now_utc = now.astimezone(UTC)
        skew = self.configuration.clock_skew_seconds
        if issued_at.timestamp() > now_utc.timestamp() + skew:
            raise TokenValidationError("Runtime token iat is in the future")
        if not_before.timestamp() > now_utc.timestamp() + skew:
            raise TokenValidationError("Runtime token is not yet valid")
        if expires_at.timestamp() <= now_utc.timestamp() - skew:
            raise TokenValidationError("Runtime token has expired")
        authority_mode = _claim_string(claims, "authority_mode")
        if authority_mode not in {"execution", "safety_control"}:
            raise TokenValidationError("Runtime token authority mode is invalid")
        return MutationAdmission(
            issuer=_claim_string(claims, "iss"),
            subject=_claim_string(claims, "sub"),
            jti=_claim_string(claims, "jti"),
            operation=operation,
            authority_mode=cast(Literal["execution", "safety_control"], authority_mode),
            issued_at=issued_at,
            not_before=not_before,
            expires_at=expires_at,
            tenant_id=_claim_string(claims, "tenant_id"),
            provider_revision_id=self.configuration.provider_revision_id,
            runtime_run_id=_claim_string(claims, "runtime_run_id"),
            agent_run_id=_claim_string(claims, "agent_run_id"),
            workflow_run_id=_claim_string(claims, "workflow_run_id"),
            work_order_id=_claim_string(claims, "work_order_id"),
            run_manifest_digest=_claim_string(claims, "run_manifest_digest"),
            runtime_authorization_digest=_claim_string(
                claims, "runtime_authorization_digest"
            ),
            invocation_id=_claim_string(claims, "invocation_id"),
            invocation_attempt_id=_claim_string(claims, "invocation_attempt_id"),
            fencing_token=_claim_integer(claims, "fencing_token"),
            policy_decision_digest=_claim_string(claims, "policy_decision_digest"),
            execution_budget_digest=_claim_string(claims, "execution_budget_digest"),
            effective_permissions_digest=_claim_string(
                claims, "effective_permissions_digest"
            ),
            operation_contract_id=EXPECTED_OPERATION_BINDINGS[operation][0],
            operation_digest_profile=EXPECTED_OPERATION_BINDINGS[operation][1],
            operation_request_digest=_claim_string(claims, "operation_request_digest"),
            system_safety_control_id=_optional_claim_string(
                claims, "system_safety_control_id"
            ),
            system_safety_control_digest=_optional_claim_string(
                claims, "system_safety_control_digest"
            ),
            clock_skew_seconds=skew,
        )

    def _strict_document(self, encoded: bytes, name: str) -> dict[str, Any]:
        try:
            value = decode_strict_ijson(
                encoded,
                max_depth=self.configuration.max_json_depth,
                max_nodes=self.configuration.max_json_nodes,
                max_number_token_bytes=self.configuration.max_number_token_bytes,
                max_decimal_exponent=self.configuration.max_decimal_exponent,
            )
        except ValueError as error:
            raise StrictJsonError(f"{name} is not Strict I-JSON") from error
        if not isinstance(value, dict) or any(
            not isinstance(key, str) for key in value
        ):
            raise StrictJsonError(f"{name} must be a JSON object")
        return cast(dict[str, Any], value)

    def _token_document(
        self, encoded: bytes, name: str, schema_id: str
    ) -> dict[str, Any]:
        try:
            document = self._strict_document(encoded, name)
            self.projection.validate(schema_id, document)
        except (ContractSchemaError, StrictJsonError) as error:
            raise TokenValidationError(
                "Runtime token document is not admitted"
            ) from error
        return document

    def _validate_claim_bindings(
        self,
        claims: Mapping[str, Any],
        *,
        authenticated_caller: str,
        operation: RuntimeOperation,
    ) -> None:
        expected_contract, expected_profile = EXPECTED_OPERATION_BINDINGS[operation]
        expected = {
            "aud": self.configuration.provider_audience,
            "iss": "agent-platform",
            "operation": operation,
            "operation_contract_id": expected_contract,
            "operation_digest_profile": expected_profile,
            "provider_revision_id": self.configuration.provider_revision_id,
            "sub": authenticated_caller,
        }
        if any(claims.get(name) != value for name, value in expected.items()):
            raise TokenValidationError(
                "Runtime token does not match the operation execution context"
            )
        authority_mode = claims.get("authority_mode")
        if operation == "start" and authority_mode != "execution":
            raise TokenValidationError("Start requires execution authority")
        if operation in {"read_status", "read_events"} and authority_mode != (
            "safety_control"
        ):
            raise TokenValidationError("Runtime reads require safety-control authority")
        if operation == "submit_command" and authority_mode == "safety_control":
            if (
                claims.get("system_safety_control_id") is None
                or claims.get("system_safety_control_digest") is None
            ):
                raise TokenValidationError(
                    "safety-control token lacks its command authority binding"
                )
        elif any(
            name in claims
            for name in (
                "system_safety_control_id",
                "system_safety_control_digest",
            )
        ):
            raise TokenValidationError(
                "Runtime token adds an unadmitted safety-control binding"
            )


def _decode_base64url(segment: bytes) -> bytes:
    if any(
        byte not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for byte in segment
    ):
        raise TokenValidationError("Runtime token contains invalid base64url")
    if len(segment) % 4 == 1:
        raise TokenValidationError("Runtime token contains invalid base64url")
    padding = b"=" * (-len(segment) % 4)
    try:
        decoded = base64.b64decode(segment + padding, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as error:
        raise TokenValidationError(
            "Runtime token contains invalid base64url"
        ) from error
    if base64.urlsafe_b64encode(decoded).rstrip(b"=") != segment:
        raise TokenValidationError("Runtime token base64url is not canonical")
    return decoded


def _validate_schema_reference_closure(
    documents: list[Mapping[str, Any]], schema_ids: set[str]
) -> None:
    pending: list[object] = list(documents)
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and not reference.startswith("#"):
                target = reference.partition("#")[0]
                if target not in schema_ids:
                    raise ConfigurationError(
                        "Runtime Schema reference escapes the admitted closure"
                    )
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def _numeric_date(value: object, name: str) -> datetime:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TokenValidationError(f"Runtime token {name} is not an integer")
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise TokenValidationError(
            f"Runtime token {name} is outside datetime range"
        ) from error


def _claim_string(claims: Mapping[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise TokenValidationError(f"Runtime token {name} is not a non-empty string")
    return value


def _optional_claim_string(claims: Mapping[str, Any], name: str) -> str | None:
    if name not in claims:
        return None
    return _claim_string(claims, name)


def _claim_integer(claims: Mapping[str, Any], name: str) -> int:
    value = claims.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TokenValidationError(f"Runtime token {name} is not an integer")
    return value


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ConfigurationError(f"{name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{name} must be a non-empty string")
    return value
