# Go JCS Conformance Harness

This directory contains a small self-contained RFC 8785 conformance implementation
used only to verify the shared test vectors without requiring network downloads.

Production Go code should use an independently reviewed RFC 8785 implementation and
must pass the same vectors. The harness intentionally has no external Go modules,
so `go test ./...` is reproducible offline.
