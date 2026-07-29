from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeBuildIdentity:
    provider_api_version: str
    contract_source_revision: str
    contract_manifest_digest: str
    runtime_openapi_sha256: str
    runtime_schema_closure_sha256: str
    conformance_suite_id: str
    conformance_suite_version: str
    conformance_suite_digest: str
    target_profile: str


BUILD_IDENTITY = RuntimeBuildIdentity(
    provider_api_version="1.0.0",
    contract_source_revision=(
        "c7548d4a7e181895ca6c7c0ccfb585ccc2352433da8856c57d1d09ca3cb9a7e7"
    ),
    contract_manifest_digest=(
        "sha256:fac0299efcf04471f58f1f0668818a5148526371bd413deb5993c5aacb2762ce"
    ),
    runtime_openapi_sha256=(
        "f75bd9484d9059435021f65147cab1a22b4cb0376ea47ce6e165fde0494f5811"
    ),
    runtime_schema_closure_sha256=(
        "8135d0b684499052c3cbc6078e3d8e806628d12695125b654205e75f50e0c4ba"
    ),
    conformance_suite_id="agent-runtime-provider",
    conformance_suite_version="1.0.0",
    conformance_suite_digest=(
        "sha256:9ef6d50df9f1032476ea2ada2c16d70c15d88368acf59794062df7dfce0bb356"
    ),
    target_profile="runtime-core-v1",
)
