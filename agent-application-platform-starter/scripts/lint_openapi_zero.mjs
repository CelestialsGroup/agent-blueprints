import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const redocly = path.join(root, "node_modules", ".bin", "redocly");
const openapiDir = path.join(root, "build", "openapi-src", "openapi");
const documents = [
  "agent-access-v1.yaml",
  "plugin-invocation-v1.yaml",
  "delivery-webhook-v1.yaml",
  "sandbox-provider-v1.yaml",
  "agent-runtime-provider-v1.yaml",
];

if (!fs.existsSync(redocly) || !fs.existsSync(openapiDir)) {
  throw new Error("Run bootstrap_contracts.sh and scripts/prepare_openapi.py first.");
}

for (const document of documents) {
  const target = path.join(openapiDir, document);
  const result = spawnSync(redocly, ["lint", target, "--format", "json"], {
    cwd: root,
    encoding: "utf8",
  });
  if (result.stderr) process.stderr.write(result.stderr);
  let report;
  try {
    report = JSON.parse(result.stdout);
  } catch {
    process.stderr.write(result.stdout || "");
    throw new Error(`Redocly did not emit JSON for ${document}`);
  }
  const { errors = 0, warnings = 0 } = report.totals ?? {};
  if (errors !== 0 || warnings !== 0 || result.status !== 0) {
    process.stderr.write(`${JSON.stringify(report, null, 2)}\n`);
    throw new Error(
      `${document}: expected 0 errors and 0 warnings, got ${errors} errors and ${warnings} warnings`,
    );
  }
  console.log(`${document}: 0 errors, 0 warnings`);
}
