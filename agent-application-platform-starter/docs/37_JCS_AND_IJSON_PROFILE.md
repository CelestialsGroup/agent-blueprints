# RFC 8785 JCS and Strict I-JSON Profile — v0.9.0

ExecutionGrant request_digest、SchemaReference、ProviderRevision、AdmissionDecision、RunManifest 和人工 Decision 的安全摘要都使用 RFC 8785 JCS + SHA-256。

进入安全摘要前必须从 raw bytes 严格拒绝：duplicate key、NaN/Infinity、lone surrogate、非 UTF-8，以及数学值为整数且超出 ±(2^53-1) 的任何 number token。词法检查使用十进制系数/scale 的精确运算，因此 `9007199254740992.0`、`9007199254740992e0`、`1000000000000000000000` 和 `1e21` 都必须拒绝。更大整数和 Decimal 使用字符串/领域定点类型；不执行 Unicode normalization。

共享向量：`contracts/testdata/jcs-v1/vectors.json`。

- Python：`rfc8785==0.1.4` + duplicate/safe integer raw parser；
- Node：`strict_parse.mjs` 在 `JSON.parse` 前检查 token；
- Go：`strictCanonicalize` 在 float64 转换前检查整数，同时 canonicalizer 拒绝 duplicate/surrogate。

RFC 8785 canonicalizer 与平台 Strict I-JSON Admission Profile 是两个测试层：RFC 8785 的参考向量可包含 `1E30`，但它不能通过平台安全 Admission Parser。三个语言必须执行全部 5 个 canonicalization、3 个 strict-valid 和 10 个 strict-invalid vectors，不得把 parser-level case 标记为 skip/documented。Admission Parser 必须在 `BigInt`/`big.Int`/`Decimal` 分配前拒绝超过 1024 字节的 number token 或绝对值大于 400 的十进制 exponent；这是资源治理边界，不改变 RFC 8785 canonicalization。

HTTP Handler 必须保留原始 Request Bytes，先严格解析，再按 Digest Profile 删除指定字段、JCS、SHA-256 并比较 Grant；宽松解析后的对象不能用于安全摘要。
