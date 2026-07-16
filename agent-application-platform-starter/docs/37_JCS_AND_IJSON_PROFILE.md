# RFC 8785 JCS 与 I-JSON Profile

## 1. 安全用途

ExecutionGrant 的 `request_digest`、SchemaReference Digest、RunManifest Digest
以及所有安全相关 JSON Digest 都必须使用 RFC 8785 JCS。

禁止使用：

```text
json.dumps(sort_keys=True)
普通 JSON.stringify + 仅排序顶层
语言默认 Map 序列化
```

## 2. 输入约束

进入安全摘要前必须通过严格 I-JSON Parser：

- UTF-8
- 禁止重复 Object Key
- 禁止 NaN、Infinity
- 禁止 Lone Surrogate
- 安全关键整数限制在 ±(2^53-1)
- 更大的整数、Decimal、货币最小单位使用字符串或领域专用定点表示
- 不执行 Unicode Normalization
- 不改变原始字符串代码点

## 3. 标准实现

参考实现：

- Python：`rfc8785==0.1.4`
- JavaScript：ECMAScript `JSON.stringify` Primitive Serialization + UTF-16 Key Sort
- Go：`github.com/gowebpki/jcs@v1.0.1`

## 4. 跨语言门禁

以下三项必须得到完全相同的 canonical bytes：

```text
scripts/jcs/verify_python.py
scripts/jcs/verify_node.mjs
scripts/jcs/go/jcs_test.go
```

统一 Test Vector：

```text
contracts/testdata/jcs-v1/vectors.json
```

任何语言实现产生不同字节都必须阻止合并。

## 5. HTTP 解析

API Gateway 或 Handler 必须保留原始 Request Bytes，并使用严格 Parser 验证：

1. 严格解析并拒绝非法 I-JSON。
2. 按 WorkOrder Digest Profile 删除 `execution_grant`。
3. JCS Canonicalize。
4. SHA-256。
5. 与 ExecutionGrant 比较。

不能先解析成会丢失 Number 或重复 Key 信息的宽松对象，再执行安全验证。
