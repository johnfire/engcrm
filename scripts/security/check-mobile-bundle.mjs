import { readFileSync } from "node:fs";
import { evaluateBundle } from "./mobile-dependency-policy.mjs";

try {
  if (process.argv.length !== 3) throw new Error("Supply the generated Android source map path");
  const policy = JSON.parse(readFileSync(new URL("./mobile-dependency-policy.json", import.meta.url)));
  const sourceMap = JSON.parse(readFileSync(process.argv[2], "utf8"));
  const unexpected = evaluateBundle(sourceMap, policy);
  if (unexpected.length) throw new Error(`Tool-only packages reached the app: ${unexpected.join(", ")}`);
  console.log(`Verified ${sourceMap.sources.length} bundled source paths; reviewed tooling packages are absent.`);
} catch (error) {
  console.error(`Android bundle gate failed: ${error.message}`);
  process.exitCode = 1;
}
