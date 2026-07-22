import fs from "node:fs";
import { canonicalize } from "./canonicalize.mjs";

const raw = fs.readFileSync(0, "utf8");
const value = JSON.parse(raw);
process.stdout.write(canonicalize(value));
