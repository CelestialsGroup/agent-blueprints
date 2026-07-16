import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "./jcs/canonicalize.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = path.join(root, "contracts/compatibility/v0.8.5-contract-manifest.json");
const sha = (bytes) => `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;
const walk = (directory) => fs.existsSync(directory)
  ? fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const target = path.join(directory, entry.name);
      return entry.isDirectory() ? walk(target) : [target];
    })
  : [];

const paths = [
  ...walk(path.join(root, "contracts/schemas")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(root, "examples/schemas")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(root, "contracts/openapi")).filter((item) => item.endsWith(".yaml")),
  ...walk(path.join(root, "contracts/state-machines")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(root, "contracts/testdata")),
  path.join(root, "docs/23_STATE_MACHINE_SPEC.md"),
  path.join(root, "docs/26_DATA_MODEL_INVARIANTS.md"),
].sort();

const resources = paths.map((target) => {
  const relative = path.relative(root, target).split(path.sep).join("/");
  if (target.endsWith(".schema.json")) {
    const value = JSON.parse(fs.readFileSync(target, "utf8"));
    return { path: relative, kind: "json-schema", id: value.$id, digest: sha(Buffer.from(canonicalize(value), "utf8")) };
  }
  if (relative.startsWith("contracts/openapi/")) {
    return { path: relative, kind: "openapi", id: relative, digest: sha(fs.readFileSync(target)) };
  }
  if (relative.startsWith("contracts/state-machines/")) {
    return { path: relative, kind: "state-machine", id: relative, digest: sha(fs.readFileSync(target)) };
  }
  return { path: relative, kind: "governance", id: relative, digest: sha(fs.readFileSync(target)) };
});
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const resourcesDigest = sha(Buffer.from(canonicalize(resources), "utf8"));
if (manifest.resource_count !== resources.length || manifest.resources_digest !== resourcesDigest) {
  throw new Error("Contract inventory changed without manifest refresh");
}
const unsigned = structuredClone(manifest);
const expected = unsigned.manifest_digest;
delete unsigned.manifest_digest;
const actual = sha(Buffer.from(canonicalize(unsigned), "utf8"));
if (actual !== expected) throw new Error(`Manifest self-digest mismatch: ${actual} != ${expected}`);
console.log(`Verified v0.8.5 contract manifest over ${resources.length} governed resources.`);
