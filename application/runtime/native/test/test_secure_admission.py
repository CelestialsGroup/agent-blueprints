from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from agent_native_runtime.admission import SecureAdmissionCore
from agent_native_runtime.contract_projection import canonicalize_json
from agent_native_runtime.errors import (
    AdmissionError,
    AuthorizationBindingError,
    ConfigurationDriftError,
    ConfigurationError,
    DigestMismatchError,
    EncodedBodyTooLargeError,
    MutationReplayError,
    StaleFencingError,
    StrictJsonError,
    TokenValidationError,
)
from agent_native_runtime.kernel import NativeRuntimeKernel
from agent_native_runtime.model import RuntimeConfiguration, format_timestamp
from agent_native_runtime.security import (
    RuntimeContractProjection,
    SecurityConfiguration,
    VerificationKey,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()
CALLER = "spn_agent_runtime_controller"


def document_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonicalize_json(value)).hexdigest()


def refresh_self_digest(document: dict[str, Any], field: str) -> None:
    unsigned = dict(document)
    unsigned.pop(field, None)
    document[field] = document_digest(unsigned)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class Executor:
    def start(self, runtime_run_id: str, restored_state: bytes | None) -> None:
        del runtime_run_id, restored_state

    def cancel(self, runtime_run_id: str) -> str:
        return f"test-executor://cancellation/{runtime_run_id}"

    def checkpoint(self, runtime_run_id: str) -> bytes:
        return runtime_run_id.encode()


class SecureAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.clock = FakeClock()
        self.eddsa_private = ed25519.Ed25519PrivateKey.generate()
        self.es256_private = ec.generate_private_key(ec.SECP256R1())
        self.runtime_configuration = RuntimeConfiguration(
            provider_revision_id="apr_01J00000000000000000000000",
            runtime_revision="native-runtime-secure-test-v1",
            provider_audience=(
                "urn:agent-platform:provider-instance:api_native_runtime"
            ),
            event_registry_id="agent-runtime-core",
            event_registry_version=1,
            event_registry_digest=(
                "sha256:d60c4b90063af5d3b889b10d3847fc431a3eee2f7fa3ba27ffe49ccbba251b43"
            ),
            state_root=Path(self.temporary.name) / "state",
            work_lease_seconds=5,
        )
        self.security_configuration = self.security_config()
        SecureAdmissionCore.migrate(
            self.runtime_configuration,
            self.security_configuration,
            clock=self.clock,
        )
        self.core = SecureAdmissionCore.open_current(
            self.runtime_configuration,
            self.security_configuration,
            clock=self.clock,
        )

    def security_config(self) -> SecurityConfiguration:
        return SecurityConfiguration(
            provider_revision_id=self.runtime_configuration.provider_revision_id,
            runtime_revision=self.runtime_configuration.runtime_revision,
            provider_audience=self.runtime_configuration.provider_audience,
            trusted_callers=frozenset({CALLER}),
            verification_keys=(
                self.verification_key("eddsa-test", "EdDSA", self.eddsa_private),
                self.verification_key("es256-test", "ES256", self.es256_private),
            ),
            application_root=ROOT,
            contract_root=CONTRACT_ROOT,
            clock_skew_seconds=0,
        )

    @staticmethod
    def verification_key(
        kid: str,
        algorithm: Literal["EdDSA", "ES256"],
        private_key: ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey,
    ) -> VerificationKey:
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return VerificationKey(kid=kid, algorithm=algorithm, public_key_pem=public_pem)

    def timestamp(self, *, minutes: int = 0, seconds: int = 0) -> str:
        return format_timestamp(
            self.clock() + timedelta(minutes=minutes, seconds=seconds)
        )

    def start_document(self) -> dict[str, Any]:
        document = cast(
            dict[str, Any],
            json.loads(
                (
                    CONTRACT_ROOT
                    / "examples/contracts/agent-runtime-start-no-sandbox.json"
                ).read_text(encoding="utf-8")
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
        now = int(self.clock().timestamp())
        return {
            "iss": "agent-platform",
            "sub": CALLER,
            "aud": self.runtime_configuration.provider_audience,
            "jti": jti,
            "iat": now,
            "nbf": now,
            "exp": now + 240,
            "tenant_id": document["tenant_id"],
            "provider_revision_id": self.runtime_configuration.provider_revision_id,
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

    def sign(
        self,
        claims: dict[str, Any],
        *,
        algorithm: Literal["EdDSA", "ES256"] = "EdDSA",
        kid: str | None = None,
        private_key: ed25519.Ed25519PrivateKey
        | ec.EllipticCurvePrivateKey
        | None = None,
        headers: dict[str, Any] | None = None,
    ) -> str:
        selected_key = private_key or (
            self.eddsa_private if algorithm == "EdDSA" else self.es256_private
        )
        selected_kid = kid or ("eddsa-test" if algorithm == "EdDSA" else "es256-test")
        selected_headers = {
            "kid": selected_kid,
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

    def admit_start(self) -> tuple[dict[str, Any], dict[str, Any], str]:
        document = self.start_document()
        claims = self.start_claims(document, "runtime-start-jti-00000001")
        token = self.sign(claims)
        self.core.start(self.encode(document), token, authenticated_caller=CALLER)
        return document, claims, token

    def read_claims(
        self,
        start: dict[str, Any],
        *,
        operation: Literal["read_status", "read_events"],
        fencing_token: int,
        after_event_sequence: int = 0,
        limit: int = 1000,
    ) -> dict[str, Any]:
        authorization = cast(dict[str, Any], start["runtime_authorization"])
        policy = cast(dict[str, Any], authorization["policy_decision"])
        budget = cast(dict[str, Any], authorization["execution_budget"])
        permissions = cast(dict[str, Any], authorization["effective_permissions"])
        descriptor: dict[str, Any] = {
            "operation": operation,
            "runtime_run_id": start["runtime_run_id"],
            "invocation_id": start["invocation_id"],
            "invocation_attempt_id": start["invocation_attempt_id"],
            "fencing_token": fencing_token,
        }
        if operation == "read_events":
            descriptor.update(
                {"after_event_sequence": after_event_sequence, "limit": limit}
            )
        now = int(self.clock().timestamp())
        return {
            "iss": "agent-platform",
            "sub": CALLER,
            "aud": self.runtime_configuration.provider_audience,
            "jti": f"runtime-{operation}-jti-000001",
            "iat": now,
            "nbf": now,
            "exp": now + 240,
            "tenant_id": start["tenant_id"],
            "provider_revision_id": self.runtime_configuration.provider_revision_id,
            "runtime_run_id": start["runtime_run_id"],
            "agent_run_id": start["agent_run_id"],
            "workflow_run_id": start["workflow_run_id"],
            "work_order_id": start["work_order_id"],
            "run_manifest_digest": start["run_manifest_digest"],
            "runtime_authorization_digest": authorization["authorization_digest"],
            "authority_mode": "safety_control",
            "operation": operation,
            "operation_contract_id": (
                "urn:agent-platform:agent-runtime-status-operation-descriptor:v1"
                if operation == "read_status"
                else "urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1"
            ),
            "operation_digest_profile": "rfc8785-full-document-v1",
            "operation_request_digest": document_digest(descriptor),
            "invocation_id": start["invocation_id"],
            "invocation_attempt_id": start["invocation_attempt_id"],
            "fencing_token": fencing_token,
            "policy_decision_digest": policy["decision_digest"],
            "execution_budget_digest": budget["budget_digest"],
            "effective_permissions_digest": permissions["permissions_digest"],
        }

    def cancel_document(self, runtime_run_id: str) -> dict[str, Any]:
        document = cast(
            dict[str, Any],
            json.loads(
                (
                    CONTRACT_ROOT
                    / "examples/contracts/agent-runtime-system-safety-command.json"
                ).read_text(encoding="utf-8")
            ),
        )
        document["runtime_run_id"] = runtime_run_id
        document["command_sequence"] = 1
        document["fencing_token"] = 2
        document["deadline_at"] = self.timestamp(minutes=5)
        refresh_self_digest(document, "command_digest")
        return document

    def command_claims(
        self, start: dict[str, Any], command: dict[str, Any]
    ) -> dict[str, Any]:
        authorization = cast(dict[str, Any], start["runtime_authorization"])
        policy = cast(dict[str, Any], authorization["policy_decision"])
        budget = cast(dict[str, Any], authorization["execution_budget"])
        permissions = cast(dict[str, Any], authorization["effective_permissions"])
        now = int(self.clock().timestamp())
        return {
            "iss": "agent-platform",
            "sub": CALLER,
            "aud": self.runtime_configuration.provider_audience,
            "jti": "runtime-command-jti-0000001",
            "iat": now,
            "nbf": now,
            "exp": now + 240,
            "tenant_id": start["tenant_id"],
            "provider_revision_id": self.runtime_configuration.provider_revision_id,
            "runtime_run_id": start["runtime_run_id"],
            "agent_run_id": start["agent_run_id"],
            "workflow_run_id": start["workflow_run_id"],
            "work_order_id": start["work_order_id"],
            "run_manifest_digest": start["run_manifest_digest"],
            "runtime_authorization_digest": authorization["authorization_digest"],
            "authority_mode": "safety_control",
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
            "system_safety_control_id": command["system_safety_control_id"],
            "system_safety_control_digest": command["system_safety_control_digest"],
        }

    def test_secure_lifecycle_uses_both_algorithms_and_authorized_reads(self) -> None:
        print(
            "secure-admission-public-key-fingerprints:"
            + ",".join(
                f"{key.kid}={key.fingerprint}"
                for key in self.security_configuration.verification_keys
            )
        )
        start, _, _ = self.admit_start()
        self.assertTrue(self.core.kernel.process_one(Executor(), owner="worker-1"))

        status_claims = self.read_claims(
            start, operation="read_status", fencing_token=1
        )
        status_token = self.sign(status_claims)
        self.assertEqual(
            self.core.status(
                cast(str, start["runtime_run_id"]),
                status_token,
                authenticated_caller=CALLER,
            ).status,
            "running",
        )
        event_claims = self.read_claims(start, operation="read_events", fencing_token=1)
        events = self.core.events(
            cast(str, start["runtime_run_id"]),
            self.sign(event_claims),
            authenticated_caller=CALLER,
        )
        self.assertEqual(
            [event.type for event in events.events], ["runtime.run.started"]
        )

        command = self.cancel_document(cast(str, start["runtime_run_id"]))
        command_token = self.sign(
            self.command_claims(start, command), algorithm="ES256"
        )
        accepted = self.core.submit_command(
            cast(str, start["runtime_run_id"]),
            self.encode(command),
            command_token,
            authenticated_caller=CALLER,
        )
        self.assertEqual(accepted.status, "cancel_requested")

        with (
            patch.object(
                self.core.kernel.store,
                "_status",
                side_effect=AssertionError("state exposed before fencing check"),
            ),
            self.assertRaises(StaleFencingError),
        ):
            self.core.status(
                cast(str, start["runtime_run_id"]),
                status_token,
                authenticated_caller=CALLER,
            )

    def test_read_path_and_cursor_replacement_are_rejected(self) -> None:
        start, _, _ = self.admit_start()
        runtime_run_id = cast(str, start["runtime_run_id"])

        status_claims = self.read_claims(
            start, operation="read_status", fencing_token=1
        )
        with self.assertRaises(AuthorizationBindingError):
            self.core.status(
                "runtime-run-path-replacement",
                self.sign(status_claims),
                authenticated_caller=CALLER,
            )

        event_claims = self.read_claims(
            start,
            operation="read_events",
            fencing_token=1,
            after_event_sequence=0,
            limit=1000,
        )
        with self.assertRaises(AdmissionError):
            self.core.events(
                runtime_run_id,
                self.sign(event_claims),
                authenticated_caller=CALLER,
                after_event_sequence=1,
                limit=1000,
            )

    def test_invalid_tokens_never_open_store_or_reveal_run_existence(self) -> None:
        start, _, _ = self.admit_start()
        existing_runtime_run_id = cast(str, start["runtime_run_id"])
        wrong_signing_key = ed25519.Ed25519PrivateKey.generate()
        rejection_outcomes: dict[tuple[str, str], tuple[type[BaseException], str]] = {}

        def rejected_tokens(claims: dict[str, Any]) -> tuple[tuple[str, str], ...]:
            wrong_subject = deepcopy(claims)
            wrong_subject["sub"] = "other-caller"
            wrong_audience = deepcopy(claims)
            wrong_audience["aud"] = "urn:agent-platform:provider-instance:other"
            return (
                (
                    "signature",
                    self.sign(claims, private_key=wrong_signing_key),
                ),
                ("typ", self.sign(claims, headers={"typ": "JWT"})),
                ("kid", self.sign(claims, kid="unknown-key")),
                (
                    "algorithm",
                    self.sign(claims, algorithm="ES256", kid="eddsa-test"),
                ),
                ("subject", self.sign(wrong_subject)),
                ("audience", self.sign(wrong_audience)),
            )

        for runtime_run_id in (
            existing_runtime_run_id,
            "runtime-run-does-not-exist",
        ):
            target = deepcopy(start)
            target["runtime_run_id"] = runtime_run_id
            command = self.cancel_document(runtime_run_id)
            requests = (
                ("command", self.command_claims(target, command)),
                (
                    "status",
                    self.read_claims(
                        target,
                        operation="read_status",
                        fencing_token=1,
                    ),
                ),
                (
                    "event",
                    self.read_claims(
                        target,
                        operation="read_events",
                        fencing_token=1,
                    ),
                ),
            )
            for operation, claims in requests:
                for rejection, token in rejected_tokens(claims):
                    with (
                        self.subTest(
                            operation=operation,
                            rejection=rejection,
                            runtime_run_id=runtime_run_id,
                        ),
                        patch.object(
                            self.core.kernel.store,
                            "_connect",
                            side_effect=AssertionError(
                                "store opened before token verification"
                            ),
                        ),
                        self.assertRaises(AdmissionError) as caught,
                    ):
                        if operation == "command":
                            self.core.submit_command(
                                runtime_run_id,
                                self.encode(command),
                                token,
                                authenticated_caller=CALLER,
                            )
                        elif operation == "status":
                            self.core.status(
                                runtime_run_id,
                                token,
                                authenticated_caller=CALLER,
                            )
                        else:
                            self.core.events(
                                runtime_run_id,
                                token,
                                authenticated_caller=CALLER,
                            )
                    outcome = (type(caught.exception), str(caught.exception))
                    key = (operation, rejection)
                    if runtime_run_id == existing_runtime_run_id:
                        rejection_outcomes[key] = outcome
                    else:
                        self.assertEqual(outcome, rejection_outcomes[key])

        for operation in ("command", "status", "event"):
            self.assertEqual(
                rejection_outcomes[(operation, "signature")],
                (
                    TokenValidationError,
                    "Runtime token signature is invalid",
                ),
            )

    def test_command_digest_operation_and_time_fail_closed(self) -> None:
        start, _, _ = self.admit_start()
        self.assertTrue(self.core.kernel.process_one(Executor(), owner="worker-1"))
        runtime_run_id = cast(str, start["runtime_run_id"])
        command = self.cancel_document(runtime_run_id)

        wrong_digest = self.command_claims(start, command)
        wrong_digest["operation_request_digest"] = "sha256:" + "0" * 64

        wrong_operation = self.command_claims(start, command)
        wrong_operation["operation"] = "read_status"

        late_command = deepcopy(command)
        late_command["deadline_at"] = self.timestamp(minutes=3)
        refresh_self_digest(late_command, "command_digest")
        late_claims = self.command_claims(start, late_command)
        late_claims["exp"] = int(self.clock().timestamp()) + 181

        cases = (
            ("digest", command, wrong_digest),
            ("operation", command, wrong_operation),
            ("deadline", late_command, late_claims),
        )
        for index, (name, body, claims) in enumerate(cases, start=1):
            claims["jti"] = f"runtime-command-negative-{index:08d}"
            with self.subTest(name=name), self.assertRaises(AdmissionError):
                self.core.submit_command(
                    runtime_run_id,
                    self.encode(body),
                    self.sign(claims),
                    authenticated_caller=CALLER,
                )
            self.assertEqual(
                self.core.kernel.store.count_jti(
                    "agent-platform", cast(str, claims["jti"])
                ),
                0,
            )
        connection = self.core.kernel.store._connect()
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM runtime_commands").fetchone()[
                    0
                ],
                0,
            )
        finally:
            connection.close()

    def test_idempotent_command_replay_rechecks_authority(self) -> None:
        start, _, _ = self.admit_start()
        self.assertTrue(self.core.kernel.process_one(Executor(), owner="worker-1"))
        runtime_run_id = cast(str, start["runtime_run_id"])
        system_command = self.cancel_document(runtime_run_id)
        command = deepcopy(system_command)
        del command["system_safety_control_id"]
        del command["system_safety_control_digest"]
        command["authorized_control_request_id"] = "control-user-cancel-0001"
        refresh_self_digest(command, "command_digest")

        execution_claims = self.command_claims(start, system_command)
        execution_claims["jti"] = "runtime-command-user-jti-00001"
        execution_claims["authority_mode"] = "execution"
        execution_claims["operation_request_digest"] = command["command_digest"]
        del execution_claims["system_safety_control_id"]
        del execution_claims["system_safety_control_digest"]
        self.core.submit_command(
            runtime_run_id,
            self.encode(command),
            self.sign(execution_claims),
            authenticated_caller=CALLER,
        )

        safety_replay = deepcopy(execution_claims)
        safety_replay["jti"] = "runtime-command-safety-replay-0001"
        safety_replay["authority_mode"] = "safety_control"
        with self.assertRaises(AdmissionError):
            self.core.submit_command(
                runtime_run_id,
                self.encode(command),
                self.sign(safety_replay),
                authenticated_caller=CALLER,
            )
        self.assertEqual(
            self.core.kernel.store.count_jti(
                "agent-platform", "runtime-command-safety-replay-0001"
            ),
            0,
        )

    def test_token_negative_matrix_has_no_runtime_or_jti_side_effect(self) -> None:
        document = self.start_document()
        base = self.start_claims(document, "runtime-negative-jti-000001")
        wrong_signing_key = ed25519.Ed25519PrivateKey.generate()
        cases: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for name, field, value in (
            ("audience", "aud", "urn:agent-platform:provider-instance:other"),
            ("subject", "sub", "other-caller"),
            ("provider", "provider_revision_id", "other-revision"),
            ("digest", "operation_request_digest", "sha256:" + "0" * 64),
            ("policy", "policy_decision_digest", "sha256:" + "1" * 64),
            ("operation", "operation", "read_status"),
            (
                "contract",
                "operation_contract_id",
                "urn:agent-platform:agent-runtime-command:v1",
            ),
            ("profile", "operation_digest_profile", "rfc8785-full-document-v1"),
            ("invocation", "invocation_id", "other-invocation"),
        ):
            claims = deepcopy(base)
            claims["jti"] = f"runtime-negative-{name}-000001"
            claims[field] = value
            cases.append((name, claims, {}))
        expired = deepcopy(base)
        expired.update(
            {
                "jti": "runtime-negative-expired-0001",
                "iat": int(self.clock().timestamp()) - 301,
                "nbf": int(self.clock().timestamp()) - 300,
                "exp": int(self.clock().timestamp()) - 1,
            }
        )
        cases.append(("expired", expired, {}))
        future = deepcopy(base)
        future.update(
            {
                "jti": "runtime-negative-future-00001",
                "iat": int(self.clock().timestamp()) + 1,
                "nbf": int(self.clock().timestamp()) + 1,
                "exp": int(self.clock().timestamp()) + 240,
            }
        )
        cases.append(("future", future, {}))
        overlong = deepcopy(base)
        overlong.update(
            {
                "jti": "runtime-negative-ttl-0000001",
                "exp": int(self.clock().timestamp()) + 301,
            }
        )
        cases.append(("ttl", overlong, {}))
        cases.extend(
            (
                ("wrong_typ", base, {"headers": {"typ": "JWT"}}),
                ("extra_header", base, {"headers": {"extra": "rejected"}}),
                ("unknown_kid", base, {"kid": "unknown-key"}),
                (
                    "wrong_signature",
                    base,
                    {"private_key": wrong_signing_key},
                ),
                (
                    "algorithm_key_mismatch",
                    base,
                    {"algorithm": "ES256", "kid": "eddsa-test"},
                ),
            )
        )
        extra_claim = deepcopy(base)
        extra_claim["unadmitted"] = True
        cases.append(("extra_claim", extra_claim, {}))

        for name, claims, token_options in cases:
            with self.subTest(name=name), self.assertRaises(AdmissionError):
                self.core.start(
                    self.encode(document),
                    self.sign(claims, **token_options),
                    authenticated_caller=CALLER,
                )

        compact = self.sign(base)
        segments = compact.split(".")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        final_index = alphabet.index(segments[2][-1])
        replacement_index = (final_index & 0x30) | ((final_index + 1) & 0x0F)
        segments[2] = segments[2][:-1] + alphabet[replacement_index]
        with self.assertRaises(AdmissionError):
            self.core.start(
                self.encode(document),
                ".".join(segments),
                authenticated_caller=CALLER,
            )
        connection = self.core.kernel.store._connect()
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM runtime_runs").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM consumed_mutation_jtis"
                ).fetchone()[0],
                0,
            )
        finally:
            connection.close()

    def test_digest_and_strict_json_fail_before_jti_consumption(self) -> None:
        document = self.start_document()
        claims = self.start_claims(document, "runtime-digest-jti-00000001")
        token = self.sign(claims)

        digest_conflict = deepcopy(document)
        digest_conflict["conversation_id"] = "different-conversation"
        with self.assertRaises(DigestMismatchError):
            self.core.start(
                self.encode(digest_conflict), token, authenticated_caller=CALLER
            )

        encoded = self.encode(document)
        duplicate = b'{"protocol_version":"v1",' + encoded[1:]
        with self.assertRaises(StrictJsonError):
            self.core.start(duplicate, token, authenticated_caller=CALLER)
        unsafe = encoded.replace(
            b'"fencing_token":1', b'"fencing_token":9007199254740992'
        )
        with self.assertRaises(StrictJsonError):
            self.core.start(unsafe, token, authenticated_caller=CALLER)
        with self.assertRaises(EncodedBodyTooLargeError):
            self.core.start(
                b" " * (8 * 1024 * 1024 + 1),
                token,
                authenticated_caller=CALLER,
            )
        self.assertEqual(
            self.core.kernel.store.count_jti(
                "agent-platform", "runtime-digest-jti-00000001"
            ),
            0,
        )

    def test_start_nested_digest_and_gateway_semantics_fail_before_jti(self) -> None:
        nested_digest = self.start_document()
        nested_authorization = cast(
            dict[str, Any], nested_digest["runtime_authorization"]
        )
        nested_budget = cast(dict[str, Any], nested_authorization["execution_budget"])
        nested_limits = cast(dict[str, Any], nested_budget["limits"])
        nested_limits["max_model_requests"] = 201
        refresh_self_digest(nested_authorization, "authorization_digest")
        refresh_self_digest(nested_digest, "request_digest")

        gateway_mismatch = self.start_document()
        gateway_bindings = cast(dict[str, Any], gateway_mismatch["gateway_bindings"])
        model_binding = cast(dict[str, Any], gateway_bindings["model"])
        model_port = cast(dict[str, Any], model_binding["port"])
        model_port["gateway_kind"] = "tool"
        refresh_self_digest(gateway_mismatch, "request_digest")

        grant_mismatch = self.start_document()
        grant_authorization = cast(
            dict[str, Any], grant_mismatch["runtime_authorization"]
        )
        grants = cast(list[dict[str, Any]], grant_authorization["artifact_grants"])
        grants[0]["runtime_run_id"] = "runtime-run-grant-replacement"
        refresh_self_digest(grants[0], "grant_digest")
        refresh_self_digest(grant_authorization, "authorization_digest")
        refresh_self_digest(grant_mismatch, "request_digest")

        for index, (name, document) in enumerate(
            (
                ("nested_digest", nested_digest),
                ("gateway", gateway_mismatch),
                ("grant", grant_mismatch),
            ),
            start=1,
        ):
            jti = f"runtime-start-semantic-negative-{index:04d}"
            claims = self.start_claims(document, jti)
            with self.subTest(name=name), self.assertRaises(AdmissionError):
                self.core.start(
                    self.encode(document),
                    self.sign(claims),
                    authenticated_caller=CALLER,
                )
            self.assertEqual(
                self.core.kernel.store.count_jti("agent-platform", jti),
                0,
            )

    def test_mutation_jti_is_consumed_only_with_committed_start(self) -> None:
        document = self.start_document()
        claims = self.start_claims(document, "runtime-replay-jti-00000001")
        token = self.sign(claims)
        self.core.start(self.encode(document), token, authenticated_caller=CALLER)
        self.assertEqual(
            self.core.kernel.store.count_jti(
                "agent-platform", "runtime-replay-jti-00000001"
            ),
            1,
        )
        with self.assertRaises(MutationReplayError):
            self.core.start(self.encode(document), token, authenticated_caller=CALLER)

    def test_security_configuration_is_immutable_and_rejects_private_keys(
        self,
    ) -> None:
        private_pem = self.eddsa_private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        with self.assertRaises(ConfigurationError):
            VerificationKey(
                kid="private-key", algorithm="EdDSA", public_key_pem=private_pem
            )

        replacement = ed25519.Ed25519PrivateKey.generate()
        drifted = SecurityConfiguration(
            provider_revision_id=self.runtime_configuration.provider_revision_id,
            runtime_revision=self.runtime_configuration.runtime_revision,
            provider_audience=self.runtime_configuration.provider_audience,
            trusted_callers=frozenset({CALLER}),
            verification_keys=(
                self.verification_key("eddsa-test", "EdDSA", replacement),
            ),
            application_root=ROOT,
            contract_root=CONTRACT_ROOT,
            clock_skew_seconds=0,
        )
        with self.assertRaises(ConfigurationDriftError):
            SecureAdmissionCore.open_current(
                self.runtime_configuration, drifted, clock=self.clock
            )

    def test_security_binding_interruption_is_idempotently_recoverable(self) -> None:
        runtime = replace(
            self.runtime_configuration,
            state_root=Path(self.temporary.name) / "security-binding-interruption",
        )
        NativeRuntimeKernel.migrate(runtime, clock=self.clock)

        with self.assertRaises(ConfigurationDriftError):
            SecureAdmissionCore.open_current(
                runtime,
                self.security_configuration,
                clock=self.clock,
            )

        SecureAdmissionCore.migrate(
            runtime,
            self.security_configuration,
            clock=self.clock,
        )
        SecureAdmissionCore.migrate(
            runtime,
            self.security_configuration,
            clock=self.clock,
        )
        reopened = SecureAdmissionCore.open_current(
            runtime,
            self.security_configuration,
            clock=self.clock,
        )
        self.assertEqual(reopened.kernel.configuration, runtime)

    def test_missing_security_metadata_fails_open_current_without_write(self) -> None:
        connection = self.core.kernel.store._connect()
        try:
            connection.execute("DELETE FROM provider_security_metadata")
        finally:
            connection.close()
        database_path = self.core.kernel.store.database_path
        before = database_path.read_bytes()

        with self.assertRaises(ConfigurationDriftError):
            SecureAdmissionCore.open_current(
                self.runtime_configuration,
                self.security_configuration,
                clock=self.clock,
            )

        self.assertEqual(database_path.read_bytes(), before)

    def test_projection_loader_normalizes_non_object_lock_input(self) -> None:
        application_root = Path(self.temporary.name) / "invalid-application"
        manifest_target = (
            application_root / "internal/generated/runtimeapi/projection-manifest.json"
        )
        manifest_target.parent.mkdir(parents=True)
        manifest_target.write_text(
            (ROOT / "internal/generated/runtimeapi/projection-manifest.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        (application_root / "dependency-lock.json").write_text("[]", encoding="utf-8")
        invalid = SecurityConfiguration(
            provider_revision_id=self.runtime_configuration.provider_revision_id,
            runtime_revision=self.runtime_configuration.runtime_revision,
            provider_audience=self.runtime_configuration.provider_audience,
            trusted_callers=frozenset({CALLER}),
            verification_keys=self.security_configuration.verification_keys,
            application_root=application_root,
            contract_root=CONTRACT_ROOT,
            clock_skew_seconds=0,
        )
        with self.assertRaises(ConfigurationError):
            RuntimeContractProjection.load(invalid)


if __name__ == "__main__":
    unittest.main()
