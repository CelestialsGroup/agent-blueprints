# RFC 8785 JCS and Strict I-JSON Profile — v0.8.3

ExecutionGrant request_digest、SchemaReference、ProviderRevision、AdmissionDecision、RunManifest 和人工 Decision 的安全摘要都使用 RFC 8785 JCS + SHA-256。

进入摘要前必须从 raw bytes 严格拒绝：duplicate key、NaN/Infinity、lone surrogate、非 UTF-8，以及任何 canonical number value 为整数且超出 ±(2^53-1) 的 token。该规则同样覆盖 `9007199254740992.0` 与 `9007199254740992e0`，不能按词法中是否存在 `.eE` 绕过。更大整数和 Decimal 使用字符串/领域定点类型；不执行 Unicode normalization。

共享向量：`contracts/testdata/jcs-v1/vectors.json`。

- Python：`rfc8785==0.1.4` + duplicate/safe integer raw parser；
- Node：`strict_parse.mjs` 在 `JSON.parse` 前检查 token；
- Go：`strictCanonicalize` 在 float64 转换前检查整数，同时 canonicalizer 拒绝 duplicate/surrogate。

三个语言必须执行全部 5 个 valid 和 7 个 invalid vectors，不得把 parser-level case 标记为 skip/documented。

HTTP Handler 必须保留原始 Request Bytes，先严格解析，再按 Digest Profile 删除指定字段、JCS、SHA-256 并比较 Grant；宽松解析后的对象不能用于安全摘要。
