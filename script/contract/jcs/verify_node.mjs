import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "./canonicalize.mjs";
import { strictParse } from "./strict_parse.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const scriptRoot = path.resolve(here, "../..");
const contractRoot = path.resolve(
  process.env.AGENT_CONTRACT_ROOT ?? path.join(scriptRoot, "../contract"),
);
const vectors = JSON.parse(fs.readFileSync(path.join(contractRoot, "testdata/jcs-v1/vectors.json"), "utf8"));

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

const evidenceDir = path.join(scriptRoot, "build", "validation");
const contractManifest = JSON.parse(fs.readFileSync(
  path.join(contractRoot, "compatibility", "contract-manifest.json"), "utf8",
));
fs.mkdirSync(evidenceDir, { recursive: true });
fs.writeFileSync(path.join(evidenceDir, "node-jcs.json"), `${JSON.stringify({
  runtime: `Node.js ${process.versions.node}`,
  canonicalization_vectors: vectors.valid.length,
  strict_valid_vectors: vectors.strict_valid.length,
  strict_invalid_vectors: vectors.invalid.length,
  contract_manifest_digest: contractManifest.manifest_digest,
  status: "passed",
}, null, 2)}\n`);
console.log(`Node JCS/Strict I-JSON: ${vectors.valid.length} canonicalization, ${vectors.strict_valid.length} strict-valid and ${vectors.invalid.length} strict-invalid vectors passed.`);
