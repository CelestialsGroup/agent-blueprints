# RFC 8785 JCS 与 Strict I-JSON Profile — v0.9.0

ExecutionGrant request_digest、SchemaReference、ProviderRevision、AdmissionDecision、RunManifest 和人工 Decision 的安全摘要都使用 RFC 8785 JCS + SHA-256。

进入安全摘要前必须从原始字节严格拒绝：重复键、NaN/Infinity、单独 Surrogate、非 UTF-8，以及数学值为整数且超出 ±(2^53-1) 的任何 Number Token。词法检查使用十进制系数/Scale 的精确运算，因此 `9007199254740992.0`、`9007199254740992e0`、`1000000000000000000000` 和 `1e21` 都必须拒绝。更大整数和 Decimal 使用字符串/领域定点类型；不执行 Unicode 规范化。

共享向量：`contracts/testdata/jcs-v1/vectors.json`。

- Python：`rfc8785==0.1.4` + 重复键/安全整数原始 Parser；
- Node：`strict_parse.mjs` 在 `JSON.parse` 前检查 Token；
- Go：`strictCanonicalize` 在 float64 转换前检查整数，同时 Canonicalizer 拒绝重复键/Surrogate。

RFC 8785 Canonicalizer 与平台 Strict I-JSON 准入 Profile 是两个测试层：RFC 8785 的参考向量可包含 `1E30`，但它不能通过平台安全准入 Parser。三个语言必须执行全部 5 个规范化向量、3 个 Strict-valid 向量和 10 个 Strict-invalid 向量，不得把 Parser 层 Case 标记为 Skip/Documented。准入 Parser 必须在 `BigInt`/`big.Int`/`Decimal` 分配前拒绝超过 1024 字节的 Number Token，或绝对值大于 400 的十进制 Exponent；这是资源治理边界，不改变 RFC 8785 规范化。

HTTP Handler 必须保留原始 Request Bytes，先严格解析，再按摘要 Profile 删除指定字段、执行 JCS、计算 SHA-256 并比较 Grant；宽松解析后的对象不能用于安全摘要。
