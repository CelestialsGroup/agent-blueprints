from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeBuildIdentity:
    provider_api_version: str
    conformance_suite_id: str
    conformance_suite_version: str
    conformance_suite_digest: str
    target_profile: str


BUILD_IDENTITY = RuntimeBuildIdentity(
    provider_api_version="1.0.0",
    conformance_suite_id="agent-runtime-provider",
    conformance_suite_version="1.0.0",
    conformance_suite_digest=(
        "sha256:9ef6d50df9f1032476ea2ada2c16d70c15d88368acf59794062df7dfce0bb356"
    ),
    target_profile="runtime-core-v1",
)
