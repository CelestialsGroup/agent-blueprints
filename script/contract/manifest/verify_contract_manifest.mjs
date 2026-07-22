import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "../jcs/canonicalize.mjs";

const scriptRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const contractRoot = path.resolve(
  process.env.AGENT_PLATFORM_CONTRACT_ROOT ?? path.join(scriptRoot, "../contract"),
);
const manifestPath = path.join(contractRoot, "compatibility/contract-manifest.json");
const sha = (bytes) => `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;
const walk = (directory) => fs.existsSync(directory)
  ? fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const target = path.join(directory, entry.name);
      return entry.isDirectory() ? walk(target) : [target];
    })
  : [];

const paths = [
  ...walk(path.join(contractRoot, "schemas")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(contractRoot, "examples/schemas")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(contractRoot, "openapi")).filter((item) => item.endsWith(".yaml")),
  ...walk(path.join(contractRoot, "state-machines")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(contractRoot, "event-types")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(contractRoot, "conformance")).filter((item) => item.endsWith(".json")),
  ...walk(path.join(contractRoot, "testdata")),
].sort();

const resources = paths.map((target) => {
  const relative = path.relative(contractRoot, target).split(path.sep).join("/");
  if (target.endsWith(".schema.json")) {
    const value = JSON.parse(fs.readFileSync(target, "utf8"));
    return { path: relative, kind: "json-schema", id: value.$id, digest: sha(Buffer.from(canonicalize(value), "utf8")) };
  }
  if (relative.startsWith("openapi/")) {
    return { path: relative, kind: "openapi", id: relative, digest: sha(fs.readFileSync(target)) };
  }
  if (relative.startsWith("state-machines/")) {
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
console.log(`Verified contract manifest over ${resources.length} governed resources.`);
