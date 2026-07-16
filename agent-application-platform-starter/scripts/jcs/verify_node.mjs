import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "./canonicalize.mjs";
import { strictParse } from "./strict_parse.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const vectors = JSON.parse(fs.readFileSync(path.join(root, "contracts/testdata/jcs-v1/vectors.json"), "utf8"));

for (const vector of vectors.valid) {
  const actual = canonicalize(JSON.parse(vector.input));
  if (actual !== vector.canonical) {
    throw new Error(`${vector.id}: expected ${vector.canonical}, got ${actual}`);
  }
}

for (const vector of vectors.strict_valid) {
  const actual = canonicalize(strictParse(vector.input));
  if (actual !== vector.canonical) {
    throw new Error(`${vector.id}: expected ${vector.canonical}, got ${actual}`);
  }
}

for (const vector of vectors.invalid) {
  let failed = false;
  try {
    canonicalize(strictParse(vector.input));
  } catch {
    failed = true;
  }
  if (!failed) throw new Error(`Expected invalid vector to fail: ${vector.id}`);
}

console.log(`Node JCS/Strict I-JSON: ${vectors.valid.length} canonicalization, ${vectors.strict_valid.length} strict-valid and ${vectors.invalid.length} strict-invalid vectors passed.`);
