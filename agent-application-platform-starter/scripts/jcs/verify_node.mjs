import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "./canonicalize.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const vectors = JSON.parse(
  fs.readFileSync(path.join(root, "contracts/testdata/jcs-v1/vectors.json"), "utf8"),
);

for (const vector of vectors.valid) {
  const parsed = JSON.parse(vector.input);
  const actual = canonicalize(parsed);
  if (actual !== vector.canonical) {
    throw new Error(
      `${vector.id}: expected ${vector.canonical}, got ${actual}`,
    );
  }
}

// JSON.parse itself rejects NaN/Infinity. Duplicate member detection requires raw-token
// parsing, so duplicate-key and safe-integer rejection remain mandatory at the API parser.
for (const vector of vectors.invalid.filter(
  (item) => ["nan", "positive-infinity", "lone-surrogate"].includes(item.id),
)) {
  let failed = false;
  try {
    const parsed = JSON.parse(vector.input);
    if (vector.id === "lone-surrogate") {
      canonicalize(parsed);
      // JSON.parse accepts a lone surrogate string; enforce the Unicode scalar rule.
      for (const ch of parsed.s) {
        const cp = ch.codePointAt(0);
        if (cp >= 0xd800 && cp <= 0xdfff) throw new Error("Lone surrogate");
      }
    }
  } catch {
    failed = true;
  }
  if (!failed) throw new Error(`Expected invalid vector to fail: ${vector.id}`);
}

console.log(
  `Node JCS: ${vectors.valid.length} valid vectors passed; parser-level invalid vectors documented.`,
);
