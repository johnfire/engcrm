import assert from "node:assert/strict";
import { test } from "node:test";
import { evaluateAudit, evaluateBundle } from "./mobile-dependency-policy.mjs";

function fixture() {
  return {
    report: { metadata: { vulnerabilities: { high: 1 } }, vulnerabilities: {
      zod: { severity: "high", nodes: ["node_modules/expo/node_modules/zod"], via: [
        { severity: "high", url: "https://github.com/advisories/GHSA-mrhx-c7xc-m3w5" },
      ] },
    } },
    policy: { minimumSeverity: "high", toolingOnlyPackages: ["zod"], exceptions: [{
      package: "zod", advisory: "GHSA-mrhx-c7xc-m3w5", severity: "high", versions: ["3.25.76"],
      paths: ["node_modules/expo/node_modules/zod"], expires: "2026-12-05",
      reason: "Reviewed CLI-only dependency, prohibited in the Android bundle.",
    }] },
    lockfile: { packages: { "node_modules/expo/node_modules/zod": { version: "3.25.76" } } },
  };
}

test("only the precise reviewed advisory, version and location is accepted", () => {
  const { report, policy, lockfile } = fixture();
  const verdict = evaluateAudit(report, policy, lockfile, "2026-11-05");
  assert.equal(verdict.blocked.length, 0);
  assert.equal(verdict.accepted.length, 1);
  assert.equal(verdict.stale.length, 0);
});

for (const change of ["expired", "new-version", "new-path", "new-advisory", "critical"]) {
  test(`release refuses ${change} even for a previously reviewed dependency`, () => {
    const { report, policy, lockfile } = fixture();
    if (change === "expired") policy.exceptions[0].expires = "2026-11-01";
    if (change === "new-version") lockfile.packages["node_modules/expo/node_modules/zod"].version = "3.25.77";
    if (change === "new-path") report.vulnerabilities.zod.nodes.push("node_modules/zod");
    if (change === "new-advisory") report.vulnerabilities.zod.via[0].url = "https://github.com/advisories/GHSA-aaaa-bbbb-cccc";
    if (change === "critical") report.vulnerabilities.zod.via[0].severity = "critical";
    assert.equal(evaluateAudit(report, policy, lockfile, "2026-11-05").blocked.length, 1);
  });
}

test("a fixed finding requires removing its obsolete exception", () => {
  const { policy, lockfile } = fixture();
  const report = { metadata: { vulnerabilities: {} }, vulnerabilities: {} };
  assert.equal(evaluateAudit(report, policy, lockfile, "2026-11-05").stale.length, 1);
});

test("low findings remain visible without blocking the chosen high threshold", () => {
  const { report, policy, lockfile } = fixture();
  report.vulnerabilities.zod.via[0].severity = "low";
  policy.exceptions = [];
  assert.equal(evaluateAudit(report, policy, lockfile).blocked.length, 0);
});

for (const report of [{ error: { message: "registry unavailable" } }, {}, {
  metadata: { vulnerabilities: { high: 1 } }, vulnerabilities: { zod: { via: [], nodes: [] } },
}]) {
  test("incomplete scanner output fails closed", () => {
    const { policy, lockfile } = fixture();
    assert.throws(() => evaluateAudit(report, policy, lockfile));
  });
}

test("bundle inspection detects nested and Windows-style tool package paths", () => {
  const { policy } = fixture();
  for (const source of ["node_modules/expo/node_modules/zod/index.js", "..\\node_modules\\zod\\index.js"]) {
    assert.deepEqual(evaluateBundle({ sources: [source] }, policy), ["zod"]);
  }
  assert.deepEqual(evaluateBundle({ sources: ["services/zod-not-a-package.ts", "node_modules/axios/index.js"] }, policy), []);
  assert.throws(() => evaluateBundle({ sources: [] }, policy));
});
