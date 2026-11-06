import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { evaluateAudit } from "./mobile-dependency-policy.mjs";

try {
  const mobileDirectory = fileURLToPath(new URL("../../engcrm-mobile/", import.meta.url));
  const scan = spawnSync("npm", ["audit", "--json", "--registry=https://registry.npmjs.org"], {
    cwd: mobileDirectory, encoding: "utf8", maxBuffer: 10 * 1024 * 1024, timeout: 120000,
  });
  if (scan.error || ![0, 1].includes(scan.status)) throw new Error("Dependency scanner could not complete");
  const policy = JSON.parse(readFileSync(new URL("./mobile-dependency-policy.json", import.meta.url)));
  const lockfile = JSON.parse(readFileSync(new URL("../../engcrm-mobile/package-lock.json", import.meta.url)));
  const verdict = evaluateAudit(JSON.parse(scan.stdout), policy, lockfile);
  console.log(JSON.stringify(verdict, null, 2));
  if (verdict.blocked.length || verdict.stale.length) process.exitCode = 1;
} catch (error) {
  console.error(`Mobile dependency gate failed: ${error.message}`);
  process.exitCode = 1;
}
