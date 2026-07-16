# Contract Examples

WorkOrder example uses:

```text
Idempotency-Key: work-order-example-0001
```

Expected digests:

```text
request_digest: sha256:88ce4d187a6fe5197cecaa870c2d5a00fb7a3b089e57aa7946a239d9f8f03789
idempotency_key_digest: sha256:6bf53ca6b162632ebe7a477b424bedb41cae0759b08b27970fe9dbc7199ff87c
scenario_definition_digest: sha256:dd7b535a7cd877a389665d18edd8b2340c41e1af13c2029d33be666518dccd30
```

The example request digest is computed over RFC 8785-compatible canonical JSON after removing only `execution_grant`.
