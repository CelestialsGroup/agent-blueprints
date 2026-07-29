# Generated Go Code

Generated sqlc and OpenAPI/JSON Schema transport code belongs here in clearly
named child packages. Generation inputs remain `db/` and the locked external
Contract checkout.

Do not hand-edit generated files or use them as the domain model. Generation
must be reproducible with pinned tools, and stale-output checks belong in the
implementation Gate.

`runtimeapi/` is the B03.2-P0 transport-only projection of the locked Runtime
Provider Schema closure. Its manifest records external input IDs and digests;
the authoritative Schemas remain in Contract. Run
`script/generate_runtime_contract.sh --check` to verify scratch regeneration.
