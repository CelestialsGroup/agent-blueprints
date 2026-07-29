import json
import os
import unittest
from pathlib import Path

from agent_native_runtime import BUILD_IDENTITY

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()


class RuntimeBuildIdentityTest(unittest.TestCase):
    def test_identity_matches_runtime_conformance_suite(self) -> None:
        suite_path = CONTRACT_ROOT / "conformance/runtime/v1/suite.json"
        suite = json.loads(suite_path.read_text(encoding="utf-8"))

        self.assertEqual(BUILD_IDENTITY.conformance_suite_id, suite["suite_id"])
        self.assertEqual(
            BUILD_IDENTITY.conformance_suite_version, suite["suite_version"]
        )
        self.assertEqual(BUILD_IDENTITY.conformance_suite_digest, suite["suite_digest"])
        self.assertIn(
            BUILD_IDENTITY.target_profile,
            {profile["profile_id"] for profile in suite["profiles"]},
        )
        lock = json.loads((ROOT / "dependency-lock.json").read_text(encoding="utf-8"))
        projection = json.loads(
            (ROOT / "internal/generated/runtimeapi/projection-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            BUILD_IDENTITY.contract_source_revision,
            lock["contract"]["source_revision"],
        )
        self.assertEqual(
            BUILD_IDENTITY.contract_manifest_digest,
            lock["contract"]["manifest_digest"],
        )
        self.assertEqual(
            BUILD_IDENTITY.runtime_openapi_sha256,
            projection["openapi_sha256"],
        )
        self.assertEqual(
            BUILD_IDENTITY.runtime_schema_closure_sha256,
            projection["schema_closure_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
