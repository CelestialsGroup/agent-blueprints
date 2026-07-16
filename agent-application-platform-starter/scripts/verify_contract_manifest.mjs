import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "./jcs/canonicalize.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = path.join(root, "contracts/compatibility/v0.8.1-contract-manifest.json");
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const sha256 = (bytes) => `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;

const unsigned = structuredClone(manifest);
const expectedManifestDigest = unsigned.manifest_digest;
delete unsigned.manifest_digest;
const actualManifestDigest = sha256(Buffer.from(canonicalize(unsigned), "utf8"));
if (actualManifestDigest !== expectedManifestDigest) {
  throw new Error(`Manifest digest mismatch: ${actualManifestDigest} != ${expectedManifestDigest}`);
}

for (const resource of manifest.resources) {
  const resourcePath = path.join(root, resource.path);
  if (!fs.existsSync(resourcePath)) throw new Error(`Missing resource: ${resource.path}`);
  let actual;
  if (resource.kind === "json-schema") {
    const value = JSON.parse(fs.readFileSync(resourcePath, "utf8"));
    if (value.$id !== resource.id) throw new Error(`Schema ID changed: ${resource.path}`);
    actual = sha256(Buffer.from(canonicalize(value), "utf8"));
  } else {
    actual = sha256(fs.readFileSync(resourcePath));
  }
  if (actual !== resource.digest) {
    throw new Error(`Resource changed without manifest update: ${resource.path}`);
  }
}
console.log(`Verified immutable contract manifest with ${manifest.resources.length} resources.`);
