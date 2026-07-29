from __future__ import annotations

import json
import os
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Protocol, cast

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from jsonschema.exceptions import ValidationError

from agent_native_runtime.contract_projection import (
    ALLOWED_JWS_ALGORITHMS,
    build_draft202012_validator,
    canonicalize_json,
    decode_json_without_duplicate_keys,
    decode_strict_ijson,
)
from agent_native_runtime.generated.runtimeapi import (
    agent_runtime_capabilities,
    agent_runtime_start_request,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()


class Validator(Protocol):
    def validate(self, instance: object) -> None: ...


class RuntimeContractProjectionTest(unittest.TestCase):
    documents: ClassVar[list[Mapping[str, Any]]]
    fixtures: ClassVar[dict[str, list[tuple[str, str]]]]

    @classmethod
    def setUpClass(cls) -> None:
        projection = cast(
            dict[str, Any],
            json.loads(
                (
                    ROOT / "internal/generated/runtimeapi/projection-manifest.json"
                ).read_text(encoding="utf-8")
            ),
        )
        cls.documents = [
            cast(
                Mapping[str, Any],
                json.loads((CONTRACT_ROOT / item["path"]).read_text(encoding="utf-8")),
            )
            for item in projection["schemas"]
        ]
        cls.fixtures = cast(
            dict[str, list[tuple[str, str]]],
            json.loads(
                (ROOT / "test/conformance/runtime-contract-fixtures.json").read_text(
                    encoding="utf-8"
                )
            ),
        )

    def test_generated_transport_is_importable_and_closed(self) -> None:
        self.assertTrue(agent_runtime_capabilities.Schema.__closed__)
        self.assertTrue(agent_runtime_start_request.Schema.__closed__)

    def test_locked_runtime_fixtures_have_draft2020_parity(self) -> None:
        validators: dict[str, Validator] = {}
        for relative, schema_id in self.fixtures["positive"]:
            validator = validators.setdefault(
                schema_id,
                cast(Validator, build_draft202012_validator(schema_id, self.documents)),
            )
            value = json.loads((CONTRACT_ROOT / relative).read_text(encoding="utf-8"))
            validator.validate(value)
        for relative, schema_id in self.fixtures["negative"]:
            validator = validators.setdefault(
                schema_id,
                cast(Validator, build_draft202012_validator(schema_id, self.documents)),
            )
            value = json.loads((CONTRACT_ROOT / relative).read_text(encoding="utf-8"))
            with self.subTest(relative=relative), self.assertRaises(ValidationError):
                validator.validate(value)

    def test_jcs_matches_locked_vectors(self) -> None:
        vectors = json.loads(
            (CONTRACT_ROOT / "testdata/jcs-v1/vectors.json").read_text(encoding="utf-8")
        )
        for vector in vectors["valid"] + vectors["strict_valid"]:
            with self.subTest(vector=vector["id"]):
                value = decode_json_without_duplicate_keys(vector["input"].encode())
                self.assertEqual(canonicalize_json(value).decode(), vector["canonical"])

    def test_json_decoder_rejects_duplicate_and_non_finite_values(self) -> None:
        for encoded in (b'{"a":1,"a":2}', b'{"n":NaN}', b'{"n":Infinity}'):
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                decode_json_without_duplicate_keys(encoded)

    def test_strict_ijson_matches_every_locked_vector(self) -> None:
        vectors = json.loads(
            (CONTRACT_ROOT / "testdata/jcs-v1/vectors.json").read_text(encoding="utf-8")
        )
        for vector in vectors["strict_valid"]:
            with self.subTest(vector=vector["id"]):
                value = decode_strict_ijson(vector["input"].encode())
                self.assertEqual(canonicalize_json(value).decode(), vector["canonical"])
        for vector in vectors["invalid"]:
            with self.subTest(vector=vector["id"]), self.assertRaises(ValueError):
                decode_strict_ijson(vector["input"].encode())

    def test_strict_ijson_rejects_encoding_and_structural_overflow(self) -> None:
        rejected = (
            b"\xef\xbb\xbf{}",
            b'"\xff"',
            b"[[[0]]]",
            b'{"a":1,"b":2}',
            b'{"n":12345}',
        )
        options: tuple[dict[str, int], ...] = (
            {},
            {},
            {"max_depth": 3},
            {"max_nodes": 4},
            {"max_number_token_bytes": 4},
        )
        for encoded, bounds in zip(rejected, options, strict=True):
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                decode_strict_ijson(encoded, **bounds)

    def test_jose_allowlist_supports_eddsa_and_es256(self) -> None:
        claims = {"contract": "runtime-core-v1"}
        keys = (
            ("EdDSA", ed25519.Ed25519PrivateKey.generate()),
            ("ES256", ec.generate_private_key(ec.SECP256R1())),
        )
        for algorithm, private_key in keys:
            with self.subTest(algorithm=algorithm):
                encoded = jwt.encode(
                    claims,
                    private_key,
                    algorithm=algorithm,
                    headers={"kid": "test-key", "typ": "agent-runtime-invocation+jwt"},
                )
                decoded = jwt.decode(
                    encoded,
                    private_key.public_key(),
                    algorithms=sorted(ALLOWED_JWS_ALGORITHMS),
                )
                self.assertEqual(decoded, claims)

    def test_jose_allowlist_rejects_hs256(self) -> None:
        encoded = jwt.encode(
            {"contract": "not-admitted"},
            "01234567890123456789012345678901",
            algorithm="HS256",
        )
        with self.assertRaises(jwt.InvalidAlgorithmError):
            jwt.decode(
                encoded,
                "01234567890123456789012345678901",
                algorithms=sorted(ALLOWED_JWS_ALGORITHMS),
            )


if __name__ == "__main__":
    unittest.main()
