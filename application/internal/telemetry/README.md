# Telemetry

Provide OpenTelemetry, structured logging, metrics, correlation, attribute
allowlists, and redaction adapters here. Domain packages should depend on a
small observability port rather than vendor SDKs.

Telemetry is operational evidence, not execution, billing, authorization, or
replay truth. Prompt, token, secret, code, and raw recording content must be
excluded or scrubbed before export.
